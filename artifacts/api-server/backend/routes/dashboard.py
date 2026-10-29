from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.dependencies import get_current_user, require_attendee, require_roles
from backend.models import Category, City, Event, Notification, Organizer, Registration, Review, SavedEvent, ScheduleItem, User, Venue
from backend.schemas import (
    AdminDashboard,
    Analytics,
    Dashboard,
    EventCard,
    EventInput,
    NotificationOut,
    OrganizerDashboard,
    RegistrationOut,
    ScheduleItemInput,
    ScheduleItemOut,
    UserOut,
)
from backend.serializers import event_card
from backend.routes.platform_ops import owned_organizer, owned_organizer_ids, unique_organizer_slug
from backend.services import event_creation
from backend.services.lifecycle import transition_event_state
from backend.services.sectors import REMOVED_SECTOR_NOTE, REMOVED_SECTOR_SLUGS, is_removed_sector

router = APIRouter(tags=["dashboards"])


def registration_out(registration: Registration, user: User | None = None) -> RegistrationOut:
    event = registration.event
    u = user or (registration.user if hasattr(registration, "user") else None)
    ticket_code = f"100T-{event.id:04d}-{registration.id:05d}" if event else f"100T-0000-{registration.id:05d}"
    qr_data = f"100TIMES:PASS:EVENT={event.slug if event else 'event'}:REG={ticket_code}:USER={u.email if u else ''}:TIER={registration.ticket_type}"
    venue_name = event.venue.name if event and event.venue else ""
    city_name = event.venue.city.name if event and event.venue and event.venue.city else ""
    loc_str = f"{city_name}" if city_name else (event.location if event else "")
    return RegistrationOut(
        id=registration.id,
        eventId=registration.event_id,
        eventTitle=event.title if event else "Event",
        eventSlug=event.slug if event else "",
        ticketType=registration.ticket_type,
        registeredAt=registration.registered_at,
        status=registration.status,
        userName=u.name if u else "",
        company=u.company if u else None,
        jobTitle=u.job_title if u else None,
        ticketCode=ticket_code,
        qrCode=qr_data,
        eventLocation=loc_str,
        eventVenue=venue_name,
        eventStartDate=event.start_date.isoformat() if event and event.start_date else "",
        eventEndDate=event.end_date.isoformat() if event and event.end_date else "",
        eventStartTime=event.start_time if event and event.start_time else "",
    )


@router.get("/home")
def home(db: Session = Depends(get_db)) -> dict:
    user_id = None
    featured = db.scalars(
        select(Event).options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.status == "published").order_by(Event.start_date).limit(4)
    ).all()
    categories = db.scalars(select(Category).where(Category.slug.not_in(REMOVED_SECTOR_SLUGS)).order_by(Category.name).limit(6)).all()
    cities = db.scalars(select(City).order_by(City.name).limit(8)).all()
    from backend.serializers import category_out, city_out
    return {
        "featured": [event_card(db, item, user_id) for item in featured],
        "trending": [category_out(db, item) for item in categories],
        "cities": [city_out(db, item) for item in cities],
        "eventTypes": ["Conferences", "Exhibitions", "Trade shows", "Workshops", "Summits", "Networking"],
        "stats": {
            "events": int(db.scalar(select(func.count(Event.id)).where(Event.status == "published")) or 0),
            "cities": int(db.scalar(select(func.count(City.id))) or 0),
            "organizers": int(db.scalar(select(func.count(Organizer.id))) or 0),
        },
    }


@router.get("/dashboard", response_model=Dashboard)
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> Dashboard:
    saved_rows = db.scalars(
        select(Event).join(SavedEvent, SavedEvent.event_id == Event.id)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(SavedEvent.user_id == user.id).order_by(desc(SavedEvent.created_at))
    ).all()
    registrations = db.scalars(
        select(Registration)
        .options(selectinload(Registration.event).selectinload(Event.venue).selectinload(Venue.city))
        .where(Registration.user_id == user.id).order_by(desc(Registration.registered_at))
    ).all()
    notifications = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(desc(Notification.created_at)).limit(10)).all()
    recommended = db.scalars(
        select(Event).options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.status == "published").order_by(Event.start_date).limit(4)
    ).all()
    return Dashboard(
        userName=user.name,
        savedCount=len(saved_rows),
        registrationCount=len(registrations),
        attendedCount=sum(1 for item in registrations if item.event and item.event.end_date < __import__("datetime").date.today()),
        upcoming=[registration_out(item, user) for item in registrations if item.status == "confirmed"],
        saved=[event_card(db, item, user.id) for item in saved_rows],
        recommended=[event_card(db, item, user.id) for item in recommended],
        notifications=[NotificationOut.model_validate(item) for item in notifications],
    )


