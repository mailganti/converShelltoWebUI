# controller/emailer.py
"""
Email sending module for the Orchestration System.
Light theme - works reliably in ALL email clients including Outlook.
"""

import os
import subprocess
import logging
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Union
from datetime import datetime

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "orchestration@localhost")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "30"))
SENDMAIL_PATH = os.getenv("SENDMAIL_PATH", "/usr/sbin/sendmail")
EMAIL_DRY_RUN = os.getenv("EMAIL_DRY_RUN", "true").lower() == "true"


def build_email_html(
    title: str,
    title_color: str,
    accent_color: str,
    message: str,
    details: dict,
    button_text: str = None,
    button_url: str = None,
    button_color: str = "#0284c7",
    footer: str = None,
    preview_text: str = ""
) -> str:
    """
    Clean light-themed HTML email that works in ALL clients including Outlook.
    """
    rows = ""
    for i, (label, value) in enumerate(details.items()):
        clean_value = re.sub(r'<[^>]+>', '', str(value))
        row_bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        rows += f"""
        <tr>
            <td bgcolor="{row_bg}" style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#64748b;font-weight:600;width:160px;font-family:Arial,sans-serif;font-size:14px;">
                {label}
            </td>
            <td bgcolor="{row_bg}" style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#1e293b;font-family:Arial,sans-serif;font-size:14px;">
                {clean_value}
            </td>
        </tr>"""
    
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
<div style="display:none;font-size:1px;color:#f1f5f9;max-height:0;overflow:hidden;">{preview_text}</div>

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
        {rows}
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


# =============================================================================
# Email Templates
# =============================================================================

def build_approval_request_email(workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes, dashboard_url):
    return build_email_html(
        title="Workflow Approval Required",
        title_color="#b45309",  # Amber-700
        accent_color="#f59e0b",  # Amber-500
        message="A new workflow has been submitted and requires your approval.",
        details={
            "Workflow ID": workflow_id,
            "Requestor": requestor,
            "Requestor Email": requestor_email or "N/A",
            "Script": script_id,
            "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
            "Reason": reason or "No reason provided",
            "Expires In": f"{ttl_minutes} minutes"
        },
        button_text="Open Dashboard to Approve",
        button_url=dashboard_url,
        button_color="#0284c7",  # Sky-600
        footer=f"Requested by: {requestor}",
        preview_text=f"Workflow approval needed for {script_id}"
    )


def build_workflow_approved_email(workflow_id, script_id, targets, approved_by, approval_notes=None, dashboard_url=None):
    return build_email_html(
        title="Workflow Approved",
        title_color="#047857",  # Emerald-700
        accent_color="#10b981",  # Emerald-500
        message="Your workflow request has been approved and is ready for execution.",
        details={
            "Workflow ID": workflow_id,
            "Script": script_id,
            "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
            "Approved By": approved_by,
            "Notes": approval_notes or "No additional notes"
        },
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#059669",  # Emerald-600
        footer="You can now execute this workflow from the dashboard.",
        preview_text=f"Workflow {workflow_id} has been approved"
    )


def build_workflow_denied_email(workflow_id, script_id, targets, denied_by, denial_reason=None, dashboard_url=None):
    return build_email_html(
        title="Workflow Denied",
        title_color="#be123c",  # Rose-700
        accent_color="#f43f5e",  # Rose-500
        message="Your workflow request has been denied.",
        details={
            "Workflow ID": workflow_id,
            "Script": script_id,
            "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
            "Denied By": denied_by,
            "Reason": denial_reason or "No reason provided"
        },
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#e11d48",  # Rose-600
        footer="Please contact the approver if you have questions.",
        preview_text=f"Workflow {workflow_id} has been denied"
    )


