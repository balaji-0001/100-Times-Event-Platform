from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.dependencies import optional_current_user
from backend.models import Category, City, Event, Organizer, Review, Speaker, Venue, User
from backend.schemas import (
    CategoryOut,
    CityOut,
    DirectoryDetail,
    OrganizerDetail,
    OrganizerOut,
    SpeakerDetail,
    SpeakerOut,
    VenueDetail,
    VenueOut,
)
from backend.serializers import category_out, city_out, event_card, organizer_out, review_out, venue_out

router = APIRouter(tags=["directories"])


def directory_events(db: Session, where, user_id: int | None) -> list:
    rows = db.scalars(
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(where, Event.status == "published")
        .order_by(Event.start_date)
        .limit(6)
    ).all()
    return [event_card(db, row, user_id) for row in rows]


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryOut]:
    return [category_out(db, item) for item in db.scalars(select(Category).order_by(Category.name)).all()]


@router.get("/categories/{slug}", response_model=DirectoryDetail)
def get_category(slug: str, db: Session = Depends(get_db), user: User | None = Depends(optional_current_user)) -> DirectoryDetail:
    category = db.scalar(select(Category).where(Category.slug == slug))
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    related = db.scalars(select(Category).where(Category.id != category.id).order_by(Category.name).limit(3)).all()
    return DirectoryDetail(name=category.name, slug=category.slug, description=category.description, events=directory_events(db, Event.category_id == category.id, user.id if user else None), related=[item.name for item in related])


@router.get("/cities", response_model=list[CityOut])
def list_cities(db: Session = Depends(get_db)) -> list[CityOut]:
    return [city_out(db, item) for item in db.scalars(select(City).order_by(City.name)).all()]


@router.get("/cities/{slug}", response_model=DirectoryDetail)
def get_city(slug: str, db: Session = Depends(get_db), user: User | None = Depends(optional_current_user)) -> DirectoryDetail:
    city = db.scalar(select(City).where(City.slug == slug))
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    related = db.scalars(select(City).where(City.id != city.id).order_by(City.name).limit(3)).all()
    return DirectoryDetail(
        name=city.name,
        slug=city.slug,
        description=city.description or f"A growing hub for ambitious people and the ideas that bring them together. Explore the strongest rooms in {city.name}.",
        events=directory_events(db, Event.venue.has(Venue.city_id == city.id), user.id if user else None),
        related=[item.name for item in related],
    )


@router.get("/organizers", response_model=list[OrganizerOut])
def list_organizers(db: Session = Depends(get_db)) -> list[OrganizerOut]:
    return [organizer_out(db, item) for item in db.scalars(select(Organizer).order_by(Organizer.name)).all()]


@router.get("/organizers/{slug}", response_model=OrganizerDetail)
def get_organizer(slug: str, db: Session = Depends(get_db), user: User | None = Depends(optional_current_user)) -> OrganizerDetail:
    organizer = db.scalar(select(Organizer).where(Organizer.slug == slug))
    if not organizer:
        raise HTTPException(status_code=404, detail="Organizer not found")
    events = directory_events(db, Event.organizer_id == organizer.id, user.id if user else None)
    reviews = db.scalars(
        select(Review).join(Event).options(selectinload(Review.user)).where(Event.organizer_id == organizer.id).order_by(Review.created_at.desc()).limit(10)
    ).all()
    return OrganizerDetail(organizer=organizer_out(db, organizer), events=events, reviews=[review_out(item) for item in reviews])


@router.get("/venues", response_model=list[VenueOut])
def list_venues(db: Session = Depends(get_db)) -> list[VenueOut]:
    return [venue_out(item) for item in db.scalars(select(Venue).options(selectinload(Venue.city)).order_by(Venue.name)).all()]


@router.get("/venues/{slug}", response_model=VenueDetail)
def get_venue(slug: str, db: Session = Depends(get_db), user: User | None = Depends(optional_current_user)) -> VenueDetail:
    venue = db.scalar(select(Venue).options(selectinload(Venue.city)).where(Venue.slug == slug))
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return VenueDetail(
        venue=venue_out(venue),
        description=venue.description or "A versatile destination built for ideas, introductions, and large-format gatherings.",
        facilities=["Fast Wi-Fi", "Accessible entrances", "Catering", "Live production"],
        events=directory_events(db, Event.venue_id == venue.id, user.id if user else None),
    )


@router.get("/speakers/{slug}", response_model=SpeakerDetail)
def get_speaker(slug: str, db: Session = Depends(get_db), user: User | None = Depends(optional_current_user)) -> SpeakerDetail:
    speaker = db.scalar(select(Speaker).where(Speaker.slug == slug))
    if not speaker:
        raise HTTPException(status_code=404, detail="Speaker not found")
    rows = db.scalars(
        select(Event).options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.status == "published").order_by(Event.start_date).limit(6)
    ).all()
    return SpeakerDetail(
        speaker=SpeakerOut.model_validate(speaker),
        biography=speaker.biography or "A generous, practical voice for the people building more useful technology and more resilient organizations.",
        events=[event_card(db, item, user.id if user else None) for item in rows],
    )