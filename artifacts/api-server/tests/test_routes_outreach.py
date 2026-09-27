"""HTTP-layer tests for the Organizer Outreach routes — same minimal
standalone-app pattern as `test_routes_discovery.py`. This router requires
ADMIN auth (added alongside the new status model), so the fixture overrides
`get_current_user` the same way."""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import DiscoveredEvent, DiscoveredOrganizer, OutreachMessage, User
from backend.routes import outreach as outreach_routes


def _admin_user() -> User:
    return User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(outreach_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin_user
    return TestClient(app)


def _make_outreach(db_session, status="PENDING_APPROVAL", **overrides) -> OutreachMessage:
    organizer = DiscoveredOrganizer(name="Pune Riders Collective", email="hello@puneriders.test", website="https://example-events.test")
    db_session.add(organizer)
    db_session.flush()
    event = DiscoveredEvent(name="Pune Cycling Meetup", match_score=90, organizer_status="FOUND", organizer_id=organizer.id)
    db_session.add(event)
    db_session.flush()
    fields = dict(
        event_id=event.id, organizer_id=organizer.id, recipient=organizer.email,
        subject="Help more people discover Pune Cycling Meetup on 100Times", message="Hi there...", status=status,
        created_at=datetime.now(timezone.utc),
    )
    fields.update(overrides)
    message = OutreachMessage(**fields)
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    return message


def test_list_outreach(client, db_session):
    _make_outreach(db_session)
    response = client.get("/api/acquisition/outreach")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "PENDING_APPROVAL"
    assert body[0]["organizer"]["email"] == "hello@puneriders.test"


def test_list_outreach_filters_by_status(client, db_session):
    _make_outreach(db_session, status="DELIVERED", sent_at=datetime.now(timezone.utc))
    _make_outreach(db_session, status="APPROVED", failure_reason="SMTP send failed: connection refused")
    response = client.get("/api/acquisition/outreach", params={"status": "approved"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "APPROVED"


def test_edit_outreach_before_send(client, db_session):
    message = _make_outreach(db_session, status="PENDING_APPROVAL")
    response = client.patch(f"/api/acquisition/outreach/{message.id}/edit", json={"subject": "Updated subject", "message": "Updated body text"})
    assert response.status_code == 200
    assert response.json()["subject"] == "Updated subject"


def test_edit_outreach_rejected_after_send(client, db_session):
    message = _make_outreach(db_session, status="DELIVERED", sent_at=datetime.now(timezone.utc))
    response = client.patch(f"/api/acquisition/outreach/{message.id}/edit", json={"subject": "xx", "message": "y y y y"})
    assert response.status_code == 409


def test_approve_then_send_action_uses_mock_provider(client, db_session):
    message = _make_outreach(db_session, status="PENDING_APPROVAL")
    approve = client.post(f"/api/acquisition/outreach/{message.id}/action", json={"action": "approve"})
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"

    response = client.post(f"/api/acquisition/outreach/{message.id}/action", json={"action": "send"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DELIVERED"


def test_send_requires_prior_approval(client, db_session):
    message = _make_outreach(db_session, status="PENDING_APPROVAL")
    response = client.post(f"/api/acquisition/outreach/{message.id}/action", json={"action": "send"})
    assert response.status_code == 409


def test_reject_action(client, db_session):
    message = _make_outreach(db_session, status="PENDING_APPROVAL")
    response = client.post(f"/api/acquisition/outreach/{message.id}/action", json={"action": "reject", "reason": "Not relevant"})
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_legacy_ignore_action_maps_to_rejected(client, db_session):
    message = _make_outreach(db_session, status="PENDING_APPROVAL")
    response = client.post(f"/api/acquisition/outreach/{message.id}/action", json={"action": "ignore"})
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_restrict_organizer_action_blocks_future_outreach(client, db_session):
    message = _make_outreach(db_session, status="PENDING_APPROVAL")
    response = client.post(f"/api/acquisition/outreach/{message.id}/action", json={"action": "restrict_organizer"})
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    organizer = db_session.get(DiscoveredOrganizer, message.organizer_id)
    assert organizer.blocked is True


def test_opt_out_action_suppresses_the_contact(client, db_session):
    message = _make_outreach(db_session, status="DELIVERED", sent_at=datetime.now(timezone.utc))
    response = client.post(f"/api/acquisition/outreach/{message.id}/action", json={"action": "opt_out", "reason": "unsubscribe"})
    assert response.status_code == 200
    assert response.json()["status"] == "OPTED_OUT"

    from backend.services.social_agent.outreach import suppression
    assert suppression.is_suppressed(db_session, "hello@puneriders.test") is True


def test_stats_endpoint(client, db_session):
    _make_outreach(db_session, status="DELIVERED", sent_at=datetime.now(timezone.utc))
    _make_outreach(db_session, status="APPROVED", failure_reason="SMTP send failed: connection refused")
    response = client.get("/api/acquisition/outreach/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["eventsFound"] == 2
    assert body["messagesSent"] == 1
    assert body["failedMessages"] == 1
    assert body["emailProviderStatus"] == "NOT_CONFIGURED"


def test_process_followups_endpoint_runs(client, db_session):
    response = client.post("/api/acquisition/outreach/process-followups")
    assert response.status_code == 200
    body = response.json()
    assert body["followUpsDrafted"] == 0


def test_batch_run_requires_ai_configured(client, db_session, monkeypatch):
    from tests.conftest import FakeAIClient

    monkeypatch.setattr("backend.services.social_agent.outreach.orchestrator.get_ai_client", lambda: FakeAIClient(configured=False))
    response = client.post("/api/acquisition/outreach/batch-run", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["drafted"] == 0


def test_outreach_routes_require_admin(db_session):
    app = FastAPI()
    app.include_router(outreach_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as unauthenticated_client:
        assert unauthenticated_client.get("/api/acquisition/outreach").status_code == 401
