# controller/routes/workflows.py - SSL-compatible workflow routes

from fastapi import APIRouter, HTTPException, Depends, Body, BackgroundTasks, Request
from pydantic import BaseModel
from typing import List, Optional
import logging
import uuid
import os
import httpx

from controller.db.db import get_db
from controller.deps import verify_token, require_admin, require_approver, verify_approver_jwt, require_execution_token

# Safe email import - won't crash if emailer module is missing
try:
    from controller.emailer import send_email
    EMAIL_ENABLED = True
except ImportError:
    EMAIL_ENABLED = False
    def send_email(*args, **kwargs):
        logging.getLogger(__name__).warning("Email module not available - email not sent")
        return False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])

# SSL Configuration
SSL_ENABLED = os.getenv("SSL_ENABLED", "true").lower() == "true"
SSL_VERIFY = os.getenv("SSL_VERIFY", "false").lower() == "true"
SSL_CA_CERTS = os.getenv("SSL_CA_CERTS", "./certs/certChain.pem")


# =============================================================================
# Request Models
# =============================================================================

class CreateWorkflowRequest(BaseModel):
    script_id: str
    targets: List[str]
    requestor: str
    reason: str
    required_approval_levels: int = 1
    ttl_minutes: int = 60
    notify_email: str = ""        # Approver's email
    requestor_email: str = ""     # Requestor's email for notifications
    script_params: Optional[dict] = None  # Parameters to pass to script at execution


class ApproveWorkflowRequest(BaseModel):
    approver: str
    level: int = 1


class ExecuteWorkflowRequest(BaseModel):
    parameters: Optional[dict] = None
    environment: Optional[dict] = None
    timeout: Optional[int] = None


class ReexecRequest(BaseModel):
    note: Optional[str] = None
    requester_email: Optional[str] = None


class ApprovePayload(BaseModel):
    request_id: int


# =============================================================================
# Helper Functions
# =============================================================================

def get_ssl_verify_config():
    if not SSL_VERIFY:
        return False
    if SSL_CA_CERTS and os.path.exists(SSL_CA_CERTS):
        return SSL_CA_CERTS
    return False


def build_email_html(
    title: str,
    title_color: str,
    accent_color: str,
    message: str,
    details: list,
    button_text: str = None,
    button_url: str = None,
    button_color: str = "#0284c7",
    footer: str = None
) -> str:
    """
    Build styled HTML email - LIGHT THEME that works in Outlook.
    Uses bgcolor on every cell for maximum compatibility.
    
    Args:
        title: Email header title
        title_color: Color for title text (hex)
        accent_color: Color for accent bar and logo (hex)
        message: Main message paragraph
        details: List of tuples [(label, value), ...]
        button_text: Optional CTA button text
        button_url: Optional CTA button URL
        button_color: Button background color
        footer: Optional footer text
    """
    from datetime import datetime
    
    # Build details rows with alternating backgrounds
    rows_html = ""
    for i, (label, value) in enumerate(details):
        row_bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        rows_html += f"""
        <tr>
            <td bgcolor="{row_bg}" style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#64748b;font-weight:600;width:160px;font-family:Arial,sans-serif;font-size:14px;">
                {label}
            </td>
            <td bgcolor="{row_bg}" style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#1e293b;font-family:Arial,sans-serif;font-size:14px;">
                {value}
            </td>
        </tr>"""
    
    # Build button if provided
    button_html = ""
    if button_text and button_url:
        button_html = f"""
        <tr>
            <td colspan="2" bgcolor="#ffffff" align="center" style="padding:28px 0 8px 0;">
                <table cellpadding="0" cellspacing="0" border="0">
                    <tr>
                        <td bgcolor="{button_color}" style="border-radius:6px;">
                            <a href="{button_url}" style="display:inline-block;padding:14px 32px;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;font-family:Arial,sans-serif;">
                                {button_text}
                            </a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>"""
    
    # Build footer row
    footer_html = ""
    if footer:
        footer_html = f"""
        <tr>
            <td colspan="2" bgcolor="#ffffff" style="padding:16px 0 0 0;font-size:13px;color:#64748b;font-family:Arial,sans-serif;">
                {footer}
            </td>
        </tr>"""

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return f"""<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
</head>
<body bgcolor="#f1f5f9" style="margin:0;padding:0;background-color:#f1f5f9;font-family:Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f1f5f9">
<tr>
<td bgcolor="#f1f5f9" align="center" style="padding:32px 16px;">

<table width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff" style="border:1px solid #e2e8f0;border-radius:8px;">

<!-- Accent Bar -->
<tr>
<td bgcolor="{accent_color}" height="4" style="font-size:1px;line-height:1px;">&nbsp;</td>
</tr>

<!-- Header -->
<tr>
<td bgcolor="#ffffff" style="padding:24px 32px 16px 32px;">
    <table cellpadding="0" cellspacing="0" border="0">
    <tr>
    <td bgcolor="{accent_color}" width="44" height="44" align="center" valign="middle" style="border-radius:8px;">
        <span style="color:#ffffff;font-size:16px;font-weight:bold;font-family:Arial,sans-serif;">O</span>
    </td>
    <td bgcolor="#ffffff" style="padding-left:16px;">
        <div style="font-size:20px;font-weight:700;color:{title_color};font-family:Arial,sans-serif;">{title}</div>
    </td>
    </tr>
    </table>
</td>
</tr>

<!-- Message -->
<tr>
<td bgcolor="#ffffff" style="padding:0 32px 24px 32px;color:#475569;font-size:15px;line-height:1.6;font-family:Arial,sans-serif;">
    {message}
</td>
</tr>

<!-- Details Table -->
<tr>
<td bgcolor="#ffffff" style="padding:0 32px 24px 32px;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;border-radius:6px;">
        {rows_html}
        {button_html}
        {footer_html}
    </table>
</td>
</tr>

<!-- Footer -->
<tr>
<td bgcolor="#f8fafc" style="padding:16px 32px;border-top:1px solid #e2e8f0;font-size:12px;color:#94a3b8;font-family:Arial,sans-serif;">
    Orchestration System &bull; {timestamp}
</td>
</tr>

</table>

</td>
</tr>
</table>
</body>
</html>"""


