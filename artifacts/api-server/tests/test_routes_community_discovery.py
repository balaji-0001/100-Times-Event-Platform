"""HTTP-layer tests for the Community Discovery Agent admin routes — same
minimal standalone-app pattern as `test_routes_discovery.py`."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import AgentRun, Community, DiscoveredCommunity, User
from backend.routes import community_discovery as community_discovery_routes


def _admin_user() -> User:
    return User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")


def _regular_user() -> User:
    return User(id=2, name="Attendee", email="attendee@100times.test", password_hash="x", role="USER")


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(community_discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin_user
    return TestClient(app)


def _seed_community(db_session, **overrides) -> DiscoveredCommunity:
    values = dict(
        platform="telegram", name="Pune Tech Talks", canonical_url="https://t.me/punetechtalks",
        description="Tech meetups in Pune.", category="Technology", member_count=500,
        confidence_score=70, approval_status="DISCOVERED",
    )
    values.update(overrides)
    community = DiscoveredCommunity(**values)
    db_session.add(community)
    db_session.commit()
    db_session.refresh(community)
    return community


def test_community_discovery_routes_require_authentication():
    app = FastAPI()
    app.include_router(community_discovery_routes.router, prefix="/api")
    with TestClient(app) as unauthenticated_client:
        assert unauthenticated_client.get("/api/community-discovery/communities").status_code == 401
        assert unauthenticated_client.post("/api/community-discovery/run").status_code == 401


def test_community_discovery_routes_reject_non_admin(db_session):
    app = FastAPI()
    app.include_router(community_discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _regular_user
    with TestClient(app) as non_admin_client:
        assert non_admin_client.get("/api/community-discovery/communities").status_code == 403


def test_trigger_run_needs_no_ai_key(client, db_session):
    response = client.post("/api/community-discovery/run", json={"cities": ["Pune"], "searchDepth": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "community_discovery").one()
    assert run.status == "completed"


def test_auto_toggle_defaults_off_and_flips_live(client, db_session):
    from backend.core.config import get_settings

    settings = get_settings()
    status = client.get("/api/community-discovery/auto").json()
    assert status == {"enabled": False, "intervalMinutes": settings.community_discovery_scan_interval_minutes}

    on = client.patch("/api/community-discovery/auto", json={"enabled": True})
    assert on.status_code == 200
    assert on.json()["enabled"] is True
    assert client.get("/api/community-discovery/auto").json()["enabled"] is True

    off = client.patch("/api/community-discovery/auto", json={"enabled": False})
    assert off.json()["enabled"] is False


def test_list_and_filter_communities(client, db_session):
    _seed_community(db_session, name="Pune Tech Talks", platform="telegram", city="Pune")
    _seed_community(db_session, name="Blr Builders", platform="discord", canonical_url="https://discord.gg/blrbuilders", city="Bengaluru")

    all_rows = client.get("/api/community-discovery/communities").json()
    assert len(all_rows) == 2

    telegram_only = client.get("/api/community-discovery/communities", params={"platform": "telegram"}).json()
    assert len(telegram_only) == 1 and telegram_only[0]["name"] == "Pune Tech Talks"

    pune_only = client.get("/api/community-discovery/communities", params={"city": "Pune"}).json()
    assert len(pune_only) == 1


def test_get_community_detail_and_404(client, db_session):
    community = _seed_community(db_session)
    found = client.get(f"/api/community-discovery/communities/{community.id}")
    assert found.status_code == 200 and found.json()["name"] == "Pune Tech Talks"
    assert client.get("/api/community-discovery/communities/999999").status_code == 404


def test_approve_action_materializes_a_real_community(client, db_session):
    community = _seed_community(db_session)

    response = client.post(f"/api/community-discovery/communities/{community.id}/action", json={"action": "approve"})
    assert response.status_code == 200
    body = response.json()
    assert body["approvalStatus"] == "APPROVED"
    assert body["connectionStatus"] == "CONNECTION_REQUIRED"
    assert body["communityId"] is not None

    real = db_session.get(Community, body["communityId"])
    assert real is not None
    assert real.name == "Pune Tech Talks"
    assert real.promotion_allowed is False  # approving the lead never auto-grants promotion permission
    assert real.automation_allowed is False
    assert real.discovered_community_id == community.id


def test_reject_action_records_reason(client, db_session):
    community = _seed_community(db_session)

    response = client.post(f"/api/community-discovery/communities/{community.id}/action", json={"action": "reject", "reason": "Not relevant to our categories"})
    assert response.status_code == 200
    body = response.json()
    assert body["approvalStatus"] == "REJECTED"
    assert body["rejectionReason"] == "Not relevant to our categories"


def test_action_writes_an_audit_log(client, db_session):
    from backend.models import AuditLog

    community = _seed_community(db_session)
    client.post(f"/api/community-discovery/communities/{community.id}/action", json={"action": "approve"})

    entry = db_session.query(AuditLog).filter(AuditLog.entity == "DiscoveredCommunity", AuditLog.entity_id == str(community.id)).one()
    assert entry.action == "COMMUNITY_APPROVE"
    assert entry.actor == "admin@100times.test"


def test_action_404_for_missing_community(client):
    assert client.post("/api/community-discovery/communities/999999/action", json={"action": "approve"}).status_code == 404


def test_stats_reflect_real_counts(client, db_session):
    _seed_community(db_session, name="A", platform="telegram", approval_status="NEEDS_REVIEW")
    _seed_community(db_session, name="B", platform="discord", canonical_url="https://discord.gg/b", approval_status="APPROVED")

    stats = client.get("/api/community-discovery/stats").json()
    assert stats["communitiesTotal"] == 2
    assert stats["needsReviewTotal"] == 1
    assert stats["approvedTotal"] == 1
    assert stats["telegramTotal"] == 1
    assert stats["discordTotal"] == 1
