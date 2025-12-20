"""
Reports API - Bypass approval workflow for read-only status scripts
====================================================================

Add to your existing FastAPI app:
    from reports import router as reports_router
    app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
"""

import asyncio
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel

# ============================================================================
# Configuration
# ============================================================================

# Directory containing report scripts (read-only, no approval needed)
REPORTS_SCRIPTS_DIR = os.getenv("REPORTS_SCRIPTS_DIR", "/u01/app/ssaAgent/orchestration-system/scripts/reports")

# Allowed script extensions
ALLOWED_EXTENSIONS = {".sh", ".py", ".pl"}

# Maximum execution time for reports (seconds)
MAX_EXECUTION_TIME = 300  # 5 minutes

# ============================================================================
# Models
# ============================================================================

class ReportScript(BaseModel):
    """Report script metadata"""
    id: str
    name: str
    description: str
    filename: str
    category: str
    last_modified: str
    estimated_time: Optional[str] = None


class ReportRunRequest(BaseModel):
    """Request to run a report"""
    parameters: Optional[dict] = None


class ReportRunResponse(BaseModel):
    """Response from running a report"""
    run_id: str
    script_id: str
    status: str
    started_at: str


class ReportResult(BaseModel):
    """Report execution result"""
    run_id: str
    script_id: str
    status: str  # running, completed, failed
    started_at: str
    completed_at: Optional[str] = None
    exit_code: Optional[int] = None
    output: Optional[str] = None
    html_output: Optional[str] = None


# ============================================================================
# In-memory storage for running reports
# ============================================================================

running_reports: dict = {}
report_results: dict = {}


# ============================================================================
# Helper Functions
# ============================================================================

