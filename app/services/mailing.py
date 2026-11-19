"""Envio SMTP com STARTTLS; sujeito às políticas do tenant Microsoft 365."""
import smtplib
from email.message import EmailMessage
from app.db import get_setting
from app.security import decrypt


def send_report(destination, subject, content):
    host = get_setting("smtp_host") or "smtp.office365.com"
    port = int(get_setting("smtp_port") or 587)
    user = get_setting("smtp_user")
    secret = get_setting("smtp_password")
    if not user or not secret:
        raise ValueError("SMTP não configurado")
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = destination
    msg["Subject"] = subject
    msg.set_content(content)
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(user, decrypt(secret))
        smtp.send_message(msg)
