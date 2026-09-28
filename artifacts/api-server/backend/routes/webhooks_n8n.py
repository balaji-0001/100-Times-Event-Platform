"""n8n Webhook Integration & Idempotent Workflow Endpoints (Sections 6, 16, 17, 22).

Provides secured, idempotent webhook endpoints for all 8 mandatory n8n workflows:
- POST /api/webhooks/n8n/registration
- POST /api/webhooks/n8n/event-published
- POST /api/webhooks/n8n/event-cancelled
- POST /api/webhooks/n8n/event-rescheduled
- POST /api/webhooks/n8n/event-completed
- POST /api/webhooks/n8n/attendee-followup
- POST /api/webhooks/n8n/organizer-followup
- POST /api/webhooks/n8n/attendance
- POST /api/webhooks/n8n/reminders-dispatch
"""

from datetime import date, datetime, timezone
import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db import get_db
from backend.models import Event, Organizer, Registration, User
from backend.services.notifications import send_templated_notification
from backend.services.registration_automation import (
    automate_registration,
    cancel_event_workflow,
    dispatch_due_reminders,
    execute_idempotent_automation,
    initiate_or_advance_organizer_followup,
    mark_attendance_and_noshows,
    reschedule_event_workflow,
)

router = APIRouter(prefix="/webhooks/n8n", tags=["n8n-webhooks"])

WORKFLOW_CATALOG = [
    {
        "id": "01-event-registration",
        "file": "01-event-registration.json",
        "name": "WORKFLOW 1 — Event Registration",
        "webhook": "/api/webhooks/n8n/registration",
        "trigger": "New attendee registration",
        "description": "Validates event & attendee, creates registration & ticket, sends confirmation email/notification, adds calendar invite, notifies organizer, and schedules timezone-aware reminders.",
    },
    {
        "id": "02-event-confirmation",
        "file": "02-event-confirmation.json",
        "name": "WORKFLOW 2 — Event Confirmation",
        "webhook": "/api/webhooks/n8n/registration",
        "trigger": "Registration confirmed",
        "description": "Dispatches confirmation pass, QR ticket code, calendar invite (.ics & Google Calendar), venue/online join details, and organizer alert.",
    },
    {
        "id": "03-event-reminders",
        "file": "03-event-reminders.json",
        "name": "WORKFLOW 3 — Event Reminders (T-7d, T-24h, T-1h)",
        "webhook": "/api/webhooks/n8n/reminders-dispatch",
        "trigger": "Scheduled cron / timezone-aware timer",
        "description": "Sends 7-day, 24-hour, and 1-hour reminders based on the event's actual IANA timezone. Automatically skips cancelled registrations or cancelled events.",
    },
    {
        "id": "04-event-cancellation",
        "file": "04-event-cancellation.json",
        "name": "WORKFLOW 4 — Event Cancellation",
        "webhook": "/api/webhooks/n8n/event-cancelled",
        "trigger": "Organizer cancels event",
        "description": "Updates event status to CANCELLED, cancels pending reminders, emails all registered attendees, cancels calendar reservations, and starts organizer follow-up.",
    },
    {
        "id": "05-event-reschedule",
        "file": "05-event-reschedule.json",
        "name": "WORKFLOW 5 — Event Reschedule",
        "webhook": "/api/webhooks/n8n/event-rescheduled",
        "trigger": "Event date/time/timezone modified",
        "description": "Detects changed schedule fields, recalculates T-7d/T-24h/T-1h reminders in the event's timezone, and sends updated calendar details to attendees.",
    },
    {
        "id": "06-attendee-post-event",
        "file": "06-attendee-post-event.json",
        "name": "WORKFLOW 6 — Post-Event Attendee Follow-up",
        "webhook": "/api/webhooks/n8n/attendee-followup",
        "trigger": "Event completed",
        "description": "Prompts attendees for attendance confirmation, 1-5 star rating, review feedback, and similar future event opt-in.",
    },
    {
        "id": "07-organizer-followup",
        "file": "07-organizer-followup.json",
        "name": "WORKFLOW 7 — Organizer Follow-up (1d & +2d Cadence)",
        "webhook": "/api/webhooks/n8n/organizer-followup",
        "trigger": "Post-event or cancellation follow-up sequence",
        "description": "Collects attendance numbers, event outcome, and repeat event date. Follows up after 1 day and +2 days if unanswered, stopping after max attempts.",
    },
    {
        "id": "08-attendance",
        "file": "08-attendance.json",
        "name": "WORKFLOW 8 — Event No-Show / Attendance Tracking",
        "webhook": "/api/webhooks/n8n/attendance",
        "trigger": "Check-in & post-event reconciliation",
        "description": "Marks ATTENDED vs NO_SHOW registrations and sends tailored follow-up notifications asking no-shows if they want future event alerts.",
    },
]


