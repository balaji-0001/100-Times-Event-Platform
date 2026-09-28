"""Trust Agent (Agent 3) — Event Trust, Safety & Completeness Verification Engine.

Purpose:
Determine whether an event submitted by an organizer is trustworthy, legitimate,
complete, duplicate, suspicious, spam, illegal, misleading, or requires human review.

Decision Logic:
- HIGH confidence + safe (score >= threshold, no duplicates, no prohibited/scam signals,
  no missing mandatory fields) -> APPROVED -> automatically publish (`PUBLISHED`).
- MEDIUM or LOW confidence -> NEEDS_REVIEW -> human review queue ("Your event is under review.").
- Clearly invalid / duplicate / prohibited -> REJECTED or DUPLICATE.
"""

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import (
    AgentRun,
    DiscoveredEvent,
    DuplicateCandidate,
    Event,
    Organizer,
    OrganizerProfile,
    TrustDecision,
    TrustReview,
)
from backend.services.audit import record_audit_log
from backend.services.lifecycle import advance_organizer_stage, transition_event_state
from backend.services.notifications import send_templated_notification
from backend.services.social_agent.ai_client import AIClientError, get_ai_client

PROHIBITED_TERMS = (
    "ponzi",
    "guaranteed 100x crypto return",
    "double your money overnight",
    "illegal weapons",
    "darknet market",
    "pyramid scheme",
    "unlicensed casino",
    "wire transfer only no refund",
    "whatsapp crypto group signal",
)

SPAM_PATTERNS = (
    r"(?i)\b(buy cheap|free money|click here to claim|100% guaranteed profit|earn \$\d+ daily)\b",
    r"(.)\1{7,}",  # excessive repeated characters
)


class DuplicateCandidateSchema(BaseModel):
    candidate_event_id: int | None = None
    candidate_discovered_event_id: int | None = None
    title: str
    similarity_score: int = Field(ge=0, le=100)
    reason: str


class TrustAgentResult(BaseModel):
    status: Literal["APPROVED", "NEEDS_REVIEW", "REJECTED", "DUPLICATE"]
    score: int = Field(ge=0, le=100)
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duplicate_candidates: list[DuplicateCandidateSchema] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    recommended_action: Literal["AUTO_PUBLISH", "HUMAN_REVIEW", "REJECT", "REQUEST_CHANGES"]
    checks_summary: dict[str, bool] = Field(default_factory=dict)


def _is_valid_http_url(url: str | None) -> bool:
    if not url:
        return True
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _detect_duplicates(db: Session, event: Event) -> list[DuplicateCandidateSchema]:
    """Compare the event against existing published/pending Events and DiscoveredEvents."""
    candidates: list[DuplicateCandidateSchema] = []
    title_norm = (event.title or "").strip().lower()
    if not title_norm:
        return candidates

    existing_events = db.scalars(
        select(Event).where(Event.id != event.id, Event.status.in_(["published", "pending"]))
    ).all()

    for other in existing_events:
        other_title = (other.title or "").strip().lower()
        ratio = int(round(SequenceMatcher(None, title_norm, other_title).ratio() * 100))
        same_date = bool(event.start_date and other.start_date and event.start_date == other.start_date)
        if ratio >= 85 or (ratio >= 72 and same_date):
            candidates.append(
                DuplicateCandidateSchema(
                    candidate_event_id=other.id,
                    title=other.title,
                    similarity_score=min(100, ratio + (10 if same_date else 0)),
                    reason=f"Similar title ({ratio}% match)" + (" on the exact same date" if same_date else ""),
                )
            )

    discovered_rows = db.scalars(select(DiscoveredEvent).limit(100)).all()
    for disc in discovered_rows:
        disc_title = (disc.name or "").strip().lower()
        if not disc_title:
            continue
        ratio = int(round(SequenceMatcher(None, title_norm, disc_title).ratio() * 100))
        same_date = bool(event.start_date and disc.event_date and event.start_date == disc.event_date)
        if ratio >= 92 and same_date:
            candidates.append(
                DuplicateCandidateSchema(
                    candidate_discovered_event_id=disc.id,
                    title=disc.name or "Discovered Event",
                    similarity_score=ratio,
                    reason=f"Matches discovered external listing ({ratio}% title similarity on same date)",
                )
            )
    return candidates


