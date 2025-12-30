# controller/emailer.py
"""
Email sending module for the Orchestration System.
Styled to match the dark dashboard theme.
Supports SMTP and sendmail.
"""

import os
import subprocess
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Union

logger = logging.getLogger(__name__)

# SMTP Configuration from environment
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "orchestration@localhost")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "30"))

# Path to sendmail (common locations)
SENDMAIL_PATH = os.getenv("SENDMAIL_PATH", "/usr/sbin/sendmail")

# For testing/development - log emails instead of sending
EMAIL_DRY_RUN = os.getenv("EMAIL_DRY_RUN", "true").lower() == "true"

# Log configuration at startup
logger.info(f"[EMAILER CONFIG] SMTP_HOST={SMTP_HOST}, SMTP_PORT={SMTP_PORT}, SMTP_FROM={SMTP_FROM}")
logger.info(f"[EMAILER CONFIG] EMAIL_DRY_RUN={EMAIL_DRY_RUN}, SENDMAIL_PATH={SENDMAIL_PATH}")


# =============================================================================
# Email Template - Dark Theme (matches dashboard CSS)
# =============================================================================

def build_email_html(
    title: str,
    title_color: str = "#38bdf8",  # sky-400
    message: str = "",
    details: dict = None,
    button_text: str = None,
    button_url: str = None,
    button_color: str = "#0ea5e9",  # sky-500
    footer: str = None
) -> str:
    """
    Build HTML email with dark theme matching dashboard.
    
    Colors from dashboard:
    - Background: #020617 (bg-base)
    - Panel: #0f172a (slightly lighter)
    - Border: #334155 (slate-700)
    - Text primary: #f1f5f9
    - Text secondary: #94a3b8
    - Text muted: #64748b
    - Sky accent: #38bdf8, #0ea5e9
    - Emerald (success): #a7f3d0, #10b981
    - Amber (warning): #fde68a, #f59e0b
    - Rose (error): #fecaca, #f43f5e
    """
    
    # Build details table rows
    details_html = ""
    if details:
        rows = []
        for i, (label, value) in enumerate(details.items()):
            bg = "#0f172a" if i % 2 == 0 else "#020617"
            rows.append(f'''
                <tr style="background: {bg};">
                    <td style="padding: 12px 16px; border: 1px solid #334155; color: #94a3b8; font-weight: 600; width: 140px;">{label}</td>
                    <td style="padding: 12px 16px; border: 1px solid #334155; color: #f1f5f9;">{value}</td>
                </tr>
            ''')
        details_html = f'''
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; border-radius: 8px; overflow: hidden;">
                {''.join(rows)}
            </table>
        '''
    
    # Build button - email-client compatible (no gradients, table-based)
    button_html = ""
    if button_text and button_url:
        # Use table-based button for maximum email client compatibility
        # Solid color since gradients don't work in most email clients
        btn_bg = "#0ea5e9"  # sky-500
        if "Deny" in button_text or "denied" in title.lower():
            btn_bg = "#f43f5e"  # rose
        elif "Approve" in button_text or "approved" in title.lower():
            btn_bg = "#10b981"  # emerald
            
        button_html = f'''
            <div style="margin: 24px 0; text-align: center;">
                <!--[if mso]>
                <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="{button_url}" style="height:40px;v-text-anchor:middle;width:200px;" arcsize="50%" strokecolor="{btn_bg}" fillcolor="{btn_bg}">
                <w:anchorlock/>
                <center style="color:#020617;font-family:sans-serif;font-size:12px;font-weight:bold;">{button_text}</center>
                </v:roundrect>
                <![endif]-->
                <!--[if !mso]><!-->
                <table border="0" cellspacing="0" cellpadding="0" style="margin: 0 auto;">
                    <tr>
                        <td align="center" bgcolor="{btn_bg}" style="
                            background-color: {btn_bg};
                            border-radius: 50px;
                            padding: 0;
                        ">
                            <a href="{button_url}" target="_blank" style="
                                display: inline-block;
                                padding: 12px 28px;
                                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                                font-size: 13px;
                                font-weight: 600;
                                color: #020617;
                                text-decoration: none;
                                border-radius: 50px;
                                background-color: {btn_bg};
                            ">{button_text}</a>
                        </td>
                    </tr>
                </table>
                <!--<![endif]-->
            </div>
        '''
    
    # Build footer
    footer_html = ""
    if footer:
        footer_html = f'''
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #334155; color: #64748b; font-size: 11px; text-align: center;">
                {footer}
            </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background: #020617; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <!-- Header -->
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="
                    display: inline-block;
                    width: 48px;
                    height: 48px;
                    border-radius: 50%;
                    background: radial-gradient(circle at 25% 25%, #38bdf8, #0f172a 60%, #020617 100%);
                    box-shadow: 0 0 0 1px rgba(56,189,248,0.6), 0 14px 30px rgba(8,47,73,0.8);
                    line-height: 48px;
                    font-size: 14px;
                    font-weight: 700;
                    letter-spacing: 0.1em;
                    color: white;
                ">ORC</div>
                <div style="margin-top: 12px; font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.15em;">
                    Orchestration System
                </div>
            </div>
            
            <!-- Main Panel -->
            <div style="
                background: radial-gradient(circle at 0 0, rgba(148,163,184,0.06), transparent 50%), #0f172a;
                border: 1px solid #334155;
                border-radius: 16px;
                padding: 28px;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            ">
                <!-- Title -->
                <h1 style="
                    margin: 0 0 16px 0;
                    font-size: 22px;
                    font-weight: 600;
                    color: {title_color};
                ">{title}</h1>
                
                <!-- Message -->
                <p style="margin: 0 0 20px 0; color: #94a3b8; font-size: 14px; line-height: 1.6;">
                    {message}
                </p>
                
                <!-- Details Table -->
                {details_html}
                
                <!-- Button -->
                {button_html}
                
                <!-- Footer -->
                {footer_html}
            </div>
            
            <!-- Email Footer -->
            <div style="text-align: center; margin-top: 20px; color: #475569; font-size: 10px;">
                This is an automated message from the Orchestration System.<br>
                Please do not reply to this email.
            </div>
        </div>
    </body>
    </html>
    '''


