from types import SimpleNamespace

import pytest

from services import email_service


def test_smtp_requires_all_configuration(monkeypatch):
    monkeypatch.setattr(email_service.config, "SMTP_HOST", None)
    with pytest.raises(RuntimeError, match="SMTP email delivery"):
        email_service._send_smtp("user@example.com", "123456")


def test_smtp_builds_and_sends_message(monkeypatch):
    sent = []
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self): sent.append("tls")
        def login(self, user, password): sent.append((user, password))
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr(email_service.config, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_service.config, "SMTP_PORT", 587)
    monkeypatch.setattr(email_service.config, "SMTP_USERNAME", "mailer")
    monkeypatch.setattr(email_service.config, "SMTP_PASSWORD", SimpleNamespace(get_secret_value=lambda: "secret"))
    monkeypatch.setattr(email_service.config, "SMTP_FROM_EMAIL", "no-reply@example.com")
    monkeypatch.setattr(email_service.config, "SMTP_USE_TLS", True)
    monkeypatch.setattr(email_service.smtplib, "SMTP", SMTP)
    email_service._send_smtp("user@example.com", "123456")
    assert "tls" in sent and ("mailer", "secret") in sent
    message = sent[-1]
    assert message["To"] == "user@example.com" and "123456" in message.get_content()


@pytest.mark.asyncio
async def test_console_mode_does_not_open_smtp(monkeypatch, caplog):
    monkeypatch.setattr(email_service.config, "APP_EMAIL_MODE", "console")
    caplog.set_level("INFO")
    await email_service.send_verification_code("user@example.com", "123456")
    assert "APP VERIFICATION CODE" in caplog.text
