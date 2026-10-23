"""HTTP-layer tests for Agent 4's community-promotion extension: the thin
dedicated router (`/run`, `/auto`, `/runs`), and the shared opportunities
endpoints now correctly handling a `community_promotion`-origin row
(no discussion at all) — including the inner-join regression this feature
could have silently reintroduced."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import AcquisitionOpportunity, Category, Community, Event, Organizer, User
from backend.routes import acquisition as acquisition_routes
from backend.routes import community_promotion as community_promotion_routes
from tests.conftest import FakeAIClient


def _admin_user() -> User:
    return User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")


@pytest.fixture()
def promo_client(db_session):
    app = FastAPI()
    app.include_router(community_promotion_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin_user
    return TestClient(app)


@pytest.fixture()
def acquisition_client(db_session):
    app = FastAPI()
    app.include_router(acquisition_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin_user
    return TestClient(app)


def _seed_match(db_session, *, platform="telegram", platform_ref=None):
    cat = Category(name="Technology", slug="technology", description="Tech", icon="sparkles")
    db_session.add(cat)
    db_session.flush()
    org = Organizer(name="Organizer", slug="organizer-x", description="desc")
    db_session.add(org)
    db_session.flush()
    event = Event(
        title="AI Builders Meetup", slug="ai-builders-meetup", description="desc", event_type="Meetup",
        start_date=date.today() + timedelta(days=10), end_date=date.today() + timedelta(days=10),
        start_time="18:00", price=Decimal("0.00"), status="published", format="offline", city_name="Pune",
        category_id=cat.id, organizer_id=org.id,
    )
    db_session.add(event)
    community = Community(
        platform=platform, name="Pune Technology Hub", slug="pune-technology-hub", url="https://t.me/punetech",
        promotion_allowed=True, external_links_allowed=True, automation_allowed=False, risk_level="low",
        quality_score=80, platform_ref=platform_ref,
    )
    db_session.add(community)
    db_session.commit()
    return event, community


def test_community_promotion_routes_require_admin():
    app = FastAPI()
    app.include_router(community_promotion_routes.router, prefix="/api")
    with TestClient(app) as unauth:
        assert unauth.post("/api/community-promotion/run").status_code == 401


def test_trigger_run_drafts_without_ai(promo_client, db_session, monkeypatch):
    from backend.services.social_agent.pipeline import community_promotion as cp_module

    monkeypatch.setattr(cp_module, "get_ai_client", lambda: FakeAIClient(configured=False))
    _seed_match(db_session)

    response = promo_client.post("/api/community-promotion/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["drafted"] == 1


def test_auto_toggle_defaults_off_and_flips_live(promo_client, db_session):
    status = promo_client.get("/api/community-promotion/auto").json()
    assert status["enabled"] is False

    on = promo_client.patch("/api/community-promotion/auto", json={"enabled": True})
    assert on.json()["enabled"] is True
    assert promo_client.get("/api/community-promotion/auto").json()["enabled"] is True


# --- shared opportunities endpoints must handle a discussion-less row -----


def test_opportunities_list_includes_community_promotion_rows(acquisition_client, db_session, monkeypatch):
    """Regression test: `/opportunities` used to INNER JOIN on discussion,
    which would silently drop every community_promotion-origin row (no
    discussion_id at all) from the list."""
    from backend.services.social_agent.pipeline import community_promotion as cp_module
    from backend.services.social_agent.community_promotion_orchestrator import run_community_promotion_agent

    monkeypatch.setattr(cp_module, "get_ai_client", lambda: FakeAIClient(configured=False))
    _seed_match(db_session)
    run_community_promotion_agent(db_session)

    response = acquisition_client.get("/api/acquisition/opportunities")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["sourceKind"] == "community_promotion"
    assert rows[0]["discussion"] is None
    assert rows[0]["promotedEvent"]["title"] == "AI Builders Meetup"
    assert rows[0]["targetCommunity"]["name"] == "Pune Technology Hub"
    assert rows[0]["targetCommunity"]["connected"] is False


def test_opportunity_detail_serializes_community_promotion_fields(acquisition_client, db_session, monkeypatch):
    from backend.services.social_agent.pipeline import community_promotion as cp_module
    from backend.services.social_agent.community_promotion_orchestrator import run_community_promotion_agent

    monkeypatch.setattr(cp_module, "get_ai_client", lambda: FakeAIClient(configured=False))
    _seed_match(db_session)
    run_community_promotion_agent(db_session)
    op = db_session.query(AcquisitionOpportunity).one()

    response = acquisition_client.get(f"/api/acquisition/opportunities/{op.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["matchExplanation"]
    assert body["generatedResponse"]


def test_publish_without_platform_ref_fails_honestly_no_crash(acquisition_client, db_session, monkeypatch):
    from backend.services.social_agent.pipeline import community_promotion as cp_module
    from backend.services.social_agent.community_promotion_orchestrator import run_community_promotion_agent

    monkeypatch.setattr(cp_module, "get_ai_client", lambda: FakeAIClient(configured=False))
    _seed_match(db_session, platform_ref=None)  # community never connected
    run_community_promotion_agent(db_session)
    op = db_session.query(AcquisitionOpportunity).one()
    acquisition_client.post(f"/api/acquisition/opportunities/{op.id}/action", json={"action": "approve"})

    response = acquisition_client.post(f"/api/acquisition/opportunities/{op.id}/publish")

    assert response.status_code == 200
    body = response.json()
    assert body["approvalStatus"] == "ready_for_manual_publishing"
    assert body["publishedUrl"] is None


def test_publish_dispatches_to_publish_post_not_publish_reply(acquisition_client, db_session, monkeypatch):
    """A community-promotion publish must call the standalone `publish_post`
    path, never `publish_reply` (there's nothing to reply to)."""
    from backend.services.social_agent.pipeline import community_promotion as cp_module
    from backend.services.social_agent.community_promotion_orchestrator import run_community_promotion_agent
    from backend.services.social_agent.types import PublishResult

    monkeypatch.setattr(cp_module, "get_ai_client", lambda: FakeAIClient(configured=False))
    _seed_match(db_session, platform="telegram", platform_ref="telegram_12345")
    run_community_promotion_agent(db_session)
    op = db_session.query(AcquisitionOpportunity).one()
    acquisition_client.post(f"/api/acquisition/opportunities/{op.id}/action", json={"action": "approve"})

    calls = {"reply": 0, "post": 0}

    class FakePublisher:
        platform = "telegram"
        is_real = False  # skip connection/permission pre-checks, go straight to the publish call

        def publish_reply(self, text, target_ref):
            calls["reply"] += 1
            return PublishResult(success=True, platform="telegram", published_url="https://t.me/x/1", message="ok")

        def publish_post(self, text, target_ref):
            calls["post"] += 1
            assert target_ref == "telegram_12345"
            return PublishResult(success=True, platform="telegram", published_url="https://t.me/x/2", message="ok")

        def verify_publication(self, result):
            return result

    import backend.routes.acquisition as acquisition_module
    monkeypatch.setattr(acquisition_module, "get_publisher", lambda platform: FakePublisher())

    response = acquisition_client.post(f"/api/acquisition/opportunities/{op.id}/publish")

    assert response.status_code == 200
    assert response.json()["approvalStatus"] == "published"
    assert calls == {"reply": 0, "post": 1}


def test_click_tracking_works_for_community_promotion_opportunity(db_session, monkeypatch):
    """The existing `/r/{id}` redirect + ClickEvent mechanism needed zero
    changes for this agent — it already reads `matching_events` generically,
    which the community-promotion orchestrator populates the same way."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as TC
    from backend.routes import redirect as redirect_routes
    from backend.services.social_agent.pipeline import community_promotion as cp_module
    from backend.services.social_agent.community_promotion_orchestrator import run_community_promotion_agent
    from backend.models import ClickEvent

    monkeypatch.setattr(cp_module, "get_ai_client", lambda: FakeAIClient(configured=False))
    _seed_match(db_session)
    run_community_promotion_agent(db_session)
    op = db_session.query(AcquisitionOpportunity).one()

    app = FastAPI()
    app.include_router(redirect_routes.router)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TC(app, follow_redirects=False)

    response = client.get(f"/r/{op.id}")

    assert response.status_code == 302
    assert "ai-builders-meetup" in response.headers["location"]
    assert db_session.query(ClickEvent).filter(ClickEvent.opportunity_id == op.id).count() == 1
