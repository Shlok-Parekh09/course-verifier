#!/usr/bin/env python3
"""email_sender.py – Send verification PDF reports via SMTP.
Reads credentials from .env (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
SMTP_FROM, SMTP_TO, SEND_EMAIL_ON_COMPLETE).
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
SMTP_TO = os.getenv("SMTP_TO", "")
ENABLED = os.getenv("SEND_EMAIL_ON_COMPLETE", "false").lower() in ("true", "1", "yes", "on")


def _build_message(subject, body_text, attachment_path=None):
    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = SMTP_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    if attachment_path and os.path.exists(attachment_path):
        filename = os.path.basename(attachment_path)
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)
    return msg


def send_report(subject, body, attachment_path=None):
    """Send the PDF report email. Returns (success:bool, message:str)."""
    if not ENABLED:
        return True, "Email sending disabled (SEND_EMAIL_ON_COMPLETE=false)."

    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM or SMTP_USER, SMTP_TO]):
        return False, "Incomplete SMTP config. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_TO in .env."

    msg = _build_message(subject, body, attachment_path)
    recipients = [r.strip() for r in SMTP_TO.split(",") if r.strip()]

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(msg["From"], recipients, msg.as_string())
        server.quit()
        return True, f"Email sent to {', '.join(recipients)}"
    except Exception as e:
        return False, f"Failed to send email: {e}"
