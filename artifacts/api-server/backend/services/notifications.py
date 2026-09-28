"""Centralized Notification & Calendar Service (Section 11).

Supports:
- In-app notifications (`Notification` model)
- Email notifications (via `get_email_provider()` — real SMTP when configured, safe MockEmailProvider fallback)
- Calendar generation (`.ics` iCalendar RFC 5545 + Google Calendar & Outlook deep links)
- Webhook / future WhatsApp & SMS channel abstractions
- All 16 mandatory notification templates
"""

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from backend.models import Event, Notification, User
from backend.services.audit import record_audit_log
from backend.services.social_agent.outreach.senders import get_email_provider

TEMPLATES: dict[str, dict[str, str]] = {
    "welcome": {
        "title": "Welcome to 100 TIMES, {name}!",
        "subject": "Welcome to 100 TIMES — Your Event & Community Hub",
        "body": (
            "Hi {name},\n\nWelcome to 100 TIMES! Your account ({email}) is active and ready. "
            "You can now discover curated gatherings, connect with peers, or launch your own events in the Organizer Studio.\n\n"
            "Explore events: {platform_url}/events\nOrganizer Studio: {platform_url}/organizer"
        ),
    },
    "account_verification": {
        "title": "Account verified for {email}",
        "subject": "Your 100 TIMES Organizer Account is Verified",
        "body": (
            "Hi {name},\n\nYour email ({email}) and organizer profile for {organization} have been verified. "
            "You can now submit events for automated Trust Agent verification and instant publishing."
        ),
    },
    "event_submitted": {
        "title": "Event submitted: {event_title}",
        "subject": "We received your event submission: {event_title}",
        "body": (
            "Hi {name},\n\nYour event '{event_title}' has been submitted to the 100 TIMES Trust Agent for verification. "
            "Status: {trust_status}."
        ),
    },
    "event_approved": {
        "title": "Event approved: {event_title}",
        "subject": "Approved! '{event_title}' passed Trust Verification",
        "body": (
            "Hi {name},\n\nGreat news! '{event_title}' has been approved with a Trust Score of {trust_score}/100 "
            "({trust_confidence} confidence) and is ready for attendees."
        ),
    },
    "event_rejected": {
        "title": "Event requires changes: {event_title}",
        "subject": "Update regarding your event submission: {event_title}",
        "body": (
            "Hi {name},\n\nYour event '{event_title}' could not be published in its current state.\n"
            "Reasons: {reasons}\n\nYou can edit your draft anytime in the Organizer Studio without re-entering your information."
        ),
    },
    "event_needs_review": {
        "title": "Your event is under review: {event_title}",
        "subject": "Your event '{event_title}' is under human review",
        "body": (
            "Hi {name},\n\nYour event '{event_title}' has been queued for our moderation team to review "
            "(Confidence: {trust_confidence}). Your draft is safely stored—you do not need to submit anything again."
        ),
    },
    "event_published": {
        "title": "Event published live: {event_title}",
        "subject": "Live on 100 TIMES: {event_title}",
        "body": (
            "Hi {name},\n\nYour event '{event_title}' is now published and accepting registrations!\n"
            "Public Event Page: {event_url}"
        ),
    },
    "registration_confirmation": {
        "title": "Registration confirmed: {event_title}",
        "subject": "Your Ticket & Confirmation for {event_title} ({ticket_code})",
        "body": (
            "Hi {attendee_name},\n\nYour registration for '{event_title}' is confirmed!\n"
            "Registration ID / Ticket Code: {ticket_code}\n"
            "Tier: {ticket_type}\n"
            "Date & Time: {event_date} at {event_time} ({event_timezone})\n"
            "Venue / Location: {event_venue}\n\n"
            "View your digital pass: {platform_url}/dashboard/registrations"
        ),
    },
    "event_reminder_7d": {
        "title": "1 Week Away: {event_title}",
        "subject": "Reminder: {event_title} is in 7 days",
        "body": (
            "Hi {attendee_name},\n\n'{event_title}' is coming up in 7 days on {event_date} at {event_time} ({event_timezone}).\n"
            "Location: {event_venue}\nTicket Code: {ticket_code}\nCalendar Link: {calendar_url}"
        ),
    },
    "event_reminder_24h": {
        "title": "Tomorrow: {event_title}",
        "subject": "Tomorrow! Venue & Instructions for {event_title}",
        "body": (
            "Hi {attendee_name},\n\n'{event_title}' is happening tomorrow ({event_date} at {event_time} {event_timezone})!\n"
            "Venue / Join Link: {event_venue}\nTicket Code: {ticket_code}"
        ),
    },
    "event_reminder_1h": {
        "title": "Starting in 1 Hour: {event_title}",
        "subject": "Starting in 1 Hour: {event_title} — Doors / Join Link Ready",
        "body": (
            "Hi {attendee_name},\n\n'{event_title}' starts in 1 hour ({event_time} {event_timezone})!\n"
            "Venue / Join URL: {event_venue}\nHave your pass ready: {ticket_code}"
        ),
    },
    "event_cancelled": {
        "title": "Cancelled: {event_title}",
        "subject": "Important Update: {event_title} has been cancelled",
        "body": (
            "Hi {attendee_name},\n\nWe regret to inform you that the organizer has cancelled '{event_title}' "
            "scheduled for {event_date}.\nReason: {cancellation_reason}\nYour calendar reservation has been cancelled."
        ),
    },
    "event_rescheduled": {
        "title": "Rescheduled: {event_title}",
        "subject": "Updated Schedule for {event_title}",
        "body": (
            "Hi {attendee_name},\n\n'{event_title}' has been rescheduled.\n"
            "New Date & Time: {event_date} at {event_time} ({event_timezone})\n"
            "Venue: {event_venue}\nYour existing registration ({ticket_code}) remains valid."
        ),
    },
    "post_event_attendee_feedback": {
        "title": "How was {event_title}?",
        "subject": "Share your feedback on {event_title}",
        "body": (
            "Hi {attendee_name},\n\nThank you for being part of '{event_title}'! Did you attend the session? "
            "We'd love your rating (1-5 stars), quick feedback, and whether you'd like recommendations for similar upcoming events."
        ),
    },
    "organizer_followup": {
        "title": "How did {event_title} go?",
        "subject": "Post-Event Check-in: {event_title} Outcome & Next Gathering",
        "body": (
            "Hi {name},\n\nCongratulations on wrapping up '{event_title}'! "
            "Please share your final attendance numbers, event outcome, and whether you're planning your next event date on 100 TIMES."
        ),
    },
    "organizer_followup_reminder": {
        "title": "Follow-up (#{attempt}): {event_title} outcome",
        "subject": "Quick follow-up (#{attempt}): How did {event_title} go?",
        "body": (
            "Hi {name},\n\nJust following up (#{attempt}) on '{event_title}'. "
            "Let us know your attendance count and if we can help launch your next event on 100 TIMES!"
        ),
    },
}


