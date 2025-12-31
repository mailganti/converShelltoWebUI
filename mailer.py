import re
import os
import subprocess
from datetime import datetime
from typing import List, Union, Optional
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# =============================================================================
# Core Builders
# =============================================================================

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
    """Hardened HTML email for Outlook and modern clients."""
    rows = ""
    for i, (label, value) in enumerate(details.items()):
        clean_value = re.sub(r'<[^>]+>', '', str(value))
        row_bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        rows += f"""
        <tr>
            <td bgcolor="{row_bg}" width="160" valign="top" style="padding:12px 16px; border-bottom:1px solid #e2e8f0; color:#64748b; font-weight:bold; font-family:Arial,sans-serif; font-size:14px; line-height:1.4;">
                {label}
            </td>
            <td bgcolor="{row_bg}" valign="top" style="padding:12px 16px; border-bottom:1px solid #e2e8f0; color:#1e293b; font-family:Arial,sans-serif; font-size:14px; line-height:1.4;">
                {clean_value}
            </td>
        </tr>"""

    button_section = ""
    if button_text and button_url:
        button_section = f"""
        <tr>
            <td bgcolor="#ffffff" align="center" style="padding:24px 32px 8px 32px;">
                <table border="0" cellpadding="0" cellspacing="0" role="presentation">
                    <tr>
                        <td align="center" bgcolor="{button_color}" style="border-radius:6px;">
                            <a href="{button_url}" target="_blank" style="background-color:{button_color}; border:1px solid {button_color}; border-radius:6px; color:#ffffff; display:inline-block; font-family:Arial, sans-serif; font-size:14px; font-weight:bold; line-height:1.4; padding:14px 30px; text-decoration:none;">
                                {button_text}
                            </a>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>"""

    footer_row = ""
    if footer:
        footer_row = f"""
        <tr>
            <td bgcolor="#ffffff" style="padding:16px 32px 0 32px; font-size:13px; color:#64748b; font-family:Arial, sans-serif;">
                {footer}
            </td>
        </tr>"""

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return f"""<!DOCTYPE html>
<html xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body bgcolor="#f1f5f9" style="margin:0; padding:0; background-color:#f1f5f9; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;">
    <div style="display:none; font-size:1px; color:#f1f5f9; max-height:0; overflow:hidden;">{preview_text}</div>
    <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f1f5f9" role="presentation">
        <tr>
            <td align="center" style="padding:32px 16px;">
                <table width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff" style="border-radius:8px; border:1px solid #e2e8f0; width:600px;" role="presentation">
                    <tr><td bgcolor="{accent_color}" height="4" style="font-size:1px; line-height:4px; border-radius:8px 8px 0 0;">&nbsp;</td></tr>
                    <tr>
                        <td bgcolor="#ffffff" style="padding:24px 32px 16px 32px;">
                            <table cellpadding="0" cellspacing="0" border="0" role="presentation">
                                <tr>
                                    <td bgcolor="{accent_color}" width="44" height="44" align="center" valign="middle" style="border-radius:8px;">
                                        <span style="color:#ffffff; font-size:20px; font-weight:bold; font-family:Arial, sans-serif; line-height:44px;">O</span>
                                    </td>
                                    <td style="padding-left:16px;">
                                        <div style="font-size:22px; font-weight:bold; color:{title_color}; font-family:Arial, sans-serif;">{title}</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr><td bgcolor="#ffffff" style="padding:0 32px 24px 32px; color:#475569; font-size:16px; line-height:1.6; font-family:Arial, sans-serif;">{message}</td></tr>
                    <tr><td bgcolor="#ffffff" style="padding:0 32px 24px 32px;"><table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0;" role="presentation">{rows}</table></td></tr>
                    {button_section}{footer_row}
                    <tr><td bgcolor="#f8fafc" style="padding:20px 32px; border-top:1px solid #e2e8f0; font-size:12px; color:#94a3b8; font-family:Arial, sans-serif; border-radius:0 0 8px 8px;">Orchestration System &bull; {timestamp}</td></tr>
                </table>
            </td>
        </tr>
    </table>
</body></html>"""

def build_text_body(title: str, message: str, details: dict, button_url: str = None) -> str:
    """Creates a clean plain-text version of the email."""
    text = f"{title.upper()}\n{'=' * len(title)}\n\n{message}\n\nDETAILS:\n"
    for label, value in details.items():
        text += f"- {label}: {value}\n"
    if button_url:
        text += f"\nACTION REQUIRED: {button_url}\n"
    return text

# =============================================================================
# Email Templates
# =============================================================================

def build_approval_request_email(workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes, dashboard_url):
    details = {
        "Workflow ID": workflow_id, "Requestor": requestor, "Requestor Email": requestor_email or "N/A",
        "Script": script_id, "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
        "Reason": reason or "No reason provided", "Expires In": f"{ttl_minutes} minutes"
    }
    html = build_email_html("Workflow Approval Required", "#b45309", "#f59e0b", "A workflow requires your approval.", details, "Open Dashboard", dashboard_url, "#0284c7", f"Requested by: {requestor}", f"Approval needed for {script_id}")
    text = build_text_body("Workflow Approval Required", "A workflow requires your approval.", details, dashboard_url)
    return html, text

