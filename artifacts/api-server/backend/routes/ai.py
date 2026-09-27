import re
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.dependencies import get_current_user, optional_current_user
from backend.models import Category, City, Connection, Event, Registration, SavedEvent, ScheduleItem, Speaker, User, Venue
from backend.schemas import (
    AIConciergeRequest,
    AIConciergeResponse,
    AIEventBrief,
    AIEventMatch,
    AIPeerMatch,
    AttendeeProfileOut,
    EventCard,
    PersonalizedRecommendationsOut,
)
from backend.serializers import event_card

router = APIRouter(prefix="/ai", tags=["ai"])


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{3,}", text.lower()))


@router.post("/concierge", response_model=AIConciergeResponse)
def ai_concierge(
    payload: AIConciergeRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
) -> AIConciergeResponse:
    raw_query = payload.query.strip()
    query_lower = raw_query.lower()
    tokens = tokenize(query_lower)

    cities = db.scalars(select(City)).all()
    target_city = next((c for c in cities if c.name.lower() in query_lower or c.slug in query_lower), None)

    is_free = any(w in query_lower for w in ["free", "complimentary", "zero cost"])
    max_price_match = re.search(r"(?:under|below|less than|<|up to)\s*(?:rs\.?|inr|₹)?\s*(\d+)", query_lower)
    max_price = int(max_price_match.group(1)) if max_price_match else None

    is_online = "online" in query_lower or "virtual" in query_lower or "remote" in query_lower
    is_in_person = "in-person" in query_lower or "offline" in query_lower or "venue" in query_lower

    base_query = (
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.status == "published")
    )

    if target_city:
        base_query = base_query.join(Event.venue).join(Venue.city).where(City.id == target_city.id)
    if is_free:
        base_query = base_query.where(Event.price == 0)
    elif max_price is not None:
        base_query = base_query.where(Event.price <= max_price)
    if is_online:
        base_query = base_query.where(Event.format == "online")
    elif is_in_person:
        base_query = base_query.where(Event.format == "in-person")

    all_events = db.scalars(base_query).all()

    scored_matches: list[tuple[Event, int, str, list[str]]] = []
    for ev in all_events:
        score = 65
        reasons: list[str] = []
        tags: list[str] = []

        cat_name = ev.category.name if ev.category else ""
        ev_text = f"{ev.title} {ev.description or ''} {cat_name} {ev.event_type}".lower()
        ev_tokens = tokenize(ev_text)

        overlap = tokens.intersection(ev_tokens)
        if overlap:
            score += min(len(overlap) * 7, 25)
            tags.append("Keyword Match")

        if target_city and ev.venue and ev.venue.city and ev.venue.city.id == target_city.id:
            score += 8
            tags.append(f"{target_city.name} Venue")
            reasons.append(f"Located in {target_city.name}")

        if is_free and ev.price == 0:
            score += 5
            tags.append("Free Access")
            reasons.append("Complimentary admission")
        elif max_price and ev.price <= max_price:
            score += 5
            tags.append(f"Under ₹{max_price}")
            reasons.append(f"Priced within budget at ₹{int(ev.price)}")

        if user and user.job_title:
            user_tokens = tokenize(user.job_title)
            if user_tokens.intersection(ev_tokens):
                score += 10
                tags.append("Role Fit")
                reasons.append(f"Highly relevant to {user.job_title}s")

        final_score = min(score, 98)
        reason_text = " · ".join(reasons) if reasons else f"Top match for '{raw_query}'"
        scored_matches.append((ev, final_score, reason_text, tags))

    scored_matches.sort(key=lambda x: x[1], reverse=True)
    top_matches = scored_matches[:6]

    saved_event_ids = set()
    if user:
        saved_event_ids = set(db.scalars(select(SavedEvent.event_id).where(SavedEvent.user_id == user.id)).all())

    matched_cards = [
        AIEventMatch(
            event=event_card(db, ev, user.id if user else None),
            match_score=score,
            match_reason=reason,
            tags=tags[:3] or ["Curated Signal"],
        )
        for ev, score, reason, tags in top_matches
    ]

    if len(matched_cards) == 0:
        reply = f'I searched our catalog for "{raw_query}", but did not find exact matching gatherings. Here are some suggested explorations:'
        suggested = [
            "Find Intelligence & AI summits in Bengaluru",
            "Show free design & craft workshops",
            "Top technology conferences next month",
        ]
    else:
        city_note = f" in {target_city.name}" if target_city else ""
        budget_note = f" under ₹{max_price}" if max_price else (" with free admission" if is_free else "")
        plural = "s" if len(matched_cards) != 1 else ""
        reply = (
            f'I analyzed your query for "{raw_query}". Here are {len(matched_cards)} high-signal event'
            f'{plural}{city_note}{budget_note} curated for your search:'
        )
        suggested = [
            "Show upcoming AI & Machine Learning summits",
            "Find tech conferences with 1-on-1 networking",
            "What are the top design workshops in Mumbai?",
        ]

    return AIConciergeResponse(
        reply=reply,
        suggested_queries=suggested,
        matched_events=matched_cards,
    )