def _ai_trust_augmentation(event: Event, organizer: Organizer | None) -> dict[str, Any] | None:
    """Ask Gemini/Anthropic via unified `ai_client` for semantic trust assessment when configured."""
    client = get_ai_client()
    if not client.is_configured:
        return None
    schema = {
        "type": "object",
        "properties": {
            "is_safe": {"type": "boolean"},
            "semantic_score": {"type": "integer"},
            "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
            "positive_signals": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["is_safe", "semantic_score", "confidence", "risk_flags", "positive_signals"],
    }
    prompt = (
        f"Title: {event.title}\n"
        f"Description: {event.description}\n"
        f"Organizer: {organizer.name if organizer else 'Unknown'} (Company: {organizer.company_name if organizer else ''})\n"
        f"Format: {event.format}\n"
        f"City/Address: {event.city_name or ''} / {event.full_address or ''}\n"
        f"Price: {event.price}\n"
        f"Registration URL: {event.registration_url or ''}\n"
        f"Online Meeting URL: {event.online_meeting_url or ''}\n"
    )
    try:
        return client.generate_structured(
            system=(
                "You are Trust Agent (Agent 3) for the 100 TIMES event platform. "
                "Analyze this event submission for legitimacy, completeness, scam/spam indicators, "
                "prohibited content, or misleading claims."
            ),
            user=prompt,
            tool_name="trust_assessment",
            tool_description="Structured trust and safety assessment of an event submission",
            input_schema=schema,
            max_tokens=512,
        )
    except AIClientError:
        return None


def evaluate_event_trust(
    db: Session,
    event: Event,
    *,
    organizer: Organizer | None = None,
    profile: OrganizerProfile | None = None,
    auto_publish_if_approved: bool = True,
) -> tuple[TrustReview, TrustAgentResult]:
    """Run full Trust Agent evaluation on `event`, persist `TrustReview`, `TrustDecision`,
    `DuplicateCandidate`, `AgentRun`, and `AuditLog`, and transition event state accordingly."""
    settings = get_settings()
    run = AgentRun(
        agent_type="trust_agent",
        status="running",
        config_snapshot={"event_id": event.id, "auto_approve_score": settings.trust_agent_auto_approve_score},
        summary={},
    )
    db.add(run)
    db.flush()

    transition_event_state(db, event, "TRUST_CHECK", actor="trust_agent", reason="Running Trust Agent validation")

    organizer = organizer or event.organizer
    if not profile and organizer and organizer.user_id:
        profile = db.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == organizer.user_id))

    reasons: list[str] = []
    warnings: list[str] = []
    missing_fields: list[str] = []
    score = 100

    # 1. Completeness & Required Fields inspection
    if not event.title or len(event.title.strip()) < 5:
        missing_fields.append("title")
        score -= 25
    if not event.description or len(event.description.strip()) < settings.trust_agent_min_description_length:
        missing_fields.append("description")
        warnings.append(f"Event description is shorter than {settings.trust_agent_min_description_length} characters.")
        score -= 20
    if not event.start_date:
        missing_fields.append("start_date")
        score -= 25
    if not event.start_time:
        missing_fields.append("start_time")
        score -= 10
    if event.format in ("in-person", "hybrid", "offline") and not (event.venue or event.full_address or event.city_name):
        missing_fields.append("venue_or_address")
        warnings.append("Offline/hybrid event is missing a specific venue or city address.")
        score -= 20
    if event.format in ("online", "hybrid") and not event.online_meeting_url:
        warnings.append("Online/hybrid event has not provided an online meeting URL yet.")
        score -= 10

    # 2. Organizer Identity & Repeated Submission Velocity
    organizer_verified = bool(
        (organizer and (organizer.verified or organizer.email or organizer.website))
        or (profile and (profile.email_verified or profile.organization_name))
    )
    if organizer_verified:
        reasons.append("Organizer identity and contact metadata present.")
    else:
        warnings.append("Organizer profile is missing verified organization/contact details.")
        score -= 15

    if organizer:
        day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_count = int(
            db.scalar(
                select(func.count(Event.id)).where(
                    Event.organizer_id == organizer.id,
                    Event.created_at >= day_ago,
                )
            )
            or 0
        )
        if recent_count > settings.trust_agent_max_daily_submissions_per_organizer:
            warnings.append(f"High submission velocity: {recent_count} events submitted in the last 24h.")
            score -= 25

    # 3. URL & Image metadata validation
    for url_label, url_val in (
        ("registration_url", event.registration_url),
        ("online_meeting_url", event.online_meeting_url),
        ("image", event.image),
    ):
        if url_val and not _is_valid_http_url(url_val):
            warnings.append(f"Invalid URL format for {url_label}.")
            score -= 15

    # 4. Prohibited, Illegal, Scam & Spam detection
    combined_text = f"{event.title or ''} {event.description or ''} {event.terms_policy or ''}".lower()
    prohibited_hits = [term for term in PROHIBITED_TERMS if term in combined_text]
    spam_hits = [pat for pat in SPAM_PATTERNS if re.search(pat, combined_text)]

    if prohibited_hits:
        reasons.append(f"Prohibited or high-risk scam content detected: {', '.join(prohibited_hits)}")
        score = max(0, score - 75)
    if spam_hits:
        warnings.append("Promotional spam or repetitive text patterns detected.")
        score = max(0, score - 35)

    # 5. Ticket & Capacity sanity check
    if event.price and float(event.price) > 500000:
        warnings.append("Unusually high ticket price (> 500,000 INR) requires human verification.")
        score -= 25
    if event.capacity is not None and event.capacity <= 0:
        warnings.append("Event capacity must be a positive integer.")
        score -= 15

    # 6. Duplicate detection
    dup_candidates = _detect_duplicates(db, event)
    high_dup = any(d.similarity_score >= 90 for d in dup_candidates)
    if high_dup:
        reasons.append(f"Duplicate event detected ({dup_candidates[0].title}, {dup_candidates[0].similarity_score}% match).")
        score = min(score, 30)
    elif dup_candidates:
        warnings.append(f"Potential similar event found: {dup_candidates[0].title} ({dup_candidates[0].similarity_score}% match).")
        score -= 20

    # 7. Optional AI semantic analysis
    ai_eval = _ai_trust_augmentation(event, organizer)
    if ai_eval:
        ai_score = int(ai_eval.get("semantic_score", score))
        score = int(round((score * 0.7) + (ai_score * 0.3)))
        for flag in ai_eval.get("risk_flags") or []:
            warnings.append(f"AI Risk Signal: {flag}")
        for pos in ai_eval.get("positive_signals") or []:
            reasons.append(pos)
        if not ai_eval.get("is_safe", True):
            score = min(score, 40)

    score = max(0, min(100, score))

    checks_summary = {
        "information_complete": len(missing_fields) == 0,
        "organizer_verified": organizer_verified,
        "no_duplicate_detected": len(dup_candidates) == 0,
        "no_major_risk_detected": len(prohibited_hits) == 0 and len(spam_hits) == 0,
    }

    # Conservative Decision Matrix
    if prohibited_hits:
        final_status: Literal["APPROVED", "NEEDS_REVIEW", "REJECTED", "DUPLICATE"] = "REJECTED"
        confidence: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
        recommended_action: Literal["AUTO_PUBLISH", "HUMAN_REVIEW", "REJECT", "REQUEST_CHANGES"] = "REJECT"
    elif high_dup:
        final_status = "DUPLICATE"
        confidence = "HIGH"
        recommended_action = "REJECT"
    elif missing_fields:
        final_status = "NEEDS_REVIEW"
        confidence = "LOW"
        recommended_action = "REQUEST_CHANGES"
        reasons.append(f"Missing or incomplete fields: {', '.join(missing_fields)}")
    elif score >= settings.trust_agent_auto_approve_score and not warnings and all(checks_summary.values()):
        final_status = "APPROVED"
        confidence = "HIGH"
        recommended_action = "AUTO_PUBLISH"
        reasons.append("All completeness, organizer identity, duplicate, and safety checks passed with high confidence.")
    elif score >= 55:
        final_status = "NEEDS_REVIEW"
        confidence = "MEDIUM"
        recommended_action = "HUMAN_REVIEW"
        reasons.append("Event requires human moderation review before public listing.")
    else:
        final_status = "NEEDS_REVIEW"
        confidence = "LOW"
        recommended_action = "HUMAN_REVIEW"
        reasons.append("Low trust score or multiple risk warnings; flagged for human review.")

    result = TrustAgentResult(
        status=final_status,
        score=score,
        confidence=confidence,
        reasons=reasons,
        warnings=warnings,
        duplicate_candidates=dup_candidates,
        missing_fields=missing_fields,
        recommended_action=recommended_action,
        checks_summary=checks_summary,
    )

    # Persist TrustReview, DuplicateCandidate, TrustDecision
    review = TrustReview(
        event_id=event.id,
        organizer_id=organizer.id if organizer else None,
        status=result.status,
        score=result.score,
        confidence=result.confidence,
        reasons=result.reasons,
        warnings=result.warnings,
        duplicate_candidates=[d.model_dump() for d in result.duplicate_candidates],
        missing_fields=result.missing_fields,
        recommended_action=result.recommended_action,
        checks_summary=result.checks_summary,
        evaluated_by="trust_agent",
    )
    db.add(review)
    db.flush()

    for dup in result.duplicate_candidates:
        db.add(
            DuplicateCandidate(
                event_id=event.id,
                candidate_event_id=dup.candidate_event_id,
                candidate_discovered_event_id=dup.candidate_discovered_event_id,
                candidate_title=dup.title,
                similarity_score=dup.similarity_score,
                match_reason=dup.reason,
            )
        )

    decision_row = TrustDecision(
        trust_review_id=review.id,
        event_id=event.id,
        actor_type="TRUST_AGENT",
        actor_id=None,
        decision=result.recommended_action,
        previous_status="TRUST_CHECK",
        new_status=result.status,
        notes="; ".join(result.reasons or result.warnings),
    )
    db.add(decision_row)

    event.trust_score = result.score
    event.trust_status = result.status
    event.trust_confidence = result.confidence

    # Apply state transitions and notifications
    if result.status == "APPROVED" and auto_publish_if_approved:
        transition_event_state(db, event, "APPROVED", actor="trust_agent", reason="High confidence Trust Agent approval")
        transition_event_state(db, event, "PUBLISHED", actor="trust_agent", reason="Auto-published after Trust Agent approval")
        if organizer:
            advance_organizer_stage(db, organizer, profile, "PUBLISHED", actor="trust_agent", note=f"Event #{event.id} published")
        send_templated_notification(
            db,
            template_key="event_published",
            user_id=organizer.user_id if organizer else None,
            recipient_email=organizer.email if organizer else None,
            context={
                "name": organizer.name if organizer else "Organizer",
                "event_title": event.title,
                "trust_score": result.score,
                "trust_confidence": result.confidence,
                "event_url": f"{settings.platform_listing_url}/events/{event.slug}",
            },
        )
    elif result.status in ("REJECTED", "DUPLICATE"):
        transition_event_state(db, event, "REJECTED", actor="trust_agent", reason="; ".join(result.reasons))
        send_templated_notification(
            db,
            template_key="event_rejected",
            user_id=organizer.user_id if organizer else None,
            recipient_email=organizer.email if organizer else None,
            context={
                "name": organizer.name if organizer else "Organizer",
                "event_title": event.title,
                "reasons": "; ".join(result.reasons or result.warnings),
            },
        )
    else:
        transition_event_state(db, event, "NEEDS_REVIEW", actor="trust_agent", reason="Flagged for human review")
        if organizer:
            advance_organizer_stage(db, organizer, profile, "TRUST_CHECK", actor="trust_agent", note="Queued for human review")
        send_templated_notification(
            db,
            template_key="event_needs_review",
            user_id=organizer.user_id if organizer else None,
            recipient_email=organizer.email if organizer else None,
            context={
                "name": organizer.name if organizer else "Organizer",
                "event_title": event.title,
                "trust_confidence": result.confidence,
            },
        )

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.summary = {
        "event_id": event.id,
        "status": result.status,
        "score": result.score,
        "confidence": result.confidence,
        "recommended_action": result.recommended_action,
    }
    db.flush()

    record_audit_log(
        db,
        actor="trust_agent",
        action="TRUST_AGENT_DECISION",
        entity="Event",
        entity_id=event.id,
        result=result.status,
        metadata={
            "review_id": review.id,
            "score": result.score,
            "confidence": result.confidence,
            "recommended_action": result.recommended_action,
        },
    )
    return review, result