def verify_webhook_secret(
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    x_n8n_signature: str | None = Header(default=None, alias="X-N8N-Signature"),
) -> None:
    expected = get_settings().n8n_webhook_secret
    provided = x_webhook_secret or x_n8n_signature
    if not provided or not hmac.compare_digest(str(provided), str(expected)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Webhook-Secret / X-N8N-Signature header",
        )


class WebhookPayload(BaseModel):
    idempotency_key: str = Field(min_length=3, max_length=160, alias="idempotencyKey")
    event_id: int | None = Field(default=None, alias="eventId")
    registration_id: int | None = Field(default=None, alias="registrationId")
    user_id: int | None = Field(default=None, alias="userId")
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/workflows")
def get_n8n_workflows() -> list[dict[str, Any]]:
    return WORKFLOW_CATALOG


@router.post("/registration")
def webhook_registration(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    event = db.get(Event, payload.event_id) if payload.event_id else db.scalar(select(Event).limit(1))
    user = db.get(User, payload.user_id) if payload.user_id else db.scalar(select(User).limit(1))
    if not event or not user:
        raise HTTPException(status_code=404, detail="Event or User not found")

    def _run():
        res = automate_registration(
            db,
            event=event,
            user=user,
            ticket_type=payload.data.get("ticketType", "Standard"),
        )
        return {"ticketCode": res["ticketCode"], "remindersScheduled": res["remindersScheduled"]}

    run, is_dup = execute_idempotent_automation(
        db,
        workflow_id="01-event-registration",
        workflow_name="WORKFLOW 1 — Event Registration",
        idempotency_key=payload.idempotency_key,
        trigger_event="webhook.registration",
        entity_type="Event",
        entity_id=event.id,
        payload=payload.model_dump(by_alias=True),
        handler=_run,
    )
    db.commit()
    return {"status": run.status, "idempotentDuplicate": is_dup, "result": run.result}


@router.post("/event-published")
def webhook_event_published(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    event = db.get(Event, payload.event_id) if payload.event_id else db.scalar(select(Event).limit(1))
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    def _run():
        org = event.organizer
        send_templated_notification(
            db,
            template_key="event_published",
            user_id=org.user_id if org else None,
            recipient_email=org.email if org else None,
            context={"name": org.name if org else "Organizer", "event_title": event.title, "event_url": f"/events/{event.slug}"},
        )
        return {"eventId": event.id, "slug": event.slug, "status": "published_notified"}

    run, is_dup = execute_idempotent_automation(
        db,
        workflow_id="02-event-confirmation",
        workflow_name="Event Published Webhook",
        idempotency_key=payload.idempotency_key,
        trigger_event="webhook.event_published",
        entity_type="Event",
        entity_id=event.id,
        payload=payload.model_dump(by_alias=True),
        handler=_run,
    )
    db.commit()
    return {"status": run.status, "idempotentDuplicate": is_dup, "result": run.result}


@router.post("/event-cancelled")
def webhook_event_cancelled(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    event = db.get(Event, payload.event_id) if payload.event_id else db.scalar(select(Event).limit(1))
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    def _run():
        return cancel_event_workflow(db, event, reason=payload.data.get("reason", "Cancelled via n8n workflow"))

    run, is_dup = execute_idempotent_automation(
        db,
        workflow_id="04-event-cancellation",
        workflow_name="WORKFLOW 4 — Event Cancellation",
        idempotency_key=payload.idempotency_key,
        trigger_event="webhook.event_cancelled",
        entity_type="Event",
        entity_id=event.id,
        payload=payload.model_dump(by_alias=True),
        handler=_run,
    )
    db.commit()
    return {"status": run.status, "idempotentDuplicate": is_dup, "result": run.result}


@router.post("/event-rescheduled")
def webhook_event_rescheduled(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    event = db.get(Event, payload.event_id) if payload.event_id else db.scalar(select(Event).limit(1))
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    new_date_str = payload.data.get("newStartDate")
    new_date = date.fromisoformat(new_date_str) if new_date_str else event.start_date

    def _run():
        return reschedule_event_workflow(
            db,
            event,
            new_start_date=new_date,
            new_start_time=payload.data.get("newStartTime", event.start_time),
            new_timezone=payload.data.get("newTimezone", event.timezone),
        )

    run, is_dup = execute_idempotent_automation(
        db,
        workflow_id="05-event-reschedule",
        workflow_name="WORKFLOW 5 — Event Reschedule",
        idempotency_key=payload.idempotency_key,
        trigger_event="webhook.event_rescheduled",
        entity_type="Event",
        entity_id=event.id,
        payload=payload.model_dump(by_alias=True),
        handler=_run,
    )
    db.commit()
    return {"status": run.status, "idempotentDuplicate": is_dup, "result": run.result}


@router.post("/event-completed")
@router.post("/attendee-followup")
def webhook_attendee_followup(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    event = db.get(Event, payload.event_id) if payload.event_id else db.scalar(select(Event).limit(1))
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    def _run():
        regs = db.scalars(select(Registration).where(Registration.event_id == event.id, Registration.status != "cancelled")).all()
        for r in regs:
            u = db.get(User, r.user_id)
            send_templated_notification(
                db,
                template_key="post_event_attendee_feedback",
                user_id=r.user_id,
                recipient_email=r.attendee_email or (u.email if u else None),
                context={"attendee_name": r.attendee_name or (u.name if u else "Attendee"), "event_title": event.title},
            )
        return {"eventId": event.id, "attendeesPrompted": len(regs)}

    run, is_dup = execute_idempotent_automation(
        db,
        workflow_id="06-attendee-post-event",
        workflow_name="WORKFLOW 6 — Post-Event Attendee Follow-up",
        idempotency_key=payload.idempotency_key,
        trigger_event="webhook.attendee_followup",
        entity_type="Event",
        entity_id=event.id,
        payload=payload.model_dump(by_alias=True),
        handler=_run,
    )
    db.commit()
    return {"status": run.status, "idempotentDuplicate": is_dup, "result": run.result}


@router.post("/organizer-followup")
def webhook_organizer_followup(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    event = db.get(Event, payload.event_id) if payload.event_id else db.scalar(select(Event).limit(1))
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    def _run():
        followup = initiate_or_advance_organizer_followup(db, event=event, reason="POST_EVENT")
        return {
            "followupId": followup.id,
            "status": followup.status,
            "attemptCount": followup.attempt_count,
            "nextFollowupAt": followup.next_followup_at.isoformat() if followup.next_followup_at else None,
        }

    run, is_dup = execute_idempotent_automation(
        db,
        workflow_id="07-organizer-followup",
        workflow_name="WORKFLOW 7 — Organizer Follow-up",
        idempotency_key=payload.idempotency_key,
        trigger_event="webhook.organizer_followup",
        entity_type="Event",
        entity_id=event.id,
        payload=payload.model_dump(by_alias=True),
        handler=_run,
    )
    db.commit()
    return {"status": run.status, "idempotentDuplicate": is_dup, "result": run.result}


@router.post("/attendance")
def webhook_attendance(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    event = db.get(Event, payload.event_id) if payload.event_id else db.scalar(select(Event).limit(1))
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    attended_ids = payload.data.get("attendedRegistrationIds", [])

    def _run():
        return mark_attendance_and_noshows(db, event, attended_registration_ids=attended_ids)

    run, is_dup = execute_idempotent_automation(
        db,
        workflow_id="08-attendance",
        workflow_name="WORKFLOW 8 — Attendance & No-Show",
        idempotency_key=payload.idempotency_key,
        trigger_event="webhook.attendance",
        entity_type="Event",
        entity_id=event.id,
        payload=payload.model_dump(by_alias=True),
        handler=_run,
    )
    db.commit()
    return {"status": run.status, "idempotentDuplicate": is_dup, "result": run.result}


@router.post("/reminders-dispatch")
def webhook_reminders_dispatch(
    payload: WebhookPayload,
    _: None = Depends(verify_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    def _run():
        return dispatch_due_reminders(db)

    run, is_dup = execute_idempotent_automation(
        db,
        workflow_id="03-event-reminders",
        workflow_name="WORKFLOW 3 — Event Reminders Dispatch",
        idempotency_key=payload.idempotency_key,
        trigger_event="webhook.reminders_dispatch",
        entity_type="EventReminder",
        entity_id=payload.event_id,
        payload=payload.model_dump(by_alias=True),
        handler=_run,
    )
    db.commit()
    return {"status": run.status, "idempotentDuplicate": is_dup, "result": run.result}
