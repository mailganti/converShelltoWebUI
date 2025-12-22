# controller/routes/agents.py - SSL-compatible agent routes

"""
Agent routes with proper RBAC and SSL support
- Heartbeat: agent token only
- Registration/Management: admin token only
- Health checks: Support HTTP and HTTPS agents
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel, validator, Field
from typing import Optional, List
import re
import socket
import logging
import os
import httpx

from controller.db.db import get_db
from controller.deps import verify_token, require_admin, require_agent, require_authenticated_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

# SSL Configuration
SSL_ENABLED = os.getenv("SSL_ENABLED", "true").lower() == "true"
SSL_VERIFY = os.getenv("SSL_VERIFY", "false").lower() == "true"
SSL_CA_CERTS = os.getenv("SSL_CA_CERTS", "./certs/certChain.pem")


# =============================================================================
# Pydantic Models
# =============================================================================

class AgentRegister(BaseModel):
    agent_name: str = Field(..., min_length=2, max_length=255)
    host: str = Field(..., max_length=253)
    port: int = Field(..., ge=1, le=65535)
    status: str = Field(default="online")
    ssl_enabled: bool = Field(default=True)
    
    @validator('agent_name')
    def validate_agent_name(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Agent name must contain only letters, numbers, hyphens, and underscores')
        return v
    
    @validator('host')
    def validate_host(cls, v):
        ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        ipv6_pattern = r'^[0-9a-fA-F:]+$'
        hostname_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
        
        if not (re.match(ipv4_pattern, v) or re.match(ipv6_pattern, v) or re.match(hostname_pattern, v)):
            raise ValueError('Invalid host format')
        return v


class AgentUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern='^(online|offline|maintenance)$')
    ssl_enabled: Optional[bool] = None


class HeartbeatRequest(BaseModel):
    agent_name: str
    timestamp: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def get_ssl_verify_config():
    """Get SSL verification config for httpx client"""
    if not SSL_VERIFY:
        return False
    if SSL_CA_CERTS and os.path.exists(SSL_CA_CERTS):
        return SSL_CA_CERTS
    return False


def is_host_reachable(host: str) -> tuple:
    """Check if host is reachable via DNS"""
    try:
        socket.getaddrinfo(host, None)
        return True, "Host is reachable"
    except socket.gaierror:
        return False, "Host not reachable or DNS resolution failed"


async def check_agent_health(host: str, port: int, ssl_enabled: bool = False) -> tuple:
    """Check if agent is responding via HTTP health check"""
    protocol = "https" if ssl_enabled else "http"
    url = f"{protocol}://{host}:{port}/health"
    
    verify_ssl = get_ssl_verify_config()
    
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=verify_ssl) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return True, f"Agent is healthy: {data.get('status', 'ok')}"
            else:
                return False, f"Agent returned status {response.status_code}"
    except httpx.ConnectError:
        return False, "Cannot connect to agent"
    except httpx.TimeoutException:
        return False, "Agent health check timeout"
    except httpx.RequestError as e:
        return False, f"Request error: {str(e)}"
    except Exception as e:
        return False, f"Health check failed: {str(e)}"


# =============================================================================
# Routes
# =============================================================================

@router.get("")
@router.get("/")
async def list_agents(
    limit: Optional[int] = Query(None, ge=1, le=1000),
    status: Optional[str] = Query(None, pattern='^(online|offline|maintenance)$'),
    user: dict = Depends(verify_token)
):
    """List all agents with real-time status"""
    db = get_db()
    
    try:
        agents = db.list_agents_with_status(limit=limit, status=status)
    except AttributeError:
        agents = db.list_agents(limit=limit)
    
    logger.debug(f"Listed {len(agents)} agents (user: {user.get('token_name', 'unknown')})")
    
    return {
        "agents": agents,
        "count": len(agents),
        "ssl_enabled": SSL_ENABLED
    }


@router.get("/{agent_name}")
async def get_agent(
    agent_name: str,
    user: dict = Depends(verify_token)
):
    """Get specific agent details"""
    db = get_db()
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    try:
        status = db.get_agent_status(agent_name, timeout_seconds=60)
        agent['status'] = status
    except Exception:
        pass
    
    return agent


@router.post("")
@router.post("/")
async def register_agent(
    agent: AgentRegister,
    user: dict = Depends(require_admin)
):
    """Register a new agent (admin only)"""
    db = get_db()
    
    logger.info(f"Agent registration: {agent.agent_name} at {agent.host}:{agent.port}")
    
    existing = db.get_agent(agent.agent_name)
    
    try:
        existing_host_port = db.get_agent_by_host_port(agent.host, agent.port)
    except AttributeError:
        existing_host_port = None
    
    if existing:
        if existing_host_port and existing_host_port.get('agent_name') != agent.agent_name:
            raise HTTPException(
                status_code=409,
                detail=f"Host:port {agent.host}:{agent.port} already in use by agent '{existing_host_port['agent_name']}'"
            )
    else:
        if existing_host_port:
            raise HTTPException(
                status_code=409,
                detail=f"Host:port {agent.host}:{agent.port} already in use by agent '{existing_host_port['agent_name']}'"
            )
    
    try:
        registered = db.register_agent(
            agent_name=agent.agent_name,
            host=agent.host,
            port=agent.port,
            status=agent.status,
            ssl_enabled=agent.ssl_enabled
        )
    except TypeError:
        db.create_agent(agent.agent_name, agent.host, agent.port, agent.status, agent.ssl_enabled)
        registered = db.get_agent(agent.agent_name)
    
    protocol = "https" if agent.ssl_enabled else "http"
    logger.info(f"Agent {agent.agent_name} registered at {protocol}://{agent.host}:{agent.port}")
    
    return {
        "message": "Agent registered successfully",
        "agent": registered,
        "endpoint": f"{protocol}://{agent.host}:{agent.port}"
    }


@router.post("/heartbeat")
async def agent_heartbeat(request: Request):
    """
    Receive heartbeat from agent.
    Agent authenticates with X-Agent-Token header.
    """
    db = get_db()
    
    token = request.headers.get("X-Agent-Token") or request.headers.get("X-Agent-Auth")
    if not token:
        raise HTTPException(status_code=401, detail="Missing X-Agent-Token header")
    
    token_row = db.get_token_by_value(token)
    if not token_row or token_row.get("revoked") == 1:
        raise HTTPException(status_code=401, detail="Invalid or revoked token")
    
    if token_row.get("role") != "agent":
        raise HTTPException(status_code=403, detail="Token is not an agent token")
    
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    agent_name = payload.get("agent_name")
    if not agent_name:
        raise HTTPException(status_code=400, detail="agent_name required")
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not registered")
    
    try:
        db.update_agent_heartbeat(agent_name)
    except AttributeError:
        db.update_agent_status(agent_name, "online")
    
    logger.debug(f"Heartbeat from {agent_name}")
    
    return {"status": "ok", "agent_name": agent_name}


@router.put("/{agent_name}/status")
async def update_agent_status(
    agent_name: str,
    update: AgentUpdate,
    user: dict = Depends(require_admin)
):
    """Update agent status/SSL (admin only)"""
    db = get_db()
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    if update.status:
        db.update_agent_status(agent_name, update.status)
        logger.info(f"Agent {agent_name} status updated to {update.status}")
    
    if update.ssl_enabled is not None:
        try:
            db.update_agent_ssl(agent_name, update.ssl_enabled)
        except AttributeError:
            logger.warning("update_agent_ssl not implemented")
    
    return db.get_agent(agent_name)


@router.delete("/{agent_name}")
async def deregister_agent(
    agent_name: str,
    user: dict = Depends(require_admin)
):
    """Deregister an agent (admin only)"""
    db = get_db()
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    try:
        db.deregister_agent(agent_name)
    except AttributeError:
        db.delete_agent(agent_name)
    
    logger.info(f"Agent {agent_name} deregistered")
    
    return {"status": "deleted", "agent_name": agent_name}


@router.post("/{agent_name}/ping")
async def ping_agent(
    agent_name: str,
    user: dict = Depends(verify_token)
):
    """Ping agent to check if reachable"""
    db = get_db()
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    reachable, dns_msg = is_host_reachable(agent['host'])
    ssl_enabled = agent.get('ssl_enabled', SSL_ENABLED)
    is_healthy, health_msg = await check_agent_health(agent['host'], agent['port'], ssl_enabled)
    
    return {
        "agent_name": agent_name,
        "host": agent['host'],
        "port": agent['port'],
        "protocol": "https" if ssl_enabled else "http",
        "dns_reachable": reachable,
        "dns_message": dns_msg,
        "health_check": is_healthy,
        "health_message": health_msg,
        "overall_status": "online" if (reachable and is_healthy) else "offline"
    }
