from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.dependencies import get_current_user, require_roles
from backend.models import Category, City, Event, Notification, Organizer, Registration, Review, SavedEvent, ScheduleItem, User, Venue
from backend.schemas import (
    AdminDashboard,
    Analytics,
    Dashboard,
    EventCard,
    EventInput,
    NotificationOut,
    OrganizerDashboard,
    ProfileUpdateInput,
    RegistrationOut,
    ScheduleItemInput,
    ScheduleItemOut,
    UserOut,
)
from backend.serializers import event_card
from backend.routes.events import slugify
from backend.services import event_creation

router = APIRouter(tags=["dashboards"])


def registration_out(registration: Registration, user: User | None = None) -> RegistrationOut:
    event = registration.event
    u = user or (registration.user if hasattr(registration, "user") else None)
    ticket_code = f"100T-{event.id:04d}-{registration.id:05d}" if event else f"100T-0000-{registration.id:05d}"
    qr_data = f"100TIMES:PASS:EVENT={event.slug if event else 'event'}:REG={ticket_code}:USER={u.email if u else ''}:TIER={registration.ticket_type}"
    venue_name = event.venue.name if event and event.venue else "Convention Center"
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
        eventStartTime=event.start_time if event and event.start_time else "09:00",
    )


@router.get("/home")
def home(db: Session = Depends(get_db)) -> dict:
    user_id = None
    featured = db.scalars(
        select(Event).options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.status == "published").order_by(Event.start_date).limit(4)
    ).all()
    categories = db.scalars(select(Category).order_by(Category.name).limit(6)).all()
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
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Dashboard:
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
def saved_events(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[EventCard]:
    rows = db.scalars(
        select(Event).join(SavedEvent, SavedEvent.event_id == Event.id)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(SavedEvent.user_id == user.id)
    ).all()
    return [event_card(db, item, user.id) for item in rows]


@router.get("/dashboard/registrations", response_model=list[RegistrationOut])
def registrations(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[RegistrationOut]:
    rows = db.scalars(
        select(Registration)
        .options(selectinload(Registration.event).selectinload(Event.venue).selectinload(Venue.city))
        .where(Registration.user_id == user.id)
        .order_by(desc(Registration.registered_at))
    ).all()
    return [registration_out(item, user) for item in rows]


@router.get("/dashboard/schedule", response_model=list[ScheduleItemOut])
def list_schedule(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[ScheduleItemOut]:
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
def add_schedule_item(payload: ScheduleItemInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ScheduleItemOut:
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
def delete_schedule_item(schedule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.get(ScheduleItem, schedule_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    db.delete(item)
    db.commit()
    return None


@router.patch("/dashboard/profile", response_model=UserOut)
def update_profile(payload: ProfileUpdateInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> UserOut:
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.job_title is not None:
        user.job_title = payload.job_title.strip() or None
    if payload.company is not None:
        user.company = payload.company.strip() or None
    if payload.bio is not None:
        user.bio = payload.bio.strip() or None
    if payload.country is not None:
        user.country = payload.country.strip() or None
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/dashboard/notifications", response_model=list[NotificationOut])
def notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[NotificationOut]:
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(desc(Notification.created_at))).all()
    return [NotificationOut.model_validate(item) for item in rows]


@router.get("/organizer", response_model=OrganizerDashboard)
def organizer_dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> OrganizerDashboard:
    events = db.scalars(select(Event).options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city)).where(Event.organizer_id == user.id).order_by(desc(Event.created_at)).limit(5)).all()
    event_ids = select(Event.id).where(Event.organizer_id == user.id)
    registrations = int(db.scalar(select(func.count(Registration.id)).where(Registration.event_id.in_(event_ids))) or 0)
    total = int(db.scalar(select(func.count(Event.id)).where(Event.organizer_id == user.id)) or 0)
    published = int(db.scalar(select(func.count(Event.id)).where(Event.organizer_id == user.id, Event.status == "published")) or 0)
    return OrganizerDashboard(totalEvents=total, publishedEvents=published, registrations=registrations, views=registrations * 19, conversionRate=round(registrations / max(total * 100, 1) * 100, 1), recentEvents=[event_card(db, item, user.id) for item in events])


@router.get("/organizer/events", response_model=list[EventCard])
def organizer_events(db: Session = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> list[EventCard]:
    rows = db.scalars(select(Event).options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city)).where(Event.organizer_id == user.id).order_by(desc(Event.created_at))).all()
    return [event_card(db, item, user.id) for item in rows]


@router.post("/organizer/events", response_model=EventCard, status_code=status.HTTP_201_CREATED)
def create_organizer_event(payload: EventInput, db: Session = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> EventCard:
    organizer = db.scalar(select(Organizer).where(Organizer.id == user.id))
    if not organizer:
        organizer = Organizer(id=user.id, name=user.name, slug=slugify(user.name), description="100 TIMES community organizer", logo=user.name[:2].upper())
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
    )
    db.commit()
    db.refresh(event)
    return event_card(db, event, user.id)


@router.get("/organizer/analytics", response_model=Analytics)
def organizer_analytics(db: Session = Depends(get_db), user: User = Depends(require_roles("ORGANIZER", "ADMIN"))) -> Analytics:
    count = int(db.scalar(select(func.count(Registration.id)).join(Event).where(Event.organizer_id == user.id)) or 0)
    return Analytics(views=[count * 7, count * 10, count * 12, count * 15], registrations=[max(1, count // 4)] * 4, conversion=[3.4, 4.1, 4.8, 5.2], ticketDistribution={"Free": count // 5, "Standard": count, "Premium": count // 3, "VIP": count // 8})


@router.get("/admin", response_model=AdminDashboard)
def admin_dashboard(db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN"))) -> AdminDashboard:
    def total(model) -> int:
        return int(db.scalar(select(func.count(model.id))) or 0)

    categories = db.scalars(select(Category).order_by(Category.name).limit(5)).all()
    return AdminDashboard(users=total(User), events=total(Event), organizers=total(Organizer), registrations=total(Registration), reviews=total(Review), userGrowth=[total(User)] * 7, eventGrowth=[total(Event)] * 7, popularCategories=[item.name for item in categories])
