"""Per-attendee event state: favourites, recently viewed, registration.

Where each fact lives (no duplication):
- platform event favourites   -> `saved_events` (same table the site's heart button uses)
- platform event registration -> `registrations` (written only by the real registration API)
- discovered event favourites, every view, "opened the official registration
  page", and the attendee's own confirmation of an external registration
  -> `attendee_event_activity`

Registration status is only ever REGISTERED when there is a platform
`Registration` row, or the attendee explicitly confirmed they completed the
organizer's external registration. Opening the registration page is
recorded separately and is never treated as registering.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AttendeeEventActivity, Registration, SavedEvent
from backend.services.attendee_agent.catalog import DISCOVERED, PLATFORM, CatalogEvent, fingerprint

EXTERNAL_STATUSES = ("NONE", "REGISTERED", "NOT_ATTENDING")
_PLATFORM_STATUS = {
    "confirmed": "REGISTERED",
    "registered": "REGISTERED",
    "attended": "REGISTERED",
    "waitlisted": "WAITLISTED",
    "cancelled": "CANCELLED",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_activity(db: Session, user_id: int, kind: str, event_id: int, create: bool = False) -> AttendeeEventActivity | None:
    column = AttendeeEventActivity.event_id if kind == PLATFORM else AttendeeEventActivity.discovered_event_id
    row = db.scalar(select(AttendeeEventActivity).where(AttendeeEventActivity.user_id == user_id, column == event_id))
    if row is None and create:
        row = AttendeeEventActivity(
            user_id=user_id,
            event_id=event_id if kind == PLATFORM else None,
            discovered_event_id=event_id if kind == DISCOVERED else None,
        )
        db.add(row)
        db.flush()
    return row


def _ensure_fingerprint(row: AttendeeEventActivity, item: CatalogEvent) -> None:
    if row.change_fingerprint is None:
        row.change_fingerprint = fingerprint(item)


def record_view(db: Session, user_id: int, item: CatalogEvent) -> None:
    row = get_activity(db, user_id, item.kind, item.id, create=True)
    row.view_count = (row.view_count or 0) + 1
    row.last_viewed_at = _now()
    db.flush()


def set_saved(db: Session, user_id: int, item: CatalogEvent, saved: bool) -> None:
    if item.kind == PLATFORM:
        existing = db.scalar(select(SavedEvent).where(SavedEvent.user_id == user_id, SavedEvent.event_id == item.id))
        if saved and not existing:
            db.add(SavedEvent(user_id=user_id, event_id=item.id))
        elif not saved and existing:
            db.delete(existing)
        if saved:
            _ensure_fingerprint(get_activity(db, user_id, item.kind, item.id, create=True), item)
    else:
        row = get_activity(db, user_id, item.kind, item.id, create=True)
        row.is_saved = saved
        row.saved_at = _now() if saved else None
        if saved:
            _ensure_fingerprint(row, item)
    db.flush()


def mark_registration_opened(db: Session, user_id: int, item: CatalogEvent) -> None:
    row = get_activity(db, user_id, item.kind, item.id, create=True)
    row.registration_opened_at = _now()
    db.flush()


def set_external_registration(db: Session, user_id: int, item: CatalogEvent, status: str) -> AttendeeEventActivity:
    """Record the attendee's own answer about an EXTERNAL registration.
    Callers must only invoke this after the attendee explicitly confirmed."""
    if item.kind != DISCOVERED:
        raise ValueError("Platform events are registered through 100 TIMES registration, not self-reported")
    if status not in EXTERNAL_STATUSES:
        raise ValueError(f"status must be one of {', '.join(EXTERNAL_STATUSES)}")
    row = get_activity(db, user_id, item.kind, item.id, create=True)
    row.external_registration_status = status
    row.external_registration_confirmed_at = _now() if status != "NONE" else None
    if status == "REGISTERED":
        _ensure_fingerprint(row, item)
    db.flush()
    return row


def states_for(db: Session, user_id: int, refs: list[tuple[str, int]]) -> dict[tuple[str, int], dict[str, Any]]:
    """Saved/registration/view state for each requested event."""
    platform_ids = [i for k, i in refs if k == PLATFORM]
    discovered_ids = [i for k, i in refs if k == DISCOVERED]
    saved_platform: set[int] = set()
    regs: dict[int, Registration] = {}
    activities: dict[tuple[str, int], AttendeeEventActivity] = {}
    if platform_ids:
        saved_platform = set(
            db.scalars(select(SavedEvent.event_id).where(SavedEvent.user_id == user_id, SavedEvent.event_id.in_(platform_ids))).all()
        )
        regs = {
            r.event_id: r
            for r in db.scalars(select(Registration).where(Registration.user_id == user_id, Registration.event_id.in_(platform_ids))).all()
        }
        for row in db.scalars(
            select(AttendeeEventActivity).where(AttendeeEventActivity.user_id == user_id, AttendeeEventActivity.event_id.in_(platform_ids))
        ).all():
            activities[(PLATFORM, row.event_id)] = row
    if discovered_ids:
        for row in db.scalars(
            select(AttendeeEventActivity).where(
                AttendeeEventActivity.user_id == user_id, AttendeeEventActivity.discovered_event_id.in_(discovered_ids)
            )
        ).all():
            activities[(DISCOVERED, row.discovered_event_id)] = row

    out: dict[tuple[str, int], dict[str, Any]] = {}
    for kind, event_id in refs:
        act = activities.get((kind, event_id))
        state: dict[str, Any] = {
            "saved": False,
            "registrationStatus": "NOT_REGISTERED",
            "registrationSource": None,
            "registrationConfirmedAt": None,
            "registrationPageOpenedAt": act.registration_opened_at.isoformat() if act and act.registration_opened_at else None,
            "lastViewedAt": act.last_viewed_at.isoformat() if act and act.last_viewed_at else None,
            "ticketCode": None,
        }
        if kind == PLATFORM:
            state["saved"] = event_id in saved_platform
            reg = regs.get(event_id)
            if reg:
                state["registrationStatus"] = _PLATFORM_STATUS.get((reg.status or "").lower(), (reg.status or "").upper())
                state["registrationSource"] = "platform"
                state["registrationConfirmedAt"] = reg.registered_at.isoformat() if reg.registered_at else None
                state["ticketCode"] = reg.registration_code
        elif act:
            state["saved"] = bool(act.is_saved)
            if act.external_registration_status in ("REGISTERED", "NOT_ATTENDING"):
                state["registrationStatus"] = act.external_registration_status
                state["registrationSource"] = "self_reported"
                state["registrationConfirmedAt"] = (
                    act.external_registration_confirmed_at.isoformat() if act.external_registration_confirmed_at else None
                )
        if state["registrationStatus"] == "NOT_REGISTERED" and state["registrationPageOpenedAt"]:
            state["registrationStatus"] = "REGISTRATION_PAGE_OPENED"
        out[(kind, event_id)] = state
    return out


def tracked_refs(db: Session, user_id: int) -> dict[str, list[tuple[str, int, datetime | None]]]:
    """Everything this attendee saved, registered for, or viewed."""
    saved: list[tuple[str, int, datetime | None]] = [
        (PLATFORM, s.event_id, s.created_at)
        for s in db.scalars(select(SavedEvent).where(SavedEvent.user_id == user_id)).all()
    ]
    registered: list[tuple[str, int, datetime | None]] = [
        (PLATFORM, r.event_id, r.registered_at)
        for r in db.scalars(select(Registration).where(Registration.user_id == user_id)).all()
        if (r.status or "").lower() in ("confirmed", "registered", "attended", "waitlisted")
    ]
    viewed: list[tuple[str, int, datetime | None]] = []
    for act in db.scalars(select(AttendeeEventActivity).where(AttendeeEventActivity.user_id == user_id)).all():
        kind, event_id = (PLATFORM, act.event_id) if act.event_id else (DISCOVERED, act.discovered_event_id)
        if kind == DISCOVERED and act.is_saved:
            saved.append((kind, event_id, act.saved_at))
        if kind == DISCOVERED and act.external_registration_status == "REGISTERED":
            registered.append((kind, event_id, act.external_registration_confirmed_at))
        if act.last_viewed_at:
            viewed.append((kind, event_id, act.last_viewed_at))
    return {"saved": saved, "registered": registered, "viewed": viewed}