# =============================================================================
# Pre-built Email Templates
# =============================================================================

def build_approval_request_email(
    workflow_id: str,
    script_id: str,
    requestor: str,
    requestor_email: str,
    targets: List[str],
    reason: str,
    ttl_minutes: int,
    dashboard_url: str
) -> str:
    """Build approval request email"""
    requestor_display = f'<a href="mailto:{requestor_email}" style="color: #38bdf8;">{requestor}</a>' if requestor_email else requestor
    
    return build_email_html(
        title="⏳ Workflow Approval Required",
        title_color="#fde68a",  # amber for pending/action required
        message="A new workflow has been submitted and requires your approval.",
        details={
            "Workflow ID": f'<code style="background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-family: monospace;">{workflow_id}</code>',
            "Requestor": requestor_display,
            "Script": f'<code style="background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #f1f5f9; font-family: monospace;">{script_id}</code>',
            "Target Agents": ', '.join(targets),
            "Reason": reason or "No reason provided",
            "Expires In": f'<span style="color: #fde68a;">{ttl_minutes} minutes</span>'
        },
        button_text="Open Dashboard to Review",
        button_url=dashboard_url,
        button_color="#0ea5e9",  # sky blue
        footer=f"Requested by: {requestor}"
    )


def build_workflow_approved_email(
    workflow_id: str,
    script_id: str,
    targets: List[str],
    approved_by: str,
    approval_notes: str = None,
    dashboard_url: str = None
) -> str:
    """Build workflow approved notification email"""
    notes = approval_notes or "No additional notes"
    
    return build_email_html(
        title="✓ Workflow Approved",
        title_color="#a7f3d0",  # emerald for success
        message="Your workflow request has been approved and is ready for execution.",
        details={
            "Workflow ID": f'<code style="background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-family: monospace;">{workflow_id}</code>',
            "Script": f'<code style="background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #f1f5f9; font-family: monospace;">{script_id}</code>',
            "Target Agents": ', '.join(targets),
            "Approved By": f'<span style="color: #a7f3d0;">{approved_by}</span>',
            "Notes": notes
        },
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#10b981",  # emerald
        footer="You can now execute this workflow from the dashboard."
    )


