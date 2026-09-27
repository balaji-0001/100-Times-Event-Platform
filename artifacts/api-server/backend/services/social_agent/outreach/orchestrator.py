"""Organizer Outreach orchestrator ("Agent 2" — Organizer Research & 100Times
Promotion Agent). Shared by two entry points:

  - `run_organizer_outreach`: the ORIGINAL single-post flow the social-
    listening pipeline calls per matched discussion (see
    `pipeline/discovery_pipeline.py`) — extracts, verifies, finds the
    organizer, dedups, drafts, and lands the message at PENDING_APPROVAL
    in one call.
  - `run_outreach_agent`: the NEW batch flow — selects eligible candidates
    from `discovered_events`/`discovered_organizers` (populated by EITHER
    producer: the social pipeline or the Event Discovery Agent), persists
    each as an `OutreachMessage` starting at NEW, and walks it through
    RESEARCHED -> EMAIL_GENERATED -> PENDING_APPROVAL, logging one
    `AgentRun`/`OutreachCampaign` per batch — mirrors
    `discovery_agent/orchestrator.py`'s idempotent-run discipline.

Human approval before send, in both flows: a message only ever reaches
PENDING_APPROVAL here — nothing in this module calls `send_outreach_message`
itself. Sending only happens when a human clicks "Approve" then "Send" (or
the follow-up sweep drafts one, which also waits for approval) on the
dashboard (`routes/outreach.py`). This mirrors the Attendee Agent's own
rule (no auto-publish without an explicit human action) and the project's
outreach spec ("Use human approval for real outbound messages").

Every stage that skips drafting records *why* (via `AgentAction`, the same
audit table the rest of the agent uses) rather than silently doing nothing.
This module never raises out to its caller for expected "couldn't proceed"
cases (below threshold, event not upcoming, organizer not found, duplicate,
blocked/suppressed) — it returns a result dict describing the outcome;
callers wrap unexpected exceptions themselves (see `discovery_pipeline.py`)
so Organizer Outreach can never break the discovery pipeline it hangs off of.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AgentAction, AgentRun, Community, DiscoveredEvent, DiscoveredOrganizer, OutreachCampaign, OutreachMessage
from backend.services.social_agent import state_machine
from backend.services.social_agent.ai_client import AIClientError, get_ai_client, not_configured_message
from backend.services.social_agent.outreach import duplicate_check, eligibility, event_verification, message_generator, organizer_finder, suppression
from backend.services.social_agent.outreach.senders import get_email_provider
from backend.services.social_agent.outreach.types import EventDetails, OrganizerContactInfo, OutreachRunConfig, OutreachRunSummary
from backend.services.social_agent.pipeline.event_extraction import ExtractedEventAI


def _log(opportunity_id: int | None, action_type: str, detail: str) -> AgentAction:
    return AgentAction(opportunity_id=opportunity_id, action_type=action_type, result=detail, created_at=datetime.now(timezone.utc))


def to_event_details(event: DiscoveredEvent) -> EventDetails:
    """Shared ORM -> dataclass adapter, used by both `run_outreach_agent`
    and `followup.py` so the two don't drift into separate copies."""
    return EventDetails(
        name=event.name, date=event.date, location=event.location, category=event.category,
        url=event.url, source_url=event.source_url, organizer_name_hint=None, match_score=event.match_score,
        venue=event.venue, city=event.city, event_format=event.event_format,
        ticket_url=event.ticket_url, subcategory=event.subcategory,
    )


def to_organizer_contact_info(organizer: DiscoveredOrganizer | None) -> OrganizerContactInfo:
    if organizer is None:
        return OrganizerContactInfo(found=False)
    return OrganizerContactInfo(
        found=True, name=organizer.name, email=organizer.email,
        website=organizer.website, linkedin=organizer.linkedin, source_url=organizer.source_url,
    )


def _get_or_create_organizer(db: Session, contact: OrganizerContactInfo) -> DiscoveredOrganizer:
    organizer = None
    if contact.email:
        organizer = db.execute(select(DiscoveredOrganizer).where(DiscoveredOrganizer.email == contact.email)).scalars().first()
    if organizer is None and contact.website:
        organizer = db.execute(select(DiscoveredOrganizer).where(DiscoveredOrganizer.website == contact.website)).scalars().first()
    if organizer is None:
        organizer = DiscoveredOrganizer(
            name=contact.name or "Unknown Organizer",
            email=contact.email,
            website=contact.website,
            linkedin=contact.linkedin,
            source_url=contact.source_url,
            created_at=datetime.now(timezone.utc),
        )
        db.add(organizer)
        db.flush()
    return organizer


def _today_sent_count(db: Session) -> int:
    today = datetime.now(timezone.utc).date()
    rows = db.execute(select(OutreachMessage.sent_at).where(OutreachMessage.sent_at.isnot(None))).scalars().all()
    return sum(1 for sent_at in rows if sent_at and sent_at.date() == today)


