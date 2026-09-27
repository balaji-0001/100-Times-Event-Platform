"""Organizer Outreach tests — organizer finder (network mocked), duplicate
prevention, message generation (AI mocked, never a real network call), and
the full orchestrator flow end to end against the in-memory DB."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.models import DiscoveredEvent, DiscoveredOrganizer, OutreachMessage
from backend.services.social_agent.outreach import duplicate_check, event_verification, message_generator, organizer_finder
from backend.services.social_agent.outreach.followup import process_followups
from backend.services.social_agent.outreach.orchestrator import run_organizer_outreach, send_outreach_message
from backend.services.social_agent.outreach.types import EventDetails, OrganizerContactInfo
from backend.services.social_agent.pipeline.event_extraction import ExtractedEventAI
from tests.conftest import FakeAIClient


def _extracted_event(**overrides) -> ExtractedEventAI:
    base = dict(
        is_genuine_event=True,
        event_name="Pune Cycling Meetup",
        category="Cycling",
        event_type="Meetup",
        description="A weekend cycling meetup for Pune riders.",
        date="2026-11-01",
        time="07:00 AM",
        location="Pune",
        organizer="Pune Riders Collective",
        registration_url="https://example-events.test/pune-cycling-meetup",
        is_free=True,
        price=None,
        confidence_score=90,
        relevance_score=90,
        reason="Clear, specific event with a real registration link.",
    )
    base.update(overrides)
    return ExtractedEventAI(**base)


class _FakeResponse:
    def __init__(self, status_code=200, text="", content_type="text/html"):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}


# --- Event Verification ---

def test_verify_event_rejects_confidently_past_date():
    event = _extracted_event(date="2020-01-01")
    result = event_verification.verify_event(event, community=None)
    assert result.is_upcoming is False
    assert "past" in result.reason.lower()


def test_verify_event_allows_unparseable_date_with_a_note():
    event = _extracted_event(date="sometime next spring")
    result = event_verification.verify_event(event, community=None)
    assert result.is_upcoming is True
    assert any("could not confidently parse" in n.lower() for n in result.notes)


def test_verify_event_flags_high_risk_community_without_rejecting():
    from backend.models import Community

    community = Community(platform="reddit", name="r/sketchy", slug="r-sketchy", url="https://reddit.com/r/sketchy", risk_level="high")
    event = _extracted_event(date="2026-11-01")
    result = event_verification.verify_event(event, community=community)
    assert result.is_upcoming is True
    assert any("high-risk" in n.lower() for n in result.notes)


def test_outreach_rejects_event_with_past_date_before_finding_organizer(db_session, monkeypatch):
    from backend.services.social_agent.outreach import orchestrator

    called = {"count": 0}

    def _should_not_be_called(event):
        called["count"] += 1
        return OrganizerContactInfo(found=True, email="x@example.test")

    monkeypatch.setattr(orchestrator.organizer_finder, "find_organizer", _should_not_be_called)

    event = _extracted_event(date="2020-01-01")
    result = run_organizer_outreach(db_session, discussion_id=None, opportunity_id=None, extracted_event=event, source_url="https://reddit.com/r/pune/x")

    assert result["outcome"] == "REJECTED_NOT_UPCOMING"
    assert called["count"] == 0
    assert db_session.query(OutreachMessage).count() == 0


# --- Organizer Finder ---

def test_organizer_finder_returns_not_found_without_url():
    result = organizer_finder.find_organizer(EventDetails(
        name="Some Event", date=None, location=None, category=None, url=None,
        source_url=None, organizer_name_hint="Some Organizer", match_score=90,
    ))
    assert result.found is False


def test_organizer_finder_extracts_mailto_and_linkedin(monkeypatch):
    html = """
    <html><head><title>Pune Riders Collective</title></head>
    <body>
      <a href="mailto:hello@puneriders.test">Contact us</a>
      <a href="https://www.linkedin.com/company/pune-riders-collective">LinkedIn</a>
    </body></html>
    """
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(text=html))

    result = organizer_finder.find_organizer(EventDetails(
        name="Pune Cycling Meetup", date="2026-11-01", location="Pune", category="Cycling",
        url="https://example-events.test/pune-cycling-meetup", source_url="https://reddit.com/r/pune/abc",
        organizer_name_hint="Pune Riders Collective", match_score=90,
    ))

    assert result.found is True
    assert result.email == "hello@puneriders.test"
    assert result.linkedin == "https://www.linkedin.com/company/pune-riders-collective"
    assert result.name == "Pune Riders Collective"


def test_organizer_finder_follows_organizer_website_when_event_page_has_no_email(monkeypatch):
    """Priority 1 (event page) has an organizer website but no email ->
    priority 2 (that organizer's own site) is fetched and its mailto used."""
    event_page_html = """
    <html><head><script type="application/ld+json">
    {"organizer": {"name": "Pune Riders Collective", "url": "https://puneriders.test"}}
    </script></head><body>No direct contact here.</body></html>
    """
    organizer_site_html = """
    <html><body><a href="mailto:hello@puneriders.test">Email us</a></body></html>
    """

    def _fake_get(url, *a, **k):
        if "puneriders.test" in url and "example-events" not in url:
            return _FakeResponse(text=organizer_site_html)
        return _FakeResponse(text=event_page_html)

    monkeypatch.setattr(httpx, "get", _fake_get)

    result = organizer_finder.find_organizer(EventDetails(
        name="Pune Cycling Meetup", date="2026-11-01", location="Pune", category="Cycling",
        url="https://example-events.test/pune-cycling-meetup", source_url=None,
        organizer_name_hint=None, match_score=90,
    ))

    assert result.found is True
    assert result.email == "hello@puneriders.test"
    assert result.name == "Pune Riders Collective"
    assert result.website == "https://puneriders.test"


def test_organizer_finder_reports_not_found_when_page_has_no_contact(monkeypatch):
    html = "<html><head><title>Event Page</title></head><body>No contact info here.</body></html>"
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(text=html))

    result = organizer_finder.find_organizer(EventDetails(
        name="Mystery Event", date=None, location=None, category=None,
        url="https://example-events.test/mystery", source_url=None,
        organizer_name_hint=None, match_score=90,
    ))
    assert result.found is False