async def notify_agent_of_workflow(
    agent_host: str,
    agent_port: int,
    workflow_id: str,
    ssl_enabled: bool = False
) -> bool:
    """Notify agent that a workflow is ready for execution"""
    protocol = "https" if ssl_enabled else "http"
    url = f"{protocol}://{agent_host}:{agent_port}/execute-workflow"

    verify_ssl = get_ssl_verify_config()

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=verify_ssl) as client:
            response = await client.post(url, json={"workflow_id": workflow_id})
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to notify agent at {url}: {e}")
        return False


# =============================================================================
# Endpoints
# =============================================================================

@router.get("")
@router.get("/")
async def list_workflows(
    limit: Optional[int] = None,
    status: Optional[str] = None,
    token: dict = Depends(verify_token)
):
    """List workflows with optional filters"""
    try:
        db = get_db()
        workflows = db.list_workflows(limit=limit, status=status)
        return {
            "workflows": workflows,
            "count": len(workflows),
            "ssl_enabled": SSL_ENABLED
        }
    except Exception as e:
        logger.error(f"Error listing workflows: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    token: dict = Depends(verify_token)
):
    """Get a workflow by ID"""
    db = get_db()
    workflow = db.get_workflow(workflow_id)

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return workflow


@router.post("")
@router.post("/")
async def create_workflow(
    request: CreateWorkflowRequest,
    token: dict = Depends(verify_token)
):
    """Create a new workflow and notify approver"""
    db = get_db()
    workflow_id = f"wf_{uuid.uuid4().hex[:12]}"

    try:
        # Try with requestor_email and script_params (newer DB schema)
        try:
            workflow = db.create_workflow(
                workflow_id=workflow_id,
                script_id=request.script_id,
                targets=request.targets,
                requestor=request.requestor,
                required_levels=request.required_approval_levels,
                notify_email=request.notify_email,
                requestor_email=request.requestor_email,
                ttl_minutes=request.ttl_minutes,
                reason=request.reason,
                script_params=request.script_params
            )
        except TypeError:
            # Fallback for older DB schema without requestor_email/script_params
            workflow = db.create_workflow(
                workflow_id=workflow_id,
                script_id=request.script_id,
                targets=request.targets,
                requestor=request.requestor,
                required_levels=request.required_approval_levels,
                notify_email=request.notify_email,
                ttl_minutes=request.ttl_minutes,
                reason=request.reason
            )
            # Store in workflow dict for later use
            workflow["requestor_email"] = request.requestor_email
            workflow["script_params"] = request.script_params

        db.add_audit(
            workflow_id=workflow_id,
            action="created",
            user=request.requestor,
            note=f"Workflow created: {request.reason}"
        )

        logger.info(f"Workflow created: {workflow_id}")
        
        # Send email notification to approver
        logger.info(f"[EMAIL] notify_email={request.notify_email}, requestor_email={request.requestor_email}, EMAIL_ENABLED={EMAIL_ENABLED}")
        
        if request.notify_email:
            logger.info(f"[EMAIL] Attempting to send approval notification to {request.notify_email}")
            try:
                api_host = os.getenv("API_HOST", "https://localhost:7585")
                dashboard_url = f"{api_host}/dashboard"
                
                # Build details list
                details = [
                    ("Workflow ID", workflow_id),
                    ("Requestor", request.requestor),
                    ("Requestor Email", request.requestor_email or "N/A"),
                    ("Script", request.script_id),
                    ("Target Agents", ', '.join(request.targets)),
                    ("Reason", request.reason),
                    ("Expires In", f"{request.ttl_minutes} minutes"),
                ]
                
                # Add script parameters if present
                if request.script_params:
                    params_display = ', '.join([f'{k}: {v}' for k, v in request.script_params.items()])
                    details.append(("Parameters", params_display))
                
                html_content = build_email_html(
                    title="Workflow Approval Required",
                    title_color="#b45309",  # Amber-700
                    accent_color="#f59e0b",  # Amber-500
                    message="A new workflow has been submitted and requires your approval.",
                    details=details,
                    button_text="Open Dashboard to Approve",
                    button_url=dashboard_url,
                    button_color="#0284c7",  # Sky-600
                    footer=f"Requested by: {request.requestor}"
                )
                
                result = send_email(
                    to=request.notify_email,
                    subject=f"[Action Required] Workflow Approval: {request.script_id} - {request.requestor}",
                    html_body=html_content
                )
                logger.info(f"[EMAIL] send_email returned: {result}")
                logger.info(f"Approval notification sent to {request.notify_email} for workflow {workflow_id}")
                
            except Exception as email_error:
                logger.error(f"Failed to send approval email: {email_error}")
                # Don't fail workflow creation if email fails
        
        return workflow

    except Exception as e:
        logger.error(f"Error creating workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/approve")
