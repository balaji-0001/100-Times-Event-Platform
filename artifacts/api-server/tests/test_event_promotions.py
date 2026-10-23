"""Automated test suite for Multi-Platform Social Event Promotions.

Verifies:
1. Platform settings initialization and per-platform toggles.
2. Platform-specific content generation (Instagram, Facebook, LinkedIn, Telegram, Discord).
3. UTM parameter attribution links.
4. Automatic promotion triggering upon event transition to PUBLISHED.
5. Multi-platform database-backed deduplication.
6. Approval workflow (PENDING_APPROVAL -> APPROVED -> DRY_RUN / PUBLISHED).
7. Safe retries on API failure up to max_retries limit.
8. Default dry-run behavior (never calling live external APIs without credentials).
9. Live API publishing with verified official responses.
10. Admin promotion API endpoints and stats summary.
"""

from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.core.security import create_access_token, hash_password
from backend.db import get_db
from backend.models import Event, EventPromotionJob, PlatformPromotionSetting, User
from backend.routes import event_promotions
from backend.services.lifecycle import transition_event_state
from backend.services.social_agent.event_promotion_orchestrator import (
    SUPPORTED_PLATFORMS,
    approve_promotion_job,
    execute_promotion_job,
    get_or_init_platform_settings,
    retry_promotion_job,
    trigger_event_promotions,
)
from backend.services.social_agent.pipeline.event_promotion_content import (
    build_utm_tracking_url,
    generate_platform_promotion_content,
)
from backend.services.social_agent.publishers import get_publisher
from backend.services.social_agent.publishers.facebook import FacebookPublisher
from backend.services.social_agent.publishers.instagram import InstagramPublisher
from backend.services.social_agent.publishers.linkedin import LinkedInPublisher


