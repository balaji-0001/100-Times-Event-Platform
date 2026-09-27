"""HTTP-layer tests for the approval/publish routes.

Everything else in this suite tests the pipeline/services directly; this
file drives the actual FastAPI route handlers over HTTP, with the DB
dependency overridden to the in-memory test session — a minimal standalone
app (just this one router) is used instead of importing `backend.main`, so
the real app's startup lifespan (schema creation + demo-data seeding
against the real dev database) is never triggered by a test run.
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.models import AcquisitionOpportunity, Discussion
from backend.routes import acquisition as acquisition_routes


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(acquisition_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _make_opportunity(db_session, seeded_catalog, platform="telegram", external_id="telegram_123_456") -> AcquisitionOpportunity:
    discussion = Discussion(
        community_id=seeded_catalog["community"].id,
        platform=platform,
        external_id=external_id,
        url="https://t.me/test/456",
        title="Any AI hackathons in Pune?",
        content="Looking for an AI hackathon in Pune.",
        intent_classification="HIGH_INTENT",
        intent_confidence=0.9,
        status="processed",
        pipeline_status="PENDING_APPROVAL",
    )
    db_session.add(discussion)
    db_session.flush()

    op = AcquisitionOpportunity(
        discussion_id=discussion.id,
        matching_events=[],
        relevance_score=90,
        generated_response="Check out the AI Builders Hackathon!",
        response_variations=["Check out the AI Builders Hackathon!"],
        approval_status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(op)
    db_session.commit()
    db_session.refresh(op)
    return op


def test_approve_action_transitions_to_approved(client, db_session, seeded_catalog):
    op = _make_opportunity(db_session, seeded_catalog)

    response = client.post(f"/api/acquisition/opportunities/{op.id}/action", json={"action": "approve"})

    assert response.status_code == 200
    assert response.json()["approvalStatus"] == "approved"


def test_reject_action_transitions_to_rejected(client, db_session, seeded_catalog):
    op = _make_opportunity(db_session, seeded_catalog)

    response = client.post(f"/api/acquisition/opportunities/{op.id}/action", json={"action": "reject"})

    assert response.status_code == 200
    assert response.json()["approvalStatus"] == "rejected"


def test_invalid_transition_returns_400(client, db_session, seeded_catalog):
    op = _make_opportunity(db_session, seeded_catalog)
    client.post(f"/api/acquisition/opportunities/{op.id}/action", json={"action": "reject"})

    # Rejected is terminal — approving afterwards must fail, not silently succeed.
    response = client.post(f"/api/acquisition/opportunities/{op.id}/action", json={"action": "approve"})

    assert response.status_code == 400


def test_approve_and_publish_on_platform_with_no_real_publisher_enters_manual_mode(client, db_session, seeded_catalog):
    op = _make_opportunity(db_session, seeded_catalog, platform="discord", external_id="discord_abc")

    response = client.post(f"/api/acquisition/opportunities/{op.id}/action", json={"action": "approve_and_publish"})

    assert response.status_code == 200
    body = response.json()
    # Discord has no real publisher yet — approve_and_publish must not fake success.
    assert body["approvalStatus"] == "ready_for_manual_publishing"
    assert body["publishedUrl"] is None


def test_publish_before_approval_is_rejected(client, db_session, seeded_catalog):
    op = _make_opportunity(db_session, seeded_catalog)

    response = client.post(f"/api/acquisition/opportunities/{op.id}/publish")

    assert response.status_code == 400


def test_mark_published_requires_manual_publishing_mode_first(client, db_session, seeded_catalog):
    op = _make_opportunity(db_session, seeded_catalog, platform="discord", external_id="discord_xyz")

    # Straight to mark-published without ever calling /publish first.
    response = client.post(f"/api/acquisition/opportunities/{op.id}/mark-published", json={"publishedUrl": "https://discord.com/fake"})

    assert response.status_code == 400


def test_connector_status_reports_expected_vocabulary(client):
    response = client.get("/api/acquisition/connectors/status")

    assert response.status_code == 200
    statuses = {row["platform"]: row["status"] for row in response.json()}
    assert statuses["reddit"] == "APPROVAL_REQUIRED"
    assert statuses["instagram"] == "APPROVAL_REQUIRED"
    assert statuses["discord"] in ("MOCK", "REAL")  # REAL only if a real token happens to be set in this environment