async def approve_workflow(
    workflow_id: str,
    request: ApproveWorkflowRequest,
    user: dict = Depends(require_approver)
):
    """Approve a workflow and notify requestor"""
    db = get_db()

    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if workflow["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Workflow is already {workflow['status']}")

    success = db.add_approval(workflow_id, request.approver, request.level)
    if not success:
        raise HTTPException(status_code=400, detail="Already approved by this user")

    workflow = db.get_workflow(workflow_id)
    approvals = workflow.get("approvals", [])

    if len(approvals) >= workflow["required_approval_levels"]:
        db.update_workflow_status(workflow_id, "approved")
        db.add_audit(workflow_id=workflow_id, action="fully_approved", user=request.approver, note="Workflow fully approved")
        logger.info(f"Workflow approved: {workflow_id}")
        
        # Send approval notification to requestor
        requestor_email = workflow.get("requestor_email") or workflow.get("notify_email")
        if requestor_email:
            try:
                api_host = os.getenv("API_HOST", "https://localhost:7585")
                dashboard_url = f"{api_host}/dashboard"
                
                html_content = build_email_html(
                    title="Workflow Approved",
                    title_color="#047857",  # Emerald-700
                    accent_color="#10b981",  # Emerald-500
                    message="Your workflow has been approved and is ready for execution.",
                    details=[
                        ("Workflow ID", workflow_id),
                        ("Script", workflow.get("script_id", "N/A")),
                        ("Approved By", request.approver),
                        ("Status", "APPROVED"),
                    ],
                    button_text="Open Dashboard to Execute",
                    button_url=dashboard_url,
                    button_color="#059669",  # Emerald-600
                    footer="You can now execute this workflow from the dashboard."
                )
                
                send_email(
                    to=requestor_email,
                    subject=f"[Approved] Workflow Ready: {workflow.get('script_id', workflow_id)}",
                    html_body=html_content
                )
                logger.info(f"Approval notification sent to {requestor_email} for workflow {workflow_id}")
                
            except Exception as email_error:
                logger.error(f"Failed to send approval notification: {email_error}")
        
        return {"message": "Workflow fully approved", "workflow_id": workflow_id, "status": "approved"}

    db.add_audit(workflow_id=workflow_id, action="partial_approval", user=request.approver,
                 note=f"Approval {len(approvals)}/{workflow['required_approval_levels']}")

    return {
        "message": "Approval added",
        "workflow_id": workflow_id,
        "approvals": len(approvals),
        "required": workflow["required_approval_levels"]
    }