def build_workflow_executed_email(workflow_id, script_id, targets, executed_by, exit_codes=None, dashboard_url=None):
    results = "Execution completed"
    if exit_codes:
        result_lines = []
        for agent, code in exit_codes.items():
            status = "Success" if code == 0 else f"Failed (exit: {code})"
            result_lines.append(f"{agent}: {status}")
        results = "; ".join(result_lines)
    
    return build_email_html(
        title="Workflow Executed",
        title_color="#0369a1",  # Sky-700
        accent_color="#0ea5e9",  # Sky-500
        message="Your approved workflow has been executed.",
        details={
            "Workflow ID": workflow_id,
            "Script": script_id,
            "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
            "Executed By": executed_by,
            "Results": results
        },
        button_text="View Details" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#0284c7",  # Sky-600
        footer="Check the dashboard for full execution logs.",
        preview_text=f"Workflow {workflow_id} has been executed"
    )


# =============================================================================
# Send Email
# =============================================================================

def send_email(
    to: Union[str, List[str]],
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    from_addr: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
) -> bool:
    """Send HTML email."""
    
    if isinstance(to, str):
        to = [to]
    if isinstance(cc, str):
        cc = [cc]
    
    to = [addr.strip() for addr in to if addr and addr.strip()]
    cc = [addr.strip() for addr in (cc or []) if addr and addr.strip()]
    
    if not to:
        logger.warning("No recipients")
        return False
    
    sender = from_addr or SMTP_FROM
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    
    if not text_body:
        text_body = re.sub(r'<[^>]+>', '', html_body)
        text_body = re.sub(r'\s+', ' ', text_body).strip()
    
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    if EMAIL_DRY_RUN:
        logger.info(f"[DRY RUN] To: {', '.join(to)}, Subject: {subject}")
        return True
    
    try:
        if os.path.exists(SENDMAIL_PATH):
            proc = subprocess.Popen([SENDMAIL_PATH, "-t", "-oi"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, stderr = proc.communicate(msg.as_string().encode('utf-8'))
            if proc.returncode == 0:
                logger.info(f"Email sent to {', '.join(to)}")
                return True
            logger.error(f"sendmail failed: {stderr.decode()}")
            return False
        else:
            import smtplib, ssl
            ctx = ssl.create_default_context()
            if SMTP_USE_SSL:
                srv = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT, context=ctx)
            else:
                srv = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT)
                if SMTP_USE_TLS:
                    srv.starttls(context=ctx)
            if SMTP_USER and SMTP_PASSWORD:
                srv.login(SMTP_USER, SMTP_PASSWORD)
            srv.sendmail(sender, to + cc, msg.as_string())
            srv.quit()
            logger.info(f"Email sent via SMTP to {', '.join(to)}")
            return True
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False


# =============================================================================
# Convenience Functions
# =============================================================================

def send_approval_request(approver_email, workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes=60, dashboard_url=None):
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    html = build_approval_request_email(workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes, dashboard)
    return send_email(to=approver_email, subject=f"[Action Required] Workflow Approval: {script_id} - {requestor}", html_body=html)

def send_workflow_approved(requestor_email, workflow_id, script_id, targets, approved_by, approval_notes=None, dashboard_url=None):
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    html = build_workflow_approved_email(workflow_id, script_id, targets, approved_by, approval_notes, dashboard)
    return send_email(to=requestor_email, subject=f"[Approved] Workflow {workflow_id}: {script_id}", html_body=html)

def send_workflow_denied(requestor_email, workflow_id, script_id, targets, denied_by, denial_reason=None, dashboard_url=None):
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    html = build_workflow_denied_email(workflow_id, script_id, targets, denied_by, denial_reason, dashboard)
    return send_email(to=requestor_email, subject=f"[Denied] Workflow {workflow_id}: {script_id}", html_body=html)

def send_workflow_executed(requestor_email, workflow_id, script_id, targets, executed_by, exit_codes=None, dashboard_url=None):
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    html = build_workflow_executed_email(workflow_id, script_id, targets, executed_by, exit_codes, dashboard)
    return send_email(to=requestor_email, subject=f"[Executed] Workflow {workflow_id}: {script_id}", html_body=html)
