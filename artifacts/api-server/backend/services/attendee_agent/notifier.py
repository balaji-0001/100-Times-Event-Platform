"""Attendee notification sweep — reminders, registration deadlines, event
changes and newly discovered matching events.

Consent first: only attendees whose `AttendeePreference.notify_consent` is
true are considered at all, and each of the four kinds has its own opt-out.
Every notice is idempotent through `AttendeeNotificationLog` (one row per
user + dedupe key), so re-running the sweep never repeats a notice.

What each kind is built from (all real data):
- reminders: externally-registered discovered events the attendee confirmed
  themselves (T-7 days and T-1 day). Platform registrations keep using the
  existing `EventReminder` pipeline (`registration_automation.
  dispatch_due_reminders`), which this sweep also runs and which now
  respects the same opt-out.
- deadlines: saved, not-yet-registered events whose source published a
  registration deadline (`offers.validThrough`) falling within 3 days.
- changes: date/time/location/format/status differences against the
  snapshot taken when the attendee saved or registered. Platform events the
  attendee is registered for are excluded because the organizer cancel/
  reschedule workflows already notify registrants.
- new matches: events first seen after the attendee's last check that
  score >= NEW_MATCH_THRESHOLD with the shared matching algorithm. The very
  first sweep only sets the watermark, so nobody gets the whole back
  catalog as "new".

Email goes out only when the attendee opted in AND real SMTP is configured;
otherwise the in-app notification is created and the email status is
recorded as `not_configured` — never a pretend send through the mock
provider.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AttendeeNotificationLog, AttendeePreference, Notification, User
from backend.services.attendee_agent import catalog as catalog_module
from backend.services.attendee_agent import tracking
from backend.services.attendee_agent.catalog import DISCOVERED, PLATFORM, CatalogEvent
from backend.services.attendee_agent.matching import Preferences, rank
from backend.services.audit import record_audit_log

logger = logging.getLogger("attendee_agent.notifier")

NEW_MATCH_THRESHOLD = 60
DEADLINE_WINDOW_DAYS = 3
_FIELD_LABELS = {
    "startDate": "start date",
    "endDate": "end date",
    "startTime": "start time",
    "city": "city",
    "country": "country",
    "venue": "venue",
    "mode": "attendance mode",
    "status": "status",
}


def _email_status(user: User, prefs: AttendeePreference, subject: str, body: str) -> str:
    if not prefs.notify_by_email:
        return "not_requested"
    from backend.services.social_agent.outreach.senders import get_email_provider, provider_status

    if provider_status()["status"] != "REAL":
        return "not_configured"
    try:
        result = get_email_provider().send(recipient=user.email, subject=subject, body=body)
        return "sent" if result.ok else "failed"
    except Exception:
        logger.exception("Attendee notification email failed for user %s", user.id)
        return "failed"


def _already_sent(db: Session, user_id: int, key: str) -> bool:
    return db.scalar(
        select(AttendeeNotificationLog.id).where(AttendeeNotificationLog.user_id == user_id, AttendeeNotificationLog.dedupe_key == key)
    ) is not None


def _send(
    db: Session,
    user: User,
    prefs: AttendeePreference,
    *,
    key: str,
    kind: str,
    title: str,
    message: str,
    metadata: dict[str, Any],
) -> bool:
    if _already_sent(db, user.id, key):
        return False
    email_status = _email_status(user, prefs, title, message)
    note = Notification(
        user_id=user.id,
        title=title,
        message=message,
        channel="in_app+email" if email_status == "sent" else "in_app",
        template_key=f"attendee_{kind}",
        status="sent",
        metadata_json={**metadata, "kind": kind, "email_status": email_status},
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(note)
    db.flush()
    db.add(AttendeeNotificationLog(user_id=user.id, dedupe_key=key, kind=kind, notification_id=note.id, email_status=email_status))
    db.flush()
    return True


def _where(item: CatalogEvent) -> str:
    if item.attendance_mode == "online" and not item.city:
        return "online"
    return ", ".join(p for p in (item.venue, item.city, item.country) if p) or "location not published"


def _diff_text(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    changes = []
    for field, label in _FIELD_LABELS.items():
        if (old or {}).get(field) != new.get(field):
            changes.append(f"{label}: {old.get(field) or 'not set'} → {new.get(field) or 'not set'}")
    return changes


def _sweep_user(db: Session, user: User, prefs: AttendeePreference, catalog: list[CatalogEvent], today: date, now: datetime) -> dict[str, int]:
    counts = {"reminder": 0, "deadline": 0, "change": 0, "new_matches": 0}
    tracked = tracking.tracked_refs(db, user.id)
    registered = {(k, i) for k, i, _ in tracked["registered"]}
    saved = {(k, i) for k, i, _ in tracked["saved"]}
    watched = registered | saved
    items = catalog_module.get_events(db, sorted(watched), today)

    for ref in sorted(watched):
        item = items.get(ref)
        if item is None:
            continue
        kind, event_id = ref
        days_to_start = (item.start_date - today).days

        if prefs.notify_event_reminders and kind == DISCOVERED and ref in registered and item.eligible and 0 <= days_to_start <= 7:
            window = "1d" if days_to_start <= 1 else "7d"
            when = "today" if days_to_start == 0 else ("tomorrow" if days_to_start == 1 else f"in {days_to_start} days")
            if _send(
                db, user, prefs,
                key=f"reminder:d:{event_id}:{window}", kind="reminder",
                title=f"Reminder: {item.title} is {when}",
                message=f"{item.title} starts {item.start_date.isoformat()}{' at ' + item.start_time if item.start_time else ''} — {_where(item)}. Event page: {item.official_url}",
                metadata={"ref": item.ref, "startDate": item.start_date.isoformat()},
            ):
                counts["reminder"] += 1

        deadline = item.registration_deadline
        if prefs.notify_deadlines and ref in saved and ref not in registered and item.eligible and deadline:
            days_left = (deadline - today).days
            if 0 <= days_left <= DEADLINE_WINDOW_DAYS:
                if _send(
                    db, user, prefs,
                    key=f"deadline:{kind}:{event_id}:{deadline.isoformat()}", kind="deadline",
                    title=f"Registration closes {'today' if days_left == 0 else deadline.isoformat()}: {item.title}",
                    message=f"The organizer lists {deadline.isoformat()} as the last day to register for {item.title}. Register: {item.registration_url or (f'/events/{item.internal_slug}' if item.internal_slug else 'see the event page')}",
                    metadata={"ref": item.ref, "deadline": deadline.isoformat()},
                ):
                    counts["deadline"] += 1

        activity = tracking.get_activity(db, user.id, kind, event_id, create=True)
        current = catalog_module.fingerprint(item)
        if activity.change_fingerprint is None:
            activity.change_fingerprint = current
        elif activity.change_fingerprint != current:
            changes = _diff_text(activity.change_fingerprint, current)
            platform_registrant = kind == PLATFORM and ref in registered
            if prefs.notify_event_changes and changes and not platform_registrant:
                if _send(
                    db, user, prefs,
                    key=f"change:{kind}:{event_id}:{catalog_module.fingerprint_hash(current)}", kind="change",
                    title=f"Update to {item.title}",
                    message="What changed — " + "; ".join(changes),
                    metadata={"ref": item.ref, "changes": changes},
                ):
                    counts["change"] += 1
            activity.change_fingerprint = current
    db.flush()

    if prefs.notify_new_matches:
        watermark = prefs.last_new_match_check_at
        if watermark is not None:
            watermark = watermark if watermark.tzinfo else watermark.replace(tzinfo=timezone.utc)
            fresh = [e for e in catalog if e.first_seen_at and e.first_seen_at > watermark and (e.kind, e.id) not in watched]
            top = rank(fresh, Preferences.from_model(prefs), min_percent=NEW_MATCH_THRESHOLD)[:5]
            if top:
                lines = [f"• {e.title} ({e.start_date.isoformat()}, {_where(e)}) — {m.percent}% match" for e, m in top]
                if _send(
                    db, user, prefs,
                    key=f"new_matches:{watermark.isoformat()}", kind="new_matches",
                    title=f"{len(top)} new event{'s' if len(top) != 1 else ''} match your preferences",
                    message="\n".join(lines),
                    metadata={"refs": [e.ref for e, _ in top], "percents": [m.percent for _, m in top]},
                ):
                    counts["new_matches"] += 1
        prefs.last_new_match_check_at = now
    return counts


def run_attendee_notifications(db: Session, now: datetime | None = None, today: date | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    today = today or now.date()
    summary: dict[str, Any] = {"usersConsidered": 0, "reminder": 0, "deadline": 0, "change": 0, "new_matches": 0, "errors": []}

    consenting = db.scalars(select(AttendeePreference).where(AttendeePreference.notify_consent.is_(True))).all()
    catalog = catalog_module.load_catalog(db, today) if consenting else []
    for prefs in consenting:
        user = db.get(User, prefs.user_id)
        if user is None:
            continue
        summary["usersConsidered"] += 1
        try:
            with db.begin_nested():
                counts = _sweep_user(db, user, prefs, catalog, today, now)
            for k, v in counts.items():
                summary[k] += v
        except Exception as exc:  # one bad user never stops the sweep
            logger.exception("Attendee notification sweep failed for user %s", user.id)
            summary["errors"].append(f"user {user.id}: {exc}")

    from backend.services.registration_automation import dispatch_due_reminders

    summary["platformReminders"] = dispatch_due_reminders(db, now)
    record_audit_log(
        db,
        actor="attendee_agent",
        action="ATTENDEE_NOTIFICATION_SWEEP",
        entity="AttendeePreference",
        result="FAILED" if summary["errors"] else "SUCCESS",
        metadata={k: v for k, v in summary.items() if k != "errors"} | {"errorCount": len(summary["errors"])},
    )
    db.flush()
    return summary