@router.post("/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    background_tasks: BackgroundTasks,
    request: Optional[ExecuteWorkflowRequest] = Body(default=None),
    user: dict = Depends(require_admin)
):
    """Execute an approved workflow (one-time only)"""
    db = get_db()

    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Check workflow status - only "approved" can be executed
    status = workflow.get("status")
    if status == "executed":
        raise HTTPException(status_code=400, detail="Workflow has already been executed")
    if status == "denied":
        raise HTTPException(status_code=400, detail="Workflow was denied")
    if status == "expired":
        raise HTTPException(status_code=400, detail="Workflow has expired")
    if status != "approved":
        raise HTTPException(status_code=400, detail=f"Workflow is not approved (status: {status})")

    script_id = workflow.get("script_id")
    if not script_id:
        raise HTTPException(status_code=400, detail="Workflow has no script")

    targets = workflow.get("targets") or []
    if not targets:
        raise HTTPException(status_code=400, detail="Workflow has no targets")

    # Get parameters - use request params, fall back to stored script_params
    stored_params = workflow.get("script_params") or {}
    exec_params = (request.parameters if request and request.parameters else stored_params)
    
    # Import and call scripts execution
    from controller.routes.scripts import ExecuteScriptRequest, execute_script

    exec_request = ExecuteScriptRequest(
        target_agents=targets,
        parameters=exec_params,
        environment=(request.environment if request and request.environment else {}),
        timeout=(request.timeout if request and request.timeout else None),
    )

    # Mark as executing before we start (prevents concurrent execution)
    db.update_workflow_status(workflow_id, "executing")
    
    try:
        result = await execute_script(
            script_id=script_id,
            request=exec_request,
            background_tasks=background_tasks,
            user=user
        )
        
        # Mark as executed after successful execution
        db.update_workflow_status(workflow_id, "executed")
        db.add_audit(workflow_id=workflow_id, action="executed", 
                     user=user.get("username", "unknown"), note="Workflow executed successfully")
        
        return {
            "message": "Workflow executed",
            "workflow_id": workflow_id,
            "status": "executed",
            "script_result": result
        }
        
    except Exception as e:
        # Mark as failed but don't allow re-execution
        db.update_workflow_status(workflow_id, "failed")
        db.add_audit(workflow_id=workflow_id, action="execution_failed",
                     user=user.get("username", "unknown"), note=str(e))
        raise


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    token: dict = Depends(verify_token)
):
    """Delete a workflow"""
    db = get_db()

    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    db.delete_workflow(workflow_id)
    logger.info(f"Workflow deleted: {workflow_id}")

    return {"message": "Workflow deleted", "workflow_id": workflow_id}


class DenyWorkflowRequest(BaseModel):
    denier: Optional[str] = None
    reason: Optional[str] = None


@router.post("/{workflow_id}/deny")
async def deny_workflow(
    workflow_id: str,
    request: DenyWorkflowRequest = Body(default=None),
    user: dict = Depends(require_approver)
):
    """Deny a pending workflow and notify requestor"""
    db = get_db()

    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if workflow["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot deny workflow with status: {workflow['status']}")

    denier = request.denier if request and request.denier else user.get("username", "unknown")
    reason = request.reason if request and request.reason else "Denied"
    
    db.update_workflow_status(workflow_id, "denied")
    db.add_audit(workflow_id=workflow_id, action="denied", user=denier, note=reason)
    
    logger.info(f"Workflow denied: {workflow_id} by {denier}")
    
    # Send denial notification to requestor
    requestor_email = workflow.get("requestor_email") or workflow.get("notify_email")
    if requestor_email:
        try:
            html_content = build_email_html(
                title="Workflow Denied",
                title_color="#be123c",  # Rose-700
                accent_color="#f43f5e",  # Rose-500
                message="Your workflow request has been denied.",
                details=[
                    ("Workflow ID", workflow_id),
                    ("Script", workflow.get("script_id", "N/A")),
                    ("Denied By", denier),
                    ("Reason", reason),
                    ("Status", "DENIED"),
                ],
                footer="If you believe this was in error, please contact the approver or submit a new workflow request."
            )
            
            send_email(
                to=requestor_email,
                subject=f"[Denied] Workflow Request: {workflow.get('script_id', workflow_id)}",
                html_body=html_content
            )
            logger.info(f"Denial notification sent to {requestor_email} for workflow {workflow_id}")
            
        except Exception as email_error:
            logger.error(f"Failed to send denial notification: {email_error}")

    return {
        "message": "Workflow denied",
        "workflow_id": workflow_id,
        "status": "denied",
        "denier": denier,
        "reason": reason
    }


