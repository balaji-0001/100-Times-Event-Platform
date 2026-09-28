"""Event Lifecycle & Organizer Automation Lifecycle State Machines.

Enforces valid state transitions for both Events (Section 10) and Organizers (Section 9),
while keeping legacy `Event.status` ('draft', 'pending', 'published') synchronized so
existing marketplace queries remain 100% compatible.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Event, Organizer, OrganizerProfile
from backend.services.audit import record_audit_log

# ---------------------------------------------------------------------------
# Event Lifecycle State Machine (Section 10)
# ---------------------------------------------------------------------------

EVENT_STATES = (
    "DRAFT",
    "SUBMITTED",
    "TRUST_CHECK",
    "NEEDS_REVIEW",
    "APPROVED",
    "PUBLISHED",
    "REGISTRATION_OPEN",
    "REGISTRATION_CLOSED",
    "EVENT_STARTED",
    "EVENT_COMPLETED",
    "REJECTED",
    "CANCELLED",
    "RESCHEDULED",
)

VALID_EVENT_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"DRAFT", "SUBMITTED", "TRUST_CHECK", "CANCELLED"},
    "SUBMITTED": {"TRUST_CHECK", "NEEDS_REVIEW", "APPROVED", "REJECTED", "DRAFT", "CANCELLED"},
    "TRUST_CHECK": {"APPROVED", "NEEDS_REVIEW", "REJECTED", "PUBLISHED", "REGISTRATION_OPEN"},
    "NEEDS_REVIEW": {"APPROVED", "PUBLISHED", "REGISTRATION_OPEN", "REJECTED", "DRAFT", "CANCELLED"},
    "APPROVED": {"PUBLISHED", "REGISTRATION_OPEN", "CANCELLED", "RESCHEDULED"},
    "PUBLISHED": {"REGISTRATION_OPEN", "REGISTRATION_CLOSED", "EVENT_STARTED", "EVENT_COMPLETED", "CANCELLED", "RESCHEDULED"},
    "REGISTRATION_OPEN": {"REGISTRATION_CLOSED", "EVENT_STARTED", "EVENT_COMPLETED", "CANCELLED", "RESCHEDULED", "PUBLISHED"},
    "REGISTRATION_CLOSED": {"REGISTRATION_OPEN", "EVENT_STARTED", "EVENT_COMPLETED", "CANCELLED", "RESCHEDULED"},
    "EVENT_STARTED": {"EVENT_COMPLETED", "CANCELLED"},
    "EVENT_COMPLETED": {"EVENT_COMPLETED"},
    "REJECTED": {"DRAFT", "SUBMITTED", "TRUST_CHECK", "APPROVED", "NEEDS_REVIEW"},
    "CANCELLED": {"DRAFT", "RESCHEDULED"},
    "RESCHEDULED": {"PUBLISHED", "REGISTRATION_OPEN", "REGISTRATION_CLOSED", "EVENT_STARTED", "CANCELLED", "TRUST_CHECK"},
}


class InvalidStateTransitionError(ValueError):
    """Raised when an invalid Event or Organizer state transition is attempted."""


def legacy_status_for_lifecycle(lifecycle_state: str) -> str:
    """Map rich lifecycle state to the 3-state legacy `Event.status` column
    ('draft', 'pending', 'published') used by existing marketplace cards."""
    state = (lifecycle_state or "DRAFT").upper()
    if state in {"PUBLISHED", "REGISTRATION_OPEN", "REGISTRATION_CLOSED", "EVENT_STARTED", "EVENT_COMPLETED", "RESCHEDULED", "APPROVED"}:
        return "published"
    if state in {"SUBMITTED", "TRUST_CHECK", "NEEDS_REVIEW"}:
        return "pending"
    return "draft"


def transition_event_state(
    db: Session,
    event: Event,
    next_state: str,
    *,
    actor: str = "system",
    actor_id: int | None = None,
    reason: str | None = None,
    force: bool = False,
) -> Event:
    current = (event.lifecycle_state or "DRAFT").upper()
    target = next_state.upper()
    if target not in EVENT_STATES:
        raise InvalidStateTransitionError(f"Unknown event lifecycle state: {target}")

    allowed = VALID_EVENT_TRANSITIONS.get(current, set())
    if not force and current != target and target not in allowed:
        raise InvalidStateTransitionError(
            f"Invalid event state transition from {current} to {target}. Allowed targets: {sorted(allowed)}"
        )

    event.lifecycle_state = target
    event.status = legacy_status_for_lifecycle(target)
    event.updated_at = datetime.now(timezone.utc)
    db.flush()

    record_audit_log(
        db,
        actor=actor,
        actor_id=actor_id,
        action="EVENT_STATE_TRANSITION",
        entity="Event",
        entity_id=event.id,
        result="SUCCESS",
        metadata={"from": current, "to": target, "legacy_status": event.status, "reason": reason},
    )
    return event


# ---------------------------------------------------------------------------
# Organizer Lifecycle Automation (Section 9)
# ---------------------------------------------------------------------------

ORGANIZER_STAGES = (
    "DISCOVERY",
    "INVITED",
    "SIGNED_UP",
    "CREATED_EVENT",
    "SUBMITTED",
    "TRUST_CHECK",
    "APPROVED",
    "PUBLISHED",
    "REGISTRATIONS",
    "EVENT_COMPLETED",
    "FOLLOW_UP",
    "REPEAT_ORGANIZER",
)

_STAGE_ORDER = {stage: idx for idx, stage in enumerate(ORGANIZER_STAGES)}


def advance_organizer_stage(
    db: Session,
    organizer: Organizer | None,
    profile: OrganizerProfile | None,
    next_stage: str,
    *,
    actor: str = "system",
    actor_id: int | None = None,
    note: str | None = None,
) -> str:
    target = next_stage.upper()
    if target not in _STAGE_ORDER:
        return organizer.lifecycle_stage if organizer else "SIGNED_UP"

    now_iso = datetime.now(timezone.utc).isoformat()

    if organizer:
        current_idx = _STAGE_ORDER.get(organizer.lifecycle_stage or "SIGNED_UP", 0)
        if _STAGE_ORDER[target] >= current_idx or target == "REPEAT_ORGANIZER":
            organizer.lifecycle_stage = target

    if profile:
        current_idx = _STAGE_ORDER.get(profile.lifecycle_stage or "SIGNED_UP", 0)
        if _STAGE_ORDER[target] >= current_idx or target == "REPEAT_ORGANIZER":
            profile.lifecycle_stage = target
        history = list(profile.lifecycle_history or [])
        history.append({"stage": target, "timestamp": now_iso, "actor": actor, "note": note or ""})
        profile.lifecycle_history = history
        profile.updated_at = datetime.now(timezone.utc)

    db.flush()
    record_audit_log(
        db,
        actor=actor,
        actor_id=actor_id,
        action="ORGANIZER_STAGE_ADVANCE",
        entity="Organizer",
        entity_id=organizer.id if organizer else (profile.user_id if profile else None),
        result="SUCCESS",
        metadata={"stage": target, "note": note},
    )
    return target
