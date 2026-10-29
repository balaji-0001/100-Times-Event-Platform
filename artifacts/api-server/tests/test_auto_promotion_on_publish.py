"""Social promotion runs whenever an event is published — including from the
admin Events page — and event pictures are sent as full web addresses."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import User
from backend.routes import dashboard as dashboard_routes
from backend.services.social_agent import event_promotion_orchestrator
from backend.services.social_agent.pipeline import event_promotion_content


def test_admin_publish_triggers_social_promotion(db_session, seeded_catalog, monkeypatch):
    calls = []
    monkeypatch.setattr(event_promotion_orchestrator, "trigger_event_promotions", lambda db, event, actor="system", **k: calls.append((event.id, actor)) or [])
    event = seeded_catalog["event"]
    event.status, event.lifecycle_state = "draft", "DRAFT"
    db_session.commit()

    app = FastAPI()
    app.include_router(dashboard_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: User(id=99, name="Admin", email="admin@100times.io", role="ADMIN", password_hash="h")
    resp = TestClient(app).patch(f"/api/admin/events/{event.id}/status", json={"status": "published"})

    assert resp.status_code == 200 and resp.json()["status"] == "published"
    assert calls == [(event.id, "admin@100times.io")]
    db_session.refresh(event)
    assert event.lifecycle_state == "PUBLISHED"


def test_event_pictures_become_full_web_addresses(monkeypatch):
    monkeypatch.setattr(event_promotion_content, "get_settings", lambda: SimpleNamespace(public_base_url=None, platform_listing_url="https://100times.in/"))
    media = event_promotion_content.public_media
    assert media(SimpleNamespace(image="/event-images/technology/3.jpg")) == ["https://100times.in/event-images/technology/3.jpg"]
    assert media(SimpleNamespace(image="https://images.example.com/a.jpg")) == ["https://images.example.com/a.jpg"]
    assert media(SimpleNamespace(image=None)) == []
    monkeypatch.setattr(event_promotion_content, "get_settings", lambda: SimpleNamespace(public_base_url=None, platform_listing_url=""))
    assert media(SimpleNamespace(image="/uploads/x.jpg")) == []  # no public site: no address to give
