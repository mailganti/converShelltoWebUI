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
    OUTLOOK COMPATIBLE HTML EMAIL.
    Uses: VML for buttons, <font> tags, bgcolor, MSO conditionals.
    """
    
    # Details table
    details_html = ""
    if details:
        rows = []
        for i, (label, value) in enumerate(details.items()):
            row_bg = "#1e293b" if i % 2 == 0 else "#0f172a"
            rows.append(f'''<tr>
<td bgcolor="{row_bg}" width="140" valign="top" style="padding:12px 16px;border-bottom:1px solid #334155;"><font color="#94a3b8" face="Arial,sans-serif" size="2">{label}</font></td>
<td bgcolor="{row_bg}" valign="top" style="padding:12px 16px;border-bottom:1px solid #334155;"><font color="#f1f5f9" face="Arial,sans-serif" size="2">{value}</font></td>
</tr>''')
        details_html = f'''<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#0f172a">
{''.join(rows)}
</table>'''
    
    # VML button for Outlook
    button_html = ""
    if button_text and button_url:
        button_html = f'''<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="padding:28px 0;">
<!--[if mso]>
<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="{button_url}" style="height:44px;v-text-anchor:middle;width:240px;" arcsize="10%" stroke="f" fillcolor="{button_color}">
<w:anchorlock/>
<center><![endif]-->
<a href="{button_url}" style="background-color:{button_color};color:#ffffff;display:inline-block;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;line-height:44px;text-align:center;text-decoration:none;width:240px;mso-hide:all;">{button_text}</a>
<!--[if mso]></center>
</v:roundrect>
<![endif]-->
</td>
</tr>
</table>'''
    
    footer_html = f"<br>{footer}" if footer else ""
    
    return f'''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<meta http-equiv="X-UA-Compatible" content="IE=edge"/>
<!--[if gte mso 9]>
<xml>
<o:OfficeDocumentSettings>
<o:AllowPNG/>
<o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings>
</xml>
<![endif]-->
<!--[if mso]>
<style type="text/css">
body,table,td{{font-family:Arial,sans-serif!important;}}
</style>
<![endif]-->
<title>Orchestration Notification</title>
</head>
<body bgcolor="#020617" style="margin:0;padding:0;background-color:#020617;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#020617">
<tr>
<td align="center" valign="top" style="padding:40px 20px;">

<table width="600" cellpadding="0" cellspacing="0" border="0">

<!-- HEADER -->
<tr>
<td align="center" style="padding-bottom:32px;">
<table cellpadding="0" cellspacing="0" border="0">
<tr>
<td bgcolor="#0f172a" width="50" height="50" align="center" valign="middle" style="border:1px solid #38bdf8;">
<font color="#38bdf8" face="Arial,sans-serif" size="3"><b>ORC</b></font>
</td>
</tr>
</table>
<table cellpadding="0" cellspacing="0" border="0">
<tr>
<td align="center" style="padding-top:12px;">
<font color="#ffffff" face="Arial,sans-serif" size="2"><b>ORCHESTRATION</b></font>
</td>
</tr>
</table>
</td>
</tr>

<!-- MAIN CARD -->
<tr>
<td bgcolor="#020617" style="border:1px solid #334155;">

<!-- Title Bar -->
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td bgcolor="#1e293b" style="padding:20px 24px;border-bottom:1px solid #334155;">
<font color="{title_color}" face="Arial,sans-serif" size="4"><b>{title}</b></font>
</td>
</tr>
</table>

<!-- Content -->
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td bgcolor="#020617" style="padding:24px;">

<table cellpadding="0" cellspacing="0" border="0">
<tr>
<td style="padding-bottom:24px;">
<font color="#cbd5e1" face="Arial,sans-serif" size="2">{message}</font>
</td>
</tr>
</table>

{details_html}

{button_html}

</td>
</tr>
</table>

</td>
</tr>

<!-- FOOTER -->
<tr>
<td align="center" style="padding-top:24px;">
<font color="#64748b" face="Arial,sans-serif" size="1">This is an automated message from the Orchestration System.{footer_html}</font>
</td>
</tr>

</table>

</td>
</tr>
</table>
</body>
</html>'''


# =============================================================================
# Email Templates
# =============================================================================

def build_approval_request_email(workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes, dashboard_url):
    email_link = f'<a href="mailto:{requestor_email}" style="color:#38bdf8;">{requestor_email}</a>' if requestor_email else ""
    return build_email_html(
        title="⏳ Workflow Approval Required",
        title_color="#fde68a",
        message="A new workflow has been submitted and requires your approval.",
        details={
            "Workflow ID": f'<font color="#38bdf8">{workflow_id}</font>',
            "Requestor": requestor,
            "Requestor Email": email_link,
            "Script": f'<font color="#38bdf8">{script_id}</font>',
            "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
            "Reason": reason or "No reason provided",
            "Expires In": f'{ttl_minutes} minutes'
        },
        button_text="Open Dashboard to Approve",
        button_url=dashboard_url,
        button_color="#0ea5e9",
        footer=f"Requested by: {requestor}"
    )


def build_workflow_approved_email(workflow_id, script_id, targets, approved_by, approval_notes=None, dashboard_url=None):
    return build_email_html(
        title="✓ Workflow Approved",
        title_color="#a7f3d0",
        message="Your workflow request has been approved and is ready for execution.",
        details={
            "Workflow ID": f'<font color="#38bdf8">{workflow_id}</font>',
            "Script": f'<font color="#38bdf8">{script_id}</font>',
            "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
            "Approved By": f'<font color="#a7f3d0">{approved_by}</font>',
            "Notes": approval_notes or "No additional notes"
        },
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#10b981",
        footer="You can now execute this workflow from the dashboard."
    )


def build_workflow_denied_email(workflow_id, script_id, targets, denied_by, denial_reason=None, dashboard_url=None):
    return build_email_html(
        title="✗ Workflow Denied",
        title_color="#fecaca",
        message="Your workflow request has been denied.",
        details={
            "Workflow ID": f'<font color="#38bdf8">{workflow_id}</font>',
            "Script": f'<font color="#38bdf8">{script_id}</font>',
            "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
            "Denied By": f'<font color="#fecaca">{denied_by}</font>',
            "Reason": f'<font color="#fecaca">{denial_reason or "No reason provided"}</font>'
        },
        button_text="View in Dashboard" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#e11d48",
        footer="Please contact the approver if you have questions."
    )


def build_workflow_executed_email(workflow_id, script_id, targets, executed_by, exit_codes=None, dashboard_url=None):
    results = ""
    if exit_codes:
        for agent, code in exit_codes.items():
            color = "#a7f3d0" if code == 0 else "#fecaca"
            status = "Success" if code == 0 else f"Failed (exit: {code})"
            results += f'<font color="{color}">{agent}: {status}</font><br/>'
    else:
        results = "Execution completed"
    
    return build_email_html(
        title="⚡ Workflow Executed",
        title_color="#38bdf8",
        message="Your approved workflow has been executed.",
        details={
            "Workflow ID": f'<font color="#38bdf8">{workflow_id}</font>',
            "Script": f'<font color="#38bdf8">{script_id}</font>',
            "Target Agents": ', '.join(targets) if isinstance(targets, list) else targets,
            "Executed By": executed_by,
            "Results": results
        },
        button_text="View Details" if dashboard_url else None,
        button_url=dashboard_url,
        button_color="#0ea5e9",
        footer="Check the dashboard for full execution logs."
    )


# =============================================================================
# Send Email
# =============================================================================

def send_email(to, subject, html_body, text_body=None, from_addr=None, cc=None):
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


# Convenience wrappers
def send_approval_request(approver_email, workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes=60, dashboard_url=None):
    html = build_approval_request_email(workflow_id, script_id, requestor, requestor_email, targets, reason, ttl_minutes, dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard")
    return send_email(to=approver_email, subject=f"[Action Required] Workflow Approval: {script_id} - {requestor}", html_body=html)

def send_workflow_approved(requestor_email, workflow_id, script_id, targets, approved_by, approval_notes=None, dashboard_url=None):
    html = build_workflow_approved_email(workflow_id, script_id, targets, approved_by, approval_notes, dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard")
    return send_email(to=requestor_email, subject=f"[Approved] Workflow {workflow_id}: {script_id}", html_body=html)

def send_workflow_denied(requestor_email, workflow_id, script_id, targets, denied_by, denial_reason=None, dashboard_url=None):
    html = build_workflow_denied_email(workflow_id, script_id, targets, denied_by, denial_reason, dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard")
    return send_email(to=requestor_email, subject=f"[Denied] Workflow {workflow_id}: {script_id}", html_body=html)

def send_workflow_executed(requestor_email, workflow_id, script_id, targets, executed_by, exit_codes=None, dashboard_url=None):
    html = build_workflow_executed_email(workflow_id, script_id, targets, executed_by, exit_codes, dashboard_url or os.getenv("API_HOST", "https://localhost:7585") + "/dashboard")
    return send_email(to=requestor_email, subject=f"[Executed] Workflow {workflow_id}: {script_id}", html_body=html)
