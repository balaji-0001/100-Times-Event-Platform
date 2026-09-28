import math
import re
from datetime import date as date_type
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.dependencies import get_current_user, optional_current_user, require_roles
from backend.models import AcquisitionReferralEvent, Category, City, Event, Notification, Registration, Review, SavedEvent, Speaker, User, Venue
from backend.services.social_agent.attribution import attribute_registration
from backend.schemas import (
    ActionResult,
    EventCard,
    EventDetail,
    EventInput,
    EventList,
    RegistrationInput,
    RegistrationOut,
    ReviewInput,
    ReviewOut,
)
from backend.serializers import event_card, review_out

router = APIRouter(prefix="/events", tags=["events"])


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def load_event(db: Session, event_id: int) -> Event:
    event = db.scalar(
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.id == event_id)
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("", response_model=EventList)
def list_events(
    q: str | None = None,
    category: str | None = None,
    city: str | None = None,
    eventType: str | None = None,
    date: str | None = None,
    format: str = Query("all", pattern="^(all|online|in-person)$"),
    sort: str = Query("soonest", pattern="^(soonest|popular|newest)$"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
) -> EventList:
    query = (
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.status == "published")
    )
    if q:
        term = f"%{q.strip()}%"
        query = query.where(
            or_(
                Event.title.ilike(term),
                Event.description.ilike(term),
                Event.event_type.ilike(term),
            )
        )
    if category:
        query = query.join(Category).where(or_(Category.slug == category, Category.name.ilike(category)))
    if city:
        query = query.join(Event.venue).join(Venue.city).where(or_(City.name.ilike(city), City.slug == city))
    if eventType:
        query = query.where(Event.event_type.ilike(eventType))
    if format != "all":
        query = query.where(Event.format == format)
    if date:
        try:
            query = query.where(Event.start_date >= date_type.fromisoformat(date))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc
    if sort == "popular":
        query = query.order_by(desc(select(func.count(Registration.id)).where(Registration.event_id == Event.id).scalar_subquery()))
    elif sort == "newest":
        query = query.order_by(desc(Event.created_at))
    else:
        query = query.order_by(asc(Event.start_date), asc(Event.start_time))
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int(db.scalar(count_query) or 0)
    rows = db.scalars(query.offset((page - 1) * pageSize).limit(pageSize)).all()
    return EventList(items=[event_card(db, row, user.id if user else None) for row in rows], total=total, page=page, pageSize=pageSize, totalPages=max(1, math.ceil(total / pageSize)))


@router.get("/{slug}", response_model=EventDetail)
def get_event(slug: str, db: Session = Depends(get_db), user: User | None = Depends(optional_current_user)) -> EventDetail:
    query = (
        select(Event)
        .options(
            selectinload(Event.category), selectinload(Event.organizer),
            selectinload(Event.venue).selectinload(Venue.city),
            selectinload(Event.reviews).selectinload(Review.user),
        )
        .where(Event.slug == slug)
    )
    if user and user.role in ("ADMIN", "ORGANIZER"):
        pass
    else:
        query = query.where(Event.status == "published")

    event = db.scalar(query)
    if not event and slug.isdigit():
        event = db.scalar(
            select(Event)
            .options(
                selectinload(Event.category), selectinload(Event.organizer),
                selectinload(Event.venue).selectinload(Venue.city),
                selectinload(Event.reviews).selectinload(Review.user),
            )
            .where(Event.id == int(slug))
        )

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    reviews = [review_out(review) for review in sorted(event.reviews, key=lambda item: item.created_at, reverse=True)]
    related_query = (
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.category_id == event.category_id, Event.id != event.id, Event.status == "published")
        .order_by(Event.start_date)
        .limit(3)
    )
    related = [event_card(db, item, user.id if user else None) for item in db.scalars(related_query).all()]
    card = event_card(db, event, user.id if user else None)
    return EventDetail(
        **card.model_dump(),
        description=event.description,
        organizerId=event.organizer_id or 0,
        venueId=event.venue_id or 0,
        agenda=[
            {"time": "09:30 AM", "title": "Doors open & coffee", "detail": "Settle in, meet the room, and find your people."},
            {"time": "10:30 AM", "title": "The opening signal", "detail": "A clear-eyed view of the shifts shaping the next 12 months."},
            {"time": "01:15 PM", "title": "Working sessions", "detail": "Small rooms, honest questions, practical takeaways."},
        ],
        speakers=[],
        exhibitors=["Northstar Labs", "Arcwell", "Lumen Health", "Kiteworks"],
        reviews=reviews,
        relatedEvents=related,
    )