def build_workflow_denied_email(
    workflow_id: str,
    script_id: str,
    targets: List[str],
    denied_by: str,
    denial_reason: str = None,
    dashboard_url: str = None
) -> str:
    """Build workflow denied notification email"""
    reason = denial_reason or "No reason provided"
    
    return build_email_html(
        title="✗ Workflow Denied",
        title_color="#fecaca",  # rose for error/denial
        message="Your workflow request has been denied.",
        details={
            "Workflow ID": f'<code style="background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-family: monospace;">{workflow_id}</code>',
            "Script": f'<code style="background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #f1f5f9; font-family: monospace;">{script_id}</code>',
            "Target Agents": ', '.join(targets),
            "Denied By": f'<span style="color: #fecaca;">{denied_by}</span>',
            "Reason": f'<span style="color: #fecaca;">{reason}</span>'
        },
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#f43f5e",  # rose
        footer="Please contact the approver if you have questions about this decision."
    )


def build_workflow_executed_email(
    workflow_id: str,
    script_id: str,
    targets: List[str],
    executed_by: str,
    exit_codes: dict = None,
    dashboard_url: str = None
) -> str:
    """Build workflow executed notification email"""
    
    # Build execution results
    results_html = ""
    if exit_codes:
        for agent, code in exit_codes.items():
            status_color = "#a7f3d0" if code == 0 else "#fecaca"
            status_text = "Success" if code == 0 else f"Failed (exit: {code})"
            results_html += f'<span style="color: {status_color};">{agent}: {status_text}</span><br>'
    else:
        results_html = "Execution completed"
    
    return build_email_html(
        title="⚡ Workflow Executed",
        title_color="#38bdf8",  # sky blue
        message="Your approved workflow has been executed.",
        details={
            "Workflow ID": f'<code style="background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #38bdf8; font-family: monospace;">{workflow_id}</code>',
            "Script": f'<code style="background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #f1f5f9; font-family: monospace;">{script_id}</code>',
            "Target Agents": ', '.join(targets),
            "Executed By": executed_by,
            "Results": results_html
        },
        button_text="View Details" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#0ea5e9",
        footer="Check the dashboard for full execution logs."
    )


# =============================================================================
# Send Email Function
# =============================================================================

