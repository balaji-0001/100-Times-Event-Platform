"""Rejected events can be kept for review: with "keep rejected events" on, a
run stores what it turned down (with the reason) instead of dropping it, a
later run whose rules the event passes upgrades that same row, and an admin
can restore, approve or reject any event by hand."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import DiscoveredEvent, User
from backend.routes import discovery as discovery_routes
from backend.services.discovery_agent import orchestrator
from backend.services.discovery_agent.types import DiscoveryConfig, OrganizerCandidate
from tests.test_discovery_pipeline import _candidate, _off_sector, _wire
from tests.test_discovery_scope_rules import _event


def _run_with_contacts(db_session, monkeypatch, *, keep, require_email):
    """Two Munich construction fairs; only the first organizer published an e-mail."""
    with_contact = _event("With Contact Expo 1", "Munich", "Germany", 1)
    without = _event("No Contact Expo 2", "Munich", "Germany", 2)
    _wire(monkeypatch, {"https://results.test/0": [with_contact, without]}, queries=[])
    monkeypatch.setattr(orchestrator.organizer_identifier, "identify_organizer", lambda c: OrganizerCandidate(
        found="With" in c.name, name="Fair Org GmbH", email="info@fair-org.test" if "With" in c.name else None,
        website="https://fair-org.test", confidence_score=70, sources=[c.primary_source],
        email_source_url="https://fair-org.test/contact" if "With" in c.name else None,
    ))
    config = DiscoveryConfig(countries=["Germany"], locations=[{"country": "Germany", "city": "Munich"}], cities=["Munich"], categories=["Construction"],
                             sources=["web"], search_depth=1, sources_per_query=2, require_organizer_email=require_email,
                             reject_no_organizer=require_email, reject_unmatched_category=True, fallback_to_other_sector=False,
                             min_confidence_score=0, keep_rejected_events=keep)
    return orchestrator.run_discovery_agent(db_session, config)


def _by_name(db_session):
    return {e.name: e for e in db_session.query(DiscoveredEvent).all()}


@pytest.mark.parametrize("keep", [True, False])
def test_events_without_an_organizer_email_are_kept_as_rejected_only_when_asked(db_session, monkeypatch, keep):
    summary = _run_with_contacts(db_session, monkeypatch, keep=keep, require_email=True)

    events = _by_name(db_session)
    assert events["With Contact Expo 1"].verification_status == "VERIFIED"
    assert summary.missing_organizer_email == 1
    if keep:
        kept = events["No Contact Expo 2"]
        assert kept.verification_status == "REJECTED" and kept.discovery_status == "REJECTED"
        assert "REJECTION_REASON: MISSING_ORGANIZER_EMAIL" in kept.verification_notes
    else:
        assert "No Contact Expo 2" not in events


@pytest.mark.parametrize("keep", [True, False])
def test_off_sector_events_with_a_real_sector_are_kept_but_sectorless_noise_is_not(db_session, monkeypatch, keep):
    pharma = _off_sector(1, "Pharma & Medical Devices Expo")
    pharma.event_description = "Exhibition for hospitals, pharma and healthcare suppliers."
    concert = _off_sector(2, "Music Performance by ADIGA")
    _wire(monkeypatch, {"https://results.test/0": [pharma, concert, _candidate(3)]}, queries=[])
    config = DiscoveryConfig(cities=["Pune"], categories=["Construction"], countries=["India"], country="India", sources=["web"], search_depth=1,
                             sources_per_query=2, listing_urls=[], require_organizer_email=True, reject_no_organizer=True,
                             reject_unmatched_category=True, fallback_to_other_sector=False, min_confidence_score=0, keep_rejected_events=keep)

    summary = orchestrator.run_discovery_agent(db_session, config)

    events = _by_name(db_session)
    assert events["Construction & Building Materials Expo 3"].verification_status == "VERIFIED"
    assert "Music Performance by ADIGA" not in events  # no sector of its own: never worth reviewing
    assert summary.unsupported_category == 2
    if keep:
        kept = events["Pharma & Medical Devices Expo"]
        assert kept.verification_status == "REJECTED" and kept.category != "Construction"
        assert "REJECTION_REASON: UNSUPPORTED_CATEGORY" in kept.verification_notes
        assert summary.verified_events == 1  # a kept rejection never counts toward the target
    else:
        assert set(events) == {"Construction & Building Materials Expo 3"}


def test_a_later_run_upgrades_a_previously_rejected_event_in_place(db_session, monkeypatch):
    _run_with_contacts(db_session, monkeypatch, keep=True, require_email=True)
    rejected = _by_name(db_session)["No Contact Expo 2"]
    rejected_id = rejected.id
    assert rejected.verification_status == "REJECTED"

    # Same event found again by a run that doesn't require an organizer e-mail.
    summary = _run_with_contacts(db_session, monkeypatch, keep=True, require_email=False)

    rows = db_session.query(DiscoveredEvent).filter(DiscoveredEvent.name == "No Contact Expo 2").all()
    assert [r.id for r in rows] == [rejected_id]  # upgraded, not duplicated
    upgraded = rows[0]
    assert upgraded.verification_status == "NEEDS_REVIEW" and upgraded.discovery_status != "REJECTED"
    assert any(n.startswith("Re-evaluated") and "MISSING_ORGANIZER_EMAIL" in n for n in upgraded.verification_notes)
    assert summary.duplicate_events == 1  # the already-verified one


def test_a_rejected_event_found_again_and_rejected_again_is_a_duplicate(db_session, monkeypatch):
    _run_with_contacts(db_session, monkeypatch, keep=True, require_email=True)
    summary = _run_with_contacts(db_session, monkeypatch, keep=True, require_email=True)

    assert db_session.query(DiscoveredEvent).filter(DiscoveredEvent.name == "No Contact Expo 2").count() == 1
    assert summary.duplicate_events == 2


# --- Admin review -------------------------------------------------------------------


def _admin_user() -> User:
    return User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin_user
    return TestClient(app)


def _rejected_event(db_session) -> DiscoveredEvent:
    event = DiscoveredEvent(name="Pharma Expo", city="Pune", country="India", category="Healthcare", verification_status="REJECTED",
                            discovery_status="REJECTED", discovered_by="web_discovery_agent",
                            verification_notes=["REJECTION_REASON: UNSUPPORTED_CATEGORY", "Its sector (Healthcare) is not one of the selected sectors (Construction)."])
    db_session.add(event)
    db_session.flush()
    return event


def test_admin_can_restore_approve_and_reject_an_event(client, db_session):
    event = _rejected_event(db_session)

    restored = client.post(f"/api/discovery/events/{event.id}/review", json={"action": "restore", "note": "Healthcare is fine too"})
    assert restored.status_code == 200, restored.text
    assert restored.json()["verificationStatus"] == "NEEDS_REVIEW"
    db_session.refresh(event)
    assert event.discovery_status == "NEW"
    assert "REJECTION_REASON: UNSUPPORTED_CATEGORY" in event.verification_notes  # why the agent rejected it stays visible
    assert any("admin@100times.test" in n and "Healthcare is fine too" in n for n in event.verification_notes)

    assert client.post(f"/api/discovery/events/{event.id}/review", json={"action": "approve"}).json()["verificationStatus"] == "VERIFIED"

    rejected = client.post(f"/api/discovery/events/{event.id}/review", json={"action": "reject"})
    assert rejected.json()["verificationStatus"] == "REJECTED"
    db_session.refresh(event)
    assert event.discovery_status == "REJECTED"


def test_admin_reject_of_a_never_rejected_event_records_the_reason(client, db_session):
    event = DiscoveredEvent(name="Fair", city="Pune", category="Construction", verification_status="VERIFIED", discovered_by="web_discovery_agent")
    db_session.add(event)
    db_session.flush()

    client.post(f"/api/discovery/events/{event.id}/review", json={"action": "reject"})

    db_session.refresh(event)
    assert event.verification_notes[0] == "REJECTION_REASON: ADMIN_REJECTED"


def test_review_validates_input_and_requires_admin(client, db_session):
    event = _rejected_event(db_session)
    assert client.post(f"/api/discovery/events/{event.id}/review", json={"action": "delete"}).status_code == 422
    assert client.post("/api/discovery/events/999999/review", json={"action": "restore"}).status_code == 404

    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: User(id=2, name="U", email="u@100times.test", password_hash="x", role="USER")
    assert TestClient(app).post(f"/api/discovery/events/{event.id}/review", json={"action": "restore"}).status_code == 403


def test_runs_left_running_by_a_restart_are_closed_at_startup(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from backend import db as backend_db, main
    from backend.models import AgentRun

    monkeypatch.setattr(backend_db, "SessionLocal", sessionmaker(bind=db_session.get_bind()))

    stale = AgentRun(agent_type="discovery", status="running", config_snapshot={}, summary={})
    done = AgentRun(agent_type="discovery", status="completed", config_snapshot={}, summary={})
    db_session.add_all([stale, done])
    db_session.commit()

    main._close_runs_interrupted_by_restart()

    db_session.expire_all()
    assert db_session.get(AgentRun, stale.id).status == "failed"
    assert db_session.get(AgentRun, stale.id).error == "Interrupted by a server restart"
    assert db_session.get(AgentRun, done.id).status == "completed"
