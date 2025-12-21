"""
Reports API - Backend for running read-only status reports on agents
====================================================================
Reports are registered similar to scripts but bypass the approval workflow.
They execute on selected agents and stream output via WebSocket.
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import uuid
import json
import os

router = APIRouter()

# ============================================================================
# Data Models
# ============================================================================

class ReportScript(BaseModel):
    """Registered report script"""
    script_id: str = Field(..., description="Unique report ID")
    name: str = Field(..., description="Display name")
    description: str = Field("", description="What this report does")
    script_path: str = Field(..., description="Path to script on agent")
    category: str = Field("General", description="Category for grouping")
    timeout: int = Field(300, description="Timeout in seconds")

class ReportRegisterRequest(BaseModel):
    """Request to register a new report script"""
    script_id: str
    name: Optional[str] = None
    description: str = ""
    script_path: str
    category: str = "General"
    timeout: int = 300

class ReportRunRequest(BaseModel):
    """Request to run a report"""
    target: str = Field(..., description="Agent name to run on")
    parameters: Dict[str, Any] = Field(default_factory=dict)

class ReportRun(BaseModel):
    """A report execution record"""
    run_id: str
    script_id: str
    target: str
    status: str  # pending, running, completed, failed
    started_at: datetime
    completed_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    output: str = ""

# ============================================================================
# In-Memory Storage (replace with DB in production)
# ============================================================================

# Registered report scripts
_report_scripts: Dict[str, ReportScript] = {}

# Report execution history
_report_runs: Dict[str, ReportRun] = {}

# Active WebSocket connections for streaming output
_ws_connections: Dict[str, List[WebSocket]] = {}

# ============================================================================
# Report Script Registration Endpoints
# ============================================================================

@router.get("/scripts")
async def list_report_scripts() -> List[dict]:
    """List all registered report scripts"""
    return [
        {
            "id": s.script_id,
            "script_id": s.script_id,
            "name": s.name,
            "description": s.description,
            "script_path": s.script_path,
            "category": s.category,
            "timeout": s.timeout
        }
        for s in _report_scripts.values()
    ]

@router.post("/scripts/register")
async def register_report_script(req: ReportRegisterRequest) -> dict:
    """Register a new report script"""
    script = ReportScript(
        script_id=req.script_id,
        name=req.name or req.script_id,
        description=req.description,
        script_path=req.script_path,
        category=req.category,
        timeout=req.timeout
    )
    _report_scripts[req.script_id] = script
    return {"status": "registered", "script_id": req.script_id}

@router.delete("/scripts/{script_id}")
async def unregister_report_script(script_id: str) -> dict:
    """Unregister a report script"""
    if script_id not in _report_scripts:
        raise HTTPException(status_code=404, detail="Report script not found")
    del _report_scripts[script_id]
    return {"status": "unregistered", "script_id": script_id}

# ============================================================================
# Report Execution Endpoints
# ============================================================================

@router.post("/run/{script_id}")
async def run_report(script_id: str, req: ReportRunRequest) -> dict:
    """
    Start a report execution on the specified agent.
    Returns a run_id for tracking and WebSocket connection.
    """
    if script_id not in _report_scripts:
        raise HTTPException(status_code=404, detail=f"Report script '{script_id}' not found")
    
    script = _report_scripts[script_id]
    run_id = str(uuid.uuid4())[:8]
    
    # Create run record
    run = ReportRun(
        run_id=run_id,
        script_id=script_id,
        target=req.target,
        status="pending",
        started_at=datetime.utcnow()
    )
    _report_runs[run_id] = run
    
    # Start async execution
    asyncio.create_task(_execute_report(run_id, script, req.target, req.parameters))
    
    return {
        "run_id": run_id,
        "status": "started",
        "ws_url": f"/api/reports/ws/{run_id}"
    }

async def _execute_report(run_id: str, script: ReportScript, target: str, parameters: Dict):
    """Execute the report on the target agent"""
    run = _report_runs.get(run_id)
    if not run:
        return
    
    run.status = "running"
    
    try:
        # Import agent communication module
        # This should be your existing agent execution code
        from agents import get_agent, execute_on_agent  # Adjust import as needed
        
        agent = get_agent(target)
        if not agent:
            raise Exception(f"Agent '{target}' not found or offline")
        
        # Execute script on agent
        result = await execute_on_agent(
            agent=agent,
            script_path=script.script_path,
            timeout=script.timeout,
            parameters=parameters,
            stream_callback=lambda data: _broadcast_output(run_id, data)
        )
        
        run.status = "completed"
        run.exit_code = result.get("exit_code", 0)
        run.output = result.get("output", "")
        
        # Notify WebSocket clients
        await _broadcast_complete(run_id, run.status, run.exit_code)
        
    except Exception as e:
        run.status = "failed"
        run.output = str(e)
        await _broadcast_error(run_id, str(e))
    
    finally:
        run.completed_at = datetime.utcnow()

def _broadcast_output(run_id: str, data: str):
    """Broadcast output to all connected WebSocket clients"""
    asyncio.create_task(_async_broadcast(run_id, {"type": "output", "data": data}))

async def _broadcast_complete(run_id: str, status: str, exit_code: int):
    """Broadcast completion to all connected WebSocket clients"""
    await _async_broadcast(run_id, {
        "type": "complete",
        "status": status,
        "exit_code": exit_code
    })

async def _broadcast_error(run_id: str, message: str):
    """Broadcast error to all connected WebSocket clients"""
    await _async_broadcast(run_id, {"type": "error", "message": message})

async def _async_broadcast(run_id: str, message: dict):
    """Send message to all WebSocket connections for this run"""
    if run_id not in _ws_connections:
        return
    
    dead_connections = []
    for ws in _ws_connections[run_id]:
        try:
            await ws.send_text(json.dumps(message))
        except:
            dead_connections.append(ws)
    
    # Clean up dead connections
    for ws in dead_connections:
        _ws_connections[run_id].remove(ws)

# ============================================================================
# WebSocket for Streaming Output
# ============================================================================

@router.websocket("/ws/{run_id}")
async def report_output_stream(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for streaming report output"""
    await websocket.accept()
    
    # Register connection
    if run_id not in _ws_connections:
        _ws_connections[run_id] = []
    _ws_connections[run_id].append(websocket)
    
    try:
        # Send any existing output
        run = _report_runs.get(run_id)
        if run and run.output:
            await websocket.send_text(json.dumps({"type": "output", "data": run.output}))
        
        # If already complete, send status
        if run and run.status in ("completed", "failed"):
            await websocket.send_text(json.dumps({
                "type": "complete",
                "status": run.status,
                "exit_code": run.exit_code
            }))
        
        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send ping to keep alive
                try:
                    await websocket.send_text("ping")
                except:
                    break
                    
    except WebSocketDisconnect:
        pass
    finally:
        # Unregister connection
        if run_id in _ws_connections and websocket in _ws_connections[run_id]:
            _ws_connections[run_id].remove(websocket)

