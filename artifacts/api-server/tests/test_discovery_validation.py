"""Event Discovery Agent — validation gate tests (date sanity, email
syntax, confidence scoring, REJECTED/NEEDS_REVIEW/VERIFIED outcomes)."""

from datetime import date, timedelta

from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate
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
        ticket_url="https://example.test/tickets", extraction_confidence=85,
        primary_source=CandidateSource(url="https://example.test/event", source_type="event_listing"),
    )
    status, notes, confidence, parsed = validate_event(candidate, confidence_threshold=60)
    assert status == "VERIFIED"
    assert parsed == date.fromisoformat(future)
    assert confidence >= 60


def test_validate_event_needs_review_below_confidence_threshold():
    future = (date.today() + timedelta(days=30)).isoformat()
    candidate = ExtractedEventCandidate(name="Low Confidence Event", date=future, extraction_confidence=20)
    status, notes, confidence, parsed = validate_event(candidate, confidence_threshold=60)
    assert status == "NEEDS_REVIEW"
