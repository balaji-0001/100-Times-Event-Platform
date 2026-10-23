"""Unit and integration tests for Discovery Agent Event Discovery & Validation Rules:
- Dynamic category loading from database/website across all supported categories.
- Worldwide discovery across all countries and cities.
- Mandatory public organiser email address requirement (rejects missing, dummy, asset filenames, system mailboxes, phone-only).
- Required event data validation.
- Duplicate detection & quality checks.
- Rejection reason tracking and pipeline summary metrics.
"""

from datetime import date, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select

from backend.models import Category, DiscoveredEvent, DiscoveredOrganizer, Event, OrganizerContact
from backend.services.discovery_agent import categorizer, email_verifier, orchestrator, storage, validation
from backend.services.discovery_agent.types import (
    CandidateSource,
    DiscoveryConfig,
    ExtractedEventCandidate,
    OrganizerCandidate,
    RunSummary,
)


def test_email_verifier_rejects_missing_and_whitespace():
    assert email_verifier.is_valid_organizer_email(None)[0] is False
    assert email_verifier.is_valid_organizer_email("")[0] is False
    assert email_verifier.is_valid_organizer_email("   ")[0] is False


def test_email_verifier_validates_clean_and_normalizes():
    valid, norm, err = email_verifier.is_valid_organizer_email("  Events.Team@ConferenceHub.org  ")
    assert valid is True
    assert norm == "events.team@conferencehub.org"
    assert err is None


def test_email_verifier_rejects_dummy_and_placeholder_domains():
    for dummy in ["organizer@example.com", "contact@test.com", "info@domain.com", "team@placeholder.com", "staff@sample.com"]:
        valid, _, err = email_verifier.is_valid_organizer_email(dummy)
        assert valid is False
        assert "dummy" in err.lower() or "placeholder" in err.lower()


def test_email_verifier_rejects_asset_and_image_filenames():
    for asset in ["banner@2x.png", "logo@preview.jpg", "icon@vector.svg", "theme@style.css"]:
        valid, _, err = email_verifier.is_valid_organizer_email(asset)
        assert valid is False
        assert "asset" in err.lower() or "filename" in err.lower() or "syntax" in err.lower()


def test_email_verifier_rejects_generic_automated_mailboxes():
    for sys_mail in ["noreply@company.com", "no-reply@events.com", "donotreply@domain.net", "mailer-daemon@server.org"]:
        valid, _, err = email_verifier.is_valid_organizer_email(sys_mail)
        assert valid is False
        assert "generic" in err.lower() or "automated" in err.lower()


def test_dynamic_category_loading_from_database(db_session):
    """Dynamically loads category list from the database Category table."""
    # Seed a custom dynamic category into the test database
    custom_cat = Category(name="Quantum Computing", slug="quantum-computing", description="Quantum tech events", icon="atom")
    db_session.add(custom_cat)
    db_session.commit()

    categories = categorizer.get_supported_categories(db_session)
    assert "Quantum Computing" in categories

    # Categorizer recognizes this newly added database category
    matched_cat, _ = categorizer.categorize("Global Quantum Computing Expo 2026", supported_categories=categories, db=db_session)
    assert matched_cat == "Quantum Computing"


def test_mandatory_organizer_email_rule_accepts_valid_email():
    future = (date.today() + timedelta(days=25)).isoformat()
    candidate = ExtractedEventCandidate(
        name="World Renewable Energy Conclave",
        date=future,
        category="Energy and Power Generation",
        venue="Messe Frankfurt",
        city="Frankfurt",
        country="Germany",
        extraction_confidence=85,
    )
    source = CandidateSource(url="https://energyconclave.org/contact", source_type="organizer_website")
    organizer = OrganizerCandidate(
        found=True,
        name="Global Energy Council",
        email="secretariat@energyconclave.org",
        sources=[source],
    )

    result = validation.validate_event(candidate, confidence_threshold=60, organizer=organizer)
    assert result.status == "VERIFIED"
    assert result.rejection_reason is None


def test_mandatory_organizer_email_rule_rejects_missing_email():
    """Event without organizer email must be REJECTED."""
    future = (date.today() + timedelta(days=25)).isoformat()
    candidate = ExtractedEventCandidate(
        name="World Renewable Energy Conclave",
        date=future,
        category="Energy and Power Generation",
        city="Frankfurt",
        country="Germany",
    )
    organizer = OrganizerCandidate(found=False, name="Global Energy Council", email=None)

    result = validation.validate_event(candidate, confidence_threshold=60, organizer=organizer)
    assert result.status == "REJECTED"
    assert result.rejection_reason == "MISSING_ORGANIZER_EMAIL"
    assert any("organizer email is mandatory" in n.lower() for n in result.notes)