# ============================================================================
# History & Results Endpoints
# ============================================================================

@router.get("/history")
async def get_report_history(limit: int = 20) -> List[dict]:
    """Get recent report execution history"""
    runs = sorted(
        _report_runs.values(),
        key=lambda r: r.started_at,
        reverse=True
    )[:limit]
    
    return [
        {
            "run_id": r.run_id,
            "script_id": r.script_id,
            "target": r.target,
            "status": r.status,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "exit_code": r.exit_code
        }
        for r in runs
    ]

@router.get("/result/{run_id}")
async def get_report_result(run_id: str) -> dict:
    """Get the result of a specific report run"""
    run = _report_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Report run not found")
    
    return {
        "run_id": run.run_id,
        "script_id": run.script_id,
        "target": run.target,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "exit_code": run.exit_code,
        "output": run.output
    }

@router.delete("/result/{run_id}")
async def cancel_report(run_id: str) -> dict:
    """Cancel a running report (best effort)"""
    run = _report_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Report run not found")
    
    if run.status == "running":
        run.status = "cancelled"
        run.completed_at = datetime.utcnow()
        await _broadcast_complete(run_id, "cancelled", -1)
    
    return {"status": "cancelled", "run_id": run_id}

# ============================================================================
# Integration Helper
# ============================================================================

def init_sample_reports():
    """Initialize some sample report scripts for testing"""
    samples = [
        ReportScript(
            script_id="db-status",
            name="Database Status",
            description="Check database connectivity and status",
            script_path="/opt/scripts/reports/db_status.sh",
            category="Database",
            timeout=60
        ),
        ReportScript(
            script_id="disk-usage",
            name="Disk Usage",
            description="Report disk space usage across filesystems",
            script_path="/opt/scripts/reports/disk_usage.sh",
            category="System",
            timeout=30
        ),
        ReportScript(
            script_id="service-health",
            name="Service Health Check",
            description="Check status of critical services",
            script_path="/opt/scripts/reports/service_health.sh",
            category="System",
            timeout=120
        ),
        ReportScript(
            script_id="ebs-status",
            name="EBS Instance Status",
            description="Oracle EBS concurrent manager and listener status",
            script_path="/opt/scripts/reports/ebs_status.sh",
            category="Oracle",
            timeout=180
        ),
        ReportScript(
            script_id="backup-status",
            name="Backup Status",
            description="Check recent backup completion status",
            script_path="/opt/scripts/reports/backup_status.sh",
            category="Backup",
            timeout=60
        ),
    ]
    
    for script in samples:
        _report_scripts[script.script_id] = script

# Uncomment to load samples on startup:
# init_sample_reports()