@router.get("/recommendations", response_model=PersonalizedRecommendationsOut)
def get_recommendations(
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
) -> PersonalizedRecommendationsOut:
    all_events = db.scalars(
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.status == "published")
    ).all()

    saved_event_ids = set()
    registered_event_ids = set()
    user_tokens = set()

    if user:
        saved_event_ids = set(db.scalars(select(SavedEvent.event_id).where(SavedEvent.user_id == user.id)).all())
        registered_event_ids = set(db.scalars(select(Registration.event_id).where(Registration.user_id == user.id)).all())
        if user.job_title:
            user_tokens.update(tokenize(user.job_title))
        if user.company:
            user_tokens.update(tokenize(user.company))
        if user.bio:
            user_tokens.update(tokenize(user.bio))

    scored: list[AIEventMatch] = []
    for ev in all_events:
        if ev.id in registered_event_ids:
            continue

        score = 72
        tags = []
        reasons = []

        cat_name = ev.category.name if ev.category else ""
        ev_text = f"{ev.title} {ev.description or ''} {cat_name}".lower()
        ev_tokens = tokenize(ev_text)

        overlap = user_tokens.intersection(ev_tokens)
        if overlap:
            score += min(len(overlap) * 8, 22)
            tags.append("High Profile Fit")
            terms = ", ".join(list(overlap)[:2])
            reasons.append(f"Aligned with your background in {terms}")

        if user and user.country and ev.venue and ev.venue.country and user.country.lower() in ev.venue.country.lower():
            score += 5
            citylabel = ev.venue.city.name if (ev.venue and ev.venue.city) else "Regional"
            tags.append(citylabel)

        if hasattr(ev, "registrations") and len(ev.registrations) > 0:
            score += 4
            tags.append("Active Community")

        final_score = min(score, 97)
        evcat_label = ev.category.name if ev.category else "event"
        reason_text = reasons[0] if reasons else f"Top rated {evcat_label} gathering"

        scored.append(
            AIEventMatch(
                event=event_card(db, ev, user.id if user else None),
                match_score=final_score,
                match_reason=reason_text,
                tags=tags[:3] or ["Recommended"],
            )
        )

    scored.sort(key=lambda x: x.match_score, reverse=True)
    items = scored[:limit]

    headline = "Recommended For Your Profile" if (user and user.job_title) else "Trending High-Signal Gatherings"
    user_company = user.company if (user and user.company) else "Community"
    user_title = user.job_title if (user and user.job_title) else "Attendee"
    context = (f"Curated for {user.name} ({user_title} at {user_company})") if user else "Curated based on active event registrations and industry trends"

    return PersonalizedRecommendationsOut(
        headline=headline,
        user_context=context,
        items=items,
    )


