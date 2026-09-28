"""Registration, Reminder, Cancellation, Reschedule, Attendance & Idempotent Automation Engine.

Implements:
- Section 5: Complete Event Registration Automation & Capacity/Waitlist Handling
- Section 6: Reusable Workflow Handlers (Workflows 1 to 8)
- Section 22: Strict Automation Idempotency (`AutomationRun` + `idempotency_key`)
- Section 23: Timezone-Aware Reminder Scheduling (`zoneinfo.ZoneInfo` for T-7d, T-24h, T-1h)
"""

from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import (
    AttendeeFeedback,
    AutomationRun,
    Event,
    EventMatch,
    EventReminder,
    Organizer,
    OrganizerFollowup,
    OrganizerProfile,
    Registration,
    Ticket,
    User,
)
from backend.services.audit import record_audit_log
from backend.services.lifecycle import advance_organizer_stage, transition_event_state
from backend.services.notifications import generate_calendar_links, send_templated_notification

REGISTRATION_STATES = ("REGISTERED", "CONFIRMED", "WAITLISTED", "CANCELLED", "ATTENDED", "NO_SHOW")


def parse_event_time(time_str: str | None) -> time:
    """Parse '09:30 AM', '18:00', '2:15 PM' etc. into a `datetime.time` object."""
    raw = (time_str or "09:00").strip().upper()
    m = re.match(r"^(\d{1,2}):(\d{2})(?:\s*(AM|PM))?$", raw)
    if not m:
        return time(9, 0)
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm = m.group(3)
    if ampm == "PM" and hour < 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return time(hour, minute)


