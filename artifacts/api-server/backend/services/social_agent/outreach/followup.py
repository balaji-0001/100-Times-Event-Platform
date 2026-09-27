"""7-day follow-up sweep. MVP scope, matching the spec exactly: draft at
most ONE follow-up per outreach message. Per the "never send automatically"
rule (no follow-up carve-out in the spec), Stage 1 now DRAFTS the follow-up
and stops at `FOLLOW_UP_DUE` — a human still approves+sends it, same as any
other message, rather than it going out unattended. This module also closes
out the workflow's final "Response / Final status" step in the one honest
way available without an inbound-email/webhook integration (which this
project has no credentials or infrastructure for): if a follow-up was
approved and sent and still nothing changed after another
`outreach_followup_days` window, the message is marked terminal
`COMPLETED`. A human marking a reply as received (`REPLIED`) is a manual
dashboard action — see `routes/outreach.py` — since there is no real
inbound-email channel wired up to detect that automatically.

Intended to be called on a schedule — either the existing n8n Schedule
Trigger pattern (see `infra/n8n/workflows/outreach_followup.json`) or a
manual `POST /api/acquisition/outreach/process-followups`.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AgentAction, OutreachMessage
from backend.services.social_agent import state_machine
from backend.services.social_agent.outreach.message_generator import generate_followup_message
from backend.services.social_agent.outreach.orchestrator import to_event_details, to_organizer_contact_info


def process_followups(db: Session) -> dict[str, Any]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    followup_cutoff = now - timedelta(days=settings.outreach_followup_days)
    no_response_cutoff = now - timedelta(days=settings.outreach_followup_days)

    summary = {"followUpsDrafted": 0, "markedCompleted": 0}

    # --- Stage 1: DELIVERED, past the wait window, never followed up -> draft the one allowed follow-up ---
    due_for_followup = db.execute(
        select(OutreachMessage).where(
            OutreachMessage.status == "DELIVERED",
            OutreachMessage.sent_at.isnot(None),
            OutreachMessage.sent_at <= followup_cutoff,
            OutreachMessage.follow_up_sent_at.is_(None),
        )
    ).scalars().all()

    for message in due_for_followup:
        event_details = to_event_details(message.event)
        contact = to_organizer_contact_info(message.organizer)
        content, generated_by = generate_followup_message(event_details, contact)
        message.subject = content.subject
        message.message = content.body
        message.generated_by = generated_by
        message.status = state_machine.transition_outreach_message(message.status, "FOLLOW_UP_DUE")
        db.add(AgentAction(action_type="outreach_followup_drafted", result=f"OutreachMessage #{message.id} follow-up drafted — awaiting human approval.", created_at=now))
        summary["followUpsDrafted"] += 1

    # --- Stage 2: DELIVERED, follow-up sent, past another full window with still no reply -> terminal COMPLETED ---
    stale_followups = db.execute(
        select(OutreachMessage).where(
            OutreachMessage.status == "DELIVERED",
            OutreachMessage.follow_up_sent_at.isnot(None),
            OutreachMessage.follow_up_sent_at <= no_response_cutoff,
            OutreachMessage.response_at.is_(None),
        )
    ).scalars().all()

    for message in stale_followups:
        message.status = state_machine.transition_outreach_message(message.status, "COMPLETED")
        db.add(AgentAction(action_type="outreach_marked_completed", result=f"OutreachMessage #{message.id} — no response after follow-up.", created_at=now))
        summary["markedCompleted"] += 1

    db.commit()
    return summary