@router.get("/peer-matches", response_model=list[AIPeerMatch])
def get_peer_matches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AIPeerMatch]:
    other_users = db.scalars(
        select(User)
        .where(User.id != user.id)
    ).all()

    my_regs = set(db.scalars(select(Registration.event_id).where(Registration.user_id == user.id)).all())
    my_tokens = set()
    if user.job_title:
        my_tokens.update(tokenize(user.job_title))
    if user.company:
        my_tokens.update(tokenize(user.company))
    if user.bio:
        my_tokens.update(tokenize(user.bio))

    existing_conns = db.scalars(
        select(Connection).where(or_(Connection.requester_id == user.id, Connection.addressee_id == user.id))
    ).all()
    conn_map = {}
    for c in existing_conns:
        peer_id = c.addressee_id if c.requester_id == user.id else c.requester_id
        if c.status == "accepted":
            conn_map[peer_id] = ("connected", c.id)
        elif c.status == "pending":
            conn_map[peer_id] = ("pending_sent" if c.requester_id == user.id else "pending_received", c.id)

    matches: list[AIPeerMatch] = []
    for peer in other_users:
        peer_regs = set(db.scalars(select(Registration.event_id).where(Registration.user_id == peer.id)).all())
        shared_events = my_regs.intersection(peer_regs)

        peer_tokens = set()
        if peer.job_title:
            peer_tokens.update(tokenize(peer.job_title))
        if peer.company:
            peer_tokens.update(tokenize(peer.company))
        if peer.bio:
            peer_tokens.update(tokenize(peer.bio))

        skill_overlap = my_tokens.intersection(peer_tokens)

        score = 70
        mutual: list[str] = []
        if shared_events:
            score += 15
            plural = "s" if len(shared_events) != 1 else ""
            mutual.append(f"{len(shared_events)} Shared Event{plural}")
        if skill_overlap:
            score += min(len(skill_overlap) * 6, 15)
            mutual_terms = ", ".join(list(skill_overlap)[:2])
            mutual.append(f"Expertise in {mutual_terms}")
        if peer.country and user.country and peer.country.lower() == user.country.lower():
            score += 4
            mutual.append(peer.country)

        conn_status, conn_id = conn_map.get(peer.id, ("none", None))
        final_score = min(score, 96)
        reason = f"{final_score}% Match · Complementary focus in {peer.job_title or 'Tech'}" if peer.job_title else f"{final_score}% Match"

        matches.append(
            AIPeerMatch(
                attendee=AttendeeProfileOut(
                    id=peer.id,
                    name=peer.name,
                    email=peer.email,
                    role=peer.role,
                    job_title=peer.job_title,
                    company=peer.company,
                    bio=peer.bio,
                    country=peer.country,
                    registered_event_count=len(peer_regs),
                    connection_status=conn_status,
                    connection_id=conn_id,
                ),
                match_score=final_score,
                match_reason=reason,
                mutual_interests=mutual[:3] or ["Event Networking"],
            )
        )

    matches.sort(key=lambda x: x.match_score, reverse=True)
    return matches[:8]


@router.get("/events/{event_id}/brief", response_model=AIEventBrief)
def get_event_brief(
    event_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_current_user),
) -> AIEventBrief:
    event = db.scalar(
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.venue).selectinload(Venue.city), selectinload(Event.organizer))
        .where(Event.id == event_id)
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    cat_name = event.category.name if event.category else "Industry"
    city_name = event.venue.city.name if (event.venue and event.venue.city) else "Global"

    summary = (
        f"{event.title} is an executive-level {event.event_type.lower()} focusing on breakthrough advances in {cat_name}. "
        f"Brings together practitioners, engineers, and decision-makers in {city_name} for curated keynotes, "
        f"technical deep-dives, and structured 1-on-1 networking sessions."
    )

    org_name = event.organizer.name if event.organizer else "Industry Collectives"
    key_takeaways = [
        f"Implementation frameworks for {cat_name.lower()} innovations at enterprise scale.",
        f"Direct access to leading speakers and founders from {org_name}.",
        "Actionable case studies on system latency, distributed workflows, and team execution.",
        "Dedicated peer roundtables and networking circles for long-term collaboration.",
    ]

    target_audience = [
        "Engineering Leaders & Principal Architects",
        "Product Managers & Design Leads",
        "Founders, Operators & Tech Investors",
        "Domain Specialists & R&D Researchers",
    ]

    rec_role = user.job_title if (user and user.job_title) else "Product & Engineering Practitioners"

    return AIEventBrief(
        event_id=event.id,
        title=event.title,
        summary=summary,
        key_takeaways=key_takeaways,
        target_audience=target_audience,
        recommended_role=rec_role,
        highlight_session="Opening Keynote & Interactive Panel Discussion",
    )