def parse_script_metadata(script_path: Path) -> dict:
    """
    Parse script header for metadata.
    
    Expected format in script:
    # REPORT_NAME: Database Status
    # REPORT_DESC: Shows current database connection status
    # REPORT_CATEGORY: Database
    # REPORT_TIME: ~30 seconds
    """
    metadata = {
        "name": script_path.stem.replace("_", " ").title(),
        "description": "No description available",
        "category": "General",
        "estimated_time": None,
    }
    
    try:
        with open(script_path, 'r') as f:
            for line in f:
                if not line.startswith("#"):
                    break
                line = line.strip()
                if line.startswith("# REPORT_NAME:"):
                    metadata["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("# REPORT_DESC:"):
                    metadata["description"] = line.split(":", 1)[1].strip()
                elif line.startswith("# REPORT_CATEGORY:"):
                    metadata["category"] = line.split(":", 1)[1].strip()
                elif line.startswith("# REPORT_TIME:"):
                    metadata["estimated_time"] = line.split(":", 1)[1].strip()
    except Exception:
        pass
    
    return metadata


def discover_report_scripts() -> List[ReportScript]:
    """Discover all report scripts in the reports directory"""
    scripts = []
    reports_dir = Path(REPORTS_SCRIPTS_DIR)
    
    if not reports_dir.exists():
        return scripts
    
    for script_path in reports_dir.rglob("*"):
        if script_path.is_file() and script_path.suffix in ALLOWED_EXTENSIONS:
            # Get relative path for category
            rel_path = script_path.relative_to(reports_dir)
            category = str(rel_path.parent) if rel_path.parent != Path(".") else "General"
            
            metadata = parse_script_metadata(script_path)
            if category != "General":
                metadata["category"] = category.replace("/", " > ").title()
            
            stat = script_path.stat()
            
            scripts.append(ReportScript(
                id=str(rel_path).replace("/", "__").replace("\\", "__"),
                name=metadata["name"],
                description=metadata["description"],
                filename=script_path.name,
                category=metadata["category"],
                last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                estimated_time=metadata["estimated_time"],
            ))
    
    return sorted(scripts, key=lambda s: (s.category, s.name))


def get_script_path(script_id: str) -> Path:
    """Convert script ID back to path"""
    rel_path = script_id.replace("__", "/")
    script_path = Path(REPORTS_SCRIPTS_DIR) / rel_path
    
    # Security check - ensure path is within reports directory
    try:
        script_path.resolve().relative_to(Path(REPORTS_SCRIPTS_DIR).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid script path")
    
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="Script not found")
    
    return script_path


# ============================================================================
# Router
# ============================================================================

router = APIRouter()


@router.get("/scripts", response_model=List[ReportScript])
async def list_report_scripts():
    """List all available report scripts"""
    return discover_report_scripts()


@router.get("/scripts/{script_id}", response_model=ReportScript)
async def get_report_script(script_id: str):
    """Get details of a specific report script"""
    script_path = get_script_path(script_id)
    metadata = parse_script_metadata(script_path)
    stat = script_path.stat()
    
    rel_path = script_path.relative_to(Path(REPORTS_SCRIPTS_DIR))
    category = str(rel_path.parent) if rel_path.parent != Path(".") else "General"
    
    return ReportScript(
        id=script_id,
        name=metadata["name"],
        description=metadata["description"],
        filename=script_path.name,
        category=category.replace("/", " > ").title() if category != "General" else metadata["category"],
        last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        estimated_time=metadata["estimated_time"],
    )


@router.post("/run/{script_id}", response_model=ReportRunResponse)
async def run_report(script_id: str, request: ReportRunRequest = None):
    """
    Run a report script immediately (no approval required).
    Returns a run_id to track the execution.
    """
    script_path = get_script_path(script_id)
    
    # Generate run ID
    run_id = f"{script_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    started_at = datetime.now().isoformat()
    
    # Initialize result
    report_results[run_id] = ReportResult(
        run_id=run_id,
        script_id=script_id,
        status="running",
        started_at=started_at,
    )
    
    # Start execution in background
    asyncio.create_task(_execute_report(run_id, script_path, request.parameters if request else None))
    
    return ReportRunResponse(
        run_id=run_id,
        script_id=script_id,
        status="running",
        started_at=started_at,
    )


@router.get("/result/{run_id}", response_model=ReportResult)
async def get_report_result(run_id: str):
    """Get the result of a report execution"""
    if run_id not in report_results:
        raise HTTPException(status_code=404, detail="Report run not found")
    
    return report_results[run_id]


@router.websocket("/ws/{run_id}")
async def report_output_stream(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for streaming report output in real-time.
    Connect before or during execution to receive output as it's generated.
    """
    await websocket.accept()
    
    try:
        # Check if this is a valid run
        if run_id not in report_results and run_id not in running_reports:
            await websocket.send_json({"type": "error", "message": "Report run not found"})
            await websocket.close()
            return
        
        # Register this websocket
        if run_id not in running_reports:
            running_reports[run_id] = {"websockets": []}
        
        if "websockets" not in running_reports[run_id]:
            running_reports[run_id]["websockets"] = []
        
        running_reports[run_id]["websockets"].append(websocket)
        
        # Send any existing output
        if run_id in report_results:
            result = report_results[run_id]
            if result.output:
                await websocket.send_json({
                    "type": "output",
                    "data": result.output
                })
            if result.status != "running":
                await websocket.send_json({
                    "type": "complete",
                    "status": result.status,
                    "exit_code": result.exit_code
                })
        
        # Keep connection open until report completes or client disconnects
        while True:
            try:
                # Wait for messages (mainly for ping/pong)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_text("ping")
                except:
                    break
            
            # Check if report is done
            if run_id in report_results and report_results[run_id].status != "running":
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        # Remove websocket from tracking
        if run_id in running_reports and "websockets" in running_reports[run_id]:
            try:
                running_reports[run_id]["websockets"].remove(websocket)
            except ValueError:
                pass


async def _execute_report(run_id: str, script_path: Path, parameters: dict = None):
    """Execute a report script and capture output"""
    output_lines = []
    
    try:
        # Build command
        if script_path.suffix == ".py":
            cmd = ["python3", str(script_path)]
        elif script_path.suffix == ".pl":
            cmd = ["perl", str(script_path)]
        else:
            cmd = ["bash", str(script_path)]
        
        # Add parameters as environment variables
        env = os.environ.copy()
        if parameters:
            for key, value in parameters.items():
                env[f"REPORT_PARAM_{key.upper()}"] = str(value)
        
        # Execute
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            cwd=str(script_path.parent),
        )
        
        running_reports[run_id] = {
            "process": process,
            "websockets": running_reports.get(run_id, {}).get("websockets", [])
        }
        
        # Stream output
        async def read_output():
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                
                decoded = line.decode('utf-8', errors='replace')
                output_lines.append(decoded)
                
                # Send to connected websockets
                for ws in running_reports.get(run_id, {}).get("websockets", []):
                    try:
                        await ws.send_json({
                            "type": "output",
                            "data": decoded
                        })
                    except:
                        pass
        
        # Wait for completion with timeout
        try:
            await asyncio.wait_for(read_output(), timeout=MAX_EXECUTION_TIME)
            await process.wait()
            exit_code = process.returncode
            status = "completed" if exit_code == 0 else "failed"
        except asyncio.TimeoutError:
            process.kill()
            output_lines.append("\n[ERROR] Report execution timed out\n")
            exit_code = -1
            status = "failed"
        
        # Check for HTML output file
        html_output = None
        html_file = script_path.with_suffix('.html')
        output_html_file = script_path.parent / f"{script_path.stem}_output.html"
        
        for hf in [html_file, output_html_file]:
            if hf.exists():
                try:
                    html_output = hf.read_text()
                except:
                    pass
                break
        
        # Update result
        full_output = "".join(output_lines)
        report_results[run_id] = ReportResult(
            run_id=run_id,
            script_id=report_results[run_id].script_id,
            status=status,
            started_at=report_results[run_id].started_at,
            completed_at=datetime.now().isoformat(),
            exit_code=exit_code,
            output=full_output,
            html_output=html_output,
        )
        
        # Notify websockets of completion
        for ws in running_reports.get(run_id, {}).get("websockets", []):
            try:
                await ws.send_json({
                    "type": "complete",
                    "status": status,
                    "exit_code": exit_code
                })
            except:
                pass
        
    except Exception as e:
        report_results[run_id] = ReportResult(
            run_id=run_id,
            script_id=report_results[run_id].script_id,
            status="failed",
            started_at=report_results[run_id].started_at,
            completed_at=datetime.now().isoformat(),
            exit_code=-1,
            output=f"Error: {str(e)}",
        )
    
    finally:
        # Cleanup
        if run_id in running_reports:
            del running_reports[run_id]


@router.get("/history", response_model=List[ReportResult])
async def get_report_history(limit: int = 20):
    """Get recent report execution history"""
    results = list(report_results.values())
    results.sort(key=lambda r: r.started_at, reverse=True)
    return results[:limit]


@router.delete("/result/{run_id}")
async def cancel_report(run_id: str):
    """Cancel a running report"""
    if run_id not in running_reports:
        raise HTTPException(status_code=404, detail="Report not running")
    
    process = running_reports[run_id].get("process")
    if process:
        process.kill()
    
    if run_id in report_results:
        report_results[run_id].status = "cancelled"
        report_results[run_id].completed_at = datetime.now().isoformat()
    
    return {"status": "cancelled"}
