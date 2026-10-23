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


def test_trigger_run_needs_no_ai_key(client, db_session, monkeypatch):
    """The automation runs on fixed rules: no AI key, nothing found (hermetic test),
    and the run still completes cleanly."""
    monkeypatch.setattr("backend.services.discovery_agent.web_search.search", lambda *args, **kwargs: [])
    monkeypatch.setattr("backend.services.discovery_agent.listing_sources.build_listing_urls", lambda *args, **kwargs: [])
    response = client.post("/api/discovery/run", json={"cities": ["Pune"], "searchDepth": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["new_events"] == 0

    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "discovery").one()
    assert run.status == "completed"
    assert db_session.query(DiscoveredEvent).count() == 0

def test_auto_toggle_defaults_off_and_flips_live(client, db_session):
    from backend.core.config import get_settings

    status = client.get("/api/discovery/auto").json()
    assert status["enabled"] is False
    assert status["intervalMinutes"] == get_settings().discovery_scan_interval_minutes

    on = client.patch("/api/discovery/auto", json={"enabled": True})
    assert on.status_code == 200
    assert on.json()["enabled"] is True
    assert client.get("/api/discovery/auto").json()["enabled"] is True  # persisted, visible to a fresh read

    # Test updating scope settings with multi-country and state checklists
    configured = client.patch(
        "/api/discovery/auto",
        json={
            "country": "India",
            "countries": ["India", "Dubai", "United States"],
            "states": ["Maharashtra", "Dubai Emirate", "California"],
            "categories": ["Healthcare", "Finance"],
            "cities": ["Pune", "Mumbai", "Dubai", "San Francisco"],
        }
    )
    assert configured.status_code == 200
    conf_data = configured.json()
    assert conf_data["country"] == "India"
    assert conf_data["countries"] == ["India", "Dubai", "United States"]
    assert "Maharashtra" in conf_data["states"]
    assert "Dubai Emirate" in conf_data["states"]
    assert "Healthcare" in conf_data["categories"]
    assert "Pune" in conf_data["cities"]
    assert "Dubai" in conf_data["cities"]

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


def test_stats_reflects_real_counts_beyond_the_list_endpoints_cap(client, db_session):
    """`/events` and `/organizers` cap at 200 rows for the browsing table —
    `/stats` must report true totals that keep growing past that cap, since
    the console's overview numbers are computed from this endpoint, not by
    counting a capped list client-side."""
    from backend.models import DiscoveredEvent, DiscoveredOrganizer, OrganizerContact

    organizer = DiscoveredOrganizer(name="Pune Riders Collective", email="hello@puneriders.test")
    db_session.add(organizer)
    db_session.flush()
    db_session.add(OrganizerContact(discovered_organizer_id=organizer.id, contact_type="email", value="hello@puneriders.test"))

    # 205 events — past the 200-row list cap — mixed verification/format so every bucket is exercised.
    for i in range(205):
        db_session.add(DiscoveredEvent(
            name=f"Event {i}", city="Pune", category="Technology",
            organizer_id=organizer.id if i == 0 else None,
            organizer_status="FOUND" if i == 0 else "NOT_FOUND",
            discovered_by="web_discovery_agent",
            verification_status="NEEDS_REVIEW" if i % 2 == 0 else "VERIFIED",
            event_format="offline" if i % 3 == 0 else ("online" if i % 3 == 1 else "hybrid"),
            venue=None if i % 3 == 0 else "Some Venue",  # offline rows (i%3==0) are missing a venue
        ))
    db_session.commit()

    stats = client.get("/api/discovery/stats")
    assert stats.status_code == 200
    body = stats.json()

    assert body["eventsTotal"] == 205  # past the 200-row list-endpoint cap
    assert body["organizersTotal"] == 1
    assert body["contactsTotal"] == 1
    assert body["organizersWithEmailTotal"] == 1
    assert body["needsReviewTotal"] == 103  # i % 2 == 0 for i in 0..204
    assert body["newEventsTotal"] == 205  # every row defaults to discovery_status="NEW"
    assert body["offlineTotal"] == 69  # i % 3 == 0
    assert body["onlineTotal"] == 68  # i % 3 == 1
    assert body["hybridTotal"] == 68  # i % 3 == 2
    assert body["venueMissingTotal"] == 69  # the offline rows, all missing a venue
    assert len(body["venueMissingSample"]) == 5  # sample capped, not the full count
    capped_list = client.get("/api/discovery/events", params={"limit": 200})
    assert len(capped_list.json()) < body["eventsTotal"]  # proves the list IS capped while stats isn't


def test_stats_requires_admin():
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    with TestClient(app) as unauthenticated_client:
        assert unauthenticated_client.get("/api/discovery/stats").status_code == 401