def test_mandatory_organizer_email_rule_rejects_phone_only():
    """Phone number, contact form, or URL alone does NOT satisfy mandatory email requirement."""
    future = (date.today() + timedelta(days=25)).isoformat()
    candidate = ExtractedEventCandidate(
        name="World Renewable Energy Conclave",
        date=future,
        category="Energy and Power Generation",
        city="Frankfurt",
        country="Germany",
    )
    organizer = OrganizerCandidate(
        found=True,
        name="Global Energy Council",
        phone="+49 69 123456",
        website="https://energyconclave.org",
        email=None,
    )

    result = validation.validate_event(candidate, confidence_threshold=60, organizer=organizer)
    assert result.status == "REJECTED"
    assert result.rejection_reason == "MISSING_ORGANIZER_EMAIL"
    assert any("phone number alone does not satisfy" in n.lower() for n in result.notes)


def test_duplicate_events_are_identified_and_skipped(db_session):
    future = (date.today() + timedelta(days=35)).isoformat()
    source = CandidateSource(url="https://worldfinancesummit.org", source_type="official_site")
    candidate = ExtractedEventCandidate(
        name="World Finance & Banking Summit",
        date=future,
        category="Finance",
        city="Singapore",
        country="Singapore",
        url="https://worldfinancesummit.org",
        primary_source=source,
        sources=[source],
    )
    organizer = OrganizerCandidate(
        found=True,
        name="World Finance Forum",
        email="info@worldfinancesummit.org",
        sources=[source],
    )

    summary = RunSummary()
    # 1. First insertion succeeds
    event1 = storage.persist_event(
        db_session,
        candidate=candidate,
        organizer=organizer,
        verification_status="VERIFIED",
        verification_notes=[],
        confidence_score=90,
        event_date=date.fromisoformat(future),
        summary=summary,
    )
    assert event1 is not None
    assert summary.new_events == 1
    assert summary.accepted_events == 1
    assert summary.duplicate_events == 0

    # 2. Second insertion of same event is detected as duplicate and skipped
    event2 = storage.persist_event(
        db_session,
        candidate=candidate,
        organizer=organizer,
        verification_status="VERIFIED",
        verification_notes=[],
        confidence_score=90,
        event_date=date.fromisoformat(future),
        summary=summary,
    )
    assert event2 is None
    assert summary.duplicate_events == 1
    assert summary.new_events == 1  # count does not double


def test_rejected_events_record_rejection_reason_and_summary_counts(db_session):
    future = (date.today() + timedelta(days=15)).isoformat()
    source = CandidateSource(url="https://nolicense-conference.test", source_type="listing")
    candidate = ExtractedEventCandidate(
        name="Unlicensed Crypto Meet",
        date=future,
        category="Finance",
        city="Dubai",
        country="Dubai",
        url=source.url,
        primary_source=source,
        sources=[source],
    )
    # Organizer with NO email
    organizer = OrganizerCandidate(found=False, name="Anonymous Host", email=None, sources=[source])

    summary = RunSummary()
    val_result = validation.validate_event(candidate, confidence_threshold=60, organizer=organizer)
    assert val_result.status == "REJECTED"
    assert val_result.rejection_reason == "MISSING_ORGANIZER_EMAIL"

    saved_event = storage.persist_event(
        db_session,
        candidate=candidate,
        organizer=organizer,
        verification_status=val_result.status,
        verification_notes=val_result.notes,
        confidence_score=val_result.confidence,
        event_date=val_result.parsed_date,
        summary=summary,
        rejection_reason=val_result.rejection_reason,
    )

    assert saved_event is not None
    assert saved_event.verification_status == "REJECTED"
    assert saved_event.discovery_status == "REJECTED"
    assert any("REJECTION_REASON: MISSING_ORGANIZER_EMAIL" in note for note in saved_event.verification_notes)
    assert summary.rejected_events == 1
    assert summary.missing_organizer_email == 1
    assert summary.accepted_events == 0
    assert summary.new_events == 0  # not accepted into pipeline


def test_past_event_is_rejected_with_expired_reason():
    past = (date.today() - timedelta(days=20)).isoformat()
    candidate = ExtractedEventCandidate(
        name="Past Expo 2025",
        date=past,
        category="Healthcare",
        city="London",
        country="United Kingdom",
    )
    organizer = OrganizerCandidate(found=True, name="Medical Expo", email="info@medicalexpo.test")

    result = validation.validate_event(candidate, confidence_threshold=60, organizer=organizer)
    assert result.status == "REJECTED"
    assert result.rejection_reason == "PAST_OR_EXPIRED"
    assert any("past" in n.lower() for n in result.notes)

