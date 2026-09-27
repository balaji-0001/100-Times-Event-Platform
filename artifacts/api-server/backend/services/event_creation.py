"""Shared Event-creation logic.

Used by both the organizer dashboard (`routes/dashboard.py::create_organizer_
event`, a human authoring their own event) and the acquisition Case-B
approval flow (`routes/acquisition.py`, a human approving a new-event
candidate the Demand Capture pipeline discovered) — one place resolves
category/venue/slug so the two paths can never drift apart.
"""

from datetime import date as date_cls
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Category, City, Event, Organizer, Venue
from backend.routes.events import slugify

DEFAULT_EVENT_IMAGE = "https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?auto=format&fit=crop&w=1200&q=82"


def resolve_category(db: Session, category_name: str) -> Category:
    name = (category_name or "General").strip() or "General"
    category = db.scalar(select(Category).where((Category.slug == slugify(name)) | (Category.name.ilike(name))))
    if not category:
        category = Category(name=name.title(), slug=slugify(name), description=f"Events about {name}.", icon="sparkles")
        db.add(category)
        db.flush()
    return category


def resolve_venue(db: Session, location: str | None) -> Venue | None:
    city_name = (location or "").strip() or "Bengaluru"
    city = db.scalar(select(City).where(City.name.ilike(f"%{city_name}%")))
    if not city:
        city = db.scalar(select(City).limit(1))
    venue = db.scalar(select(Venue).where(Venue.city_id == city.id)) if city else None
    if not venue:
        venue = db.scalar(select(Venue).limit(1))
    return venue


def unique_slug(db: Session, title: str) -> str:
    base_slug = slugify(title) or "new-event"
    slug = base_slug
    counter = 1
    while db.scalar(select(Event.id).where(Event.slug == slug)):
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def get_or_create_acquisition_organizer(db: Session) -> Organizer:
    """The system organizer profile events auto-created from an approved
    acquisition opportunity are attributed to (distinct from any human
    organizer account) — get-or-create, same pattern as the Instagram
    content-calendar community in `social_agent/orchestrator.py`."""
    organizer = db.scalar(select(Organizer).where(Organizer.slug == "100times-acquisition-agent"))
    if organizer:
        return organizer
    organizer = Organizer(
        name="100 TIMES Acquisition Agent",
        slug="100times-acquisition-agent",
        description="System organizer for events discovered and human-approved via the Demand Capture acquisition pipeline.",
        logo="AI",
    )
    db.add(organizer)
    db.flush()
    return organizer


def create_event(
    db: Session,
    *,
    title: str,
    description: str,
    event_type: str,
    category_name: str,
    location: str | None,
    start_date: date_cls,
    organizer: Organizer,
    end_date: date_cls | None = None,
    start_time: str = "18:00",
    price: Decimal = Decimal("0.00"),
    format: str = "in-person",
    status: str = "published",
    image: str = DEFAULT_EVENT_IMAGE,
) -> Event:
    category = resolve_category(db, category_name)
    venue = resolve_venue(db, location)
    slug = unique_slug(db, title)

    event = Event(
        title=title,
        slug=slug,
        description=description,
        event_type=event_type or "Event",
        start_date=start_date,
        end_date=end_date or start_date,
        start_time=start_time,
        price=price,
        status=status,
        format=format,
        category_id=category.id,
        organizer_id=organizer.id,
        venue_id=venue.id if venue else None,
        image=image,
    )
    db.add(event)
    db.flush()
    return event
