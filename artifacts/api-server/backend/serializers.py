from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Category, City, Event, Organizer, Registration, Review, SavedEvent, Venue
from backend.schemas import CategoryOut, CityOut, EventCard, EventDetail, OrganizerOut, ReviewOut, VenueOut


def event_card(db: Session, event: Event, user_id: int | None = None) -> EventCard:
    rating = db.scalar(select(func.avg(Review.rating)).where(Review.event_id == event.id))
    attendee_count = db.scalar(select(func.count(Registration.id)).where(Registration.event_id == event.id))
    saved = bool(
        user_id and db.scalar(
            select(SavedEvent.event_id).where(SavedEvent.user_id == user_id, SavedEvent.event_id == event.id)
        )
    )
    return EventCard(
        id=event.id,
        title=event.title,
        slug=event.slug,
        eventType=event.event_type,
        category=event.category.name if event.category else "Uncategorized",
        categorySlug=event.category.slug if event.category else "",
        startDate=event.start_date,
        endDate=event.end_date,
        startTime=event.start_time,
        location=event.venue.city.name if event.venue and event.venue.city else "Online",
        venue=event.venue.name if event.venue else "Online",
        organizer=event.organizer.name if event.organizer else "100 TIMES",
        image=event.image or "",
        rating=round(float(rating or 0), 1),
        attendeeCount=int(attendee_count or 0),
        price=Decimal(event.price or 0),
        format=event.format,
        isSaved=saved,
        status=event.status,
    )


def category_out(db: Session, category: Category) -> CategoryOut:
    count = db.scalar(select(func.count(Event.id)).where(Event.category_id == category.id, Event.status == "published"))
    return CategoryOut.model_validate({**category.__dict__, "event_count": int(count or 0)})


def city_out(db: Session, city: City) -> CityOut:
    count = db.scalar(
        select(func.count(Event.id))
        .join(Venue, Event.venue_id == Venue.id)
        .where(Venue.city_id == city.id, Event.status == "published")
    )
    return CityOut.model_validate({**city.__dict__, "event_count": int(count or 0), "image": city.image or ""})


def organizer_out(db: Session, organizer: Organizer) -> OrganizerOut:
    count = db.scalar(select(func.count(Event.id)).where(Event.organizer_id == organizer.id))
    rating = db.scalar(
        select(func.avg(Review.rating))
        .join(Event, Review.event_id == Event.id)
        .where(Event.organizer_id == organizer.id)
    )
    return OrganizerOut.model_validate({
        **organizer.__dict__,
        "event_count": int(count or 0),
        "rating": round(float(rating or 0), 1),
        "logo": organizer.logo or "",
    })


def venue_out(venue: Venue) -> VenueOut:
    return VenueOut.model_validate({
        **venue.__dict__,
        "city": venue.city.name if venue.city else "Online",
        "capacity": venue.capacity or 0,
        "image": venue.image or "",
    })


def review_out(review: Review) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        author=review.user.name if review.user else "100 TIMES attendee",
        rating=review.rating,
        title=review.title,
        comment=review.comment,
        createdAt=review.created_at,
    )