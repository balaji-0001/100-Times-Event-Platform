"""Event Discovery Agent — validation gate tests (date sanity, email
syntax, confidence scoring, REJECTED/NEEDS_REVIEW/VERIFIED outcomes)."""

from datetime import date, timedelta

from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate, OrganizerCandidate
from backend.services.discovery_agent.validation import try_parse_date, validate_email_syntax, validate_event


def test_try_parse_date_accepts_known_formats():
    assert try_parse_date("2026-11-01") == date(2026, 11, 1)
    assert try_parse_date("01-11-2026") == date(2026, 11, 1)


def test_try_parse_date_returns_none_for_unparseable_text():
    assert try_parse_date("sometime next spring") is None
    assert try_parse_date(None) is None


def test_validate_email_syntax():
    assert validate_email_syntax("hello@example.com") is True
    assert validate_email_syntax("not-an-email") is False
    assert validate_email_syntax(None) is False


def test_validate_event_rejects_missing_name():
    candidate = ExtractedEventCandidate(name=None, date="2026-11-01")
    status, notes, confidence, parsed = validate_event(candidate, confidence_threshold=60)
    assert status == "REJECTED"
    assert confidence == 0
    assert parsed is None


def test_validate_event_rejects_confidently_past_date():
    past = (date.today() - timedelta(days=10)).isoformat()
    candidate = ExtractedEventCandidate(name="Old Event", date=past)
    status, notes, confidence, parsed = validate_event(candidate, confidence_threshold=60)
    assert status == "REJECTED"
    assert "past" in notes[0].lower()


def test_validate_event_needs_review_for_unparseable_date():
    candidate = ExtractedEventCandidate(name="Vague Event", date="sometime next spring", extraction_confidence=90)
    status, notes, confidence, parsed = validate_event(candidate, confidence_threshold=60)
    assert status == "NEEDS_REVIEW"
    assert parsed is None
    assert any("could not confidently parse" in n.lower() for n in notes)


def test_validate_event_verified_when_confident_and_complete():
    future = (date.today() + timedelta(days=30)).isoformat()
    candidate = ExtractedEventCandidate(
        name="Pune Tech Summit", date=future, venue="Convention Centre", city="Pune",
        category="Technology",
        ticket_url="https://example.test/tickets", extraction_confidence=85,
        primary_source=CandidateSource(url="https://example.test/event", source_type="event_listing"),
    )
    organizer = OrganizerCandidate(found=True, name="Pune Tech Collective", email="hello@punetech.test")
    status, notes, confidence, parsed = validate_event(candidate, confidence_threshold=60, organizer=organizer)
    assert status == "VERIFIED"
    assert parsed == date.fromisoformat(future)
    assert confidence >= 60


def _complete_candidate(future: str) -> ExtractedEventCandidate:
    return ExtractedEventCandidate(
        name="Pune Tech Summit", date=future, venue="Convention Centre", city="Pune",
        category="Technology",
        ticket_url="https://example.test/tickets", extraction_confidence=85,
        primary_source=CandidateSource(url="https://example.test/event", source_type="event_listing"),
    )


def test_validate_event_rejects_missing_organizer_email():
    """Mandatory email requirement: without an organizer email, the event is REJECTED."""
    future = (date.today() + timedelta(days=30)).isoformat()
    organizer = OrganizerCandidate(found=True, name="Pune Tech Collective")  # no email

    result = validate_event(_complete_candidate(future), confidence_threshold=60, organizer=organizer)
    assert result.status == "REJECTED"
    assert result.rejection_reason == "MISSING_ORGANIZER_EMAIL"
    assert any("organizer email is mandatory" in n.lower() for n in result.notes)


def test_validate_event_rejects_phone_only_without_email():
    """A phone number alone does NOT satisfy the mandatory organizer email requirement."""
    future = (date.today() + timedelta(days=30)).isoformat()
    organizer = OrganizerCandidate(found=True, name="Pune Tech Collective", phone="+91 98765 43210")

    result = validate_event(_complete_candidate(future), confidence_threshold=60, organizer=organizer)
    assert result.status == "REJECTED"
    assert result.rejection_reason == "MISSING_ORGANIZER_EMAIL"
    assert any("phone number alone does not satisfy" in n.lower() for n in result.notes)


