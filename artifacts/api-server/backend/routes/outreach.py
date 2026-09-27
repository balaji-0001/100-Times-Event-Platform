"""Organizer Outreach admin API ("Agent 2") — list/inspect/act on outreach
records, the batch research+draft trigger, plus the legacy single-post
manual test-trigger and the follow-up-sweep endpoint n8n (or an admin)
calls. Nested under the existing `/acquisition` prefix (not moved to a
clean `/outreach` prefix) because the current admin dashboard
(`AcquisitionDashboardPage` in `artifacts/100-times/src/App.tsx`) already
calls these exact paths — kept stable so the working outreach tab doesn't
break ahead of the Phase 9 dashboard rebuild.

Every endpoint requires ADMIN — the one other outreach-adjacent gap
(`routes/acquisition.py` has none) is a pre-existing issue, not fixed here.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.db import get_db
from backend.dependencies import require_roles
from backend.models import AgentAction, AgentRun, DiscoveredEvent, DiscoveredOrganizer, OutreachMessage, User
from backend.schemas import (
    AgentRunOut,
    DiscoveredEventOut,
    DiscoveredOrganizerOut,
    OutreachActionRequest,
    OutreachBatchRunRequest,
    OutreachEditRequest,
    OutreachMessageOut,
    OutreachRunRequest,
    OutreachStatsOut,
)
from backend.services.social_agent import state_machine
from backend.services.social_agent.outreach import suppression
from backend.services.social_agent.outreach.followup import process_followups
from backend.services.social_agent.outreach.orchestrator import run_organizer_outreach, run_outreach_agent, send_outreach_message
from backend.services.social_agent.outreach.senders import provider_status
from backend.services.social_agent.outreach.types import OutreachRunConfig
from backend.services.social_agent.pipeline import event_extraction, normalize

router = APIRouter(prefix="/acquisition/outreach", tags=["organizer-outreach"])

# Statuses a message can still be edited/withdrawn in — anything before a real send attempt.
_PRE_SEND_STATUSES = ("NEW", "RESEARCHED", "EMAIL_GENERATED", "PENDING_APPROVAL", "APPROVED", "FOLLOW_UP_DUE")
_admin = Depends(require_roles("ADMIN"))


def _serialize(message: OutreachMessage) -> OutreachMessageOut:
    event = message.event
    return OutreachMessageOut(
        id=message.id,
        event=DiscoveredEventOut.model_validate(event),
        organizer=(DiscoveredOrganizerOut.model_validate(message.organizer) if message.organizer else None),
        campaign_id=message.campaign_id,
        recipient=message.recipient,
        subject=message.subject,
        message=message.message,
        generated_by=message.generated_by,
        status=message.status,
        failure_reason=message.failure_reason,
        send_attempt_count=message.send_attempt_count,
        sent_at=message.sent_at,
        last_contacted_at=message.last_contacted_at,
        response_at=message.response_at,
        follow_up_sent_at=message.follow_up_sent_at,
        message_id=message.message_id,
        created_at=message.created_at,
    )


@router.get("", response_model=list[OutreachMessageOut])
def list_outreach(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[OutreachMessageOut]:
    stmt = select(OutreachMessage).options(
        selectinload(OutreachMessage.event).selectinload(DiscoveredEvent.sources),
        selectinload(OutreachMessage.organizer),
    ).order_by(OutreachMessage.created_at.desc())
    if status_filter:
        stmt = stmt.where(OutreachMessage.status == status_filter.upper())
    messages = db.execute(stmt).scalars().all()
    return [_serialize(m) for m in messages]


@router.get("/stats", response_model=OutreachStatsOut)
def outreach_stats(db: Session = Depends(get_db), _user: User = _admin) -> OutreachStatsOut:
    events_found = db.execute(select(func.count(DiscoveredEvent.id))).scalar_one()
    threshold = get_settings().outreach_match_threshold
    qualified_events = db.execute(
        select(func.count(DiscoveredEvent.id)).where(DiscoveredEvent.match_score >= threshold)
    ).scalar_one()
    organizers_found = db.execute(select(func.count(DiscoveredOrganizer.id))).scalar_one()
    messages_sent = db.execute(select(func.count(OutreachMessage.id)).where(OutreachMessage.sent_at.isnot(None))).scalar_one()
    follow_ups_sent = db.execute(
        select(func.count(OutreachMessage.id)).where(OutreachMessage.follow_up_sent_at.isnot(None))
    ).scalar_one()
    responses = db.execute(select(func.count(OutreachMessage.id)).where(OutreachMessage.status == "REPLIED")).scalar_one()
    failed_messages = db.execute(select(func.count(OutreachMessage.id)).where(OutreachMessage.failure_reason.isnot(None))).scalar_one()

    return OutreachStatsOut(
        events_found=events_found,
        qualified_events=qualified_events,
        organizers_found=organizers_found,
        messages_sent=messages_sent,
        follow_ups_sent=follow_ups_sent,
        responses=responses,
        failed_messages=failed_messages,
        email_provider_status=provider_status()["status"],
    )


@router.get("/runs", response_model=list[AgentRunOut])
def list_outreach_runs(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db), _user: User = _admin) -> list[AgentRunOut]:
    stmt = select(AgentRun).where(AgentRun.agent_type == "outreach").order_by(AgentRun.id.desc()).limit(limit)
    return [AgentRunOut.model_validate(run) for run in db.execute(stmt).scalars().all()]


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_outreach_run(run_id: int, db: Session = Depends(get_db), _user: User = _admin) -> AgentRunOut:
    run = db.get(AgentRun, run_id)
    if run is None or run.agent_type != "outreach":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outreach run not found")
    return AgentRunOut.model_validate(run)


@router.get("/{outreach_id}", response_model=OutreachMessageOut)
def get_outreach(outreach_id: int, db: Session = Depends(get_db), _user: User = _admin) -> OutreachMessageOut:
    message = db.get(OutreachMessage, outreach_id)
    if not message:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outreach record not found")
    return _serialize(message)


@router.patch("/{outreach_id}/edit", response_model=OutreachMessageOut)
def edit_outreach(outreach_id: int, payload: OutreachEditRequest, db: Session = Depends(get_db), _user: User = _admin) -> OutreachMessageOut:
    message = db.get(OutreachMessage, outreach_id)
    if not message:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outreach record not found")
    if message.status not in _PRE_SEND_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot edit an outreach message that is already {message.status}")
    message.subject = payload.subject
    message.message = payload.message
    db.commit()
    return _serialize(message)


@router.post("/{outreach_id}/action", response_model=OutreachMessageOut)
def act_on_outreach(outreach_id: int, payload: OutreachActionRequest, db: Session = Depends(get_db), _user: User = _admin) -> OutreachMessageOut:
    message = db.get(OutreachMessage, outreach_id)
    if not message:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outreach record not found")

    now = datetime.now(timezone.utc)

    def _transition(target: str) -> None:
        try:
            message.status = state_machine.transition_outreach_message(message.status, target)
        except state_machine.InvalidTransitionError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    if payload.action == "approve":
        _transition("APPROVED")
        db.add(AgentAction(action_type="outreach_approved", result=f"OutreachMessage #{message.id} approved by admin.", created_at=now))
        db.commit()

    elif payload.action in ("send", "retry"):
        if message.status != "APPROVED":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot send — outreach must be APPROVED first (currently {message.status}).")
        outcome = send_outreach_message(db, message)
        if outcome == "CAP_REACHED":
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Daily outreach cap ({get_settings().outreach_daily_cap}) reached — try again tomorrow or raise OUTREACH_DAILY_CAP.")

    elif payload.action in ("reject", "ignore"):
        _transition("REJECTED")
        db.add(AgentAction(action_type="outreach_rejected", result=f"OutreachMessage #{message.id} rejected by admin." + (f" Reason: {payload.reason}" if payload.reason else ""), created_at=now))
        db.commit()

    elif payload.action == "mark_replied":
        _transition("REPLIED")
        message.response_at = now
        db.add(AgentAction(action_type="outreach_marked_replied", result=f"OutreachMessage #{message.id} manually marked replied.", created_at=now))
        db.commit()

    elif payload.action == "opt_out":
        _transition("OPTED_OUT")
        if message.recipient:
            suppression.suppress(db, message.recipient, reason="opted_out", note=payload.reason)
        db.add(AgentAction(action_type="outreach_opted_out", result=f"OutreachMessage #{message.id} — recipient opted out." + (f" Reason: {payload.reason}" if payload.reason else ""), created_at=now))
        db.commit()

    elif payload.action == "restrict_organizer":
        if message.organizer:
            message.organizer.blocked = True
            if message.organizer.email:
                suppression.suppress(db, message.organizer.email, reason="admin_restricted", note=payload.reason)
        _transition("REJECTED")
        db.add(AgentAction(action_type="outreach_organizer_restricted", result=f"Organizer #{message.organizer_id} restricted from future outreach.", created_at=now))
        db.commit()

    return _serialize(message)


@router.post("/batch-run")
def trigger_batch_run(payload: OutreachBatchRunRequest | None = None, db: Session = Depends(get_db), _user: User = _admin) -> dict[str, Any]:
    """Agent 2's main entrypoint: selects eligible discovered events/
    organizers (from either producer) and drafts a message for each,
    landing at PENDING_APPROVAL. Mirrors `/discovery/run`'s manual-trigger
    shape and blocking behavior."""
    config = OutreachRunConfig(max_candidates=get_settings().outreach_max_candidates_per_run)
    if payload and payload.max_candidates is not None:
        config.max_candidates = payload.max_candidates

    summary = run_outreach_agent(db, config)
    run = db.execute(select(AgentRun).where(AgentRun.agent_type == "outreach").order_by(AgentRun.id.desc())).scalars().first()
    return {"runId": run.id if run else None, "status": run.status if run else "unknown", **summary.as_dict()}


@router.post("/run")
def run_outreach_manual(payload: OutreachRunRequest, db: Session = Depends(get_db), _user: User = _admin) -> dict[str, Any]:
    """Legacy manual test entry point: runs event extraction + the full
    Organizer Outreach flow on one post directly, without needing a real
    discovery scan first. Mirrors `/acquisition/test-discussion`'s role for
    the original pipeline. Distinct from `/batch-run` (Agent 2's real
    selection-based entrypoint)."""
    norm = normalize.normalize_signal(
        db, platform=payload.platform, community_name=payload.community_name,
        title=payload.title, content=payload.content, url=payload.url,
    )
    extraction = event_extraction.extract_event(payload.topic_summary, payload.title, payload.content)
    if not extraction.success:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, extraction.error or "Event extraction failed")
    if not extraction.data.is_genuine_event:
        return {"outcome": "NOT_A_GENUINE_EVENT", "reason": extraction.data.reason, "extractedEvent": extraction.data.model_dump()}

    result = run_organizer_outreach(
        db, discussion_id=norm.discussion.id, opportunity_id=None,
        extracted_event=extraction.data, source_url=payload.url, community=norm.community,
    )
    result["extractedEvent"] = extraction.data.model_dump()
    return result


@router.post("/process-followups")
def run_process_followups(db: Session = Depends(get_db), _user: User = _admin) -> dict[str, Any]:
    return process_followups(db)
