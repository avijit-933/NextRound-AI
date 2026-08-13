"""
services/contact_service.py — sends the landing page's contact form as a real
email via SMTP (works with Gmail app passwords, SendGrid SMTP relay, etc.).

If SMTP_HOST isn't configured, falls back to logging the message so local
development doesn't require real mail credentials.
"""
import logging
import smtplib
from email.mime.text import MIMEText

from config import settings

logger = logging.getLogger(__name__)


def send_contact_message(name: str, email: str, message: str) -> None:
    body = (
        f"New contact form submission from NextRound AI\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n\n"
        f"Message:\n{message}\n"
    )

    if not settings.SMTP_HOST:
        logger.info("SMTP not configured — logging contact message instead of sending it:\n%s", body)
        return

    msg = MIMEText(body)
    msg["Subject"] = f"NextRound AI contact form — {name}"
    msg["From"] = settings.SMTP_USER or settings.CONTACT_TO_EMAIL
    msg["To"] = settings.CONTACT_TO_EMAIL
    msg["Reply-To"] = email  # so hitting "reply" in the inbox goes straight to the sender

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(msg["From"], [settings.CONTACT_TO_EMAIL], msg.as_string())