def generate_calendar_links(event: Event) -> dict[str, str]:
    """Generate RFC 5545 .ics content plus Google Calendar and Outlook URLs."""
    start_dt_str = event.start_date.strftime("%Y%m%d") if event.start_date else "20261015"
    end_dt_str = event.end_date.strftime("%Y%m%d") if event.end_date else start_dt_str
    venue_label = (
        event.online_meeting_url
        if event.format == "online" and event.online_meeting_url
        else (event.full_address or (event.venue.name if event.venue else event.city_name or "India"))
    )
    title_enc = quote(event.title or "100 TIMES Event")
    details_enc = quote((event.description or "")[:400])
    loc_enc = quote(venue_label or "")
    tz = event.timezone or "Asia/Kolkata"

    google_url = (
        f"https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={title_enc}&dates={start_dt_str}T090000/{end_dt_str}T180000"
        f"&details={details_enc}&location={loc_enc}&ctz={quote(tz)}"
    )
    outlook_url = (
        f"https://outlook.live.com/calendar/0/deeplink/compose?path=/calendar/action/compose"
        f"&rru=addevent&subject={title_enc}&body={details_enc}&location={loc_enc}"
    )
    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//100 TIMES Event Platform//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:100times-event-{event.id}@100times.in\r\n"
        f"SUMMARY:{event.title}\r\n"
        f"DTSTART;TZID={tz}:{start_dt_str}T090000\r\n"
        f"DTEND;TZID={tz}:{end_dt_str}T180000\r\n"
        f"LOCATION:{venue_label}\r\n"
        f"DESCRIPTION:{(event.description or '')[:300]}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR"
    )
    return {
        "googleCalendarUrl": google_url,
        "outlookCalendarUrl": outlook_url,
        "icsContent": ics_content,
    }


def send_templated_notification(
    db: Session,
    *,
    template_key: str,
    user_id: int | None = None,
    recipient_email: str | None = None,
    context: dict[str, Any] | None = None,
    send_email: bool = True,
) -> Notification | None:
    """Render and dispatch a notification across in-app and email channels."""
    tpl = TEMPLATES.get(template_key)
    if not tpl:
        raise ValueError(f"Unknown notification template: {template_key}")

    ctx = {
        "name": "Organizer",
        "attendee_name": "Attendee",
        "email": recipient_email or "",
        "organization": "100 TIMES Community",
        "event_title": "Event",
        "event_date": "",
        "event_time": "09:00",
        "event_timezone": "Asia/Kolkata",
        "event_venue": "Online / Venue",
        "event_url": "https://100times.in/events",
        "platform_url": "http://localhost:5174",
        "ticket_code": "100T-PASS",
        "ticket_type": "Standard",
        "trust_status": "APPROVED",
        "trust_score": 90,
        "trust_confidence": "HIGH",
        "reasons": "None",
        "cancellation_reason": "Schedule change by organizer",
        "calendar_url": "https://calendar.google.com",
        "attempt": 1,
        **(context or {}),
    }

    title = tpl["title"].format_map(ctx)
    subject = tpl["subject"].format_map(ctx)
    body = tpl["body"].format_map(ctx)

    email_status = "skipped"
    if send_email and recipient_email:
        try:
            provider = get_email_provider()
            send_res = provider.send(recipient=recipient_email, subject=subject, body=body)
            email_status = "sent" if send_res.ok else "failed"
        except Exception:
            email_status = "failed"

    notif: Notification | None = None
    if user_id:
        notif = Notification(
            user_id=user_id,
            title=title,
            message=body,
            channel="multi" if send_email else "in_app",
            template_key=template_key,
            status="sent",
            metadata_json={"email_status": email_status, "recipient_email": recipient_email},
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(notif)
        db.flush()

    record_audit_log(
        db,
        actor="notification_service",
        actor_id=user_id,
        action=f"NOTIFICATION_{template_key.upper()}",
        entity="Notification",
        entity_id=notif.id if notif else recipient_email,
        result="SUCCESS",
        metadata={"template": template_key, "email_status": email_status},
    )
    return notif
