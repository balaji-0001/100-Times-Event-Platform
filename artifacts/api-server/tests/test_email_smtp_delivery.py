"""Tests for SMTP Email Delivery, Configuration, and Outbox."""

import pytest
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.main import app
from backend.models import User
from backend.services.notifications import send_templated_notification
from backend.services.smtp_config import get_smtp_info, save_smtp_settings, send_test_email
from backend.services.social_agent.outreach.senders import (
    MockEmailProvider,
    SMTPEmailProvider,
    clear_outbox,
    get_email_provider,
    get_outbox,
    provider_status,
    record_outbox,
)


@pytest.fixture(autouse=True)
def isolated_smtp_env(tmp_path, monkeypatch):
    """save_smtp_settings writes .env files and os.environ. Without this, a
    test run rewrote the project's REAL .env files (and blanked SMTP_* in its
    cleanup). Redirect writes to a temp file and restore the process env."""
    import os

    from backend.core.config import get_settings
    from backend.services import smtp_config

    monkeypatch.setattr(smtp_config, "_get_env_paths", lambda: [tmp_path / ".env"])
    keys = ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "SMTP_USE_TLS")
    saved = {k: os.environ.get(k) for k in keys}
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


def _admin_user():
    return User(id=999, name="Admin Test", email="admin-test@100times.in", role="ADMIN", password_hash="hash")


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin_user
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_smtp_info_and_mock_fallback():
    clear_outbox()
    info = get_smtp_info()
    assert "configured" in info
    assert "status" in info
    assert "provider" in info
    assert info["status"] in ("REAL", "NOT_CONFIGURED")


def test_mock_email_provider_records_outbox():
    clear_outbox()
    provider = MockEmailProvider()
    result = provider.send_message("recipient@test.com", "Welcome Subject", "Hello body")
    # Without SMTP nothing is delivered: never report success.
    assert result.success is False
    assert result.ok is False
    assert "SMTP is not configured" in result.message

    # Verify outbox has recorded this message
    outbox = get_outbox()
    assert len(outbox) >= 1
    item = outbox[0]
    assert item["recipient"] == "recipient@test.com"
    assert item["subject"] == "Welcome Subject"
    assert item["provider"] == "mock"
    assert item["status"] == "NOT_SENT"


def test_send_templated_notification_with_email_provider(db_session, monkeypatch):
    # A provider that really delivers (records to the Outbox like the SMTP one);
    # this test used to pass only by sending through a real SMTP account.
    from backend.services import notifications
    from backend.services.social_agent.outreach.types import SendResult

    class _Delivering:
        is_real = True

        def send(self, recipient, subject, body, html=None):
            record_outbox(recipient, subject, body, html, provider="smtp", status="DELIVERED", message_id="test-1")
            return SendResult(success=True, message_id="test-1", message="delivered")

    monkeypatch.setattr(notifications, "get_email_provider", lambda: _Delivering())
    clear_outbox()
    user = User(name="Test Attendee", email="attendee@example.com", role="USER", password_hash="pwd")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    notif = send_templated_notification(
        db_session,
        template_key="welcome",
        user_id=user.id,
        recipient_email=user.email,
        context={"name": user.name, "email": user.email},
        send_email=True,
    )
    assert notif is not None
    assert notif.template_key == "welcome"
    assert notif.metadata_json["email_status"] == "sent"

    # Outbox should have recorded it
    outbox = get_outbox()
    matching = [m for m in outbox if m["recipient"] == user.email]
    assert len(matching) == 1
    assert "Welcome" in matching[0]["subject"]


def test_smtp_api_endpoints(client):
    clear_outbox()

    try:
        # 1. GET /api/acquisition/outreach/smtp/config
        res = client.get("/api/acquisition/outreach/smtp/config")
        assert res.status_code == 200
        data = res.json()
        assert "configured" in data
        assert "status" in data
        assert "fromEmail" in data

        # 2. POST /api/acquisition/outreach/smtp/config (save settings)
        save_payload = {
            "host": "smtp.mailgun.org",
            "port": 587,
            "username": "postmaster@100times.in",
            "password": "secret_password_123",
            "fromEmail": "events@100times.in",
            "useTls": True,
        }
        res_save = client.post("/api/acquisition/outreach/smtp/config", json=save_payload)
        assert res_save.status_code == 200
        saved = res_save.json()
        assert saved["host"] == "smtp.mailgun.org"
        assert saved["port"] == 587
        assert saved["fromEmail"] == "events@100times.in"
        assert saved["configured"] is True
        assert saved["status"] == "REAL"
        assert saved["hasPassword"] is True

        # 3. GET Outbox
        res_outbox = client.get("/api/acquisition/outreach/smtp/outbox")
        assert res_outbox.status_code == 200
        assert isinstance(res_outbox.json(), list)

        # 4. POST Clear Outbox
        res_clear = client.post("/api/acquisition/outreach/smtp/outbox/clear")
        assert res_clear.status_code == 200
        assert res_clear.json() == {"status": "cleared"}

        # Outbox should now be empty
        res_empty = client.get("/api/acquisition/outreach/smtp/outbox")
        assert len(res_empty.json()) == 0
    finally:
        save_smtp_settings("", 587, "", "", "")
        clear_outbox()


def test_smtp_connection_test_invalid_host():
    # Should cleanly return False and diagnostic message without crashing
    success, message = SMTPEmailProvider.test_connection(
        host="invalid-nonexistent-smtp-domain-xyz123.com",
        port=587,
        username="user",
        password="pwd",
        timeout=2,
    )
    assert success is False
    assert len(message) > 0


def test_outbox_never_shows_one_time_tokens():
    from backend.services.social_agent.outreach.senders.outbox import record_outbox
    clear_outbox()
    record_outbox("a@b.test", "Reset", "Reset here: http://app.test/reset-password?token=abc123SECRET&x=1")
    body = get_outbox()[0]["body"]
    assert "abc123SECRET" not in body
    assert "reset-password?token=[redacted]&x=1" in body