# --- Message Generator (AI mocked — never a real Anthropic call in tests) ---

def test_message_generator_uses_ai_when_configured(monkeypatch):
    ai_response = {"subject": "AI drafted subject", "body": "AI drafted body mentioning 100.com"}
    monkeypatch.setattr(message_generator, "get_ai_client", lambda: FakeAIClient(structured_response=ai_response))

    event = EventDetails(name="Pune Cycling Meetup", date="2026-11-01", location="Pune", category="Cycling", url=None, source_url=None, organizer_name_hint=None, match_score=90)
    organizer = OrganizerContactInfo(found=True, name="Pune Riders Collective", email="hello@puneriders.test")

    content, generated_by = message_generator.generate_outreach_message(event, organizer)
    assert generated_by == "ai"
    assert content.subject == "AI drafted subject"


def test_message_generator_falls_back_deterministically_when_ai_unconfigured(monkeypatch):
    monkeypatch.setattr(message_generator, "get_ai_client", lambda: FakeAIClient(configured=False))

    event = EventDetails(name="Pune Cycling Meetup", date="2026-11-01", location="Pune", category="Cycling", url=None, source_url=None, organizer_name_hint=None, match_score=90)
    organizer = OrganizerContactInfo(found=True, name="Pune Riders Collective", email="hello@puneriders.test")

    content, generated_by = message_generator.generate_outreach_message(event, organizer)
    assert generated_by == "deterministic_fallback"
    assert "Pune Cycling Meetup" in content.body
    assert "100Times" in content.body


