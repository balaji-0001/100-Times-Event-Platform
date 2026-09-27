"""Agent 2 (Organizer Research & 100Times Promotion Agent) tests — state
machine, suppression list, eligibility selection, the batch orchestrator's
idempotency, and bounce handling. AI is always mocked."""

from datetime import datetime, timezone

import pytest

from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer, OutreachCampaign, OutreachMessage, SuppressedContact
from backend.services.social_agent import state_machine
from backend.services.social_agent.outreach import eligibility, orchestrator, suppression
from backend.services.social_agent.outreach.types import OutreachRunConfig, SendResult
from tests.conftest import FakeAIClient


def _seed_event(db_session, name="Pune Tech Summit", email="hello@puneevents.test", verification_status="NEEDS_REVIEW", blocked=False):
    organizer = DiscoveredOrganizer(name="Pune Events Collective", email=email, blocked=blocked, created_at=datetime.now(timezone.utc))
    db_session.add(organizer)
    db_session.flush()
    event = DiscoveredEvent(
        name=name, city="Pune", category="Technology", match_score=80, organizer_status="FOUND",
        organizer_id=organizer.id, verification_status=verification_status, discovered_by="web_discovery_agent",
        discovered_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()
    return event, organizer


# --- State machine ---

def test_outreach_state_machine_happy_path():
    status = "NEW"
    for target in ("RESEARCHED", "EMAIL_GENERATED", "PENDING_APPROVAL", "APPROVED", "DELIVERED", "REPLIED", "COMPLETED"):
        status = state_machine.transition_outreach_message(status, target)
    assert status == "COMPLETED"


def test_outreach_state_machine_rejects_send_before_approval():
    with pytest.raises(state_machine.InvalidTransitionError):
        state_machine.transition_outreach_message("PENDING_APPROVAL", "DELIVERED")


def test_outreach_state_machine_terminal_states_are_final():
    for terminal in ("COMPLETED", "REJECTED"):
        with pytest.raises(state_machine.InvalidTransitionError):
            state_machine.transition_outreach_message(terminal, "APPROVED")


# --- Suppression ---

def test_suppression_is_email_keyed_and_case_insensitive(db_session):
    suppression.suppress(db_session, "Hello@PuneEvents.test", reason="opted_out")
    assert suppression.is_suppressed(db_session, "hello@puneevents.test") is True
    assert suppression.is_suppressed(db_session, "someone@else.test") is False
    assert suppression.is_suppressed(db_session, None) is False


def test_suppress_is_idempotent(db_session):
    first = suppression.suppress(db_session, "a@b.test", reason="bounced")
    second = suppression.suppress(db_session, "a@b.test", reason="opted_out")
    assert first.id == second.id
    assert db_session.query(SuppressedContact).count() == 1


# --- Eligibility ---

def test_eligibility_skips_suppressed_blocked_and_already_messaged(db_session):
    ok_event, _ = _seed_event(db_session, name="OK Event", email="ok@a.test")
    _seed_event(db_session, name="Blocked Event", email="blocked@a.test", blocked=True)
    suppressed_event, _ = _seed_event(db_session, name="Suppressed Event", email="sup@a.test")
    suppression.suppress(db_session, "sup@a.test", reason="opted_out")
    messaged_event, messaged_org = _seed_event(db_session, name="Messaged Event", email="msg@a.test")
    db_session.add(OutreachMessage(event_id=messaged_event.id, organizer_id=messaged_org.id, status="PENDING_APPROVAL", created_at=datetime.now(timezone.utc)))
    _seed_event(db_session, name="Rejected Event", email="rej@a.test", verification_status="REJECTED")
    db_session.commit()

    candidates, summary = eligibility.find_eligible_candidates(db_session, OutreachRunConfig(max_candidates=10))

    assert [event.id for event, _ in candidates] == [ok_event.id]
    assert summary.skipped_suppressed == 2  # blocked flag + suppression list
    assert summary.skipped_duplicate == 1


def test_eligibility_respects_max_candidates(db_session):
    for i in range(5):
        _seed_event(db_session, name=f"Event {i}", email=f"e{i}@a.test")
    candidates, _ = eligibility.find_eligible_candidates(db_session, OutreachRunConfig(max_candidates=2))
    assert len(candidates) == 2


# --- Batch orchestrator ---

def test_run_outreach_agent_drafts_to_pending_approval_and_is_idempotent(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator, "get_ai_client", lambda: FakeAIClient(configured=True))
    monkeypatch.setattr(orchestrator.message_generator, "get_ai_client", lambda: FakeAIClient(configured=False))
    _seed_event(db_session, name="Pune Tech Summit", email="hello@puneevents.test")
    _seed_event(db_session, name="Mumbai Startup Meet", email="team@mumbaistartups.test")

    first = orchestrator.run_outreach_agent(db_session, OutreachRunConfig(max_candidates=10))
    assert first.drafted == 2
    messages = db_session.query(OutreachMessage).all()
    assert {m.status for m in messages} == {"PENDING_APPROVAL"}
    assert all(m.subject and m.message and m.campaign_id for m in messages)
    assert all(m.sent_at is None for m in messages)

    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "outreach").one()
    assert run.status == "completed"
    assert run.summary["drafted"] == 2
    assert db_session.query(OutreachCampaign).filter(OutreachCampaign.status == "completed").count() == 1

    second = orchestrator.run_outreach_agent(db_session, OutreachRunConfig(max_candidates=10))
    assert second.drafted == 0
    assert second.skipped_duplicate == 2
    assert db_session.query(OutreachMessage).count() == 2


def test_run_outreach_agent_fails_honestly_without_api_key(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator, "get_ai_client", lambda: FakeAIClient(configured=False))
    _seed_event(db_session)

    summary = orchestrator.run_outreach_agent(db_session, OutreachRunConfig(max_candidates=10))

    assert summary.drafted == 0
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "outreach").one()
    assert run.status == "failed"
    assert "AI provider is not configured" in run.error
    assert db_session.query(OutreachMessage).count() == 0


# --- Sending: bounce handling + failure revert ---

class _BouncingProvider:
    def send_message(self, recipient, subject, body):
        return SendResult(success=False, bounced=True, message="Recipient refused (bounced): 550 no such user")


class _FlakyProvider:
    def send_message(self, recipient, subject, body):
        return SendResult(success=False, message="SMTP send failed: connection reset")


def test_bounce_marks_bounced_and_suppresses_recipient(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator, "get_email_provider", lambda: _BouncingProvider())
    event, organizer = _seed_event(db_session)
    message = OutreachMessage(event_id=event.id, organizer_id=organizer.id, recipient=organizer.email, subject="s", message="m", status="APPROVED", created_at=datetime.now(timezone.utc))
    db_session.add(message)
    db_session.commit()

    assert orchestrator.send_outreach_message(db_session, message) == "BOUNCED"
    assert message.status == "BOUNCED"
    assert message.sent_at is None
    assert suppression.is_suppressed(db_session, organizer.email) is True


def test_generic_send_failure_reverts_to_approved_for_retry(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator, "get_email_provider", lambda: _FlakyProvider())
    event, organizer = _seed_event(db_session)
    message = OutreachMessage(event_id=event.id, organizer_id=organizer.id, recipient=organizer.email, subject="s", message="m", status="APPROVED", created_at=datetime.now(timezone.utc))
    db_session.add(message)
    db_session.commit()

    assert orchestrator.send_outreach_message(db_session, message) == "APPROVED"
    assert message.status == "APPROVED"
    assert message.send_attempt_count == 1
    assert "connection reset" in message.failure_reason
    assert suppression.is_suppressed(db_session, organizer.email) is False