def calculate_event_start_utc(start_date: date, start_time_str: str | None, event_timezone: str | None) -> datetime:
    """Convert an event's local date + start_time in `event_timezone` to an exact UTC `datetime`.
    Never assumes UTC or Asia/Kolkata when another valid IANA timezone is specified."""
    tz_name = (event_timezone or "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        tz = ZoneInfo("UTC")

    local_t = parse_event_time(start_time_str)
    local_dt = datetime.combine(start_date, local_t, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def compute_reminder_schedule_utc(start_date: date, start_time_str: str | None, event_timezone: str | None) -> dict[str, datetime]:
    """Return exact UTC timestamps for T-7 days, T-24 hours, and T-1 hour based on the event's timezone."""
    start_utc = calculate_event_start_utc(start_date, start_time_str, event_timezone)
    return {
        "7_DAYS": start_utc - timedelta(days=7),
        "24_HOURS": start_utc - timedelta(hours=24),
        "1_HOUR": start_utc - timedelta(hours=1),
    }


def execute_idempotent_automation(
    db: Session,
    *,
    workflow_id: str,
    workflow_name: str,
    idempotency_key: str,
    trigger_event: str,
    entity_type: str,
    entity_id: int | None,
    payload: dict[str, Any],
    handler,
) -> tuple[AutomationRun, bool]:
    """Execute `handler()` at most once per `idempotency_key`.
    Returns `(automation_run, was_duplicate)`."""
    existing = db.scalar(select(AutomationRun).where(AutomationRun.idempotency_key == idempotency_key))
    if existing:
        return existing, True

    run = AutomationRun(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        idempotency_key=idempotency_key,
        trigger_event=trigger_event,
        entity_type=entity_type,
        entity_id=entity_id,
        status="RUNNING",
        payload=payload,
        result={},
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()

    try:
        result_data = handler() or {}
        run.status = "COMPLETED"
        run.result = result_data
        run.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        run.status = "FAILED"
        run.error = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        raise

    db.flush()
    record_audit_log(
        db,
        actor="n8n_automation",
        action=f"WORKFLOW_{workflow_id.upper()}",
        entity=entity_type,
        entity_id=entity_id,
        result=run.status,
        metadata={"idempotency_key": idempotency_key, "workflow_name": workflow_name},
    )
    return run, False


def schedule_event_reminders(
    db: Session,
    *,
    event: Event,
    registration: Registration,
    user: User,
) -> list[EventReminder]:
    """Schedule T-7d, T-24h, and T-1h reminders in UTC from the event's local timezone (idempotent)."""
    schedule_map = compute_reminder_schedule_utc(event.start_date, event.start_time, event.timezone)
    created: list[EventReminder] = []
    for rem_type, utc_dt in schedule_map.items():
        idem_key = f"reminder:{event.id}:reg:{registration.id}:{rem_type}"
        existing = db.scalar(select(EventReminder).where(EventReminder.idempotency_key == idem_key))
        if existing:
            if existing.status == "CANCELLED" and registration.status in ("confirmed", "CONFIRMED", "REGISTERED"):
                existing.status = "SCHEDULED"
                existing.scheduled_for_utc = utc_dt
            created.append(existing)
            continue
        rem = EventReminder(
            event_id=event.id,
            registration_id=registration.id,
            user_id=user.id,
            reminder_type=rem_type,
            event_timezone=event.timezone or "Asia/Kolkata",
            scheduled_for_utc=utc_dt,
            status="SCHEDULED",
            idempotency_key=idem_key,
        )
        db.add(rem)
        created.append(rem)
    db.flush()
    return created


def automate_registration(
    db: Session,
    *,
    event: Event,
    user: User,
    ticket_type: str = "Standard",
    attendee_name: str | None = None,
    attendee_email: str | None = None,
    attendee_phone: str | None = None,
    company: str | None = None,
    job_title: str | None = None,
    country: str | None = None,
    allow_waitlist: bool = False,
    intent_id: int | None = None,
) -> dict[str, Any]:
    """Complete end-to-end registration automation (Workflows 1 & 2)."""
    if (event.lifecycle_state or "").upper() == "CANCELLED" or event.status == "cancelled":
        raise ValueError("Cannot register for a cancelled event.")

    active_count = int(
        db.scalar(
            select(func.count(Registration.id)).where(
                Registration.event_id == event.id,
                Registration.status.in_(["confirmed", "CONFIRMED", "REGISTERED", "ATTENDED"]),
            )
        )
        or 0
    )

    is_full = bool(event.capacity is not None and event.capacity > 0 and active_count >= event.capacity)
    if is_full and not allow_waitlist:
        raise ValueError("Event has reached maximum capacity.")

    reg_status = "waitlisted" if is_full else "confirmed"

    existing = db.scalar(select(Registration).where(Registration.event_id == event.id, Registration.user_id == user.id))
    if existing:
        existing.status = reg_status
        existing.ticket_type = ticket_type
        existing.attendee_name = attendee_name or existing.attendee_name or user.name
        existing.attendee_email = attendee_email or existing.attendee_email or user.email
        if attendee_phone is not None:
            existing.attendee_phone = attendee_phone
        if company is not None:
            existing.company = company
        if job_title is not None:
            existing.job_title = job_title
        if country is not None:
            existing.country = country
        existing.cancelled_at = None
        registration = existing
    else:
        registration = Registration(
            event_id=event.id,
            user_id=user.id,
            ticket_type=ticket_type,
            status=reg_status,
            attendee_name=attendee_name or user.name,
            attendee_email=attendee_email or user.email,
            attendee_phone=attendee_phone,
            company=company or user.company,
            job_title=job_title or user.job_title,
            country=country or user.country,
            payment_status="paid" if float(event.price or 0) > 0 else "not_required",
            calendar_added=True,
        )
        db.add(registration)
        db.flush()

    ticket_code = f"100T-{event.id:04d}-{registration.id:05d}"
    registration.registration_code = ticket_code
    qr_data = f"100TIMES:PASS:EVENT={event.slug}:REG={ticket_code}:USER={registration.attendee_email or user.email}:TIER={registration.ticket_type}"

    # Ensure Ticket row exists (idempotent)
    ticket_row = db.scalar(select(Ticket).where(Ticket.ticket_code == ticket_code))
    if not ticket_row:
        ticket_row = Ticket(
            event_id=event.id,
            registration_id=registration.id,
            ticket_code=ticket_code,
            tier_name=ticket_type,
            price=event.price or 0,
            is_free=float(event.price or 0) == 0,
            status="WAITLISTED" if is_full else "ISSUED",
            qr_payload=qr_data,
        )
        db.add(ticket_row)
        db.flush()
    else:
        ticket_row.tier_name = ticket_type
        ticket_row.qr_payload = qr_data

    # Link conversion if driven by Attendee Agent intent (explicit intent_id or active EventMatch for this event)
    match_row = None
    if intent_id:
        match_row = db.scalar(
            select(EventMatch).where(EventMatch.intent_id == intent_id, EventMatch.event_id == event.id)
        )
    if not match_row:
        match_row = db.scalar(
            select(EventMatch)
            .where(EventMatch.event_id == event.id, EventMatch.converted_registration_id.is_(None))
            .order_by(EventMatch.created_at.desc())
        )
    if match_row:
        match_row.converted_registration_id = registration.id
        match_row.recommendation_status = "CONVERTED"

    calendar_links = generate_calendar_links(event)
    reminders = schedule_event_reminders(db, event=event, registration=registration, user=user) if not is_full else []

    venue_display = (
        event.online_meeting_url
        if event.format == "online" and event.online_meeting_url
        else (event.full_address or (event.venue.name if event.venue else event.city_name or "Online / Venue"))
    )

    # Execute idempotent confirmation notification + organizer notification
    idem_key = f"wf1_reg_confirm:{event.id}:{registration.id}:{registration.status}"

    def _send_confirmations():
        send_templated_notification(
            db,
            template_key="registration_confirmation",
            user_id=user.id,
            recipient_email=user.email,
            context={
                "attendee_name": user.name,
                "event_title": event.title,
                "ticket_code": ticket_code,
                "ticket_type": ticket_type,
                "event_date": event.start_date.isoformat() if event.start_date else "",
                "event_time": event.start_time or "09:00",
                "event_timezone": event.timezone or "Asia/Kolkata",
                "event_venue": venue_display,
            },
        )
        if event.organizer:
            profile = (
                db.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == event.organizer.user_id))
                if event.organizer.user_id
                else None
            )
            advance_organizer_stage(
                db,
                event.organizer,
                profile,
                "REGISTRATIONS",
                actor="registration_automation",
                note=f"Registration {ticket_code} by {user.email}",
            )
        return {"ticket_code": ticket_code, "reminders_scheduled": len(reminders)}

    execute_idempotent_automation(
        db,
        workflow_id="01-event-registration",
        workflow_name="WORKFLOW 1 & 2 — Event Registration & Confirmation",
        idempotency_key=idem_key,
        trigger_event="registration.created",
        entity_type="Registration",
        entity_id=registration.id,
        payload={"event_id": event.id, "user_id": user.id, "ticket_code": ticket_code},
        handler=_send_confirmations,
    )

    return {
        "registration": registration,
        "ticket": ticket_row,
        "ticketCode": ticket_code,
        "qrCode": qr_data,
        "calendar": calendar_links,
        "remindersScheduled": len(reminders),
    }


def cancel_event_workflow(
    db: Session,
    event: Event,
    *,
    reason: str = "Cancelled by organizer",
    actor_id: int | None = None,
) -> dict[str, Any]:
    """WORKFLOW 4 — EVENT CANCELLATION:
    - Update event status to CANCELLED
    - Cancel all scheduled reminders
    - Notify all registered attendees
    - Start organizer follow-up workflow
    """
    transition_event_state(db, event, "CANCELLED", actor="organizer", actor_id=actor_id, reason=reason, force=True)

    # Cancel pending reminders
    reminders = db.scalars(
        select(EventReminder).where(EventReminder.event_id == event.id, EventReminder.status == "SCHEDULED")
    ).all()
    for rem in reminders:
        rem.status = "CANCELLED"

    # Notify registered attendees
    regs = db.scalars(
        select(Registration).where(Registration.event_id == event.id, Registration.status != "cancelled")
    ).all()
    notified_count = 0
    for reg in regs:
        reg.status = "cancelled"
        reg.cancelled_at = datetime.now(timezone.utc)
        attendee_user = db.get(User, reg.user_id)
        send_templated_notification(
            db,
            template_key="event_cancelled",
            user_id=reg.user_id,
            recipient_email=reg.attendee_email or (attendee_user.email if attendee_user else None),
            context={
                "attendee_name": reg.attendee_name or (attendee_user.name if attendee_user else "Attendee"),
                "event_title": event.title,
                "event_date": event.start_date.isoformat() if event.start_date else "",
                "cancellation_reason": reason,
            },
        )
        notified_count += 1

    # Start organizer follow-up workflow
    followup = None
    if event.organizer_id:
        followup = initiate_or_advance_organizer_followup(
            db, event=event, reason="EVENT_CANCELLED"
        )

    db.flush()
    return {
        "eventId": event.id,
        "lifecycleState": event.lifecycle_state,
        "attendeesNotified": notified_count,
        "remindersCancelled": len(reminders),
        "followupId": followup.id if followup else None,
    }


def reschedule_event_workflow(
    db: Session,
    event: Event,
    *,
    new_start_date: date,
    new_end_date: date | None = None,
    new_start_time: str | None = None,
    new_timezone: str | None = None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """WORKFLOW 5 — EVENT RESCHEDULE:
    - Detect changed date/time fields
    - Update event schedule and recalculate timezone-aware reminders
    - Notify all registered attendees and organizer
    """
    event.start_date = new_start_date
    event.end_date = new_end_date or new_start_date
    if new_start_time:
        event.start_time = new_start_time
    if new_timezone:
        event.timezone = new_timezone

    transition_event_state(db, event, "RESCHEDULED", actor="organizer", actor_id=actor_id, reason="Schedule updated", force=True)
    transition_event_state(db, event, "PUBLISHED", actor="organizer", actor_id=actor_id, reason="Republished after reschedule", force=True)

    # Update scheduled reminders to new UTC times
    schedule_map = compute_reminder_schedule_utc(event.start_date, event.start_time, event.timezone)
    reminders = db.scalars(select(EventReminder).where(EventReminder.event_id == event.id)).all()
    for rem in reminders:
        if rem.reminder_type in schedule_map and rem.status != "CANCELLED":
            rem.scheduled_for_utc = schedule_map[rem.reminder_type]
            rem.event_timezone = event.timezone or "Asia/Kolkata"
            rem.status = "SCHEDULED"

    regs = db.scalars(
        select(Registration).where(Registration.event_id == event.id, Registration.status != "cancelled")
    ).all()
    notified_count = 0
    for reg in regs:
        attendee_user = db.get(User, reg.user_id)
        send_templated_notification(
            db,
            template_key="event_rescheduled",
            user_id=reg.user_id,
            recipient_email=reg.attendee_email or (attendee_user.email if attendee_user else None),
            context={
                "attendee_name": reg.attendee_name or (attendee_user.name if attendee_user else "Attendee"),
                "event_title": event.title,
                "event_date": event.start_date.isoformat(),
                "event_time": event.start_time,
                "event_timezone": event.timezone,
                "event_venue": event.full_address or (event.venue.name if event.venue else event.city_name or "Venue"),
                "ticket_code": reg.registration_code or f"100T-{event.id:04d}-{reg.id:05d}",
            },
        )
        notified_count += 1

    db.flush()
    return {
        "eventId": event.id,
        "newStartDate": event.start_date.isoformat(),
        "newStartTime": event.start_time,
        "timezone": event.timezone,
        "attendeesNotified": notified_count,
        "remindersUpdated": len(reminders),
    }


def dispatch_due_reminders(db: Session, now_utc: datetime | None = None) -> dict[str, int]:
    """WORKFLOW 3 — EVENT REMINDERS:
    Dispatch due T-7d, T-24h, and T-1h reminders. Never sends if registration or event is cancelled."""
    now = now_utc or datetime.now(timezone.utc)
    due = db.scalars(
        select(EventReminder).where(
            EventReminder.status == "SCHEDULED",
            EventReminder.scheduled_for_utc <= now,
        )
    ).all()

    sent_count = 0
    skipped_count = 0
    tpl_map = {
        "7_DAYS": "event_reminder_7d",
        "24_HOURS": "event_reminder_24h",
        "1_HOUR": "event_reminder_1h",
    }

    for rem in due:
        reg = db.get(Registration, rem.registration_id)
        ev = db.get(Event, rem.event_id)
        if not reg or not ev or reg.status in ("cancelled", "CANCELLED") or (ev.lifecycle_state or "").upper() == "CANCELLED":
            rem.status = "CANCELLED"
            skipped_count += 1
            continue

        user = db.get(User, rem.user_id)
        tpl_key = tpl_map.get(rem.reminder_type, "event_reminder_24h")
        send_templated_notification(
            db,
            template_key=tpl_key,
            user_id=rem.user_id,
            recipient_email=reg.attendee_email or (user.email if user else None),
            context={
                "attendee_name": reg.attendee_name or (user.name if user else "Attendee"),
                "event_title": ev.title,
                "event_date": ev.start_date.isoformat() if ev.start_date else "",
                "event_time": ev.start_time or "09:00",
                "event_timezone": ev.timezone or "Asia/Kolkata",
                "event_venue": ev.online_meeting_url or ev.full_address or (ev.venue.name if ev.venue else "Venue"),
                "ticket_code": reg.registration_code or f"100T-{ev.id:04d}-{reg.id:05d}",
            },
        )
        rem.status = "SENT"
        rem.sent_at = now
        sent_count += 1

    db.flush()
    return {"sent": sent_count, "skipped": skipped_count}


def initiate_or_advance_organizer_followup(
    db: Session,
    *,
    event: Event,
    reason: str = "POST_EVENT",
) -> OrganizerFollowup:
    """WORKFLOW 7 — ORGANIZER FOLLOW-UP:
    - Initial contact after event ends (or cancellation)
    - If no response: Wait 1 day -> follow-up #1
    - If still no response: Wait another 2 days -> follow-up #2
    - Stop after configured `organizer_followup_max_attempts` (default 3)
    """
    settings = get_settings()
    organizer_id = event.organizer_id or 1
    organizer = db.get(Organizer, organizer_id)
    now = datetime.now(timezone.utc)

    followup = db.scalar(
        select(OrganizerFollowup).where(
            OrganizerFollowup.event_id == event.id,
            OrganizerFollowup.organizer_id == organizer_id,
        )
    )
    if not followup:
        followup = OrganizerFollowup(
            event_id=event.id,
            organizer_id=organizer_id,
            followup_reason=reason,
            status="AWAITING_RESPONSE",
            attempt_count=1,
            max_attempts=settings.organizer_followup_max_attempts,
            last_contacted_at=now,
            next_followup_at=now + timedelta(days=settings.organizer_followup_first_wait_days),
        )
        db.add(followup)
        db.flush()
        send_templated_notification(
            db,
            template_key="organizer_followup",
            user_id=organizer.user_id if organizer else None,
            recipient_email=organizer.email if organizer else None,
            context={
                "name": organizer.name if organizer else "Organizer",
                "event_title": event.title,
            },
        )
        return followup

    if followup.status == "RESPONDED" or followup.attempt_count >= followup.max_attempts:
        if followup.status != "RESPONDED":
            followup.status = "EXHAUSTED"
            followup.next_followup_at = None
        db.flush()
        return followup

    followup.attempt_count += 1
    followup.last_contacted_at = now
    if followup.attempt_count == 2:
        # Wait another 2 days for second follow-up
        followup.next_followup_at = now + timedelta(days=settings.organizer_followup_second_wait_days)
    else:
        followup.next_followup_at = None
        if followup.attempt_count >= followup.max_attempts:
            followup.status = "EXHAUSTED"

    send_templated_notification(
        db,
        template_key="organizer_followup_reminder",
        user_id=organizer.user_id if organizer else None,
        recipient_email=organizer.email if organizer else None,
        context={
            "name": organizer.name if organizer else "Organizer",
            "event_title": event.title,
            "attempt": followup.attempt_count,
        },
    )
    db.flush()
    return followup


def record_organizer_followup_response(
    db: Session,
    followup: OrganizerFollowup,
    *,
    reported_attendance: int | None = None,
    event_outcome: str | None = None,
    organizer_feedback: str | None = None,
    wants_repeat_event: bool = True,
    next_event_date: str | None = None,
) -> OrganizerFollowup:
    followup.status = "RESPONDED"
    followup.responded_at = datetime.now(timezone.utc)
    followup.next_followup_at = None
    followup.reported_attendance = reported_attendance
    followup.event_outcome = event_outcome
    followup.organizer_feedback = organizer_feedback
    followup.wants_repeat_event = wants_repeat_event
    followup.next_event_date = next_event_date

    organizer = db.get(Organizer, followup.organizer_id)
    profile = (
        db.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == organizer.user_id))
        if organizer and organizer.user_id
        else None
    )
    if organizer:
        advance_organizer_stage(
            db,
            organizer,
            profile,
            "REPEAT_ORGANIZER" if wants_repeat_event else "FOLLOW_UP",
            actor="organizer",
            note=f"Outcome recorded; wants_repeat_event={wants_repeat_event}",
        )
    db.flush()
    return followup