@router.post("/{id}/save", response_model=ActionResult)
def save_event(id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ActionResult:
    load_event(db, id)
    existing = db.scalar(select(SavedEvent).where(SavedEvent.user_id == user.id, SavedEvent.event_id == id))
    if not existing:
        db.add(SavedEvent(user_id=user.id, event_id=id))
        db.commit()
    return ActionResult(success=True, isSaved=True, message="Event saved to your calendar.")


@router.delete("/{id}/save", response_model=ActionResult)
def unsave_event(id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ActionResult:
    load_event(db, id)
    saved = db.scalar(select(SavedEvent).where(SavedEvent.user_id == user.id, SavedEvent.event_id == id))
    if saved:
        db.delete(saved)
        db.commit()
    return ActionResult(success=True, isSaved=False, message="Event removed from saved events.")


@router.post("/{id}/register", response_model=RegistrationOut, status_code=status.HTTP_201_CREATED)
def register_for_event(
    id: int,
    payload: RegistrationInput,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
) -> RegistrationOut:
    from backend.services.registration_automation import automate_registration

    event = load_event(db, id)
    if (event.lifecycle_state or "").upper() == "CANCELLED" or event.status == "cancelled":
        raise HTTPException(status_code=400, detail="This event has been cancelled")

    submitted_email = (payload.email or "").strip().lower()
    target_user = user

    if not target_user:
        target_user = db.scalar(select(User).where(func.lower(User.email) == submitted_email))
        if not target_user:
            target_user = User(
                name=f"{payload.first_name} {payload.last_name}".strip() or submitted_email.split("@")[0] or "Attendee",
                email=submitted_email or f"attendee-{int(datetime.now(timezone.utc).timestamp())}@100times.io",
                password_hash="guest_registration",
                role="USER",
                company=payload.company,
                job_title=payload.job_title,
                country=payload.country or "India",
            )
            db.add(target_user)
            db.flush()
    else:
        # If logged-in user already registered for this event and is submitting a different attendee email,
        # resolve or create that attendee's User row so both registrations are stored cleanly.
        existing_for_current = db.scalar(select(Registration).where(Registration.event_id == id, Registration.user_id == target_user.id))
        if existing_for_current and submitted_email and submitted_email != (target_user.email or "").lower():
            other_user = db.scalar(select(User).where(func.lower(User.email) == submitted_email))
            if not other_user:
                other_user = User(
                    name=f"{payload.first_name} {payload.last_name}".strip() or submitted_email.split("@")[0],
                    email=submitted_email,
                    password_hash=target_user.password_hash,
                    role="USER",
                    company=payload.company,
                    job_title=payload.job_title,
                    country=payload.country or "India",
                )
                db.add(other_user)
                db.flush()
            target_user = other_user

    existing = db.scalar(select(Registration).where(Registration.event_id == id, Registration.user_id == target_user.id))
    if not existing:
        active_count = int(
            db.scalar(
                select(func.count(Registration.id)).where(
                    Registration.event_id == id,
                    Registration.status.in_(["confirmed", "CONFIRMED", "REGISTERED", "ATTENDED"]),
                )
            )
            or 0
        )
        if event.capacity is not None and event.capacity > 0 and active_count >= event.capacity:
            raise HTTPException(status_code=409, detail="Event has reached maximum capacity")

    if payload.company:
        target_user.company = payload.company
    if payload.job_title:
        target_user.job_title = payload.job_title
    if payload.country:
        target_user.country = payload.country

    intent_id_param = request.query_params.get("intent_id")
    parsed_intent_id = int(intent_id_param) if intent_id_param and intent_id_param.isdigit() else None

    try:
        auto_res = automate_registration(
            db,
            event=event,
            user=target_user,
            ticket_type=payload.ticket_type,
            attendee_name=f"{payload.first_name} {payload.last_name}".strip(),
            attendee_email=payload.email,
            attendee_phone=payload.phone,
            company=payload.company,
            job_title=payload.job_title,
            country=payload.country,
            intent_id=parsed_intent_id,
        )
        registration = auto_res["registration"]
        db.commit()
        db.refresh(registration)
        db.refresh(target_user)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Registration could not be created") from exc

    # Real attribution: if a tracked click (via /r/{opportunity_id}) drove this
    # registration within the configured window, record it — this is the actual
    # conversion signal the acquisition analytics are built on.
    session_id = request.cookies.get("hundredtimes_sid")
    attribution = attribute_registration(db, registration, session_id, event_id=id)
    if attribution:
        db.add(
            AcquisitionReferralEvent(
                opportunity_id=attribution.opportunity_id,
                event_id=id,
                event_type="registration",
                visitor_id=session_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    ticket_code = f"100T-{event.id:04d}-{registration.id:05d}"
    qr_data = f"100TIMES:PASS:EVENT={event.slug}:REG={ticket_code}:USER={target_user.email}:TIER={registration.ticket_type}"
    venue_name = event.venue.name if event.venue else "Convention Center"
    city_name = event.venue.city.name if event.venue and event.venue.city else ""
    loc_str = f"{city_name}" if city_name else ""
    return RegistrationOut(
        id=registration.id,
        eventId=id,
        eventTitle=event.title,
        eventSlug=event.slug,
        ticketType=registration.ticket_type,
        registeredAt=registration.registered_at,
        status=registration.status,
        userName=registration.attendee_name or target_user.name,
        company=registration.company or target_user.company,
        jobTitle=registration.job_title or target_user.job_title,
        ticketCode=ticket_code,
        qrCode=qr_data,
        eventLocation=loc_str,
        eventVenue=venue_name,
        eventStartDate=event.start_date.isoformat() if event.start_date else "",
        eventEndDate=event.end_date.isoformat() if event.end_date else "",
        eventStartTime=event.start_time or "09:00",
    )


@router.post("/{id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(id: int, payload: ReviewInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ReviewOut:
    load_event(db, id)
    if db.scalar(select(Review).where(Review.event_id == id, Review.user_id == user.id)):
        raise HTTPException(status_code=409, detail="You have already reviewed this event")
    review = Review(event_id=id, user_id=user.id, rating=payload.rating, title=payload.title.strip(), comment=payload.comment.strip())
    db.add(review)
    try:
        db.commit()
        db.refresh(review)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Review could not be created") from exc
    review.user = user
    return review_out(review)