@router.get("/dashboard/saved-events", response_model=list[EventCard])
def saved_events(db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> list[EventCard]:
    rows = db.scalars(
        select(Event).join(SavedEvent, SavedEvent.event_id == Event.id)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(SavedEvent.user_id == user.id)
    ).all()
    return [event_card(db, item, user.id) for item in rows]


@router.get("/dashboard/registrations", response_model=list[RegistrationOut])
def registrations(db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> list[RegistrationOut]:
    rows = db.scalars(
        select(Registration)
        .options(selectinload(Registration.event).selectinload(Event.venue).selectinload(Venue.city))
        .where(Registration.user_id == user.id)
        .order_by(desc(Registration.registered_at))
    ).all()
    return [registration_out(item, user) for item in rows]


@router.get("/dashboard/schedule", response_model=list[ScheduleItemOut])
def list_schedule(db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> list[ScheduleItemOut]:
    items = db.scalars(
        select(ScheduleItem)
        .options(selectinload(ScheduleItem.event))
        .where(ScheduleItem.user_id == user.id)
        .order_by(ScheduleItem.created_at.desc())
    ).all()
    return [
        ScheduleItemOut(
            id=item.id,
            eventId=item.event_id,
            eventTitle=item.event.title if item.event else "Event",
            eventSlug=item.event.slug if item.event else "",
            eventDate=item.event.start_date.isoformat() if item.event else "",
            sessionTitle=item.session_title,
            sessionTime=item.session_time,
            sessionDetail=item.session_detail,
            createdAt=item.created_at,
        )
        for item in items
    ]


@router.post("/dashboard/schedule", response_model=ScheduleItemOut, status_code=status.HTTP_201_CREATED)
def add_schedule_item(payload: ScheduleItemInput, db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> ScheduleItemOut:
    event = db.get(Event, payload.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    existing = db.scalar(
        select(ScheduleItem).where(
            ScheduleItem.user_id == user.id,
            ScheduleItem.event_id == payload.event_id,
            ScheduleItem.session_title == payload.session_title,
        )
    )
    if existing:
        return ScheduleItemOut(
            id=existing.id,
            eventId=existing.event_id,
            eventTitle=event.title,
            eventSlug=event.slug,
            eventDate=event.start_date.isoformat(),
            sessionTitle=existing.session_title,
            sessionTime=existing.session_time,
            sessionDetail=existing.session_detail,
            createdAt=existing.created_at,
        )
    item = ScheduleItem(
        user_id=user.id,
        event_id=payload.event_id,
        session_title=payload.session_title,
        session_time=payload.session_time,
        session_detail=payload.session_detail,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return ScheduleItemOut(
        id=item.id,
        eventId=item.event_id,
        eventTitle=event.title,
        eventSlug=event.slug,
        eventDate=event.start_date.isoformat(),
        sessionTitle=item.session_title,
        sessionTime=item.session_time,
        sessionDetail=item.session_detail,
        createdAt=item.created_at,
    )


@router.delete("/dashboard/schedule/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_item(schedule_id: int, db: Session = Depends(get_db), user: User = Depends(require_attendee)):
    item = db.get(ScheduleItem, schedule_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    db.delete(item)
    db.commit()
    return None


@router.get("/dashboard/notifications", response_model=list[NotificationOut])
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[NotificationOut]:
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(desc(Notification.created_at))).all()
    return [NotificationOut.model_validate(item) for item in rows]


class OrganizerDashboardOut(OrganizerDashboard):
    """OrganizerDashboard with honest nulls: event page views are not tracked
    anywhere yet, so views and the view->registration conversion rate are
    unknown (null) rather than invented. (Same fields/aliases as the shared
    schema; move these two `| None` types into schemas.OrganizerDashboard.)"""

    views: int | None = None
    conversion_rate: float | None = Field(default=None, alias="conversionRate")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _caller_event_ids(user: User):
    """Ids of events whose organizer row the caller owns (Event.organizer_id is
    an FK to organizers.id — never compared with a user id)."""
    return select(Event.id).where(Event.organizer_id.in_(owned_organizer_ids(user)))


@router.get("/organizer", response_model=OrganizerDashboardOut)
def organizer_dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> OrganizerDashboardOut:
    mine = Event.organizer_id.in_(owned_organizer_ids(user))
    events = db.scalars(select(Event).options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city)).where(mine).order_by(desc(Event.created_at)).limit(5)).all()
    registrations = int(db.scalar(select(func.count(Registration.id)).where(Registration.event_id.in_(_caller_event_ids(user)))) or 0)
    total = int(db.scalar(select(func.count(Event.id)).where(mine)) or 0)
    published = int(db.scalar(select(func.count(Event.id)).where(mine, Event.status == "published")) or 0)
    return OrganizerDashboardOut(
        totalEvents=total,
        publishedEvents=published,
        registrations=registrations,
        views=None,
        conversionRate=None,
        recentEvents=[event_card(db, item, user.id) for item in events],
    )


@router.get("/organizer/events", response_model=list[EventCard])
def organizer_events(db: Session = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> list[EventCard]:
    rows = db.scalars(select(Event).options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city)).where(Event.organizer_id.in_(owned_organizer_ids(user))).order_by(desc(Event.created_at))).all()
    return [event_card(db, item, user.id) for item in rows]


@router.post("/organizer/events", response_model=EventCard, status_code=status.HTTP_201_CREATED)
def create_organizer_event(payload: EventInput, db: Session = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> EventCard:
    from backend.services.trust_agent import evaluate_event_trust

    if is_removed_sector(payload.category):
        raise HTTPException(status_code=422, detail=REMOVED_SECTOR_NOTE + " Pick another sector.")
    organizer = owned_organizer(db, user)
    if not organizer:
        organizer = Organizer(
            # id assigned by the database; slug made unique (organizers.slug is UNIQUE).
            user_id=user.id,
            name=user.name,
            slug=unique_organizer_slug(db, user.name, f"organizer-u{user.id}"),
            description="100 TIMES community organizer",
            logo=(user.name[:2] if user.name else "OR").upper(),
            email=user.email,
            verified=False,
        )
        db.add(organizer)
        db.flush()

    event = event_creation.create_event(
        db,
        title=payload.title,
        description=payload.description,
        event_type=payload.event_type,
        category_name=payload.category,
        location=payload.location,
        start_date=payload.start_date,
        end_date=payload.end_date,
        start_time=payload.start_time,
        price=payload.price,
        format=payload.format,
        organizer=organizer,
        # Not public until the Trust Agent approves it (same flow as
        # POST /organizer/events/full). Creating it "published" both skipped
        # review and made the PUBLISHED -> TRUST_CHECK transition fail.
        status="draft",
    )
    event.city_name = payload.location
    event.full_address = payload.location
    event.lifecycle_state = "DRAFT"
    db.flush()
    transition_event_state(db, event, "SUBMITTED", actor=user.email, actor_id=user.id, reason="Submitted on creation")
    evaluate_event_trust(db, event, organizer=organizer, auto_publish_if_approved=True)
    db.commit()
    db.refresh(event)
    return event_card(db, event, user.id)


ANALYTICS_WEEKS = 7
GROWTH_DAYS = 7


@router.get("/organizer/analytics", response_model=Analytics)
def organizer_analytics(db: Session = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> Analytics:
    """Only real numbers: registrations per week (last 7 weeks, oldest first)
    and the ticket-type split of the caller's non-cancelled registrations.
    Page views are not tracked, so `views` and `conversion` are empty."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(weeks=ANALYTICS_WEEKS)
    my_event_ids = _caller_event_ids(user)

    weekly = [0] * ANALYTICS_WEEKS
    for registered_at in db.scalars(select(Registration.registered_at).where(Registration.event_id.in_(my_event_ids))).all():
        ts = _as_utc(registered_at)
        if ts is None or ts < window_start or ts > now:
            continue
        weeks_ago = int((now - ts) // timedelta(weeks=1))
        if 0 <= weeks_ago < ANALYTICS_WEEKS:
            weekly[ANALYTICS_WEEKS - 1 - weeks_ago] += 1

    distribution_rows = db.execute(
        select(Registration.ticket_type, func.count(Registration.id))
        .where(Registration.event_id.in_(my_event_ids), func.lower(Registration.status) != "cancelled")
        .group_by(Registration.ticket_type)
    ).all()
    distribution = {str(ticket_type or "Unspecified"): int(n) for ticket_type, n in distribution_rows}
    return Analytics(views=[], registrations=weekly, conversion=[], ticketDistribution=distribution)


def _daily_new_counts(db: Session, column, days: int) -> list[int]:
    """Rows created on each of the last `days` UTC days (oldest first, today last)."""
    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(first_day, datetime.min.time())
    counts = [0] * days
    for created_at in db.scalars(select(column).where(column >= since)).all():
        ts = _as_utc(created_at)
        if ts is None:
            continue
        index = (ts.date() - first_day).days
        if 0 <= index < days:
            counts[index] += 1
    return counts


@router.get("/admin", response_model=AdminDashboard)
def admin_dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN"))) -> AdminDashboard:
    def total(model) -> int:
        return int(db.scalar(select(func.count(model.id))) or 0)

    categories = db.scalars(select(Category).where(Category.slug.not_in(REMOVED_SECTOR_SLUGS)).order_by(Category.name).limit(5)).all()
    # Growth = new users / new events created on each of the last 7 days (real created_at).
    return AdminDashboard(
        users=total(User),
        events=total(Event),
        organizers=total(Organizer),
        registrations=total(Registration),
        reviews=total(Review),
        userGrowth=_daily_new_counts(db, User.created_at, GROWTH_DAYS),
        eventGrowth=_daily_new_counts(db, Event.created_at, GROWTH_DAYS),
        popularCategories=[item.name for item in categories],
    )


class EventStatusUpdate(BaseModel):
    status: Literal["draft", "published", "pending"]


class UserRoleUpdate(BaseModel):
    role: Literal["USER", "ORGANIZER", "ADMIN"]


@router.get("/admin/events", response_model=list[EventCard])
def get_admin_events(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> list[EventCard]:
    events = db.scalars(
        select(Event)
        .options(
            selectinload(Event.category),
            selectinload(Event.venue),
            selectinload(Event.organizer),
            selectinload(Event.registrations),
        )
        .order_by(desc(Event.start_date))
        .limit(100)
    ).all()
    return [event_card(db, e) for e in events]


@router.patch("/admin/events/{id}/status", response_model=EventCard)
def update_admin_event_status(
    id: int,
    payload: EventStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> EventCard:
    event = db.get(Event, id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if payload.status == "published":
        # Same publish step as every other path, so social promotion runs too.
        transition_event_state(db, event, "PUBLISHED", actor=user.email, actor_id=user.id, reason="Published by admin", force=True)
    event.status = payload.status
    if payload.status == "draft":
        event.lifecycle_state = "DRAFT"
    db.commit()
    db.refresh(event)
    return event_card(db, event)


@router.get("/admin/users", response_model=list[UserOut])
def get_admin_users(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return [
        UserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role,
            country=u.country,
        )
        for u in users
    ]


@router.patch("/admin/users/{id}/role", response_model=UserOut)
def update_admin_user_role(
    id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> UserOut:
    target_user = db.get(User, id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    target_user.role = payload.role
    db.commit()
    db.refresh(target_user)
    return UserOut(
        id=target_user.id,
        name=target_user.name,
        email=target_user.email,
        role=target_user.role,
        country=target_user.country,
    )


@router.get("/admin/reviews")
def get_admin_reviews(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> list[dict]:
    reviews = db.scalars(select(Review).order_by(desc(Review.created_at)).limit(100)).all()
    out = []
    for r in reviews:
        evt = db.get(Event, r.event_id)
        u = db.get(User, r.user_id)
        out.append({
            "id": r.id,
            "author": u.name if u else "Anonymous",
            "rating": r.rating,
            "title": r.title,
            "comment": r.comment,
            "eventId": r.event_id,
            "eventTitle": evt.title if evt else "Unknown Event",
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        })
    return out


@router.delete("/admin/reviews/{id}")
def delete_admin_review(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
):
    review = db.get(Review, id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    db.delete(review)
    db.commit()
    return {"status": "ok", "message": "Review deleted"}