@router.get("/{workflow_id}/audit")
async def get_workflow_audit(
    workflow_id: str,
    token: dict = Depends(verify_token)
):
    """Get audit logs for a workflow"""
    db = get_db()

    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    logs = db.get_audit_logs(workflow_id)

    return {
        "workflow_id": workflow_id,
        "audit_logs": logs,
        "count": len(logs)
    }


# =============================================================================
# Re-execution Approval Flow
# =============================================================================

@router.post("/{workflow_id}/reexec/request")
async def request_reexecution(
    workflow_id: str,
    payload: ReexecRequest,
    user: dict = Depends(verify_token)
):
    """Request approval for re-execution of a workflow"""
    db = get_db()
    wf = db.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    requester = user.get('username') or user.get('token_name') or 'unknown'
    requester_email = payload.requester_email or wf.get('notify_email')
    req = db.create_execution_approval_request(workflow_id, requester, requester_email, payload.note or "")

    approver_target = wf.get('notify_email') or requester_email
    if not approver_target:
        logger.warning("No approver email configured for workflow %s", workflow_id)
        return {"message": "Approval request created", "request": req}

    api_host = os.getenv("API_HOST", "http://localhost:8000")
    approve_url = f"{api_host}/api/workflows/{workflow_id}/reexec/approve?request_id={req['id']}"

    html_content = build_email_html(
        title="Re-execution Approval Required",
        title_color="#b45309",  # Amber-700
        accent_color="#f59e0b",  # Amber-500
        message=f"A request to re-execute workflow has been submitted by {requester}.",
        details=[
            ("Workflow ID", workflow_id),
            ("Requester", requester),
            ("Note", payload.note or "(none)"),
            ("Approve URL", approve_url),
        ],
        footer="POST to the Approve URL to approve this request."
    )

    send_email(approver_target, f"[Action Required] Re-execution approval for {workflow_id}", html_content)
    return {"message": "Approval request created and approver notified", "request": req}


@router.post("/{workflow_id}/reexec/approve")
async def approve_reexecution(
    workflow_id: str,
    payload: ApprovePayload,
    approver_jwt: dict = Depends(verify_approver_jwt)
):
    """Approve a re-execution request (requires approver JWT)"""
    db = get_db()
    req = db.get_execution_approval_request(payload.request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if req['workflow_id'] != workflow_id:
        raise HTTPException(status_code=400, detail="Mismatched workflow")
    if req['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Request not pending")

    approver = approver_jwt.get('sub') or approver_jwt.get('username') or 'approver'
    token_row = db.approve_execution_request(payload.request_id, approver)
    if not token_row:
        raise HTTPException(status_code=500, detail="Failed to approve request")

    requester_email = req.get('requester_email') or (db.get_workflow(workflow_id) or {}).get('notify_email')
    if requester_email:
        html_content = build_email_html(
            title="Re-execution Approved",
            title_color="#047857",  # Emerald-700
            accent_color="#10b981",  # Emerald-500
            message=f"Your re-execution request for workflow {workflow_id} has been approved.",
            details=[
                ("Workflow ID", workflow_id),
                ("Token Expires", str(token_row.get('expires_at', 'N/A'))),
                ("Token", token_row.get('token', 'N/A')),
            ],
            footer="Use this token to execute the workflow."
        )
        send_email(requester_email, f"[Approved] Execution token for {workflow_id}", html_content)

    return {"message": "Approved and token issued", "token_id": token_row.get('id')}
