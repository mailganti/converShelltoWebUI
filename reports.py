# controller/routes/reports_api.py
"""
Reports API - Run read-only status scripts without approval workflow
Supports parameterized scripts and real-time output streaming
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import httpx

from controller.db.db import get_db
from controller.deps import verify_token, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])

# Store active report runs for WebSocket streaming
active_runs: Dict[str, dict] = {}

# SSL Configuration (same as agents)
SSL_ENABLED = os.getenv("SSL_ENABLED", "true").lower() == "true"
SSL_VERIFY = os.getenv("SSL_VERIFY", "false").lower() == "true"
SSL_CA_CERTS = os.getenv("SSL_CA_CERTS", "./certs/certChain.pem")


# =============================================================================
# Pydantic Models
# =============================================================================

class ReportParameter(BaseModel):
    """Schema for a report parameter definition"""
    name: str = Field(..., min_length=1, max_length=50)
    label: Optional[str] = None
    type: str = Field(default="text", pattern='^(text|number|date|select|checkbox|textarea)$')
    required: bool = False
    default: Optional[Any] = None
    placeholder: Optional[str] = None
    options: Optional[List[str]] = None  # For select type
    min: Optional[float] = None  # For number type
    max: Optional[float] = None  # For number type


class ReportScriptRegister(BaseModel):
    """Schema for registering a report script"""
    script_id: str = Field(..., min_length=1, max_length=100, pattern='^[a-zA-Z0-9_-]+$')
    name: Optional[str] = Field(None, max_length=255)
    script_path: str = Field(..., min_length=1, max_length=500)
    category: str = Field(default="General", max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    timeout: int = Field(default=300, ge=1, le=3600)
    parameters: Optional[List[ReportParameter]] = None


class ReportRunRequest(BaseModel):
    """Schema for running a report"""
    target: str = Field(..., min_length=1, max_length=255)
    parameters: Optional[Dict[str, Any]] = None


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


def init_reports_table(db):
    """Initialize the report_scripts table if it doesn't exist"""
    db.execute("""
        CREATE TABLE IF NOT EXISTS report_scripts (
            script_id VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255),
            script_path VARCHAR(500) NOT NULL,
            category VARCHAR(50) DEFAULT 'General',
            description VARCHAR(500),
            timeout INTEGER DEFAULT 300,
            parameters TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Create report_runs table for history
    db.execute("""
        CREATE TABLE IF NOT EXISTS report_runs (
            run_id VARCHAR(50) PRIMARY KEY,
            script_id VARCHAR(100) NOT NULL,
            target_agent VARCHAR(255) NOT NULL,
            parameters TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            exit_code INTEGER,
            run_by VARCHAR(255),
            FOREIGN KEY (script_id) REFERENCES report_scripts(script_id)
        )
    """)


# =============================================================================
# Routes - Script Management
# =============================================================================

@router.get("/scripts")
async def list_report_scripts(user: dict = Depends(verify_token)):
    """List all registered report scripts"""
    db = get_db()
    
    # Ensure table exists
    init_reports_table(db)
    
    try:
        rows = db.query("SELECT * FROM report_scripts ORDER BY category, name")
        scripts = []
        for row in rows:
            script = dict(row)
            # Parse parameters JSON
            if script.get('parameters'):
                try:
                    script['parameters'] = json.loads(script['parameters'])
                except json.JSONDecodeError:
                    script['parameters'] = []
            else:
                script['parameters'] = []
            scripts.append(script)
        
        return {"scripts": scripts, "count": len(scripts)}
    except Exception as e:
        logger.error(f"Error listing report scripts: {e}")
        return {"scripts": [], "count": 0}


@router.get("/scripts/{script_id}")
async def get_report_script(script_id: str, user: dict = Depends(verify_token)):
    """Get a specific report script by ID"""
    db = get_db()
    init_reports_table(db)
    
    rows = db.query("SELECT * FROM report_scripts WHERE script_id = ?", (script_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Report script '{script_id}' not found")
    
    script = dict(rows[0])
    if script.get('parameters'):
        try:
            script['parameters'] = json.loads(script['parameters'])
        except json.JSONDecodeError:
            script['parameters'] = []
    
    return script


@router.post("/scripts/register")
async def register_report_script(
    script: ReportScriptRegister,
    user: dict = Depends(require_admin)
):
    """Register a new report script (admin only)"""
    db = get_db()
    init_reports_table(db)
    
    # Check if script already exists
    existing = db.query("SELECT script_id FROM report_scripts WHERE script_id = ?", (script.script_id,))
    
    # Serialize parameters to JSON
    params_json = json.dumps([p.dict() for p in script.parameters]) if script.parameters else None
    
    if existing:
        # Update existing
        db.execute("""
            UPDATE report_scripts 
            SET name = ?, script_path = ?, category = ?, description = ?, 
                timeout = ?, parameters = ?, updated_at = datetime('now')
            WHERE script_id = ?
        """, (
            script.name or script.script_id,
            script.script_path,
            script.category,
            script.description,
            script.timeout,
            params_json,
            script.script_id
        ))
        logger.info(f"Updated report script: {script.script_id}")
        return {"message": "Report script updated", "script_id": script.script_id}
    else:
        # Insert new
        db.execute("""
            INSERT INTO report_scripts (script_id, name, script_path, category, description, timeout, parameters)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            script.script_id,
            script.name or script.script_id,
            script.script_path,
            script.category,
            script.description,
            script.timeout,
            params_json
        ))
        logger.info(f"Registered report script: {script.script_id}")
        return {"message": "Report script registered", "script_id": script.script_id}


