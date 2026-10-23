"""HTTP-layer tests for the Automation Requests queue — same minimal
standalone-app pattern as `test_routes_discovery.py`/`test_routes_outreach.py`."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import User
from backend.routes import automations as automations_routes


def _admin_user() -> User:
    return User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")


def _regular_user() -> User:
    return User(id=2, name="Attendee", email="attendee@100times.test", password_hash="x", role="USER")


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(automations_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin_user
    return TestClient(app)


def test_create_and_list_automation_request(client):
    assert client.get("/api/automations/requests").json() == []

    created = client.post("/api/automations/requests", json={"description": "Automatically restrict organizers who bounce 3+ times."})
    assert created.status_code == 201
    body = created.json()
    assert body["description"] == "Automatically restrict organizers who bounce 3+ times."
    assert body["status"] == "NEW"
    assert body["requestedBy"] == "admin@100times.test"
    assert body["note"] is None

    listed = client.get("/api/automations/requests").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_create_rejects_too_short_description(client):
    response = client.post("/api/automations/requests", json={"description": "short"})
    assert response.status_code == 422


def test_update_status_sets_status_and_note(client):
    created = client.post("/api/automations/requests", json={"description": "Auto-tag events by category keyword."}).json()

    updated = client.patch(f"/api/automations/requests/{created['id']}", params={"new_status": "IN_PROGRESS", "note": "Picked up, scoping it now."})
    assert updated.status_code == 200
    body = updated.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["note"] == "Picked up, scoping it now."


def test_update_status_rejects_unknown_status(client):
    created = client.post("/api/automations/requests", json={"description": "Auto-tag events by category keyword."}).json()

    response = client.patch(f"/api/automations/requests/{created['id']}", params={"new_status": "MAYBE"})
    assert response.status_code == 400


def test_update_status_404_for_missing_request(client):
    response = client.patch("/api/automations/requests/999999", params={"new_status": "DONE"})
    assert response.status_code == 404


def test_automation_requests_require_admin(db_session):
    app = FastAPI()
    app.include_router(automations_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as unauthenticated_client:
        assert unauthenticated_client.get("/api/automations/requests").status_code == 401
        assert unauthenticated_client.post("/api/automations/requests", json={"description": "x" * 20}).status_code == 401


def test_automation_requests_reject_non_admin(db_session):
    app = FastAPI()
    app.include_router(automations_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _regular_user
    with TestClient(app) as non_admin_client:
        assert non_admin_client.get("/api/automations/requests").status_code == 403
