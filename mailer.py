def build_email_html(
    title: str,
    title_color: str = "#38bdf8",
    message: str = "",
    details: dict = None,
    button_text: str = None,
    button_url: str = None,
    button_color: str = "#0ea5e9",
    footer: str = None
) -> str:
    """
    Build HTML email with dark theme.
    
    EMAIL CLIENT COMPATIBLE:
    - NO rgba() - use solid hex colors
    - NO linear-gradient() - use solid colors
    - NO radial-gradient() - use solid colors  
    - Uses bgcolor attribute on tables/cells
    """
    
    # Build details table rows
    details_html = ""
    if details:
        rows = []
        for i, (label, value) in enumerate(details.items()):
            # Alternating solid colors - NO RGBA!
            row_bg = "#1e293b" if i % 2 == 0 else "#0f172a"
            rows.append(f'''
                        <tr bgcolor="{row_bg}">
                            <td bgcolor="{row_bg}" style="padding: 12px 16px; border-bottom: 1px solid #334155; color: #94a3b8; font-size: 13px; width: 140px;">{label}</td>
                            <td bgcolor="{row_bg}" style="padding: 12px 16px; border-bottom: 1px solid #334155; color: #f1f5f9; font-size: 13px;">{value}</td>
                        </tr>''')
        details_html = f'''
                    <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#0f172a" style="border-collapse: collapse; border-radius: 8px;">
                        {''.join(rows)}
                    </table>'''
    
    # Build button - solid color, no gradients
    button_html = ""
    if button_text and button_url:
        button_html = f'''
                    <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                            <td align="center" style="padding: 28px 0;">
                                <table cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td bgcolor="{button_color}" style="border-radius: 6px;">
                                            <a href="{button_url}" target="_blank" style="display: inline-block; padding: 12px 32px; font-family: Arial, sans-serif; font-size: 14px; font-weight: 600; color: #ffffff; text-decoration: none;">
                                                {button_text}
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>'''
    
    # Footer text
    footer_text = ""
    if footer:
        footer_text = f"<br>{footer}"
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body bgcolor="#020617" style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #020617;">
    <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#020617" style="background-color: #020617;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table width="600" cellpadding="0" cellspacing="0" style="max-width: 600px;">
                    
                    <!-- Header with logo -->
                    <tr>
                        <td align="center" style="padding-bottom: 32px;">
                            <table cellpadding="0" cellspacing="0">
                                <tr>
                                    <td bgcolor="#0f172a" width="48" height="48" align="center" style="border-radius: 12px; border: 1px solid #38bdf8;">
                                        <span style="color: #38bdf8; font-size: 14px; font-weight: bold;">ORC</span>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin: 12px 0 0 0; color: #ffffff; font-size: 13px; font-weight: 700; letter-spacing: 2px;">ORCHESTRATION</p>
                        </td>
                    </tr>
                    
                    <!-- Main card -->
                    <tr>
                        <td bgcolor="#020617" style="border: 1px solid #334155; border-radius: 12px; background-color: #020617;">
                            
                            <!-- Title bar -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td bgcolor="#1e293b" style="padding: 20px 24px; border-bottom: 1px solid #334155; background-color: #1e293b; border-radius: 12px 12px 0 0;">
                                        <h1 style="margin: 0; color: {title_color}; font-size: 18px; font-weight: 600;">{title}</h1>
                                    </td>
                                </tr>
                            </table>
                            
                            <!-- Content -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td bgcolor="#020617" style="padding: 24px; background-color: #020617;">
                                        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0;">{message}</p>
                                        
                                        {details_html}
                                        
                                        {button_html}
                                    </td>
                                </tr>
                            </table>
                            
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td align="center" style="padding-top: 24px;">
                            <p style="color: #64748b; font-size: 11px; margin: 0;">
                                This is an automated message from the Orchestration System.{footer_text}
                            </p>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''


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
    email_link = f'<a href="mailto:{requestor_email}" style="color: #38bdf8; text-decoration: none;">{requestor_email}</a>' if requestor_email else ""
    
    return build_email_html(
        title="⏳ Workflow Approval Required",
        title_color="#fde68a",
        message="A new workflow has been submitted and requires your approval.",
        details={
            "Workflow ID": f'<span style="font-family: monospace; color: #38bdf8;">{workflow_id}</span>',
            "Requestor": requestor,
            "Requestor Email": email_link,
            "Script": f'<span style="font-family: monospace; color: #38bdf8;">{script_id}</span>',
            "Target Agents": ', '.join(targets),
            "Reason": reason or "No reason provided",
            "Expires In": f'{ttl_minutes} minutes'
        },
        button_text="Open Dashboard to Approve",
        button_url=dashboard_url,
        button_color="#0ea5e9",
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
    return build_email_html(
        title="✓ Workflow Approved",
        title_color="#a7f3d0",
        message="Your workflow request has been approved and is ready for execution.",
        details={
            "Workflow ID": f'<span style="font-family: monospace; color: #38bdf8;">{workflow_id}</span>',
            "Script": f'<span style="font-family: monospace; color: #38bdf8;">{script_id}</span>',
            "Target Agents": ', '.join(targets),
            "Approved By": f'<span style="color: #a7f3d0;">{approved_by}</span>',
            "Notes": approval_notes or "No additional notes"
        },
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#10b981",
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
    return build_email_html(
        title="✗ Workflow Denied",
        title_color="#fecaca",
        message="Your workflow request has been denied.",
        details={
            "Workflow ID": f'<span style="font-family: monospace; color: #38bdf8;">{workflow_id}</span>',
            "Script": f'<span style="font-family: monospace; color: #38bdf8;">{script_id}</span>',
            "Target Agents": ', '.join(targets),
            "Denied By": f'<span style="color: #fecaca;">{denied_by}</span>',
            "Reason": f'<span style="color: #fecaca;">{denial_reason or "No reason provided"}</span>'
        },
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#e11d48",
        footer="Please contact the approver if you have questions."
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
    results = ""
    if exit_codes:
        for agent, code in exit_codes.items():
            color = "#a7f3d0" if code == 0 else "#fecaca"
            status = "Success" if code == 0 else f"Failed (exit: {code})"
            results += f'<span style="color: {color};">{agent}: {status}</span><br>'
    else:
        results = "Execution completed"
    
    return build_email_html(
        title="⚡ Workflow Executed",
        title_color="#38bdf8",
        message="Your approved workflow has been executed.",
        details={
            "Workflow ID": f'<span style="font-family: monospace; color: #38bdf8;">{workflow_id}</span>',
            "Script": f'<span style="font-family: monospace; color: #38bdf8;">{script_id}</span>',
            "Target Agents": ', '.join(targets),
            "Executed By": executed_by,
            "Results": results
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
    """Send an email with HTML content."""
    
    if isinstance(to, str):
        to = [to]
    if isinstance(cc, str):
        cc = [cc]
    
    to = [addr.strip() for addr in to if addr and addr.strip()]
    cc = [addr.strip() for addr in (cc or []) if addr and addr.strip()]
    
    if not to:
        logger.warning("No recipients specified")
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
    
    all_recipients = to + cc
    
    if EMAIL_DRY_RUN:
        logger.info(f"[DRY RUN] Would send to: {', '.join(to)}, Subject: {subject}")
        return True
    
    try:
        if os.path.exists(SENDMAIL_PATH):
            proc = subprocess.Popen(
                [SENDMAIL_PATH, "-t", "-oi"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate(msg.as_string().encode('utf-8'))
            
            if proc.returncode == 0:
                logger.info(f"Email sent to {', '.join(to)}: {subject}")
                return True
            else:
                logger.error(f"sendmail failed: {stderr.decode('utf-8')}")
                return False
        else:
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
