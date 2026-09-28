"""Organizer Onboarding, Rich Event Creation, Trust Agent (Agent 3), Attendee Agent & Admin Ops Routes."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.dependencies import get_current_user, optional_current_user, require_roles
from backend.models import (
    AttendeeFeedback,
    AttendeeIntent,
    AuditLog,
    AutomationRun,
    Category,
    City,
    DiscoveredOrganizer,
    DuplicateCandidate,
    Event,
    EventLocation,
    EventMatch,
    EventReminder,
    Notification,
    Organization,
    Organizer,
    OrganizerFollowup,
    OrganizerProfile,
    Registration,
    TrustDecision,
    TrustReview,
    User,
    Venue,
)
from backend.routes.events import slugify
from backend.serializers import event_card
from backend.services import event_creation
from backend.services.attendee_agent import (
    extract_attendee_intent,
    get_attendee_agent_dashboard,
    process_attendee_signal,
    run_attendee_discovery_cycle,
    set_source_enabled,
)
from backend.services.audit import record_audit_log
from backend.services.lifecycle import advance_organizer_stage, transition_event_state
from backend.services.notifications import generate_calendar_links, send_templated_notification
from backend.services.registration_automation import (
    cancel_event_workflow,
    dispatch_due_reminders,
    initiate_or_advance_organizer_followup,
    mark_attendance_and_noshows,
    record_organizer_followup_response,
    reschedule_event_workflow,
)
from backend.services.trust_agent import admin_decide_trust_review, evaluate_event_trust

router = APIRouter(tags=["platform-ops"])


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------


class OrganizerOnboardingInput(BaseModel):
    organizer_name: str = Field(min_length=2, max_length=140, alias="organizerName")
    organization_name: str = Field(min_length=2, max_length=160, alias="organizationName")
    contact_email: EmailStr = Field(alias="contactEmail")
    contact_phone: str | None = Field(default=None, alias="contactPhone")
    website: str | None = None
    city: str | None = "Bengaluru"
    state: str | None = "Karnataka"
    country: str | None = "India"
    bio: str | None = None
    social_links: dict[str, str] = Field(default_factory=dict, alias="socialLinks")
    discovered_organizer_id: int | None = Field(default=None, alias="discoveredOrganizerId")


class RichEventInput(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=10000)
    organizer_name: str | None = Field(default=None, alias="organizerName")
    organization_name: str | None = Field(default=None, alias="organizationName")
    category: str = "Technology"
    event_type: str = Field(default="Conference", alias="eventType")
    start_date: date = Field(alias="startDate")
    end_date: date | None = Field(default=None, alias="endDate")
    start_time: str = Field(default="09:30", alias="startTime")
    end_time: str | None = Field(default="17:30", alias="endTime")
    timezone: str = "Asia/Kolkata"
    venue_name: str | None = Field(default=None, alias="venueName")
    full_address: str | None = Field(default=None, alias="fullAddress")
    city: str = "Bengaluru"
    state: str | None = "Karnataka"
    country: str = "India"
    format: Literal["in-person", "online", "hybrid", "offline"] = "in-person"
    online_meeting_url: str | None = Field(default=None, alias="onlineMeetingUrl")
    registration_url: str | None = Field(default=None, alias="registrationUrl")
    is_free: bool = Field(default=True, alias="isFree")
    price: Decimal = Field(default=Decimal("0.00"), ge=0)
    capacity: int | None = Field(default=250, ge=1)
    ticket_info: dict[str, Any] = Field(default_factory=dict, alias="ticketInfo")
    speaker_info: list[dict[str, Any]] = Field(default_factory=list, alias="speakerInfo")
    image: str | None = None
    contact_info: dict[str, Any] = Field(default_factory=dict, alias="contactInfo")
    social_links: dict[str, Any] = Field(default_factory=dict, alias="socialLinks")
    terms_policy: str | None = Field(default=None, alias="termsPolicy")
    tags: list[str] = Field(default_factory=list)
    target_audience: str | None = Field(default=None, alias="targetAudience")
    save_as_draft: bool = Field(default=False, alias="saveAsDraft")


class TrustAdminDecisionInput(BaseModel):
    decision: Literal["APPROVE", "REJECT", "REQUEST_CHANGES"]
    notes: str | None = None


class RescheduleInput(BaseModel):
    start_date: date = Field(alias="startDate")
    end_date: date | None = Field(default=None, alias="endDate")
    start_time: str = Field(default="09:30", alias="startTime")
    timezone: str | None = None


class CancelEventInput(BaseModel):
    reason: str = "Schedule cancelled by organizer"


class AttendanceInput(BaseModel):
    attended_registration_ids: list[int] = Field(default_factory=list, alias="attendedRegistrationIds")


class OrganizerFollowupResponseInput(BaseModel):
    reported_attendance: int | None = Field(default=None, alias="reportedAttendance")
    event_outcome: str | None = Field(default=None, alias="eventOutcome")
    organizer_feedback: str | None = Field(default=None, alias="organizerFeedback")
    wants_repeat_event: bool = Field(default=True, alias="wantsRepeatEvent")
    next_event_date: str | None = Field(default=None, alias="nextEventDate")


class AttendeeFeedbackInput(BaseModel):
    attended: bool = True
    rating: int = Field(default=5, ge=1, le=5)
    feedback: str | None = None
    wants_similar_events: bool = Field(default=True, alias="wantsSimilarEvents")


class AttendeeSignalInput(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    platform: str = "reddit"
    author_handle: str | None = Field(default=None, alias="authorHandle")
    source_url: str | None = Field(default=None, alias="sourceUrl")


class SourceToggleInput(BaseModel):
    enabled: bool
    daily_limit: int | None = Field(default=None, alias="dailyLimit")


# ---------------------------------------------------------------------------
# Helper: Get or Create Organizer + Profile for User
# ---------------------------------------------------------------------------


def _ensure_organizer_and_profile(db: Session, user: User) -> tuple[Organizer, OrganizerProfile]:
    organizer = db.scalar(select(Organizer).where((Organizer.user_id == user.id) | (Organizer.id == user.id)))
    if not organizer:
        base_slug = slugify(user.company or user.name) or f"organizer-{user.id}"
        slug = base_slug
        idx = 1
        while db.scalar(select(Organizer.id).where(Organizer.slug == slug)):
            slug = f"{base_slug}-{idx}"
            idx += 1
        organizer = Organizer(
            name=user.company or user.name,
            slug=slug,
            description=user.bio or f"Event organizer on 100 TIMES ({user.name})",
            logo=(user.name[:2] if user.name else "OR").upper(),
            email=user.email,
            user_id=user.id,
            company_name=user.company or user.name,
            contact_name=user.name,
            lifecycle_stage="SIGNED_UP",
            verified=True,
        )
        db.add(organizer)
        db.flush()

    profile = db.scalar(select(OrganizerProfile).where(OrganizerProfile.user_id == user.id))
    if not profile:
        profile = OrganizerProfile(
            user_id=user.id,
            organizer_id=organizer.id,
            organization_name=organizer.company_name or user.company or user.name,
            contact_name=user.name,
            contact_email=user.email,
            city="Bengaluru",
            country=user.country or "India",
            email_verified=True,
            identity_verified=True,
            lifecycle_stage=organizer.lifecycle_stage or "SIGNED_UP",
            lifecycle_history=[
                {
                    "stage": "SIGNED_UP",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor": user.email,
                    "note": "Organizer account initialized",
                }
            ],
        )
        db.add(profile)
        db.flush()

    if user.role == "USER":
        user.role = "ORGANIZER"
        db.flush()

    return organizer, profile


def _serialize_rich_event(db: Session, event: Event, user_id: int | None = None) -> dict[str, Any]:
    card = event_card(db, event, user_id)
    latest_review = db.scalar(
        select(TrustReview).where(TrustReview.event_id == event.id).order_by(desc(TrustReview.created_at))
    )
    cal = generate_calendar_links(event)
    return {
        **card.model_dump(by_alias=True),
        "description": event.description,
        "lifecycleState": event.lifecycle_state or ("PUBLISHED" if event.status == "published" else "DRAFT"),
        "timezone": event.timezone or "Asia/Kolkata",
        "endTime": event.end_time or "17:30",
        "fullAddress": event.full_address or "",
        "cityName": event.city_name or card.location,
        "stateName": event.state_name or "",
        "countryName": event.country_name or "India",
        "onlineMeetingUrl": event.online_meeting_url or "",
        "registrationUrl": event.registration_url or "",
        "isFree": bool(event.is_free),
        "capacity": event.capacity or 250,
        "ticketInfo": event.ticket_info or {},
        "speakerInfo": event.speaker_info or [],
        "contactInfo": event.contact_info or {},
        "socialLinks": event.social_links or {},
        "termsPolicy": event.terms_policy or "",
        "tags": event.tags or [],
        "targetAudience": event.target_audience or "",
        "viewsCount": event.views_count or 0,
        "trustScore": event.trust_score,
        "trustStatus": event.trust_status,
        "trustConfidence": event.trust_confidence,
        "calendarLinks": cal,
        "shareUrl": f"/events/{event.slug}",
        "trustReview": {
            "id": latest_review.id,
            "status": latest_review.status,
            "score": latest_review.score,
            "confidence": latest_review.confidence,
            "reasons": latest_review.reasons or [],
            "warnings": latest_review.warnings or [],
            "duplicateCandidates": latest_review.duplicate_candidates or [],
            "missingFields": latest_review.missing_fields or [],
            "recommendedAction": latest_review.recommended_action,
            "checksSummary": latest_review.checks_summary or {},
            "createdAt": latest_review.created_at.isoformat() if latest_review.created_at else "",
        }
        if latest_review
        else None,
    }


# ---------------------------------------------------------------------------
# 1. Auth Logout & Organizer Onboarding Endpoints
# ---------------------------------------------------------------------------


@router.post("/auth/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie("access_token")
    return {"success": True, "message": "Signed out successfully"}


@router.get("/organizer/profile")
def get_organizer_profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    organizer, profile = _ensure_organizer_and_profile(db, user)
    db.commit()
    return {
        "userId": user.id,
        "organizerId": organizer.id,
        "organizerName": organizer.name,
        "organizationName": profile.organization_name or organizer.company_name or organizer.name,
        "slug": organizer.slug,
        "contactName": profile.contact_name or user.name,
        "contactEmail": profile.contact_email or organizer.email or user.email,
        "contactPhone": profile.contact_phone or organizer.phone or "",
        "website": profile.website or organizer.website or "",
        "city": profile.city or "Bengaluru",
        "state": profile.state or "Karnataka",
        "country": profile.country or user.country or "India",
        "bio": profile.bio or organizer.description or "",
        "socialLinks": profile.social_links or organizer.social_links or {},
        "emailVerified": profile.email_verified,
        "identityVerified": profile.identity_verified,
        "lifecycleStage": profile.lifecycle_stage or organizer.lifecycle_stage or "SIGNED_UP",
        "lifecycleHistory": profile.lifecycle_history or [],
    }


@router.post("/organizer/onboarding")
def complete_organizer_onboarding(
    payload: OrganizerOnboardingInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    organizer, profile = _ensure_organizer_and_profile(db, user)

    # Create or update Organization row
    org_slug = slugify(payload.organization_name) or f"org-{organizer.id}"
    org_row = db.scalar(select(Organization).where(Organization.slug == org_slug))
    if not org_row:
        org_row = Organization(
            name=payload.organization_name.strip(),
            slug=org_slug,
            website=payload.website,
            city=payload.city,
            state=payload.state,
            country=payload.country or "India",
            verified=True,
        )
        db.add(org_row)
        db.flush()

    organizer.name = payload.organizer_name.strip()
    organizer.company_name = payload.organization_name.strip()
    organizer.contact_name = user.name
    organizer.email = payload.contact_email.lower()
    organizer.phone = payload.contact_phone
    organizer.website = payload.website
    organizer.description = payload.bio or f"{payload.organization_name} on 100 TIMES"
    organizer.social_links = payload.social_links
    organizer.verified = True
    if payload.discovered_organizer_id:
        organizer.discovered_organizer_id = payload.discovered_organizer_id

    profile.organization_id = org_row.id
    profile.organization_name = payload.organization_name.strip()
    profile.contact_name = payload.organizer_name.strip()
    profile.contact_email = payload.contact_email.lower()
    profile.contact_phone = payload.contact_phone
    profile.website = payload.website
    profile.city = payload.city
    profile.state = payload.state
    profile.country = payload.country or "India"
    profile.bio = payload.bio
    profile.social_links = payload.social_links
    profile.email_verified = True
    profile.identity_verified = True
    if payload.discovered_organizer_id:
        profile.discovered_organizer_id = payload.discovered_organizer_id

    user.company = payload.organization_name.strip()
    if user.role == "USER":
        user.role = "ORGANIZER"

    advance_organizer_stage(
        db,
        organizer,
        profile,
        "SIGNED_UP",
        actor=user.email,
        actor_id=user.id,
        note=f"Completed organizer onboarding for {payload.organization_name}",
    )

    send_templated_notification(
        db,
        template_key="account_verification",
        user_id=user.id,
        recipient_email=payload.contact_email,
        context={
            "name": payload.organizer_name,
            "email": payload.contact_email,
            "organization": payload.organization_name,
        },
    )

    db.commit()
    return get_organizer_profile(db=db, user=user)


# ---------------------------------------------------------------------------
# 2. Rich Event Creation, Draft, Edit, Submit to Trust Agent & Lifecycle
# ---------------------------------------------------------------------------


@router.get("/organizer/events/full")
def list_organizer_events_full(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    organizer, _ = _ensure_organizer_and_profile(db, user)
    rows = db.scalars(
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where((Event.organizer_id == organizer.id) | (Event.organizer_id == user.id))
        .order_by(desc(Event.created_at))
    ).all()
    return [_serialize_rich_event(db, ev, user.id) for ev in rows]


@router.post("/organizer/events/full", status_code=status.HTTP_201_CREATED)
def create_rich_organizer_event(
    payload: RichEventInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    organizer, profile = _ensure_organizer_and_profile(db, user)
    if payload.organization_name:
        organizer.company_name = payload.organization_name.strip()
        profile.organization_name = payload.organization_name.strip()

    fmt = "in-person" if payload.format in ("in-person", "offline", "hybrid") else "online"
    event = event_creation.create_event(
        db,
        title=payload.title.strip(),
        description=payload.description.strip(),
        event_type=payload.event_type.strip(),
        category_name=payload.category.strip(),
        location=payload.city.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date or payload.start_date,
        start_time=payload.start_time,
        price=Decimal("0.00") if payload.is_free else payload.price,
        format=fmt,
        organizer=organizer,
        status="draft",
        image=payload.image or event_creation.DEFAULT_EVENT_IMAGE,
    )

    event.end_time = payload.end_time
    event.timezone = payload.timezone or "Asia/Kolkata"
    event.is_free = payload.is_free or float(payload.price) == 0
    event.capacity = payload.capacity
    event.full_address = payload.full_address or payload.venue_name or payload.city
    event.city_name = payload.city
    event.state_name = payload.state
    event.country_name = payload.country
    event.online_meeting_url = payload.online_meeting_url
    event.registration_url = payload.registration_url
    event.ticket_info = payload.ticket_info
    event.speaker_info = payload.speaker_info
    event.contact_info = payload.contact_info or {"email": organizer.email or user.email}
    event.social_links = payload.social_links
    event.terms_policy = payload.terms_policy
    event.tags = payload.tags
    event.target_audience = payload.target_audience
    event.lifecycle_state = "DRAFT"
    event.status = "draft"
    db.flush()

    # Upsert structured EventLocation
    loc = db.scalar(select(EventLocation).where(EventLocation.event_id == event.id))
    if not loc:
        loc = EventLocation(
            event_id=event.id,
            venue_name=payload.venue_name or (event.venue.name if event.venue else payload.city),
            full_address=payload.full_address,
            city=payload.city,
            state=payload.state,
            country=payload.country,
            online_meeting_url=payload.online_meeting_url,
            registration_url=payload.registration_url,
            timezone=payload.timezone or "Asia/Kolkata",
        )
        db.add(loc)

    advance_organizer_stage(db, organizer, profile, "CREATED_EVENT", actor=user.email, actor_id=user.id, note=f"Created event '{event.title}'")

    record_audit_log(
        db,
        actor=user.email,
        actor_id=user.id,
        action="EVENT_CREATED",
        entity="Event",
        entity_id=event.id,
        metadata={"title": event.title, "save_as_draft": payload.save_as_draft},
    )

    if not payload.save_as_draft:
        transition_event_state(db, event, "SUBMITTED", actor=user.email, actor_id=user.id, reason="Submitted on creation")
        advance_organizer_stage(db, organizer, profile, "SUBMITTED", actor=user.email, actor_id=user.id)
        evaluate_event_trust(db, event, organizer=organizer, profile=profile, auto_publish_if_approved=True)

    db.commit()
    db.refresh(event)
    return _serialize_rich_event(db, event, user.id)


@router.put("/organizer/events/{event_id}")
def update_rich_organizer_event(
    event_id: int,
    payload: RichEventInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    organizer, profile = _ensure_organizer_and_profile(db, user)

    event.title = payload.title.strip()
    event.description = payload.description.strip()
    event.event_type = payload.event_type.strip()
    event.start_date = payload.start_date
    event.end_date = payload.end_date or payload.start_date
    event.start_time = payload.start_time
    event.end_time = payload.end_time
    event.timezone = payload.timezone or "Asia/Kolkata"
    event.is_free = payload.is_free or float(payload.price) == 0
    event.price = Decimal("0.00") if payload.is_free else payload.price
    event.capacity = payload.capacity
    event.format = "in-person" if payload.format in ("in-person", "offline", "hybrid") else "online"
    event.full_address = payload.full_address or payload.venue_name or payload.city
    event.city_name = payload.city
    event.state_name = payload.state
    event.country_name = payload.country
    event.online_meeting_url = payload.online_meeting_url
    event.registration_url = payload.registration_url
    event.ticket_info = payload.ticket_info
    event.speaker_info = payload.speaker_info
    event.contact_info = payload.contact_info
    event.social_links = payload.social_links
    event.terms_policy = payload.terms_policy
    event.tags = payload.tags
    event.target_audience = payload.target_audience
    if payload.image:
        event.image = payload.image

    record_audit_log(
        db,
        actor=user.email,
        actor_id=user.id,
        action="EVENT_MODIFIED",
        entity="Event",
        entity_id=event.id,
        metadata={"title": event.title, "save_as_draft": payload.save_as_draft},
    )

    if not payload.save_as_draft:
        transition_event_state(db, event, "SUBMITTED", actor=user.email, actor_id=user.id, reason="Submitted after edit", force=True)
        advance_organizer_stage(db, organizer, profile, "SUBMITTED", actor=user.email, actor_id=user.id)
        evaluate_event_trust(db, event, organizer=organizer, profile=profile, auto_publish_if_approved=True)

    db.commit()
    db.refresh(event)
    return _serialize_rich_event(db, event, user.id)


@router.post("/organizer/events/{event_id}/submit-trust")
def submit_event_to_trust_agent(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    organizer, profile = _ensure_organizer_and_profile(db, user)
    transition_event_state(db, event, "SUBMITTED", actor=user.email, actor_id=user.id, reason="Submitted to Trust Agent", force=True)
    advance_organizer_stage(db, organizer, profile, "SUBMITTED", actor=user.email, actor_id=user.id)
    evaluate_event_trust(db, event, organizer=organizer, profile=profile, auto_publish_if_approved=True)
    db.commit()
    db.refresh(event)
    return _serialize_rich_event(db, event, user.id)


@router.post("/organizer/events/{event_id}/cancel")
def cancel_organizer_event(
    event_id: int,
    payload: CancelEventInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    summary = cancel_event_workflow(db, event, reason=payload.reason, actor_id=user.id)
    db.commit()
    return {"summary": summary, "event": _serialize_rich_event(db, event, user.id)}


@router.post("/organizer/events/{event_id}/reschedule")
def reschedule_organizer_event(
    event_id: int,
    payload: RescheduleInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    summary = reschedule_event_workflow(
        db,
        event,
        new_start_date=payload.start_date,
        new_end_date=payload.end_date,
        new_start_time=payload.start_time,
        new_timezone=payload.timezone,
        actor_id=user.id,
    )
    db.commit()
    return {"summary": summary, "event": _serialize_rich_event(db, event, user.id)}


@router.post("/organizer/events/{event_id}/attendance")
def record_event_attendance(
    event_id: int,
    payload: AttendanceInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    summary = mark_attendance_and_noshows(db, event, attended_registration_ids=payload.attended_registration_ids)
    initiate_or_advance_organizer_followup(db, event=event, reason="POST_EVENT")
    db.commit()
    return summary


@router.post("/organizer/events/{event_id}/followup-response")
def submit_organizer_followup(
    event_id: int,
    payload: OrganizerFollowupResponseInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    followup = initiate_or_advance_organizer_followup(db, event=event, reason="POST_EVENT")
    record_organizer_followup_response(
        db,
        followup,
        reported_attendance=payload.reported_attendance,
        event_outcome=payload.event_outcome,
        organizer_feedback=payload.organizer_feedback,
        wants_repeat_event=payload.wants_repeat_event,
        next_event_date=payload.next_event_date,
    )
    db.commit()
    return {
        "followupId": followup.id,
        "status": followup.status,
        "wantsRepeatEvent": followup.wants_repeat_event,
        "nextEventDate": followup.next_event_date,
    }


# ---------------------------------------------------------------------------
# 3. Post-Event Attendee Feedback Endpoint (Workflow 6)
# ---------------------------------------------------------------------------


@router.post("/events/{event_id}/feedback")
def submit_event_feedback(
    event_id: int,
    payload: AttendeeFeedbackInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    reg = db.scalar(select(Registration).where(Registration.event_id == event_id, Registration.user_id == user.id))
    if reg:
        reg.status = "ATTENDED" if payload.attended else "NO_SHOW"

    fb = db.scalar(select(AttendeeFeedback).where(AttendeeFeedback.event_id == event_id, AttendeeFeedback.user_id == user.id))
    if not fb:
        fb = AttendeeFeedback(
            event_id=event_id,
            registration_id=reg.id if reg else None,
            user_id=user.id,
            attended=payload.attended,
            rating=payload.rating,
            feedback=payload.feedback,
            wants_similar_events=payload.wants_similar_events,
        )
        db.add(fb)
    else:
        fb.attended = payload.attended
        fb.rating = payload.rating
        fb.feedback = payload.feedback
        fb.wants_similar_events = payload.wants_similar_events

    record_audit_log(
        db,
        actor=user.email,
        actor_id=user.id,
        action="ATTENDEE_FEEDBACK_SUBMITTED",
        entity="Event",
        entity_id=event_id,
        metadata={"attended": payload.attended, "rating": payload.rating},
    )
    db.commit()
    return {"success": True, "attended": fb.attended, "rating": fb.rating, "wantsSimilarEvents": fb.wants_similar_events}


# ---------------------------------------------------------------------------
# 4. Trust Agent & Admin Trust Review Console Endpoints
# ---------------------------------------------------------------------------


@router.get("/trust/reviews")
def list_trust_reviews(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    query = select(TrustReview).order_by(desc(TrustReview.created_at))
    if status_filter and status_filter != "ALL":
        query = query.where(TrustReview.status == status_filter)
    reviews = db.scalars(query.limit(100)).all()

    out = []
    for r in reviews:
        ev = db.get(Event, r.event_id)
        org = db.get(Organizer, r.organizer_id) if r.organizer_id else (ev.organizer if ev else None)
        decisions = db.scalars(
            select(TrustDecision).where(TrustDecision.trust_review_id == r.id).order_by(desc(TrustDecision.created_at))
        ).all()
        out.append(
            {
                "id": r.id,
                "eventId": r.event_id,
                "eventTitle": ev.title if ev else f"Event #{r.event_id}",
                "eventSlug": ev.slug if ev else "",
                "eventLifecycleState": ev.lifecycle_state if ev else "DRAFT",
                "organizerId": org.id if org else None,
                "organizerName": org.name if org else "Organizer",
                "organizerEmail": org.email if org else "",
                "status": r.status,
                "score": r.score,
                "confidence": r.confidence,
                "reasons": r.reasons or [],
                "warnings": r.warnings or [],
                "duplicateCandidates": r.duplicate_candidates or [],
                "missingFields": r.missing_fields or [],
                "recommendedAction": r.recommended_action,
                "checksSummary": r.checks_summary or {},
                "createdAt": r.created_at.isoformat() if r.created_at else "",
                "auditHistory": [
                    {
                        "id": d.id,
                        "actorType": d.actor_type,
                        "actorId": d.actor_id,
                        "decision": d.decision,
                        "previousStatus": d.previous_status,
                        "newStatus": d.new_status,
                        "notes": d.notes,
                        "createdAt": d.created_at.isoformat() if d.created_at else "",
                    }
                    for d in decisions
                ],
            }
        )
    return out


@router.post("/trust/reviews/{review_id}/decision")
def decide_trust_review(
    review_id: int,
    payload: TrustAdminDecisionInput,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    review = db.get(TrustReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Trust review not found")
    updated = admin_decide_trust_review(
        db,
        review,
        decision=payload.decision,
        admin_user_id=admin.id,
        notes=payload.notes,
    )
    db.commit()
    return {"id": updated.id, "status": updated.status, "recommendedAction": updated.recommended_action}


# ---------------------------------------------------------------------------
# 5. Attendee Agent Endpoints (Section 7 & 8)
# ---------------------------------------------------------------------------


@router.get("/attendee-agent/dashboard")
def attendee_agent_dashboard_route(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    return get_attendee_agent_dashboard(db)


@router.post("/attendee-agent/extract-intent")
def extract_intent_route(
    payload: AttendeeSignalInput,
) -> dict[str, Any]:
    res = extract_attendee_intent(payload.text)
    return res.model_dump()


@router.post("/attendee-agent/match")
def match_attendee_signal_route(
    payload: AttendeeSignalInput,
    db: Session = Depends(get_db),
    _: User | None = Depends(optional_current_user),
) -> dict[str, Any]:
    try:
        intent, matches = process_attendee_signal(
            db,
            raw_text=payload.text,
            source_platform=payload.platform,
            author_handle=payload.author_handle,
            source_url=payload.source_url,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    events_map = {e.id: e for e in db.scalars(select(Event)).all()}
    return {
        "intent": {
            "id": intent.id,
            "category": intent.event_category,
            "location": intent.location,
            "time_range": intent.date_preference,
            "event_type": intent.event_type,
            "price_preference": intent.price_preference,
            "format_preference": intent.format_preference,
            "keywords": intent.keywords,
            "inferred_interests": intent.inferred_interests,
            "confidence": float(intent.confidence),
        },
        "matches": [
            {
                "id": m.id,
                "eventId": m.event_id,
                "eventTitle": events_map[m.event_id].title if m.event_id in events_map else "",
                "eventSlug": events_map[m.event_id].slug if m.event_id in events_map else "",
                "matchScore": m.match_score,
                "matchReasons": m.match_reasons,
                "recommendationText": m.recommendation_text,
                "trackingUrl": m.tracking_url,
            }
            for m in matches
        ],
    }


@router.post("/attendee-agent/scan")
def trigger_attendee_agent_scan(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    summary = run_attendee_discovery_cycle(db)
    db.commit()
    return summary


@router.patch("/attendee-agent/sources/{source}")
def toggle_attendee_source(
    source: str,
    payload: SourceToggleInput,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    res = set_source_enabled(db, source, payload.enabled, payload.daily_limit)
    db.commit()
    return res


# ---------------------------------------------------------------------------
# 6. Admin Extended Metrics, Audit Logs & Automation Status (Section 12)
# ---------------------------------------------------------------------------


@router.get("/admin/overview-extended")
def admin_overview_extended(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    today = date.today()
    return {
        "totalOrganizers": int(db.scalar(select(func.count(Organizer.id))) or 0),
        "newOrganizers": int(db.scalar(select(func.count(OrganizerProfile.id))) or 0),
        "totalEvents": int(db.scalar(select(func.count(Event.id))) or 0),
        "pendingReviews": int(db.scalar(select(func.count(TrustReview.id)).where(TrustReview.status == "NEEDS_REVIEW")) or 0),
        "publishedEvents": int(db.scalar(select(func.count(Event.id)).where(Event.status == "published")) or 0),
        "registrations": int(db.scalar(select(func.count(Registration.id))) or 0),
        "upcomingEvents": int(db.scalar(select(func.count(Event.id)).where(Event.start_date >= today, Event.status == "published")) or 0),
        "completedEvents": int(db.scalar(select(func.count(Event.id)).where(Event.lifecycle_state == "EVENT_COMPLETED")) or 0),
        "cancelledEvents": int(db.scalar(select(func.count(Event.id)).where(Event.lifecycle_state == "CANCELLED")) or 0),
        "trustAgentDecisions": int(db.scalar(select(func.count(TrustDecision.id))) or 0),
        "attendeeAgentActivity": int(db.scalar(select(func.count(AttendeeIntent.id))) or 0),
        "automationRuns": int(db.scalar(select(func.count(AutomationRun.id))) or 0),
        "scheduledReminders": int(db.scalar(select(func.count(EventReminder.id)).where(EventReminder.status == "SCHEDULED")) or 0),
    }


@router.get("/admin/audit-logs")
def get_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    rows = db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(min(limit, 250))).all()
    return [
        {
            "id": r.id,
            "actor": r.actor,
            "actorId": r.actor_id,
            "action": r.action,
            "entity": r.entity,
            "entityId": r.entity_id,
            "result": r.result,
            "metadata": r.metadata_json or {},
            "createdAt": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


@router.get("/admin/automation-runs")
def get_automation_runs(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    rows = db.scalars(select(AutomationRun).order_by(desc(AutomationRun.started_at)).limit(100)).all()
    return [
        {
            "id": r.id,
            "workflowId": r.workflow_id,
            "workflowName": r.workflow_name,
            "idempotencyKey": r.idempotency_key,
            "triggerEvent": r.trigger_event,
            "entityType": r.entity_type,
            "entityId": r.entity_id,
            "status": r.status,
            "result": r.result or {},
            "error": r.error,
            "startedAt": r.started_at.isoformat() if r.started_at else "",
            "completedAt": r.completed_at.isoformat() if r.completed_at else "",
        }
        for r in rows
    ]
