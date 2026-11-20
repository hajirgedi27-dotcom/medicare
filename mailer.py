"""Email add-on.

Every email in the system goes through send_email(). Delivery uses one of
two Python backends selected with MAIL_BACKEND in config.py:

  smtp      Send directly through Python's standard-library smtplib
  console   Print to the terminal (development)

No PHP bridge, Composer, or third-party email package is required.

Emails are sent in a background thread so pages never wait on the mail server,
and each attempt is recorded in the email_log table.
"""
import smtplib
import ssl
import threading
from email.message import EmailMessage
from html import escape

from db import connect_standalone


# --------------------------------------------------------------- backends --
def _deliver_smtp(cfg, payload):
    """Deliver one email directly through an SMTP server such as Gmail."""
    host = (cfg.get("SMTP_HOST") or "").strip()
    port = int(cfg.get("SMTP_PORT", 587))
    username = (cfg.get("SMTP_USER") or "").strip()
    password = cfg.get("SMTP_PASSWORD") or ""
    security = (cfg.get("SMTP_SECURITY") or "tls").strip().lower()
    timeout = int(cfg.get("MAIL_TIMEOUT", 30))

    if not host:
        raise RuntimeError("SMTP_HOST is not configured.")
    if not username or not password:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must both be configured.")
    if security not in ("tls", "ssl", "none"):
        raise RuntimeError("SMTP_SECURITY must be tls, ssl, or none.")
    if security == "ssl" and port != 465:
        raise RuntimeError("Gmail SSL normally uses port 465.")
    if security == "tls" and port != 587:
        raise RuntimeError("Gmail STARTTLS normally uses port 587.")

    # Gmail requires the authenticated account to be the sender address.
    from_email = username
    from_name = payload.get("from_name") or cfg.get("HOSPITAL_NAME", "Hospital")

    msg = EmailMessage()
    msg["From"] = f'{from_name} <{from_email}>'
    msg["To"] = payload["to"]
    msg["Subject"] = payload["subject"]
    msg.set_content(payload.get("text") or "")
    msg.add_alternative(payload.get("html") or "", subtype="html")

    context = ssl.create_default_context()

    if security == "ssl":
        with smtplib.SMTP_SSL(
            host, port, timeout=timeout, context=context
        ) as server:
            server.ehlo()
            server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            if security == "tls":
                # Explicit STARTTLS upgrade; smtplib supplies server_hostname.
                server.starttls(context=context)
                server.ehlo()
            server.login(username, password)
            server.send_message(msg)


def _deliver_console(cfg, payload):
    print(
        "\n----- EMAIL (console backend) -----\n"
        f"To: {payload['to']}\n"
        f"Subject: {payload['subject']}\n\n"
        f"{payload['text']}\n"
        "-----------------------------------\n"
    )


BACKENDS = {
    "smtp": _deliver_smtp,
    "console": _deliver_console,
}


# ------------------------------------------------------------------ core --
def _log(app, to, subject, kind, backend, status, error=None):
    conn = connect_standalone(app)
    try:
        conn.execute(
            "INSERT INTO email_log (recipient, subject, kind, backend, status, error) VALUES (?,?,?,?,?,?)",
            (to, subject, kind, backend, status, error),
        )
        conn.commit()
    finally:
        conn.close()


def _worker(app, payload, kind):
    cfg = app.config
    backend = cfg["MAIL_BACKEND"]
    try:
        BACKENDS[backend](cfg, payload)
        _log(app, payload["to"], payload["subject"], kind, backend, "sent")
    except Exception as exc:  # never let email problems break the app
        _log(app, payload["to"], payload["subject"], kind, backend, "failed", str(exc)[:500])


def send_email(app, to, subject, html_body, text_body=None, kind="general", wait=False):
    """Queue an email. Returns False if skipped (disabled / no address)."""
    cfg = app.config
    if not to or "@" not in to:
        return False
    if not cfg["MAIL_ENABLED"]:
        _log(app, to, subject, kind, cfg["MAIL_BACKEND"], "skipped", "Email disabled")
        return False
    if cfg["MAIL_BACKEND"] not in BACKENDS:
        _log(app, to, subject, kind, cfg["MAIL_BACKEND"], "failed", "Unknown MAIL_BACKEND")
        return False
    payload = {
        "to": to,
        "subject": subject,
        "html": wrap_html(cfg["HOSPITAL_NAME"], html_body),
        "text": text_body or _strip(html_body),
        "from_name": cfg["MAIL_FROM_NAME"],
        "from_email": cfg["MAIL_FROM_ADDRESS"],
    }
    t = threading.Thread(target=_worker, args=(app, payload, kind), daemon=True)
    t.start()
    if wait:
        t.join(timeout=cfg["MAIL_TIMEOUT"] + 5)
    return True