def daily_cap_available(db: Session) -> bool:
    return _today_sent_count(db) < get_settings().outreach_daily_cap


def send_outreach_message(db: Session, message: OutreachMessage) -> str:
    """Actually sends via the configured `EmailProvider`. Called ONLY from an
    explicit human approval action (`routes/outreach.py`'s send/retry) or the
    follow-up sweep after its own draft is approved — never automatically
    from `run_organizer_outreach`/`run_outreach_agent`.

    Enforces the daily cap here, as the single real send chokepoint shared by
    both callers. Returns `"DELIVERED"|"BOUNCED"|"APPROVED"|"CAP_REACHED"` —
    on `CAP_REACHED` the message is left untouched so it can be retried
    later; on a generic (non-bounce) failure it reverts to `APPROVED` so a
    human can retry, rather than dead-ending in a separate FAILED state."""
    if not daily_cap_available(db):
        return "CAP_REACHED"

    provider = get_email_provider()
    result = provider.send_message(message.recipient or "", message.subject or "", message.message or "")
    now = datetime.now(timezone.utc)
    message.send_attempt_count += 1

    if result.success:
        message.status = state_machine.transition_outreach_message(message.status, "DELIVERED")
        if message.sent_at is None:
            message.sent_at = now
        else:
            message.follow_up_sent_at = now
        message.last_contacted_at = now
        message.message_id = result.message_id
        message.failure_reason = None
        db.add(_log(None, "outreach_sent", f"Sent to {message.recipient} via {provider.__class__.__name__} ({result.message})"))
        outcome = "DELIVERED"
    elif result.bounced:
        message.status = state_machine.transition_outreach_message(message.status, "BOUNCED")
        message.failure_reason = result.message
        if message.recipient:
            suppression.suppress(db, message.recipient, reason="bounced", note=result.message)
        db.add(_log(None, "outreach_bounced", result.message))
        outcome = "BOUNCED"
    else:
        message.status = "APPROVED"  # reverted, not transitioned — same state, eligible for retry
        message.failure_reason = result.message
        db.add(_log(None, "outreach_send_failed", result.message))
        outcome = "APPROVED"

    db.commit()
    return outcome


