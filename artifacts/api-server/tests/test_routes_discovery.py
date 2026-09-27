"""HTTP-layer tests for the Event Discovery Agent admin routes — same
minimal standalone-app pattern as `test_routes_outreach.py`, but this
router requires ADMIN auth (unlike acquisition/outreach today), so these
tests also cover the 401/403 gate."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer, User
from backend.routes import discovery as discovery_routes


def _admin_user() -> User:
    return User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")


def _regular_user() -> User:
    return User(id=2, name="Attendee", email="attendee@100times.test", password_hash="x", role="USER")


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin_user
    return TestClient(app)


def test_discovery_routes_require_authentication():
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    with TestClient(app) as unauthenticated_client:
        assert unauthenticated_client.get("/api/discovery/runs").status_code == 401
        assert unauthenticated_client.post("/api/discovery/run").status_code == 401


def test_discovery_routes_reject_non_admin(db_session):
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _regular_user
    with TestClient(app) as non_admin_client:
        assert non_admin_client.get("/api/discovery/runs").status_code == 403


def test_trigger_run_without_api_key_fails_honestly(client, db_session, monkeypatch):
    from tests.conftest import FakeAIClient

    monkeypatch.setattr("backend.services.discovery_agent.orchestrator.get_ai_client", lambda: FakeAIClient(configured=False))

    response = client.post("/api/discovery/run", json={"cities": ["Pune"], "searchDepth": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["new_events"] == 0

    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "discovery").one()
    assert run.status == "failed"
    assert db_session.query(DiscoveredEvent).count() == 0


def test_auto_toggle_defaults_off_and_flips_live(client, db_session):
    from backend.core.config import get_settings

    status = client.get("/api/discovery/auto").json()
    assert status == {"enabled": False, "intervalMinutes": get_settings().discovery_scan_interval_minutes}

    on = client.patch("/api/discovery/auto", json={"enabled": True})
    assert on.status_code == 200
    assert on.json()["enabled"] is True
    assert client.get("/api/discovery/auto").json()["enabled"] is True  # persisted, visible to a fresh read

    off = client.patch("/api/discovery/auto", json={"enabled": False})
    assert off.json()["enabled"] is False
    assert client.get("/api/discovery/auto").json()["enabled"] is False


def test_auto_toggle_requires_admin():
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    with TestClient(app) as unauthenticated_client:
        assert unauthenticated_client.get("/api/discovery/auto").status_code == 401
        assert unauthenticated_client.patch("/api/discovery/auto", json={"enabled": True}).status_code == 401


def test_list_events_and_organizers(client, db_session):
    organizer = DiscoveredOrganizer(name="Pune Riders", email="hello@puneriders.test")
    db_session.add(organizer)
    db_session.flush()
    event = DiscoveredEvent(
        name="Pune Tech Summit", city="Pune", category="Technology", match_score=80,
        organizer_status="FOUND", organizer_id=organizer.id, discovered_by="web_discovery_agent",
        verification_status="VERIFIED",
    )
    db_session.add(event)
    db_session.flush()

    events_response = client.get("/api/discovery/events", params={"city": "pune"})
    assert events_response.status_code == 200
    assert len(events_response.json()) == 1
    assert events_response.json()[0]["name"] == "Pune Tech Summit"

    organizers_response = client.get("/api/discovery/organizers")
    assert organizers_response.status_code == 200
    assert len(organizers_response.json()) == 1
