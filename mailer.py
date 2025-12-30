def build_styled_html_attachment(
    title: str,
    title_color: str,
    message: str,
    details: dict,
    button_text: str = None,
    button_url: str = None,
    button_color: str = "#0ea5e9",
    footer: str = None
) -> str:
    """
    Generate a fully styled HTML file for attachment.
    Opens in browser with all CSS working perfectly.
    """
    
    # Build details rows
    rows = ""
    for i, (label, value) in enumerate(details.items()):
        row_bg = "#1e293b" if i % 2 == 0 else "#0f172a"
        rows += f'''
            <tr style="background: {row_bg};">
                <td style="padding: 12px 16px; border-bottom: 1px solid #334155; color: #94a3b8; font-weight: 600; width: 160px;">{label}</td>
                <td style="padding: 12px 16px; border-bottom: 1px solid #334155; color: #f1f5f9;">{value}</td>
            </tr>'''
    
    # Build button
    button_html = ""
    if button_text and button_url:
        button_html = f'''
            <div style="margin: 28px 0; text-align: center;">
                <a href="{button_url}" target="_blank" style="
                    display: inline-block;
                    background: linear-gradient(to top right, #38bdf8, {button_color});
                    color: #020617;
                    padding: 12px 32px;
                    text-decoration: none;
                    border-radius: 9999px;
                    font-weight: 600;
                    font-size: 14px;
                    box-shadow: 0 0 20px rgba(56, 189, 248, 0.3);
                ">{button_text}</a>
            </div>'''
    
    # Footer
    footer_html = f'<p style="color: #64748b; font-size: 12px; margin-top: 24px;">{footer}</p>' if footer else ""
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Orchestration System</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(180deg, #0f172a 0%, #020617 50%, #020617 100%);
            color: #f1f5f9;
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 650px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 32px;
        }}
        .logo {{
            display: inline-block;
            width: 56px;
            height: 56px;
            border-radius: 16px;
            background: radial-gradient(circle at 25% 25%, #38bdf8, #0f172a 60%, #020617 100%);
            box-shadow: 0 0 0 1px rgba(56,189,248,0.6), 0 14px 30px rgba(8,47,73,0.8);
            line-height: 56px;
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 0.1em;
            color: white;
            margin-bottom: 12px;
        }}
        .header-text {{
            color: #94a3b8;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.2em;
        }}
        .card {{
            background: radial-gradient(circle at 0 0, rgba(148,163,184,0.08), transparent 50%), #020617;
            border: 1px solid rgba(100, 116, 139, 0.5);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }}
        .card-header {{
            background: rgba(30, 41, 59, 0.8);
            padding: 20px 24px;
            border-bottom: 1px solid rgba(100, 116, 139, 0.4);
        }}
        .card-title {{
            font-size: 20px;
            font-weight: 600;
            color: {title_color};
        }}
        .card-body {{
            padding: 24px;
        }}
        .message {{
            color: #cbd5e1;
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 24px;
        }}
        .details-table {{
            width: 100%;
            border-collapse: collapse;
            border-radius: 8px;
            overflow: hidden;
        }}
        .footer {{
            text-align: center;
            padding: 24px;
            color: #64748b;
            font-size: 11px;
            border-top: 1px solid rgba(100, 116, 139, 0.3);
            margin-top: 32px;
        }}
        a {{ color: #38bdf8; }}
        code {{
            background: #1e293b;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Consolas', 'Monaco', monospace;
            color: #38bdf8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">ORC</div>
            <div class="header-text">Orchestration System</div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <h1 class="card-title">{title}</h1>
            </div>
            <div class="card-body">
                <p class="message">{message}</p>
                
                <table class="details-table">
                    {rows}
                </table>
                
                {button_html}
                
                {footer_html}
            </div>
        </div>
        
        <div class="footer">
            This is an automated message from the Orchestration System.<br>
            Generated: {timestamp}
        </div>
    </div>
</body>
</html>'''


# =============================================================================
# Simple Plain Text Email Body
# =============================================================================

def build_simple_email_body(title: str, message: str, details: dict, footer: str = None) -> str:
    """Simple HTML email body - directs user to open attachment."""
    rows = ""
    for label, value in details.items():
        clean_value = re.sub(r'<[^>]+>', '', str(value))
        rows += f"<tr><td style='padding:8px;border-bottom:1px solid #ddd;color:#333;'><b>{label}:</b></td><td style='padding:8px;border-bottom:1px solid #ddd;color:#555;'>{clean_value}</td></tr>"
    
    footer_html = f"<p style='color:#666;font-size:12px;margin-top:20px;'>{footer}</p>" if footer else ""
    
    return f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;margin:0;padding:20px;background:#f5f5f5;">
<div style="max-width:600px;margin:0 auto;background:#fff;padding:24px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
<h2 style="color:#1e293b;margin:0 0 16px 0;">{title}</h2>
<p style="color:#64748b;margin:0 0 20px 0;">{message}</p>
<table style="border-collapse:collapse;width:100%;">
{rows}
</table>
<div style="margin:24px 0;padding:16px;background:#e0f2fe;border-radius:6px;text-align:center;">
<p style="margin:0;color:#0369a1;font-weight:600;">📎 Open the attached HTML file for the styled version</p>
<p style="margin:8px 0 0 0;color:#0284c7;font-size:13px;">Double-click the .html attachment to view in your browser</p>
</div>
{footer_html}
<hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0;">
<p style="color:#9ca3af;font-size:11px;margin:0;">This is an automated message from the Orchestration System.</p>
</div>
</body>
</html>'''


# =============================================================================
# Email Templates
# =============================================================================

def build_approval_request_email(workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes, dashboard_url):
    details = {
        "Workflow ID": f'<code>{workflow_id}</code>',
        "Requestor": requestor,
        "Requestor Email": f'<a href="mailto:{requestor_email}">{requestor_email}</a>' if requestor_email else "N/A",
        "Script": f'<code>{script_id}</code>',
        "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
        "Reason": reason or "No reason provided",
        "Expires In": f'{ttl_minutes} minutes',
        "Dashboard": f'<a href="{dashboard_url}">{dashboard_url}</a>'
    }
    
    title = "⏳ Workflow Approval Required"
    message = "A new workflow has been submitted and requires your approval."
    footer = f"Requested by: {requestor}"
    
    body_html = build_simple_email_body(title, message, details, footer)
    attachment_html = build_styled_html_attachment(
        title, "#fde68a", message, details,
        button_text="Open Dashboard to Approve",
        button_url=dashboard_url,
        button_color="#0ea5e9",
        footer=footer
    )
    
    return body_html, attachment_html, f"workflow_approval_{workflow_id}.html"


def build_workflow_approved_email(workflow_id, script_id, targets, approved_by, approval_notes=None, dashboard_url=None):
    details = {
        "Workflow ID": f'<code>{workflow_id}</code>',
        "Script": f'<code>{script_id}</code>',
        "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
        "Approved By": approved_by,
        "Notes": approval_notes or "No additional notes",
        "Dashboard": f'<a href="{dashboard_url}">{dashboard_url}</a>' if dashboard_url else "N/A"
    }
    
    title = "✓ Workflow Approved"
    message = "Your workflow request has been approved and is ready for execution."
    footer = "You can now execute this workflow from the dashboard."
    
    body_html = build_simple_email_body(title, message, details, footer)
    attachment_html = build_styled_html_attachment(
        title, "#a7f3d0", message, details,
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#10b981",
        footer=footer
    )
    
    return body_html, attachment_html, f"workflow_approved_{workflow_id}.html"


def build_workflow_denied_email(workflow_id, script_id, targets, denied_by, denial_reason=None, dashboard_url=None):
    details = {
        "Workflow ID": f'<code>{workflow_id}</code>',
        "Script": f'<code>{script_id}</code>',
        "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
        "Denied By": denied_by,
        "Reason": denial_reason or "No reason provided",
        "Dashboard": f'<a href="{dashboard_url}">{dashboard_url}</a>' if dashboard_url else "N/A"
    }
    
    title = "✗ Workflow Denied"
    message = "Your workflow request has been denied."
    footer = "Please contact the approver if you have questions."
    
    body_html = build_simple_email_body(title, message, details, footer)
    attachment_html = build_styled_html_attachment(
        title, "#fecaca", message, details,
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#e11d48",
        footer=footer
    )
    
    return body_html, attachment_html, f"workflow_denied_{workflow_id}.html"


def build_workflow_executed_email(workflow_id, script_id, targets, executed_by, exit_codes=None, dashboard_url=None):
    results = "Execution completed"
    if exit_codes:
        result_lines = []
        for agent, code in exit_codes.items():
            status = "✓ Success" if code == 0 else f"✗ Failed (exit: {code})"
            result_lines.append(f"{agent}: {status}")
        results = "<br>".join(result_lines)
    
    details = {
        "Workflow ID": f'<code>{workflow_id}</code>',
        "Script": f'<code>{script_id}</code>',
        "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
        "Executed By": executed_by,
        "Results": results,
        "Dashboard": f'<a href="{dashboard_url}">{dashboard_url}</a>' if dashboard_url else "N/A"
    }
    
    title = "⚡ Workflow Executed"
    message = "Your approved workflow has been executed."
    footer = "Check the dashboard for full execution logs."
    
    body_html = build_simple_email_body(title, message, details, footer)
    attachment_html = build_styled_html_attachment(
        title, "#38bdf8", message, details,
        button_text="View Details" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#0ea5e9",
        footer=footer
    )
    
    return body_html, attachment_html, f"workflow_executed_{workflow_id}.html"


# =============================================================================
# Send Email with HTML Attachment
# =============================================================================

def send_email(
    to: Union[str, List[str]],
    subject: str,
    html_body: str,
    attachment_html: str = None,
    attachment_filename: str = None,
    text_body: Optional[str] = None,
    from_addr: Optional[str] = None,
    cc: Optional[Union[str, List[str]]] = None,
) -> bool:
    """Send email with optional HTML file attachment."""
    
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
    
    # Build multipart message
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    
    # HTML/Text alternatives for email body
    alt_part = MIMEMultipart("alternative")
    
    if not text_body:
        text_body = re.sub(r'<[^>]+>', '', html_body)
        text_body = re.sub(r'\s+', ' ', text_body).strip()
    
    alt_part.attach(MIMEText(text_body, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt_part)
    
    # HTML file attachment
    if attachment_html and attachment_filename:
        html_part = MIMEBase('text', 'html')
        html_part.set_payload(attachment_html.encode('utf-8'))
        encoders.encode_base64(html_part)
        html_part.add_header('Content-Disposition', 'attachment', filename=attachment_filename)
        msg.attach(html_part)
    
    if EMAIL_DRY_RUN:
        logger.info(f"[DRY RUN] To: {', '.join(to)}, Subject: {subject}, Attachment: {attachment_filename}")
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
    body, attachment, filename = build_approval_request_email(workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes, dashboard)
    return send_email(to=approver_email, subject=f"[Action Required] Workflow Approval: {script_id} - {requestor}", html_body=body, attachment_html=attachment, attachment_filename=filename)

def send_workflow_approved(requestor_email, workflow_id, script_id, targets, approved_by, approval_notes=None, dashboard_url=None):
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    body, attachment, filename = build_workflow_approved_email(workflow_id, script_id, targets, approved_by, approval_notes, dashboard)
    return send_email(to=requestor_email, subject=f"[Approved] Workflow {workflow_id}: {script_id}", html_body=body, attachment_html=attachment, attachment_filename=filename)

def send_workflow_denied(requestor_email, workflow_id, script_id, targets, denied_by, denial_reason=None, dashboard_url=None):
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    body, attachment, filename = build_workflow_denied_email(workflow_id, script_id, targets, denied_by, denial_reason, dashboard)
    return send_email(to=requestor_email, subject=f"[Denied] Workflow {workflow_id}: {script_id}", html_body=body, attachment_html=attachment, attachment_filename=filename)

def send_workflow_executed(requestor_email, workflow_id, script_id, targets, executed_by, exit_codes=None, dashboard_url=None):
    dashboard = dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard"
    body, attachment, filename = build_workflow_executed_email(workflow_id, script_id, targets, executed_by, exit_codes, dashboard)
    return send_email(to=requestor_email, subject=f"[Executed] Workflow {workflow_id}: {script_id}", html_body=body, attachment_html=attachment, attachment_filename=filename)