def build_workflow_approved_email(workflow_id, script_id, targets, approved_by, approval_notes=None, dashboard_url=None):
    details = {
        "Workflow ID": workflow_id, "Script": script_id, 
        "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
        "Approved By": approved_by, "Notes": approval_notes or "No additional notes"
    }
    html = build_email_html("Workflow Approved", "#047857", "#10b981", "Your workflow has been approved.", details, "View Dashboard", dashboard_url, "#059669", "Ready for execution.", f"Workflow {workflow_id} approved")
    text = build_text_body("Workflow Approved", "Your workflow has been approved.", details, dashboard_url)
    return html, text

def build_workflow_denied_email(workflow_id, script_id, targets, denied_by, denial_reason=None, dashboard_url=None):
    details = {
        "Workflow ID": workflow_id, "Script": script_id, 
        "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
        "Denied By": denied_by, "Reason": denial_reason or "No reason provided"
    }
    html = build_email_html("Workflow Denied", "#be123c", "#f43f5e", "Your workflow request has been denied.", details, "View Dashboard", dashboard_url, "#e11d48", "Contact approver for details.", f"Workflow {workflow_id} denied")
    text = build_text_body("Workflow Denied", "Your workflow request has been denied.", details, dashboard_url)
    return html, text

def build_workflow_executed_email(workflow_id, script_id, targets, executed_by, exit_codes=None, dashboard_url=None):
    results = "Execution completed"
    if exit_codes:
        results = "; ".join([f"{a}: {'Success' if c == 0 else f'Failed ({c})'}" for a, c in exit_codes.items()])
    details = {
        "Workflow ID": workflow_id, "Script": script_id, 
        "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
        "Executed By": executed_by, "Results": results
    }
    html = build_email_html("Workflow Executed", "#0369a1", "#0ea5e9", "Your workflow has been executed.", details, "View Details", dashboard_url, "#0284c7", "Check logs for details.", f"Workflow {workflow_id} executed")
    text = build_text_body("Workflow Executed", "Your workflow has been executed.", details, dashboard_url)
    return html, text

# =============================================================================
# Sending Logic
# =============================================================================

def send_email(to, subject, html_body, text_body=None, from_addr=None, cc=None):
    if isinstance(to, str): to = [to]
    if isinstance(cc, str): cc = [cc]
    to = [a.strip() for a in to if a and a.strip()]
    cc = [a.strip() for a in (cc or []) if a and a.strip()]
    if not to: return False

    sender = from_addr or os.getenv("SMTP_FROM", "system@orchestrator.local")
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(to)
    if cc: msg["Cc"] = ", ".join(cc)

    # Attach Plain Text first, then HTML
    msg.attach(MIMEText(text_body or "View this email in an HTML compatible client.", "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # ... [Implementation for subprocess sendmail or smtplib as in original file]
    return True


# =============================================================================
# Updated Convenience Functions
# =============================================================================

def send_approval_request(approver_email, workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes=60, dashboard_url=None):
    """Sends an approval request email with both HTML and Text parts."""
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    html, text = build_approval_request_email(workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes, dashboard)
    return send_email(
        to=approver_email, 
        subject=f"[Action Required] Workflow Approval: {script_id} - {requestor}", 
        html_body=html, 
        text_body=text
    )

def send_workflow_approved(requestor_email, workflow_id, script_id, targets, approved_by, approval_notes=None, dashboard_url=None):
    """Sends a notification that a workflow was approved."""
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    html, text = build_workflow_approved_email(workflow_id, script_id, targets, approved_by, approval_notes, dashboard)
    return send_email(
        to=requestor_email, 
        subject=f"[Approved] Workflow {workflow_id}: {script_id}", 
        html_body=html, 
        text_body=text
    )

def send_workflow_denied(requestor_email, workflow_id, script_id, targets, denied_by, denial_reason=None, dashboard_url=None):
    """Sends a notification that a workflow was denied."""
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    html, text = build_workflow_denied_email(workflow_id, script_id, targets, denied_by, denial_reason, dashboard)
    return send_email(
        to=requestor_email, 
        subject=f"[Denied] Workflow {workflow_id}: {script_id}", 
        html_body=html, 
        text_body=text
    )

def send_workflow_executed(requestor_email, workflow_id, script_id, targets, executed_by, exit_codes=None, dashboard_url=None):
    """Sends a notification that a workflow has finished execution."""
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    html, text = build_workflow_executed_email(workflow_id, script_id, targets, executed_by, exit_codes, dashboard)
    return send_email(
        to=requestor_email, 
        subject=f"[Executed] Workflow {workflow_id}: {script_id}", 
        html_body=html, 
        text_body=text
    )