# --- Duplicate check ---

def test_duplicate_check_detects_same_organizer_and_event(db_session):
    organizer = DiscoveredOrganizer(name="Pune Riders", email="hello@puneriders.test")
    db_session.add(organizer)
    db_session.flush()
    event = DiscoveredEvent(name="Pune Cycling Meetup", match_score=90, organizer_status="FOUND", organizer_id=organizer.id)
    db_session.add(event)
    db_session.flush()
    message = OutreachMessage(event_id=event.id, organizer_id=organizer.id, recipient=organizer.email, subject="s", message="m", status="DELIVERED", sent_at=datetime.now(timezone.utc))
    db_session.add(message)
    db_session.flush()

    duplicate = duplicate_check.find_duplicate(db_session, organizer, "Pune Cycling Meetup")
    assert duplicate is not None
    assert duplicate.id == message.id


def test_duplicate_check_ignores_a_rejected_message(db_session):
    """A REJECTED message (admin chose not to pursue it) shouldn't block a
    fresh attempt — unlike an APPROVED-but-failed one, which IS still an
    in-flight thread for the same organizer+event and should block."""
    organizer = DiscoveredOrganizer(name="Pune Riders", email="hello@puneriders.test")
    db_session.add(organizer)
    db_session.flush()
    event = DiscoveredEvent(name="Pune Cycling Meetup", match_score=90, organizer_status="FOUND", organizer_id=organizer.id)
    db_session.add(event)
    db_session.flush()
    db_session.add(OutreachMessage(event_id=event.id, organizer_id=organizer.id, recipient=organizer.email, subject="s", message="m", status="REJECTED"))
    db_session.flush()

    assert duplicate_check.find_duplicate(db_session, organizer, "Pune Cycling Meetup") is None


# --- Orchestrator (full flow, network + AI mocked) ---

def test_outreach_skips_below_match_threshold(db_session, monkeypatch):
    event = _extracted_event(confidence_score=40, relevance_score=40)
    result = run_organizer_outreach(db_session, discussion_id=None, opportunity_id=None, extracted_event=event, source_url="https://reddit.com/r/pune/x")

    assert result["outcome"] == "SKIPPED_BELOW_THRESHOLD"
    discovered = db_session.get(DiscoveredEvent, result["discoveredEventId"])
    assert discovered.organizer_status == "NOT_FOUND"


def test_outreach_marks_organizer_not_found(db_session, monkeypatch):
    from backend.services.social_agent.outreach import orchestrator

    monkeypatch.setattr(orchestrator.organizer_finder, "find_organizer", lambda event: OrganizerContactInfo(found=False))

    event = _extracted_event()
    result = run_organizer_outreach(db_session, discussion_id=None, opportunity_id=None, extracted_event=event, source_url="https://reddit.com/r/pune/x")

    assert result["outcome"] == "ORGANIZER_NOT_FOUND"
    discovered = db_session.get(DiscoveredEvent, result["discoveredEventId"])
    assert discovered.organizer_status == "NOT_FOUND"
    assert db_session.query(OutreachMessage).count() == 0