def test_validate_event_rejects_invalid_or_dummy_email():
    """Dummy/placeholder emails like test@example.com or asset filenames are rejected."""
    future = (date.today() + timedelta(days=30)).isoformat()
    organizer = OrganizerCandidate(found=True, name="Pune Tech Collective", email="admin@example.com")

    result = validate_event(_complete_candidate(future), confidence_threshold=60, organizer=organizer)
    assert result.status == "REJECTED"
    assert result.rejection_reason == "INVALID_ORGANIZER_EMAIL"


def test_validate_event_flags_unsupported_category_for_review():
    """Events categorized as Other or unsupported are sent for manual review."""
    future = (date.today() + timedelta(days=30)).isoformat()
    candidate = _complete_candidate(future)
    candidate.category = "Other"
    organizer = OrganizerCandidate(found=True, name="Pune Tech Collective", email="contact@punetech.test")

    result = validate_event(candidate, confidence_threshold=60, organizer=organizer)
    assert result.status == "NEEDS_REVIEW"
    assert any("manual review required" in n.lower() for n in result.notes)


def test_validate_event_verified_when_organizer_email_valid_and_complete():
    future = (date.today() + timedelta(days=30)).isoformat()
    organizer = OrganizerCandidate(found=True, name="Pune Tech Collective", email="contact@punetech.test")

    result = validate_event(_complete_candidate(future), confidence_threshold=60, organizer=organizer)
    assert result.status == "VERIFIED"
    assert result.rejection_reason is None


def test_validate_event_legacy_mode_when_require_email_false():
    """When require_organizer_email=False, legacy review/verified behavior is preserved."""
    future = (date.today() + timedelta(days=30)).isoformat()
    organizer_phone_only = OrganizerCandidate(found=True, name="Pune Tech Collective", phone="+91 98765 43210")

    status, notes, confidence, parsed = validate_event(
        _complete_candidate(future), confidence_threshold=60, organizer=organizer_phone_only, require_organizer_email=False
    )
    assert status == "VERIFIED"

    organizer_missing = OrganizerCandidate(found=False)
    status2, notes2, _, _ = validate_event(
        _complete_candidate(future), confidence_threshold=60, organizer=organizer_missing, require_organizer_email=False
    )
    assert status2 == "NEEDS_REVIEW"


def test_validate_event_skips_organizer_check_when_not_passed():
    """When require_organizer_email is False, omitting organizer skips the check."""
    future = (date.today() + timedelta(days=30)).isoformat()

    status, notes, confidence, parsed = validate_event(_complete_candidate(future), confidence_threshold=60, require_organizer_email=False)

    assert status == "VERIFIED"
    assert not any("organizer contact" in n.lower() for n in notes)


def test_validate_event_needs_review_below_confidence_threshold():
    future = (date.today() + timedelta(days=30)).isoformat()
    candidate = ExtractedEventCandidate(name="Low Confidence Event", date=future, category="Technology", extraction_confidence=20)
    organizer = OrganizerCandidate(found=True, email="hello@punetech.test")
    status, notes, confidence, parsed = validate_event(candidate, confidence_threshold=60, organizer=organizer)
    assert status == "NEEDS_REVIEW"


def test_try_parse_date_reads_real_world_formats():
    """Formats seen on real event pages; ranges resolve to their first day."""
    assert try_parse_date("2026-11-17T09:00:00+05:30") == date(2026, 11, 17)
    assert try_parse_date("2026-12-03T00:00:00.000+00:00") == date(2026, 12, 3)
    assert try_parse_date("22nd - 24th Dec 2026") == date(2026, 12, 22)
    assert try_parse_date("08 - 10 April 2027") == date(2027, 4, 8)
    assert try_parse_date("August 26-30, 2026") == date(2026, 8, 26)
    assert try_parse_date("14-16 June 2026") == date(2026, 6, 14)
    assert try_parse_date("Sept 3 2026") == date(2026, 9, 3)
