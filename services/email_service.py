"""Small email delivery adapter used by application authentication."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from config import config

logger = logging.getLogger(__name__)


def _send_smtp(to_email: str, code: str) -> None:
    if not all((config.SMTP_HOST, config.SMTP_USERNAME, config.SMTP_PASSWORD, config.SMTP_FROM_EMAIL)):
        raise RuntimeError("SMTP email delivery is not configured")
    message = EmailMessage()
    message["Subject"] = "Код подтверждения ALTER"
    message["From"] = config.SMTP_FROM_EMAIL
    message["To"] = to_email
    message.set_content(f"Код подтверждения ALTER: {code}\n\nКод действует 10 минут.")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
        if config.SMTP_USE_TLS:
            smtp.starttls()
        smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD.get_secret_value())
        smtp.send_message(message)


async def send_verification_code(to_email: str, code: str) -> None:
    if config.APP_EMAIL_MODE.casefold() == "console":
        # Deliberately useful for local Expo testing; never use this in prod.
        logger.info("APP VERIFICATION CODE email=%s code=%s", to_email, code)
        return
    await asyncio.to_thread(_send_smtp, to_email, code)