def run_organizer_outreach(
    db: Session,
    *,
    discussion_id: int | None,
    opportunity_id: int | None,
    extracted_event: ExtractedEventAI,
    source_url: str,
    community: Community | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    match_score = round((extracted_event.confidence_score + extracted_event.relevance_score) / 2)

    discovered = DiscoveredEvent(
        discussion_id=discussion_id,
        opportunity_id=opportunity_id,
        discovered_by="social_pipeline",
        name=extracted_event.event_name or None,
        date=extracted_event.date or None,
        location=extracted_event.location or None,
        category=extracted_event.category or None,
        url=extracted_event.registration_url or None,
        source_url=source_url or None,
        match_score=match_score,
        organizer_status="PENDING",
        verification_notes=[],
        created_at=datetime.now(timezone.utc),
    )
    db.add(discovered)
    db.flush()

    result: dict[str, Any] = {"discoveredEventId": discovered.id, "matchScore": match_score, "outcome": None, "reason": None}

    if match_score < settings.outreach_match_threshold:
        discovered.organizer_status = "NOT_FOUND"
        result["outcome"] = "SKIPPED_BELOW_THRESHOLD"
        result["reason"] = f"Match score {match_score} is below the configured outreach threshold ({settings.outreach_match_threshold})."
        db.add(_log(opportunity_id, "outreach_skipped_low_score", result["reason"]))
        db.commit()
        return result

    # --- Event verification: is it real, upcoming, and from a trustworthy source? ---
    verification = event_verification.verify_event(extracted_event, community)
    discovered.verification_notes = verification.notes
    if not verification.is_upcoming:
        discovered.organizer_status = "NOT_FOUND"
        result["outcome"] = "REJECTED_NOT_UPCOMING"
        result["reason"] = verification.reason
        db.add(_log(opportunity_id, "outreach_rejected_not_upcoming", verification.reason or "Event date appears to be in the past."))
        db.commit()
        return result

    event_details = EventDetails(
        name=discovered.name,
        date=discovered.date,
        location=discovered.location,
        category=discovered.category,
        url=discovered.url,
        source_url=discovered.source_url,
        organizer_name_hint=extracted_event.organizer or None,
        match_score=match_score,
    )

    contact = organizer_finder.find_organizer(event_details)
    if not contact.found or not contact.email:
        discovered.organizer_status = "NOT_FOUND"
        result["outcome"] = "ORGANIZER_NOT_FOUND"
        result["reason"] = (
            "No publicly listed organizer email was found on the event's own page "
            "(or no event URL was available to check)."
            if not event_details.url
            else "The event page didn't publish a usable organizer email address."
        )
        db.add(_log(opportunity_id, "outreach_skipped_organizer_not_found", result["reason"]))
        db.commit()
        return result

    discovered.organizer_status = "FOUND"
    organizer = _get_or_create_organizer(db, contact)
    discovered.organizer_id = organizer.id
    db.flush()

    if organizer.blocked or suppression.is_suppressed(db, organizer.email):
        result["outcome"] = "SKIPPED_ORGANIZER_BLOCKED"
        result["reason"] = "This organizer was previously restricted from outreach, or has opted out / bounced in the past."
        db.add(_log(opportunity_id, "outreach_skipped_blocked_organizer", result["reason"]))
        db.commit()
        return result

    duplicate = duplicate_check.find_duplicate(db, organizer, discovered.name)
    if duplicate is not None:
        result["outcome"] = "SKIPPED_DUPLICATE"
        result["reason"] = f"Organizer/event already contacted (outreach #{duplicate.id}, status={duplicate.status})."
        db.add(_log(opportunity_id, "outreach_skipped_duplicate", result["reason"]))
        db.commit()
        return result

    content, generated_by = message_generator.generate_outreach_message(event_details, contact)

    message = OutreachMessage(
        event_id=discovered.id,
        organizer_id=organizer.id,
        recipient=contact.email,
        subject=content.subject,
        message=content.body,
        generated_by=generated_by,
        status="PENDING_APPROVAL",
        created_at=datetime.now(timezone.utc),
    )
    db.add(message)
    db.add(_log(opportunity_id, "outreach_drafted_pending_approval", f"Outreach message #{message.id} drafted for {contact.email} — awaiting human approval to send."))
    db.commit()

    result["outreachMessageId"] = message.id
    result["outcome"] = "DRAFTED_PENDING_APPROVAL"
    result["reason"] = "Message drafted and awaiting human approval (Approve, then Send) on the dashboard."
    return result


def run_outreach_agent(db: Session, config: OutreachRunConfig | None = None) -> OutreachRunSummary:
    """Batch entrypoint: selects eligible discovered events/organizers
    (regardless of which agent found them), drafts a message for each, and
    lands it at PENDING_APPROVAL. Logs one `AgentRun` + `OutreachCampaign`
    per call, mirroring `discovery_agent/orchestrator.py`'s discipline —
    fails the whole run honestly (not per-item) if AI isn't configured,
    since drafting is entirely AI/deterministic-fallback dependent."""
    config = config or OutreachRunConfig(max_candidates=get_settings().outreach_max_candidates_per_run)
    ai_client = get_ai_client()

    run = AgentRun(
        agent_type="outreach", status="running", started_at=datetime.now(timezone.utc),
        config_snapshot=asdict(config), summary=OutreachRunSummary().as_dict(), created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    campaign = OutreachCampaign(
        name=f"Outreach batch #{run.id}", agent_type="outreach", status="running",
        config=asdict(config), started_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    summary = OutreachRunSummary()
    try:
        if not ai_client.is_configured:
            raise AIClientError(f"{not_configured_message()} — Agent 2 cannot draft outreach emails without it (the deterministic fallback still exists per-message, but a whole batch run refuses to proceed silently degraded).")

        candidates, selection_summary = eligibility.find_eligible_candidates(db, config)
        summary.candidates_considered = selection_summary.candidates_considered
        summary.skipped_duplicate = selection_summary.skipped_duplicate
        summary.skipped_suppressed = selection_summary.skipped_suppressed
        summary.skipped_no_organizer = selection_summary.skipped_no_organizer

        for event, organizer in candidates:
            message = OutreachMessage(
                event_id=event.id, organizer_id=organizer.id, campaign_id=campaign.id,
                recipient=organizer.email, status="NEW", created_at=datetime.now(timezone.utc),
            )
            db.add(message)
            db.flush()

            message.status = state_machine.transition_outreach_message(message.status, "RESEARCHED")
            db.commit()

            event_details = to_event_details(event)
            contact = to_organizer_contact_info(organizer)
            content, generated_by = message_generator.generate_outreach_message(event_details, contact)

            message.subject = content.subject
            message.message = content.body
            message.generated_by = generated_by
            message.status = state_machine.transition_outreach_message(message.status, "EMAIL_GENERATED")
            message.status = state_machine.transition_outreach_message(message.status, "PENDING_APPROVAL")
            db.add(_log(None, "outreach_drafted_pending_approval", f"Outreach message #{message.id} drafted for {organizer.email} — awaiting human approval."))
            db.commit()
            summary.drafted += 1

            run.summary = summary.as_dict()
            db.add(run)
            db.commit()

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.summary = summary.as_dict()
        campaign.status = "completed"
        campaign.completed_at = datetime.now(timezone.utc)
        db.add(run)
        db.add(campaign)
        db.commit()

    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(exc)
        run.summary = summary.as_dict()
        campaign.status = "failed"
        campaign.completed_at = datetime.now(timezone.utc)
        db.add(run)
        db.add(campaign)
        db.commit()

    return summary