@router.delete("/scripts/{script_id}")
async def delete_report_script(script_id: str, user: dict = Depends(require_admin)):
    """Delete a report script (admin only)"""
    db = get_db()
    init_reports_table(db)
    
    existing = db.query("SELECT script_id FROM report_scripts WHERE script_id = ?", (script_id,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Report script '{script_id}' not found")
    
    db.execute("DELETE FROM report_scripts WHERE script_id = ?", (script_id,))
    logger.info(f"Deleted report script: {script_id}")
    
    return {"message": "Report script deleted", "script_id": script_id}


# =============================================================================
# Routes - Report Execution
# =============================================================================

@router.post("/run/{script_id}")
async def run_report(
    script_id: str,
    request: ReportRunRequest,
    user: dict = Depends(verify_token)
):
    """Run a report script on a target agent"""
    db = get_db()
    init_reports_table(db)
    
    # Get the script
    rows = db.query("SELECT * FROM report_scripts WHERE script_id = ?", (script_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Report script '{script_id}' not found")
    
    script = dict(rows[0])
    
    # Get the target agent
    agent = db.get_agent(request.target)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{request.target}' not found")
    
    if agent.get('status') != 'online':
        raise HTTPException(status_code=400, detail=f"Agent '{request.target}' is not online")
    
    # Parse script parameters definition
    param_defs = []
    if script.get('parameters'):
        try:
            param_defs = json.loads(script['parameters']) if isinstance(script['parameters'], str) else script['parameters']
        except json.JSONDecodeError:
            param_defs = []
    
    # Validate required parameters
    provided_params = request.parameters or {}
    for param_def in param_defs:
        if param_def.get('required') and param_def['name'] not in provided_params:
            raise HTTPException(
                status_code=400, 
                detail=f"Required parameter '{param_def['name']}' is missing"
            )
    
    # Generate run ID
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    
    # Record the run
    db.execute("""
        INSERT INTO report_runs (run_id, script_id, target_agent, parameters, status, run_by)
        VALUES (?, ?, ?, ?, 'running', ?)
    """, (
        run_id,
        script_id,
        request.target,
        json.dumps(provided_params) if provided_params else None,
        user.get('username', 'unknown')
    ))
    
    # Initialize active run for WebSocket streaming
    active_runs[run_id] = {
        'script_id': script_id,
        'script_path': script['script_path'],
        'target': request.target,
        'agent': agent,
        'parameters': provided_params,
        'timeout': script.get('timeout', 300),
        'status': 'running',
        'output': [],
        'subscribers': []
    }
    
    # Start execution in background
    asyncio.create_task(execute_report(run_id, db))
    
    logger.info(f"Started report run {run_id}: {script_id} on {request.target}")
    
    return {
        "run_id": run_id,
        "script_id": script_id,
        "target": request.target,
        "status": "running"
    }


async def execute_report(run_id: str, db):
    """Execute the report script on the agent"""
    run_info = active_runs.get(run_id)
    if not run_info:
        return
    
    agent = run_info['agent']
    script_path = run_info['script_path']
    parameters = run_info['parameters']
    timeout = run_info['timeout']
    
    # Build the agent URL
    ssl_enabled = agent.get('ssl_enabled', SSL_ENABLED)
    protocol = "https" if ssl_enabled else "http"
    agent_url = f"{protocol}://{agent['host']}:{agent['port']}"
    
    verify_ssl = get_ssl_verify_config()
    
    try:
        # Build command with parameters
        cmd = script_path
        if parameters:
            # Pass parameters as environment variables or command line args
            # Option 1: As JSON env var
            param_env = {"REPORT_PARAMS": json.dumps(parameters)}
            # Option 2: As command line args (key=value format)
            param_args = " ".join([f"{k}={v}" for k, v in parameters.items() if v is not None])
            if param_args:
                cmd = f"{script_path} {param_args}"
        
        # Send to agent for execution
        async with httpx.AsyncClient(timeout=timeout + 10, verify=verify_ssl) as client:
            response = await client.post(
                f"{agent_url}/execute",
                json={
                    "command": cmd,
                    "timeout": timeout,
                    "stream": True,
                    "env": {"REPORT_PARAMS": json.dumps(parameters)} if parameters else {}
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                stdout = result.get('stdout', '')
                stderr = result.get('stderr', '')
                exit_code = result.get('exit_code', 0)
                
                # Send output to subscribers
                if stdout:
                    await broadcast_output(run_id, stdout)
                if stderr:
                    await broadcast_output(run_id, f"\n[STDERR]\n{stderr}")
                
                # Update status
                status = 'completed' if exit_code == 0 else 'failed'
                run_info['status'] = status
                run_info['exit_code'] = exit_code
                
                # Notify completion
                await broadcast_complete(run_id, status, exit_code)
                
                # Update database
                db.execute("""
                    UPDATE report_runs 
                    SET status = ?, completed_at = datetime('now'), exit_code = ?
                    WHERE run_id = ?
                """, (status, exit_code, run_id))
                
            else:
                error_msg = f"Agent returned status {response.status_code}"
                await broadcast_output(run_id, f"\n[ERROR] {error_msg}\n")
                await broadcast_complete(run_id, 'failed', -1)
                
                db.execute("""
                    UPDATE report_runs 
                    SET status = 'failed', completed_at = datetime('now'), exit_code = -1
                    WHERE run_id = ?
                """, (run_id,))
                
    except httpx.TimeoutException:
        await broadcast_output(run_id, "\n[ERROR] Execution timeout\n")
        await broadcast_complete(run_id, 'timeout', -1)
        db.execute("""
            UPDATE report_runs 
            SET status = 'timeout', completed_at = datetime('now'), exit_code = -1
            WHERE run_id = ?
        """, (run_id,))
        
    except Exception as e:
        logger.error(f"Report execution error: {e}")
        await broadcast_output(run_id, f"\n[ERROR] {str(e)}\n")
        await broadcast_complete(run_id, 'failed', -1)
        db.execute("""
            UPDATE report_runs 
            SET status = 'failed', completed_at = datetime('now'), exit_code = -1
            WHERE run_id = ?
        """, (run_id,))
    
    finally:
        # Clean up after a delay
        await asyncio.sleep(60)
        active_runs.pop(run_id, None)


async def broadcast_output(run_id: str, data: str):
    """Broadcast output to all WebSocket subscribers"""
    run_info = active_runs.get(run_id)
    if not run_info:
        return
    
    run_info['output'].append(data)
    
    message = json.dumps({"type": "output", "data": data})
    
    dead_sockets = []
    for ws in run_info['subscribers']:
        try:
            await ws.send_text(message)
        except Exception:
            dead_sockets.append(ws)
    
    # Remove dead sockets
    for ws in dead_sockets:
        run_info['subscribers'].remove(ws)


async def broadcast_complete(run_id: str, status: str, exit_code: int):
    """Broadcast completion to all WebSocket subscribers"""
    run_info = active_runs.get(run_id)
    if not run_info:
        return
    
    message = json.dumps({
        "type": "complete",
        "status": status,
        "exit_code": exit_code
    })
    
    for ws in run_info['subscribers']:
        try:
            await ws.send_text(message)
        except Exception:
            pass


# =============================================================================
# WebSocket for Real-time Output
# =============================================================================

@router.websocket("/ws/{run_id}")
async def websocket_output(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for streaming report output"""
    await websocket.accept()
    
    run_info = active_runs.get(run_id)
    if not run_info:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Run not found or already completed"
        }))
        await websocket.close()
        return
    
    # Add to subscribers
    run_info['subscribers'].append(websocket)
    
    # Send any existing output
    for output in run_info['output']:
        await websocket.send_text(json.dumps({"type": "output", "data": output}))
    
    # If already complete, send completion
    if run_info['status'] in ['completed', 'failed', 'timeout']:
        await websocket.send_text(json.dumps({
            "type": "complete",
            "status": run_info['status'],
            "exit_code": run_info.get('exit_code', -1)
        }))
    
    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        # Remove from subscribers
        if run_id in active_runs and websocket in active_runs[run_id]['subscribers']:
            active_runs[run_id]['subscribers'].remove(websocket)


# =============================================================================
# Routes - Run History
# =============================================================================

@router.get("/history")
async def get_report_history(
    limit: int = 50,
    script_id: Optional[str] = None,
    user: dict = Depends(verify_token)
):
    """Get report run history"""
    db = get_db()
    init_reports_table(db)
    
    if script_id:
        rows = db.query("""
            SELECT * FROM report_runs 
            WHERE script_id = ?
            ORDER BY started_at DESC 
            LIMIT ?
        """, (script_id, limit))
    else:
        rows = db.query("""
            SELECT * FROM report_runs 
            ORDER BY started_at DESC 
            LIMIT ?
        """, (limit,))
    
    runs = []
    for row in rows:
        run = dict(row)
        if run.get('parameters'):
            try:
                run['parameters'] = json.loads(run['parameters'])
            except json.JSONDecodeError:
                pass
        runs.append(run)
    
    return {"runs": runs, "count": len(runs)}


@router.get("/history/{run_id}")
async def get_report_run(run_id: str, user: dict = Depends(verify_token)):
    """Get details of a specific report run"""
    db = get_db()
    init_reports_table(db)
    
    rows = db.query("SELECT * FROM report_runs WHERE run_id = ?", (run_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    run = dict(rows[0])
    if run.get('parameters'):
        try:
            run['parameters'] = json.loads(run['parameters'])
        except json.JSONDecodeError:
            pass
    
    return run