def admin_decide_trust_review(
    db: Session,
    review: TrustReview,
    *,
    decision: Literal["APPROVE", "REJECT", "REQUEST_CHANGES"],
    admin_user_id: int,
    notes: str | None = None,
) -> TrustReview:
    """Execute an Admin moderation decision (Approve, Reject, Request Changes) on a TrustReview."""
    event = db.get(Event, review.event_id)
    if not event:
        raise ValueError("Event not found for TrustReview")

    organizer = db.get(Organizer, event.organizer_id) if event.organizer_id else None
    profile = (
        db.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == organizer.user_id))
        if organizer and organizer.user_id
        else None
    )

    prev_status = review.status
    if decision == "APPROVE":
        review.status = "APPROVED"
        review.recommended_action = "AUTO_PUBLISH"
        event.trust_status = "APPROVED"
        transition_event_state(db, event, "APPROVED", actor="admin", actor_id=admin_user_id, reason=notes, force=True)
        transition_event_state(db, event, "PUBLISHED", actor="admin", actor_id=admin_user_id, reason=notes, force=True)
        if organizer:
            advance_organizer_stage(db, organizer, profile, "PUBLISHED", actor="admin", actor_id=admin_user_id, note=notes)
        send_templated_notification(
            db,
            template_key="event_published",
            user_id=organizer.user_id if organizer else None,
            recipient_email=organizer.email if organizer else None,
            context={
                "name": organizer.name if organizer else "Organizer",
                "event_title": event.title,
                "trust_score": review.score,
                "trust_confidence": review.confidence,
                "event_url": f"/events/{event.slug}",
            },
        )
    elif decision == "REJECT":
        review.status = "REJECTED"
        review.recommended_action = "REJECT"
        event.trust_status = "REJECTED"
        transition_event_state(db, event, "REJECTED", actor="admin", actor_id=admin_user_id, reason=notes, force=True)
        send_templated_notification(
            db,
            template_key="event_rejected",
            user_id=organizer.user_id if organizer else None,
            recipient_email=organizer.email if organizer else None,
            context={
                "name": organizer.name if organizer else "Organizer",
                "event_title": event.title,
                "reasons": notes or "Moderation team rejected the listing.",
            },
        )
    else:  # REQUEST_CHANGES
        review.status = "NEEDS_REVIEW"
        review.recommended_action = "REQUEST_CHANGES"
        event.trust_status = "NEEDS_REVIEW"
        transition_event_state(db, event, "DRAFT", actor="admin", actor_id=admin_user_id, reason=notes, force=True)
        send_templated_notification(
            db,
            template_key="event_rejected",
            user_id=organizer.user_id if organizer else None,
            recipient_email=organizer.email if organizer else None,
            context={
                "name": organizer.name if organizer else "Organizer",
                "event_title": event.title,
                "reasons": notes or "Please update the requested fields and resubmit.",
            },
        )

    review.updated_at = datetime.now(timezone.utc)
    db.add(
        TrustDecision(
            trust_review_id=review.id,
            event_id=event.id,
            actor_type="ADMIN",
            actor_id=admin_user_id,
            decision=decision,
            previous_status=prev_status,
            new_status=review.status,
            notes=notes,
        )
    )
    db.flush()

    record_audit_log(
        db,
        actor="admin",
        actor_id=admin_user_id,
        action=f"ADMIN_TRUST_{decision}",
        entity="TrustReview",
        entity_id=review.id,
        result=review.status,
        metadata={"event_id": event.id, "notes": notes},
    )
    return review