def test_outreach_drafts_and_requires_human_approval_before_sending(db_session, monkeypatch):
    """Per the architecture spec, outreach must never auto-send — it always
    stops at a drafted, awaiting-approval message. Sending only happens via
    an explicit `send_outreach_message` call (the dashboard's "Approve &
    Send" action, or the follow-up sweep)."""
    from backend.services.social_agent.outreach import orchestrator

    contact = OrganizerContactInfo(found=True, name="Pune Riders Collective", email="hello@puneriders.test", website="https://example-events.test", source_url="https://example-events.test")
    monkeypatch.setattr(orchestrator.organizer_finder, "find_organizer", lambda event: contact)
    monkeypatch.setattr(orchestrator.message_generator, "get_ai_client", lambda: FakeAIClient(configured=False))

    event = _extracted_event()
    result = run_organizer_outreach(db_session, discussion_id=None, opportunity_id=None, extracted_event=event, source_url="https://reddit.com/r/pune/x")

    assert result["outcome"] == "DRAFTED_PENDING_APPROVAL"
    message = db_session.get(OutreachMessage, result["outreachMessageId"])
    assert message.status == "PENDING_APPROVAL"
    assert message.sent_at is None
    assert message.recipient == "hello@puneriders.test"
    assert message.generated_by == "deterministic_fallback"

    # Human approval (dashboard's "Approve" action) must happen before send_outreach_message
    # will even attempt it — the state machine rejects PENDING_APPROVAL -> DELIVERED directly.
    message.status = "APPROVED"
    outcome = send_outreach_message(db_session, message)
    assert outcome == "DELIVERED"
    assert message.status == "DELIVERED"
    assert message.sent_at is not None


def test_outreach_prevents_duplicate_initial_send(db_session, monkeypatch):
    from backend.services.social_agent.outreach import orchestrator

    contact = OrganizerContactInfo(found=True, name="Pune Riders Collective", email="hello@puneriders.test", website="https://example-events.test", source_url="https://example-events.test")
    monkeypatch.setattr(orchestrator.organizer_finder, "find_organizer", lambda event: contact)
    monkeypatch.setattr(orchestrator.message_generator, "get_ai_client", lambda: FakeAIClient(configured=False))

    event = _extracted_event()
    first = run_organizer_outreach(db_session, discussion_id=None, opportunity_id=None, extracted_event=event, source_url="https://reddit.com/r/pune/x")
    assert first["outcome"] == "DRAFTED_PENDING_APPROVAL"
    first_message = db_session.get(OutreachMessage, first["outreachMessageId"])
    first_message.status = "APPROVED"
    assert send_outreach_message(db_session, first_message) == "DELIVERED"

    second = run_organizer_outreach(db_session, discussion_id=None, opportunity_id=None, extracted_event=event, source_url="https://reddit.com/r/pune/y")
    assert second["outcome"] == "SKIPPED_DUPLICATE"
    assert db_session.query(OutreachMessage).count() == 1


def test_outreach_respects_blocked_organizer(db_session, monkeypatch):
    from backend.services.social_agent.outreach import orchestrator

    contact = OrganizerContactInfo(found=True, name="Pune Riders Collective", email="hello@puneriders.test", website="https://example-events.test", source_url="https://example-events.test")
    monkeypatch.setattr(orchestrator.organizer_finder, "find_organizer", lambda event: contact)

    organizer = DiscoveredOrganizer(name="Pune Riders Collective", email="hello@puneriders.test", website="https://example-events.test", blocked=True)
    db_session.add(organizer)
    db_session.commit()

    event = _extracted_event()
    result = run_organizer_outreach(db_session, discussion_id=None, opportunity_id=None, extracted_event=event, source_url="https://reddit.com/r/pune/x")

    assert result["outcome"] == "SKIPPED_ORGANIZER_BLOCKED"
    assert db_session.query(OutreachMessage).count() == 0


def test_outreach_respects_daily_cap_at_send_time(db_session, monkeypatch):
    """The cap is enforced when a human actually sends (or the follow-up
    sweep sends) — not at draft time, since drafting doesn't consume
    outbound volume."""
    from backend.services.social_agent.outreach import orchestrator
    from backend.core.config import get_settings

    contact = OrganizerContactInfo(found=True, name="Pune Riders Collective", email="hello@puneriders.test", website="https://example-events.test", source_url="https://example-events.test")
    monkeypatch.setattr(orchestrator.organizer_finder, "find_organizer", lambda event: contact)
    monkeypatch.setattr(orchestrator.message_generator, "get_ai_client", lambda: FakeAIClient(configured=False))

    event = _extracted_event()
    result = run_organizer_outreach(db_session, discussion_id=None, opportunity_id=None, extracted_event=event, source_url="https://reddit.com/r/pune/x")
    assert result["outcome"] == "DRAFTED_PENDING_APPROVAL"

    message = db_session.get(OutreachMessage, result["outreachMessageId"])
    monkeypatch.setattr(get_settings(), "outreach_daily_cap", 0)
    outcome = send_outreach_message(db_session, message)

    assert outcome == "CAP_REACHED"
    assert message.status == "PENDING_APPROVAL"  # left untouched — retryable once the cap resets