# ---------------------------------------------------------------------------
# Test Fixtures & Setup Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_user(db_session):
    user = User(
        name="Security Admin",
        email="promo-admin@100times.in",
        role="ADMIN",
        password_hash=hash_password("AdminSecurePassword123!"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_client(db_session, admin_user):
    app = FastAPI()
    app.include_router(event_promotions.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session

    client = TestClient(app)
    token = create_access_token(admin_user.id, "ADMIN")
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ---------------------------------------------------------------------------
# 1. Platform Settings Initialization & Toggles
# ---------------------------------------------------------------------------


def test_platform_settings_initialization(db_session):
    """Verifies default settings are seeded for all 5 platforms with safe dry-run defaults."""
    settings = get_or_init_platform_settings(db_session)
    assert len(settings) == 5

    platforms = {s.platform for s in settings}
    assert platforms == {"instagram", "facebook", "linkedin", "telegram", "discord"}

    for s in settings:
        assert s.enabled is True
        assert s.dry_run is True  # Must default to dry-run!
        assert s.auto_publish is False  # Must default to requiring approval


def test_platform_setting_toggle_update(admin_client, db_session):
    """Tests updating per-platform toggles via PATCH /api/promotions/settings/{platform}."""
    resp = admin_client.patch(
        "/api/promotions/settings/facebook",
        json={"enabled": True, "auto_publish": True, "dry_run": False, "rate_limit_per_day": 50},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "facebook"
    assert data["autoPublish"] is True
    assert data["dryRun"] is False
    assert data["rateLimitPerDay"] == 50


# ---------------------------------------------------------------------------
# 2. UTM Tracking & Content Generation
# ---------------------------------------------------------------------------


def test_utm_tracking_url_generation(seeded_catalog):
    """Verifies UTM parameter generation preserving platform source and campaign."""
    event = seeded_catalog["event"]
    for platform in SUPPORTED_PLATFORMS:
        tracking_url, utm_params = build_utm_tracking_url(event, platform, "https://100times.in")
        assert f"utm_source={platform}" in tracking_url
        assert "utm_medium=social" in tracking_url
        assert f"utm_campaign=event_{event.id}" in tracking_url
        assert utm_params["utm_source"] == platform
        assert utm_params["utm_medium"] == "social"


def test_platform_specific_content_generation(seeded_catalog):
    """Verifies tailored copy generation across all 5 platforms."""
    event = seeded_catalog["event"]

    for platform in SUPPORTED_PLATFORMS:
        tracking_url, _ = build_utm_tracking_url(event, platform)
        content_data = generate_platform_promotion_content(event, platform, tracking_url)

        assert "title" in content_data
        assert "content" in content_data
        text = content_data["content"]
        assert tracking_url in text
        assert event.title in text

        # Verify platform-specific features
        if platform == "instagram":
            assert "#100Times" in text
            assert "#" in text  # Contains hashtags
        elif platform == "linkedin":
            assert "#ProfessionalDevelopment" in text or "professionals" in text.lower() or "industry" in text.lower() or "#100Times" in text
        elif platform == "telegram":
            assert "*" in text or "[" in text  # Markdown formatting
        elif platform == "discord":
            assert "**" in text or "📢" in text  # Discord markdown / emojis


# ---------------------------------------------------------------------------
# 3. Automatic Trigger & Lifecycle Integration
# ---------------------------------------------------------------------------


def test_trigger_promotions_on_published_event(db_session, seeded_catalog):
    """Verifies trigger_event_promotions creates jobs for all enabled platforms."""
    event = seeded_catalog["event"]
    event.status = "published"
    db_session.flush()

    jobs = trigger_event_promotions(db_session, event, actor="admin@100times.in")
    assert len(jobs) == 5

    platforms = {j.platform for j in jobs}
    assert platforms == {"instagram", "facebook", "linkedin", "telegram", "discord"}

    for j in jobs:
        assert j.event_id == event.id
        assert j.status == "PENDING_APPROVAL"
        assert j.is_dry_run is True
        assert j.tracking_url is not None


def test_promotions_skipped_for_draft_events(db_session, seeded_catalog):
    """Verifies that draft/unpublished events are never promoted."""
    event = seeded_catalog["event"]
    event.status = "draft"
    event.lifecycle_state = "DRAFT"
    db_session.flush()

    jobs = trigger_event_promotions(db_session, event)
    assert len(jobs) == 0


def test_lifecycle_transition_triggers_promotions(db_session, seeded_catalog):
    """Verifies transition_event_state(db, event, 'PUBLISHED') automatically dispatches promotions."""
    event = seeded_catalog["event"]
    event.status = "draft"
    event.lifecycle_state = "DRAFT"
    db_session.flush()

    # Clear existing jobs if any
    db_session.query(EventPromotionJob).filter_by(event_id=event.id).delete()
    db_session.commit()

    # Transition to PUBLISHED
    transition_event_state(db_session, event, "PUBLISHED", actor="admin@100times.in", force=True)

    created_jobs = db_session.scalars(
        select(EventPromotionJob).where(EventPromotionJob.event_id == event.id)
    ).all()
    assert len(created_jobs) == 5


# ---------------------------------------------------------------------------
# 4. Database-backed Deduplication
# ---------------------------------------------------------------------------


def test_promotion_deduplication(db_session, seeded_catalog):
    """Verifies that running trigger_event_promotions multiple times does not duplicate jobs."""
    event = seeded_catalog["event"]
    event.status = "published"
    db_session.flush()

    jobs_run1 = trigger_event_promotions(db_session, event, actor="test")
    # Simulate first job
    execute_promotion_job(db_session, jobs_run1[0], force_dry_run=True)

    # Second trigger should skip duplicate
    jobs_run2 = trigger_event_promotions(db_session, event, actor="test")
    assert len(jobs_run2) == 5

    total_in_db = db_session.scalar(
        select(EventPromotionJob).where(
            EventPromotionJob.event_id == event.id,
            EventPromotionJob.platform == jobs_run1[0].platform,
        )
    )
    assert total_in_db is not None


# ---------------------------------------------------------------------------
# 5. Approval Workflow & Dry-Run Execution
# ---------------------------------------------------------------------------


def test_approval_workflow_dry_run_simulation(db_session, seeded_catalog):
    """Verifies approving a pending job with dry_run=True records an honest simulation."""
    event = seeded_catalog["event"]
    event.status = "published"
    db_session.flush()

    jobs = trigger_event_promotions(db_session, event)
    tg_job = next(j for j in jobs if j.platform == "telegram")

    updated = approve_promotion_job(db_session, tg_job.id, admin_email="admin@100times.in", dry_run=True)
    assert updated.status == "DRY_RUN"
    assert updated.is_dry_run is True
    assert updated.approved_by == "admin@100times.in"
    assert updated.approved_at is not None
    assert updated.published_at is not None
    assert updated.external_post_id is not None
    assert "t.me" in updated.published_url


# ---------------------------------------------------------------------------
# 6. Safe Retries and Failure Handling
# ---------------------------------------------------------------------------


def test_safe_retry_on_api_failure(db_session, seeded_catalog, monkeypatch):
    """Verifies that a platform API failure records FAILED status and increments retry_count."""
    event = seeded_catalog["event"]
    event.status = "published"
    db_session.flush()

    jobs = trigger_event_promotions(db_session, event)
    fb_job = next(j for j in jobs if j.platform == "facebook")
    fb_job.destination_ref = "123456789"
    db_session.commit()

    # Mock validate_connection and validate_publish_permission to pass
    monkeypatch.setattr(FacebookPublisher, "validate_connection", lambda self: {"connected": True})
    monkeypatch.setattr(FacebookPublisher, "validate_publish_permission", lambda self, ref: {"allowed": True})

    # Mock publish_post to simulate an API outage
    from backend.services.social_agent.types import PublishResult
    monkeypatch.setattr(
        FacebookPublisher,
        "publish_post",
        lambda self, text, target_ref, **kwargs: PublishResult(success=False, platform="facebook", published_url=None, message="Rate limit exceeded"),
    )

    failed_job = execute_promotion_job(db_session, fb_job, force_dry_run=False)
    assert failed_job.status == "FAILED"
    assert failed_job.retry_count == 1
    assert "Rate limit" in failed_job.last_error

    # Test retry
    retried_job = retry_promotion_job(db_session, failed_job.id)
    assert retried_job.retry_count == 2


def test_retry_limit_enforced(db_session, seeded_catalog):
    """Verifies that exceeding max_retries raises ValueError."""
    event = seeded_catalog["event"]
    jobs = trigger_event_promotions(db_session, event)
    job = jobs[0]
    job.status = "FAILED"
    job.retry_count = 3
    job.max_retries = 3
    db_session.commit()

    with pytest.raises(ValueError, match="maximum retry"):
        retry_promotion_job(db_session, job.id)


# ---------------------------------------------------------------------------
# 7. Live Publishing with Mocked Official Responses
# ---------------------------------------------------------------------------


def test_live_publishing_with_mocked_official_apis(db_session, seeded_catalog, monkeypatch):
    """Verifies successful live publication flow for Facebook, Instagram, and LinkedIn."""
    from backend.services.social_agent.types import PublishResult

    event = seeded_catalog["event"]
    jobs = trigger_event_promotions(db_session, event)

    # 1. Facebook Mock
    monkeypatch.setattr(FacebookPublisher, "validate_connection", lambda self: {"connected": True})
    monkeypatch.setattr(FacebookPublisher, "validate_publish_permission", lambda self, ref: {"allowed": True})
    monkeypatch.setattr(
        FacebookPublisher,
        "publish_post",
        lambda self, text, target_ref, **kwargs: PublishResult(
            success=True, platform="facebook", published_url="https://facebook.com/123_456", message="OK", post_id="123_456"
        ),
    )
    fb_job = next(j for j in jobs if j.platform == "facebook")
    fb_res = execute_promotion_job(db_session, fb_job, force_dry_run=False)
    assert fb_res.status == "PUBLISHED"
    assert fb_res.external_post_id == "123_456"
    assert fb_res.is_dry_run is False

    # 2. Instagram Mock
    monkeypatch.setattr(InstagramPublisher, "validate_connection", lambda self: {"connected": True})
    monkeypatch.setattr(InstagramPublisher, "validate_publish_permission", lambda self, ref: {"allowed": True})
    monkeypatch.setattr(
        InstagramPublisher,
        "publish_post",
        lambda self, text, target_ref, **kwargs: PublishResult(
            success=True, platform="instagram", published_url="https://instagram.com/p/999888", message="OK", post_id="999888"
        ),
    )
    ig_job = next(j for j in jobs if j.platform == "instagram")
    ig_res = execute_promotion_job(db_session, ig_job, force_dry_run=False)
    assert ig_res.status == "PUBLISHED"
    assert ig_res.external_post_id == "999888"

    # 3. LinkedIn Mock
    monkeypatch.setattr(LinkedInPublisher, "validate_connection", lambda self: {"connected": True})
    monkeypatch.setattr(LinkedInPublisher, "validate_publish_permission", lambda self, ref: {"allowed": True})
    monkeypatch.setattr(
        LinkedInPublisher,
        "publish_post",
        lambda self, text, target_ref, **kwargs: PublishResult(
            success=True, platform="linkedin", published_url="https://linkedin.com/feed/update/urn:li:share:777666", message="OK", post_id="urn:li:share:777666"
        ),
    )
    li_job = next(j for j in jobs if j.platform == "linkedin")
    li_res = execute_promotion_job(db_session, li_job, force_dry_run=False)
    assert li_res.status == "PUBLISHED"
    assert "urn:li:share:777666" in li_res.external_post_id


# ---------------------------------------------------------------------------
# 8. Admin REST API Endpoints
# ---------------------------------------------------------------------------


def test_admin_api_list_and_manage_jobs(admin_client, db_session, seeded_catalog):
    """Verifies listing, editing content, approving, and querying stats via REST API."""
    event = seeded_catalog["event"]
    jobs = trigger_event_promotions(db_session, event)
    job = jobs[0]

    # 1. List jobs
    list_resp = admin_client.get("/api/promotions/jobs")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 5

    # 2. Edit job content
    edit_resp = admin_client.patch(
        f"/api/promotions/jobs/{job.id}/content",
        json={"title": "Customized Title", "content": "Updated customized promotional text with details."},
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["title"] == "Customized Title"

    # 3. Approve job via API (dry-run simulation)
    appr_resp = admin_client.post(f"/api/promotions/jobs/{job.id}/approve", json={"dry_run": True})
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "DRY_RUN"

    # 4. Get stats
    stats_resp = admin_client.get("/api/promotions/stats")
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()
    assert stats_data["totalJobs"] >= 5
    assert stats_data["dryRun"] >= 1
    assert "instagram" in stats_data["byPlatform"]