def mark_attendance_and_noshows(
    db: Session,
    event: Event,
    *,
    attended_registration_ids: list[int],
) -> dict[str, int]:
    """WORKFLOW 8 — EVENT NO-SHOW / ATTENDANCE:
    Mark attended registrations as `ATTENDED`, remaining confirmed registrations as `NO_SHOW`,
    and send post-event feedback / future event notification follow-ups."""
    regs = db.scalars(
        select(Registration).where(
            Registration.event_id == event.id,
            Registration.status.in_(["confirmed", "CONFIRMED", "REGISTERED", "ATTENDED", "NO_SHOW"]),
        )
    ).all()

    attended_set = set(attended_registration_ids)
    attended_count = 0
    noshow_count = 0
    now = datetime.now(timezone.utc)

    for reg in regs:
        user = db.get(User, reg.user_id)
        if reg.id in attended_set:
            reg.status = "ATTENDED"
            reg.checked_in_at = now
            attended_count += 1
            send_templated_notification(
                db,
                template_key="post_event_attendee_feedback",
                user_id=reg.user_id,
                recipient_email=reg.attendee_email or (user.email if user else None),
                context={
                    "attendee_name": reg.attendee_name or (user.name if user else "Attendee"),
                    "event_title": event.title,
                },
            )
        else:
            reg.status = "NO_SHOW"
            noshow_count += 1
            send_templated_notification(
                db,
                template_key="post_event_attendee_feedback",
                user_id=reg.user_id,
                recipient_email=reg.attendee_email or (user.email if user else None),
                context={
                    "attendee_name": reg.attendee_name or (user.name if user else "Attendee"),
                    "event_title": event.title,
                },
            )

    transition_event_state(db, event, "EVENT_COMPLETED", actor="system", reason="Attendance & no-shows processed", force=True)
    db.flush()
    return {"attended": attended_count, "noShows": noshow_count}
