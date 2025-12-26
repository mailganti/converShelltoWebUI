# controller/routes/agents.py - SSL-compatible agent routes with environment access control

"""
Agent routes with proper RBAC, SSL support, and environment-based access control
- Heartbeat: agent token only
- Registration/Management: admin token only (filtered by environment access)
- Health checks: Support HTTP and HTTPS agents
- Environment filtering: Users only see agents in their allowed environments
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

# Valid environments
VALID_ENVIRONMENTS = ['DEV', 'TEST', 'PROD']


# =============================================================================
# Pydantic Models
# =============================================================================

class AgentRegister(BaseModel):
    agent_name: str = Field(..., min_length=2, max_length=255)
    host: str = Field(..., max_length=253)
    port: int = Field(..., ge=1, le=65535)
    status: str = Field(default="online")
    ssl_enabled: bool = Field(default=True)
    environment: str = Field(default="DEV", pattern='^(DEV|TEST|PROD)$')
    
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
    
    @validator('environment')
    def validate_environment(cls, v):
        v_upper = v.upper()
        if v_upper not in VALID_ENVIRONMENTS:
            raise ValueError(f'Environment must be one of: {", ".join(VALID_ENVIRONMENTS)}')
        return v_upper


class AgentUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern='^(online|offline|maintenance)$')
    ssl_enabled: Optional[bool] = None
    environment: Optional[str] = Field(None, pattern='^(DEV|TEST|PROD)$')


class HeartbeatRequest(BaseModel):
    agent_name: str
    timestamp: Optional[str] = None


class EnvironmentAccess(BaseModel):
    """Model for granting/revoking environment access"""
    username: str = Field(..., min_length=1, max_length=255)
    environment: str = Field(..., pattern='^(DEV|TEST|PROD|\\*)$')


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


def get_user_allowed_environments(db, user: dict) -> List[str]:
    """
    Get list of environments a user can access.
    Returns ['*'] if user has access to all environments.
    Returns empty list if no access configured.
    """
    user_id = user.get('user_id')
    username = user.get('username') or user.get('token_name')
    
    # If we have user_id, use it directly
    if user_id:
        environments = db.get_user_environments(user_id)
    else:
        # Look up user_id by username
        user_record = db.get_user_by_username(username)
        if not user_record:
            return []
        environments = db.get_user_environments(user_record['user_id'])
    
    return environments


def filter_agents_by_environment(agents: list, allowed_environments: List[str]) -> list:
    """
    Filter agents list based on user's allowed environments.
    If allowed_environments contains '*', return all agents.
    """
    if not allowed_environments:
        return []
    
    if '*' in allowed_environments:
        return agents
    
    return [
        agent for agent in agents 
        if agent.get('environment', 'DEV').upper() in [e.upper() for e in allowed_environments]
    ]


def user_can_access_environment(allowed_environments: List[str], target_environment: str) -> bool:
    """Check if user can access a specific environment"""
    if not allowed_environments:
        return False
    if '*' in allowed_environments:
        return True
    return target_environment.upper() in [e.upper() for e in allowed_environments]


# =============================================================================
# Routes
# =============================================================================

@router.get("/all")
async def list_all_agents(
    limit: Optional[int] = Query(None, ge=1, le=1000),
    status: Optional[str] = Query(None, pattern='^(online|offline|maintenance)$'),
    user: dict = Depends(verify_token)
):
    """
    List ALL agents without environment filtering.
    Used by Reports module to show all available agents.
    """
    db = get_db()
    
    # Get all agents without filtering
    try:
        agents = db.list_agents_with_status(limit=limit, status=status)
    except AttributeError:
        agents = db.list_agents(limit=limit)
    
    # Update status for each agent via health check

   # updated_agents = []
   # for agent in agents:
   #     ssl_enabled = agent.get('ssl_enabled', SSL_ENABLED)
   #     is_healthy, _ = await check_agent_health(agent['host'], agent['port'], ssl_enabled)
   #     agent['status'] = 'online' if is_healthy else 'offline'
   #     updated_agents.append(agent)
    
    # Apply status filter if provided
    if status:
        agents_list = [a for a in updated_agents if a.get('status') == status]
    
    return {
        "agents": agents_list,
        "count": len(agents_list),
        "ssl_enabled": SSL_ENABLED
    }


@router.get("")
@router.get("/")
async def list_agents(
    limit: Optional[int] = Query(None, ge=1, le=1000),
    status: Optional[str] = Query(None, pattern='^(online|offline|maintenance)$'),
    environment: Optional[str] = Query(None, pattern='^(DEV|TEST|PROD)$'),
    user: dict = Depends(verify_token)
):
    """List all agents with real-time status (filtered by user's environment access)"""
    db = get_db()
    
    # Get user's allowed environments
    allowed_environments = get_user_allowed_environments(db, user)
    
    if not allowed_environments:
        logger.warning(f"User {user.get('username', user.get('token_name', 'unknown'))} has no environment access configured")
        return {
            "agents": [],
            "count": 0,
            "ssl_enabled": SSL_ENABLED,
            "allowed_environments": [],
            "message": "No environment access configured. Contact an administrator."
        }
    
    # Get all agents
    try:
        agents = db.list_agents_with_status(limit=limit, status=status)
    except AttributeError:
        agents = db.list_agents(limit=limit)
    
    # Filter by environment access
    filtered_agents = filter_agents_by_environment(agents, allowed_environments)
    
    # Additional filter by specific environment if requested
    if environment:
        if not user_can_access_environment(allowed_environments, environment):
            raise HTTPException(
                status_code=403,
                detail=f"You don't have access to the {environment} environment"
            )
        filtered_agents = [a for a in filtered_agents if a.get('environment', 'DEV').upper() == environment.upper()]
    
    logger.debug(f"Listed {len(filtered_agents)} agents for user {user.get('token_name', 'unknown')} (total: {len(agents)})")
    
    return {
        "agents": filtered_agents,
        "count": len(filtered_agents),
        "ssl_enabled": SSL_ENABLED,
        "allowed_environments": allowed_environments if '*' not in allowed_environments else VALID_ENVIRONMENTS
    }


@router.get("/environments")
async def list_environments(user: dict = Depends(verify_token)):
    """List all valid environments and user's access"""
    db = get_db()
    allowed = get_user_allowed_environments(db, user)
    
    return {
        "all_environments": VALID_ENVIRONMENTS,
        "user_access": allowed if '*' not in allowed else VALID_ENVIRONMENTS,
        "has_full_access": '*' in allowed
    }


@router.get("/{agent_name}")
async def get_agent(
    agent_name: str,
    user: dict = Depends(verify_token)
):
    """Get specific agent details (if user has environment access)"""
    db = get_db()
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    # Check environment access
    allowed_environments = get_user_allowed_environments(db, user)
    agent_env = agent.get('environment', 'DEV').upper()
    
    if not user_can_access_environment(allowed_environments, agent_env):
        raise HTTPException(
            status_code=403, 
            detail=f"You don't have access to agents in the {agent_env} environment"
        )
    
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
    """Register a new agent (admin only, must have access to target environment)"""
    db = get_db()
    
    # Check if admin has access to the target environment
    allowed_environments = get_user_allowed_environments(db, user)
    if not user_can_access_environment(allowed_environments, agent.environment):
        raise HTTPException(
            status_code=403,
            detail=f"You don't have access to register agents in the {agent.environment} environment"
        )
    
    logger.info(f"Agent registration: {agent.agent_name} at {agent.host}:{agent.port} (env: {agent.environment})")
    
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
            ssl_enabled=agent.ssl_enabled,
            environment=agent.environment
        )
    except TypeError:
        # Fallback for older db interface without environment
        db.create_agent(agent.agent_name, agent.host, agent.port, agent.status, agent.ssl_enabled)
        # Try to update environment separately
        try:
            db.update_agent_environment(agent.agent_name, agent.environment)
        except AttributeError:
            logger.warning("update_agent_environment not implemented - using raw SQL")
            db.execute("UPDATE agents SET environment = ? WHERE agent_name = ?", (agent.environment, agent.agent_name))
        registered = db.get_agent(agent.agent_name)
    
    protocol = "https" if agent.ssl_enabled else "http"
    logger.info(f"Agent {agent.agent_name} registered at {protocol}://{agent.host}:{agent.port} (env: {agent.environment})")
    
    return {
        "message": "Agent registered successfully",
        "agent": registered,
        "endpoint": f"{protocol}://{agent.host}:{agent.port}",
        "environment": agent.environment
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
    """Update agent status/SSL/environment (admin only, must have environment access)"""
    db = get_db()
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    # Check access to current environment
    allowed_environments = get_user_allowed_environments(db, user)
    current_env = agent.get('environment', 'DEV').upper()
    
    if not user_can_access_environment(allowed_environments, current_env):
        raise HTTPException(
            status_code=403,
            detail=f"You don't have access to agents in the {current_env} environment"
        )
    
    # If changing environment, check access to new environment too
    if update.environment:
        new_env = update.environment.upper()
        if not user_can_access_environment(allowed_environments, new_env):
            raise HTTPException(
                status_code=403,
                detail=f"You don't have access to move agents to the {new_env} environment"
            )
        try:
            db.update_agent_environment(agent_name, new_env)
        except AttributeError:
            db.execute("UPDATE agents SET environment = ? WHERE agent_name = ?", (new_env, agent_name))
        logger.info(f"Agent {agent_name} environment changed from {current_env} to {new_env}")
    
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
    """Deregister an agent (admin only, must have environment access)"""
    db = get_db()
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    # Check environment access
    allowed_environments = get_user_allowed_environments(db, user)
    agent_env = agent.get('environment', 'DEV').upper()
    
    if not user_can_access_environment(allowed_environments, agent_env):
        raise HTTPException(
            status_code=403,
            detail=f"You don't have access to deregister agents in the {agent_env} environment"
        )
    
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
    """Ping agent to check if reachable (must have environment access)"""
    db = get_db()
    
    agent = db.get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    # Check environment access
    allowed_environments = get_user_allowed_environments(db, user)
    agent_env = agent.get('environment', 'DEV').upper()
    
    if not user_can_access_environment(allowed_environments, agent_env):
        raise HTTPException(
            status_code=403,
            detail=f"You don't have access to agents in the {agent_env} environment"
        )
    
    reachable, dns_msg = is_host_reachable(agent['host'])
    ssl_enabled = agent.get('ssl_enabled', SSL_ENABLED)
    is_healthy, health_msg = await check_agent_health(agent['host'], agent['port'], ssl_enabled)
    
    return {
        "agent_name": agent_name,
        "host": agent['host'],
        "port": agent['port'],
        "protocol": "https" if ssl_enabled else "http",
        "environment": agent.get('environment', 'DEV'),
        "dns_reachable": reachable,
        "dns_message": dns_msg,
        "health_check": is_healthy,
        "health_message": health_msg,
        "overall_status": "online" if (reachable and is_healthy) else "offline"
    }


# =============================================================================
# Environment Access Management Routes (Admin Only)
# =============================================================================

@router.get("/access/users")
async def list_user_environment_access(
    user: dict = Depends(require_admin)
):
    """List all users and their environment access (admin only)"""
    db = get_db()
    
    try:
        # Try to use view if available
        access_list = db.query("SELECT * FROM v_user_environments ORDER BY username, environment")
    except Exception:
        # Fallback to manual join
        access_list = db.query("""
            SELECT 
                u.user_id,
                u.username,
                u.full_name,
                uaa.environment,
                uaa.granted_by,
                uaa.granted_at
            FROM users u
            LEFT JOIN user_agent_access uaa ON u.user_id = uaa.user_id
            ORDER BY u.username, uaa.environment
        """)
    
    return {"user_access": access_list}


@router.post("/access/grant")
async def grant_environment_access(
    access: EnvironmentAccess,
    user: dict = Depends(require_admin)
):
    """Grant a user access to an environment (admin only)"""
    db = get_db()
    
    # Look up target user
    target_user = db.get_user_by_username(access.username)
    if not target_user:
        raise HTTPException(status_code=404, detail=f"User '{access.username}' not found")
    
    # Check if admin has access to grant (must have access to that environment or be superadmin)
    admin_environments = get_user_allowed_environments(db, user)
    if '*' not in admin_environments and access.environment != '*':
        if not user_can_access_environment(admin_environments, access.environment):
            raise HTTPException(
                status_code=403,
                detail=f"You can't grant access to {access.environment} because you don't have access to it"
            )
    
    # Only superadmins can grant superadmin access
    if access.environment == '*' and '*' not in admin_environments:
        raise HTTPException(
            status_code=403,
            detail="Only superadmins (with '*' access) can grant superadmin access"
        )
    
    try:
        db.execute("""
            INSERT OR REPLACE INTO user_agent_access (user_id, environment, granted_by, granted_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (target_user['user_id'], access.environment.upper(), user.get('username', 'admin')))
        
        logger.info(f"Granted {access.username} access to {access.environment} environment")
        
        return {
            "message": f"Granted {access.username} access to {access.environment}",
            "username": access.username,
            "environment": access.environment
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to grant access: {str(e)}")


@router.delete("/access/revoke")
async def revoke_environment_access(
    access: EnvironmentAccess,
    user: dict = Depends(require_admin)
):
    """Revoke a user's access to an environment (admin only)"""
    db = get_db()
    
    # Look up target user
    target_user = db.get_user_by_username(access.username)
    if not target_user:
        raise HTTPException(status_code=404, detail=f"User '{access.username}' not found")
    
    # Check if admin has authority to revoke
    admin_environments = get_user_allowed_environments(db, user)
    if '*' not in admin_environments:
        if access.environment == '*':
            raise HTTPException(
                status_code=403,
                detail="Only superadmins can revoke superadmin access"
            )
        if not user_can_access_environment(admin_environments, access.environment):
            raise HTTPException(
                status_code=403,
                detail=f"You can't revoke access to {access.environment} because you don't have access to it"
            )
    
    try:
        db.execute("""
            DELETE FROM user_agent_access 
            WHERE user_id = ? AND environment = ?
        """, (target_user['user_id'], access.environment.upper()))
        
        logger.info(f"Revoked {access.username}'s access to {access.environment} environment")
        
        return {
            "message": f"Revoked {access.username}'s access to {access.environment}",
            "username": access.username,
            "environment": access.environment
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to revoke access: {str(e)}")