def send_email(
    to: Union[str, List[str]],
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    from_addr: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
) -> bool:
    """
    Send an email with HTML content.
    Uses sendmail if available, otherwise logs (dry run).
    """
    import re
    
    # Normalize recipients to lists
    if isinstance(to, str):
        to = [to]
    if isinstance(cc, str):
        cc = [cc]
    
    # Filter empty addresses
    to = [addr.strip() for addr in to if addr and addr.strip()]
    cc = [addr.strip() for addr in (cc or []) if addr and addr.strip()]
    
    if not to:
        logger.warning("No recipients specified, skipping email")
        return False
    
    sender = from_addr or SMTP_FROM
    
    # Build message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    
    if cc:
        msg["Cc"] = ", ".join(cc)
    
    # Add plain text part (fallback)
    if not text_body:
        # Strip HTML for plain text version
        text_body = re.sub(r'<[^>]+>', '', html_body)
        text_body = re.sub(r'\s+', ' ', text_body).strip()
    
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    # All recipients
    all_recipients = to + cc
    
    # Dry run mode - just log
    if EMAIL_DRY_RUN:
        logger.info(f"[DRY RUN] Email would be sent:")
        logger.info(f"  To: {', '.join(to)}")
        logger.info(f"  Subject: {subject}")
        logger.info(f"  From: {sender}")
        return True
    
    try:
        # Try sendmail first
        if os.path.exists(SENDMAIL_PATH):
            cmd = [SENDMAIL_PATH, "-t", "-oi"]
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate(msg.as_string().encode('utf-8'))
            
            if proc.returncode == 0:
                logger.info(f"Email sent via sendmail to {', '.join(to)}: {subject}")
                return True
            else:
                logger.error(f"sendmail failed: {stderr.decode('utf-8')}")
                return False
        else:
            logger.warning(f"sendmail not found at {SENDMAIL_PATH}")
            
            # Try SMTP as fallback
            import smtplib
            import ssl
            
            context = ssl.create_default_context()
            
            if SMTP_USE_SSL:
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT, context=context)
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT)
                if SMTP_USE_TLS:
                    server.starttls(context=context)
            
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            
            server.sendmail(sender, all_recipients, msg.as_string())
            server.quit()
            
            logger.info(f"Email sent via SMTP to {', '.join(to)}: {subject}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


# =============================================================================
# Convenience Functions
# =============================================================================

def send_approval_request(
    approver_email: str,
    workflow_id: str,
    script_id: str,
    requestor: str,
    requestor_email: str,
    targets: List[str],
    reason: str,
    ttl_minutes: int = 60,
    dashboard_url: str = None
) -> bool:
    """Send approval request email to approver"""
    html = build_approval_request_email(
        workflow_id=workflow_id,
        script_id=script_id,
        requestor=requestor,
        requestor_email=requestor_email,
        targets=targets,
        reason=reason,
        ttl_minutes=ttl_minutes,
        dashboard_url=dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    )
    
    return send_email(
        to=approver_email,
        subject=f"[Action Required] Workflow Approval: {script_id} - {requestor}",
        html_body=html
    )


def send_workflow_approved(
    requestor_email: str,
    workflow_id: str,
    script_id: str,
    targets: List[str],
    approved_by: str,
    approval_notes: str = None,
    dashboard_url: str = None
) -> bool:
    """Send workflow approved notification to requestor"""
    html = build_workflow_approved_email(
        workflow_id=workflow_id,
        script_id=script_id,
        targets=targets,
        approved_by=approved_by,
        approval_notes=approval_notes,
        dashboard_url=dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    )
    
    return send_email(
        to=requestor_email,
        subject=f"[Approved] Workflow {workflow_id}: {script_id}",
        html_body=html
    )


def send_workflow_denied(
    requestor_email: str,
    workflow_id: str,
    script_id: str,
    targets: List[str],
    denied_by: str,
    denial_reason: str = None,
    dashboard_url: str = None
) -> bool:
    """Send workflow denied notification to requestor"""
    html = build_workflow_denied_email(
        workflow_id=workflow_id,
        script_id=script_id,
        targets=targets,
        denied_by=denied_by,
        denial_reason=denial_reason,
        dashboard_url=dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    )
    
    return send_email(
        to=requestor_email,
        subject=f"[Denied] Workflow {workflow_id}: {script_id}",
        html_body=html
    )


def send_workflow_executed(
    requestor_email: str,
    workflow_id: str,
    script_id: str,
    targets: List[str],
    executed_by: str,
    exit_codes: dict = None,
    dashboard_url: str = None
) -> bool:
    """Send workflow executed notification to requestor"""
    html = build_workflow_executed_email(
        workflow_id=workflow_id,
        script_id=script_id,
        targets=targets,
        executed_by=executed_by,
        exit_codes=exit_codes,
        dashboard_url=dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    )
    
    return send_email(
        to=requestor_email,
        subject=f"[Executed] Workflow {workflow_id}: {script_id}",
        html_body=html
    )