def _strip(html):
    import re
    text = re.sub(r"<br\s*/?>|</p>|</tr>|</h\d>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def wrap_html(hospital, body):
    return f"""<!doctype html><html><body style="margin:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#1e293b">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px">
<table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:10px;overflow:hidden">
<tr><td style="background:#0f766e;color:#fff;padding:18px 24px;font-size:18px;font-weight:bold">{escape(hospital)}</td></tr>
<tr><td style="padding:24px;font-size:15px;line-height:1.6">{body}</td></tr>
<tr><td style="padding:14px 24px;background:#f8fafc;color:#64748b;font-size:12px">This is an automated message from {escape(hospital)}. Please do not reply.</td></tr>
</table></td></tr></table></body></html>"""


# ------------------------------------------------------- email templates --
def _detail_table(rows):
    cells = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:#64748b">{escape(k)}</td><td style="padding:6px 0"><b>{escape(str(v))}</b></td></tr>'
        for k, v in rows
    )
    return f'<table cellpadding="0" cellspacing="0" style="margin:12px 0">{cells}</table>'


def appointment_booked(app, appt):
    rows = [("Date", appt["appt_date"]), ("Time", appt["appt_time"]),
            ("Doctor", appt["doctor_name"]), ("Department", appt.get("department") or "-")]
    if appt.get("reason"):
        rows.append(("Reason", appt["reason"]))
    body_p = (f'<p>Dear {escape(appt["patient_name"])},</p><p>Your appointment has been <b>confirmed</b>.</p>'
              f'{_detail_table(rows)}<p>Please arrive 10 minutes early and carry your ID.</p>')
    send_email(app, appt.get("patient_email"), "Appointment confirmed", body_p, kind="appointment_booked")
    body_d = (f'<p>Dr. {escape(appt["doctor_name"])},</p><p>A new appointment has been booked for you.</p>'
              f'{_detail_table([("Patient", appt["patient_name"])] + rows[:2] + ([("Reason", appt["reason"])] if appt.get("reason") else []))}')
    send_email(app, appt.get("doctor_email"), "New appointment booked", body_d, kind="appointment_doctor")


def appointment_cancelled(app, appt):
    rows = [("Date", appt["appt_date"]), ("Time", appt["appt_time"]), ("Doctor", appt["doctor_name"])]
    if appt.get("cancel_reason"):
        rows.append(("Reason", appt["cancel_reason"]))
    body = (f'<p>Dear {escape(appt["patient_name"])},</p><p>Your appointment has been <b>cancelled</b>.</p>'
            f'{_detail_table(rows)}<p>Please contact the hospital to book a new time.</p>')
    send_email(app, appt.get("patient_email"), "Appointment cancelled", body, kind="appointment_cancelled")
    body_d = (f'<p>Dr. {escape(appt["doctor_name"])},</p><p>An appointment has been cancelled.</p>'
              f'{_detail_table([("Patient", appt["patient_name"])] + rows)}')
    send_email(app, appt.get("doctor_email"), "Appointment cancelled", body_d, kind="appointment_cancelled")


def appointment_reminder(app, appt):
    rows = [("Date", appt["appt_date"]), ("Time", appt["appt_time"]), ("Doctor", appt["doctor_name"])]
    body = (f'<p>Dear {escape(appt["patient_name"])},</p><p>This is a friendly reminder of your appointment <b>tomorrow</b>.</p>'
            f'{_detail_table(rows)}')
    return send_email(app, appt.get("patient_email"), "Appointment reminder", body, kind="reminder")


def welcome_user(app, user, username, temp_password):
    body = (f'<p>Hello {escape(user["full_name"])},</p><p>An account has been created for you.</p>'
            f'{_detail_table([("Login URL", app.config["BASE_URL"] + "/login"), ("Username", username), ("Temporary password", temp_password)])}'
            f'<p>You will be asked to choose a new password the first time you sign in.</p>')
    send_email(app, user["email"], "Your account details", body, kind="welcome")


def password_reset(app, user, link):
    body = (f'<p>Hello {escape(user["full_name"])},</p><p>We received a request to reset your password. '
            f'This link is valid for 1 hour:</p><p><a href="{escape(link)}" style="background:#0f766e;color:#fff;padding:10px 18px;border-radius:6px;text-decoration:none">Reset password</a></p>'
            f'<p>If you did not ask for this, you can ignore this email.</p>')
    send_email(app, user["email"], "Password reset request", body, kind="password_reset")