# --- Follow-up sweep ---

def test_followup_drafted_after_window_then_completed_after_second_window(db_session, monkeypatch):
    """Stage 1 DRAFTS the follow-up and stops at FOLLOW_UP_DUE — it does not
    auto-send, per the 'never send automatically' rule (no follow-up
    carve-out). A human still approves+sends it like any other message."""
    from backend.services.social_agent.outreach import followup as followup_module

    monkeypatch.setattr(followup_module, "generate_followup_message", lambda event, organizer: (message_generator.OutreachEmailAI(subject="Follow up", body="Following up on 100Times"), "deterministic_fallback"))

    organizer = DiscoveredOrganizer(name="Pune Riders", email="hello@puneriders.test")
    db_session.add(organizer)
    db_session.flush()
    event = DiscoveredEvent(name="Pune Cycling Meetup", match_score=90, organizer_status="FOUND", organizer_id=organizer.id)
    db_session.add(event)
    db_session.flush()

    eight_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
    message = OutreachMessage(
        event_id=event.id, organizer_id=organizer.id, recipient=organizer.email,
        subject="s", message="m", status="DELIVERED", sent_at=eight_days_ago, last_contacted_at=eight_days_ago,
    )
    db_session.add(message)
    db_session.commit()

    summary = process_followups(db_session)
    assert summary["followUpsDrafted"] == 1
    db_session.refresh(message)
    assert message.status == "FOLLOW_UP_DUE"
    assert message.follow_up_sent_at is None  # drafted, not sent — still awaiting approval

    # Approve + send the follow-up draft (the human action this now requires).
    message.status = "APPROVED"
    outcome = send_outreach_message(db_session, message)
    assert outcome == "DELIVERED"
    assert message.follow_up_sent_at is not None

    # Push the follow-up send far enough into the past -> should become COMPLETED
    message.follow_up_sent_at = datetime.now(timezone.utc) - timedelta(days=8)
    db_session.commit()

    summary_2 = process_followups(db_session)
    assert summary_2["markedCompleted"] == 1
    db_session.refresh(message)
    assert message.status == "COMPLETED"


def test_followup_only_drafted_once(db_session, monkeypatch):
    from backend.services.social_agent.outreach import followup as followup_module

    monkeypatch.setattr(followup_module, "generate_followup_message", lambda event, organizer: (message_generator.OutreachEmailAI(subject="Follow up", body="Following up"), "deterministic_fallback"))

    organizer = DiscoveredOrganizer(name="Pune Riders", email="hello@puneriders.test")
    db_session.add(organizer)
    db_session.flush()
    event = DiscoveredEvent(name="Pune Cycling Meetup", match_score=90, organizer_status="FOUND", organizer_id=organizer.id)
    db_session.add(event)
    db_session.flush()

    eight_days_ago = datetime.now(timezone.utc) - timedelta(days=8)
    message = OutreachMessage(
        event_id=event.id, organizer_id=organizer.id, recipient=organizer.email,
        subject="s", message="m", status="DELIVERED", sent_at=eight_days_ago,
        follow_up_sent_at=eight_days_ago + timedelta(hours=1),
    )
    db_session.add(message)
    db_session.commit()

    summary = process_followups(db_session)
    assert summary["followUpsDrafted"] == 0  # already had a follow-up — MVP drafts only one
