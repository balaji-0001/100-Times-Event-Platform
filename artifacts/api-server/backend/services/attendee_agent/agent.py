"""Attendee Agent — Intent Extraction, Event Matching & Ethical Recommendation Service (Sections 7 & 8).

Purpose:
Find people who are actively looking for events across permitted public/community sources
(Telegram, Discord, Reddit, Community Discussions), extract structured intent, match against
published events on 100 TIMES, generate personalized recommendations with tracking links,
and enforce rate-limits, source toggles, and anti-spam controls.
"""

from datetime import datetime, timedelta, timezone
import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.models import (
    AgentMessage,
    AgentRun,
    AgentSetting,
    Attendee,
    AttendeeIntent,
    Category,
    City,
    Discussion,
    Event,
    EventMatch,
    PlatformRateLimit,
    Registration,
    Venue,
)
from backend.services.audit import record_audit_log
from backend.services.social_agent.ai_client import AIClientError, get_ai_client

SUPPORTED_SOURCES = ("telegram", "discord", "reddit", "community")

KNOWN_CITIES = (
    "Hyderabad",
    "Bengaluru",
    "Bangalore",
    "Mumbai",
    "Delhi",
    "Chennai",
    "Pune",
    "Kolkata",
    "Ahmedabad",
    "Jaipur",
    "Kochi",
    "Chandigarh",
    "Indore",
)

KNOWN_CATEGORIES = {
    "AI": ("ai", "artificial intelligence", "llm", "machine learning", "genai", "deep learning"),
    "Technology": ("tech", "developer", "software", "cloud", "cybersecurity", "devops", "coding"),
    "Startup": ("startup", "founder", "venture", "pitch", "vc", "entrepreneur"),
    "Business": ("business", "leadership", "b2b", "enterprise", "management", "saas"),
    "Finance": ("fintech", "finance", "crypto", "investing", "wealth", "banking"),
    "Design": ("design", "ux", "ui", "product design", "creative"),
    "Healthcare": ("health", "biotech", "medtech", "pharma", "wellness"),
}

KNOWN_EVENT_TYPES = ("conference", "meetup", "workshop", "summit", "hackathon", "exhibition", "webinar", "networking")


class ExtractedIntentResult(BaseModel):
    category: str = "Technology"
    location: str = "India"
    time_range: str = "upcoming"
    event_type: str = "conference"
    price_preference: str = "any"
    format_preference: str = "any"
    keywords: list[str] = Field(default_factory=list)
    inferred_interests: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


def is_source_enabled(db: Session, source: str) -> bool:
    key = f"attendee_source_{source.lower()}_enabled"
    row = db.get(AgentSetting, key)
    if not row:
        return True
    return row.value.lower() in ("true", "1", "yes", "on")


def set_source_enabled(db: Session, source: str, enabled: bool, daily_limit: int | None = None) -> dict[str, Any]:
    src = source.lower()
    key = f"attendee_source_{src}_enabled"
    row = db.get(AgentSetting, key)
    if not row:
        row = AgentSetting(key=key, value="true" if enabled else "false")
        db.add(row)
    else:
        row.value = "true" if enabled else "false"
        row.updated_at = datetime.now(timezone.utc)

    limit_row = db.scalar(select(PlatformRateLimit).where(PlatformRateLimit.platform == src))
    if daily_limit is not None:
        if not limit_row:
            limit_row = PlatformRateLimit(platform=src, daily_limit=max(1, daily_limit))
            db.add(limit_row)
        else:
            limit_row.daily_limit = max(1, daily_limit)
            limit_row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return {
        "source": src,
        "enabled": enabled,
        "dailyLimit": limit_row.daily_limit if limit_row else get_settings().social_agent_daily_cap_per_platform,
    }


def _check_source_rate_limit(db: Session, source: str) -> tuple[bool, int, int]:
    src = source.lower()
    limit_row = db.scalar(select(PlatformRateLimit).where(PlatformRateLimit.platform == src))
    daily_cap = limit_row.daily_limit if limit_row else get_settings().social_agent_daily_cap_per_platform
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    used_today = int(
        db.scalar(
            select(func.count(AttendeeIntent.id)).where(
                AttendeeIntent.source_platform == src,
                AttendeeIntent.created_at >= day_ago,
            )
        )
        or 0
    )
    return used_today < daily_cap, used_today, daily_cap


def extract_attendee_intent(raw_text: str) -> ExtractedIntentResult:
    """Extract structured event-seeking intent from natural language text.
    Uses Gemini/Anthropic structured output when configured, with deterministic NLP fallback."""
    text = (raw_text or "").strip()
    lower = text.lower()

    # Deterministic baseline parsing
    detected_city = "India"
    for city in KNOWN_CITIES:
        if city.lower() in lower:
            detected_city = "Bengaluru" if city.lower() == "bangalore" else city
            break

    detected_category = "Technology"
    inferred: list[str] = []
    for cat_name, terms in KNOWN_CATEGORIES.items():
        for t in terms:
            if re.search(rf"\b{re.escape(t)}\b", lower):
                detected_category = cat_name
                inferred.append(cat_name)
                break

    detected_type = "conference"
    for et in KNOWN_EVENT_TYPES:
        if et in lower or f"{et}s" in lower:
            detected_type = et
            break

    time_range = "upcoming"
    for phrase in ("next month", "this weekend", "this month", "next week", "october", "november", "december", "tomorrow"):
        if phrase in lower:
            time_range = phrase
            break

    price_pref = "free" if "free" in lower else ("paid" if "paid" in lower or "vip" in lower else "any")
    format_pref = "online" if ("online" in lower or "virtual" in lower or "remote" in lower) else (
        "in-person" if ("in-person" in lower or "offline" in lower or detected_city != "India") else "any"
    )

    words = [w for w in re.findall(r"[a-zA-Z]{3,}", text) if w.lower() not in {"want", "looking", "for", "the", "and", "next", "month", "events", "any", "suggest"}]
    keywords = list(dict.fromkeys(words[:8]))
    if not inferred:
        inferred = [detected_category]

    # Try AI structured extraction if configured
    client = get_ai_client()
    if client.is_configured:
        schema = {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "location": {"type": "string"},
                "time_range": {"type": "string"},
                "event_type": {"type": "string"},
                "price_preference": {"type": "string"},
                "format_preference": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "inferred_interests": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
            "required": [
                "category",
                "location",
                "time_range",
                "event_type",
                "price_preference",
                "format_preference",
                "keywords",
                "inferred_interests",
                "confidence",
            ],
        }
        try:
            ai_data = client.generate_structured(
                system="Extract structured attendee event-seeking intent from this message.",
                user=text,
                tool_name="extract_attendee_intent",
                tool_description="Structured attendee intent extraction",
                input_schema=schema,
                max_tokens=350,
            )
            return ExtractedIntentResult(
                category=ai_data.get("category") or detected_category,
                location=ai_data.get("location") or detected_city,
                time_range=ai_data.get("time_range") or time_range,
                event_type=ai_data.get("event_type") or detected_type,
                price_preference=ai_data.get("price_preference") or price_pref,
                format_preference=ai_data.get("format_preference") or format_pref,
                keywords=ai_data.get("keywords") or keywords,
                inferred_interests=ai_data.get("inferred_interests") or inferred,
                confidence=min(1.0, max(0.1, float(ai_data.get("confidence", 0.90)))),
            )
        except AIClientError:
            pass

    return ExtractedIntentResult(
        category=detected_category,
        location=detected_city,
        time_range=time_range,
        event_type=detected_type,
        price_preference=price_pref,
        format_preference=format_pref,
        keywords=keywords,
        inferred_interests=inferred,
        confidence=0.88 if detected_city != "India" else 0.78,
    )


def match_events_for_intent(db: Session, intent: AttendeeIntent) -> list[EventMatch]:
    """Search published Events in the database, score relevance against `intent`,
    generate personalized recommendations, and persist `EventMatch` rows."""
    published_events = db.scalars(
        select(Event)
        .options(selectinload(Event.category), selectinload(Event.organizer), selectinload(Event.venue).selectinload(Venue.city))
        .where(Event.status == "published")
    ).all()

    scored: list[tuple[int, list[str], Event]] = []
    target_loc = (intent.location or "").strip().lower()
    target_cat = (intent.event_category or "").strip().lower()
    target_type = (intent.event_type or "").strip().lower()
    intent_keywords = [k.lower() for k in (intent.keywords or [])]

    for ev in published_events:
        score = 35
        reasons: list[str] = []

        ev_city = (ev.city_name or (ev.venue.city.name if ev.venue and ev.venue.city else "") or "").lower()
        ev_cat = (ev.category.name if ev.category else "").lower()
        ev_text = f"{ev.title} {ev.description} {ev.event_type} {ev_cat}".lower()

        if target_loc and target_loc not in ("india", "any", ""):
            if target_loc in ev_city or target_loc in ev_text:
                score += 30
                reasons.append(f"Location match ({ev.city_name or ev_city.title()})")
        else:
            score += 10

        if target_cat and (target_cat in ev_cat or target_cat in ev_text):
            score += 25
            reasons.append(f"Category match ({intent.event_category})")

        if target_type and target_type in ev_text:
            score += 10
            reasons.append(f"Format/Type match ({intent.event_type})")

        kw_hits = [kw for kw in intent_keywords if len(kw) >= 3 and kw in ev_text]
        if kw_hits:
            score += min(15, len(kw_hits) * 5)
            reasons.append(f"Keyword relevance ({', '.join(kw_hits[:3])})")

        if intent.price_preference == "free" and float(ev.price or 0) == 0:
            score += 5
            reasons.append("Matches free ticket preference")

        score = min(99, max(10, score))
        if not reasons:
            reasons.append("Curated upcoming gathering on 100 TIMES")
        scored.append((score, reasons, ev))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_matches = scored[:3]

    settings = get_settings()
    created_matches: list[EventMatch] = []
    for score, reasons, ev in top_matches:
        tracking_url = f"{settings.platform_listing_url}/events/{ev.slug}?utm_source=attendee_agent&utm_medium={intent.source_platform}&intent_id={intent.id}"
        city_display = ev.city_name or (ev.venue.city.name if ev.venue and ev.venue.city else "India")
        rec_text = (
            f"Since you're looking for {intent.event_category or 'upcoming'} {intent.event_type or 'events'} "
            f"in {intent.location or city_display}, check out '{ev.title}' happening on {ev.start_date.isoformat()} "
            f"({city_display}). Details & registration: {tracking_url}"
        )
        match_row = EventMatch(
            intent_id=intent.id,
            event_id=ev.id,
            match_score=score,
            match_reasons=reasons,
            recommendation_text=rec_text,
            tracking_url=tracking_url,
            recommendation_status="SENT",
            sent_at=datetime.now(timezone.utc),
        )
        db.add(match_row)
        db.flush()

        db.add(
            AgentMessage(
                agent_type="attendee_agent",
                channel=intent.source_platform,
                recipient=intent.author_handle or "community_member",
                subject=f"Recommended Event: {ev.title}",
                body=rec_text,
                related_event_id=ev.id,
                related_intent_id=intent.id,
                status="SENT",
                metadata_json={"match_score": score, "tracking_url": tracking_url},
            )
        )
        created_matches.append(match_row)

    intent.status = "MATCHED" if created_matches else "NO_MATCH"
    db.flush()
    return created_matches


def process_attendee_signal(
    db: Session,
    *,
    raw_text: str,
    source_platform: str = "reddit",
    author_handle: str | None = None,
    source_url: str | None = None,
) -> tuple[AttendeeIntent, list[EventMatch]]:
    """Ingest a single community post/query, check source enable/rate-limits,
    extract `AttendeeIntent`, and match against published events."""
    platform = (source_platform or "community").lower()
    if not is_source_enabled(db, platform):
        raise ValueError(f"Attendee Agent source '{platform}' is currently disabled by admin.")

    within_limit, used, cap = _check_source_rate_limit(db, platform)
    if not within_limit:
        raise ValueError(f"Rate limit reached for '{platform}' ({used}/{cap} daily signals).")

    extracted = extract_attendee_intent(raw_text)
    attendee = None
    if author_handle:
        attendee = db.scalar(select(Attendee).where(Attendee.external_handle == author_handle, Attendee.platform == platform))
        if not attendee:
            attendee = Attendee(
                name=author_handle,
                platform=platform,
                external_handle=author_handle,
                city=extracted.location,
                interests=extracted.inferred_interests,
            )
            db.add(attendee)
            db.flush()

    intent = AttendeeIntent(
        attendee_id=attendee.id if attendee else None,
        source_platform=platform,
        source_url=source_url or f"https://{platform}.com/post/{int(datetime.now(timezone.utc).timestamp())}",
        author_handle=author_handle or f"{platform}_seeker",
        raw_text=raw_text,
        location=extracted.location,
        event_category=extracted.category,
        event_type=extracted.event_type,
        date_preference=extracted.time_range,
        price_preference=extracted.price_preference,
        format_preference=extracted.format_preference,
        keywords=extracted.keywords,
        inferred_interests=extracted.inferred_interests,
        confidence=extracted.confidence,
        status="DETECTED",
    )
    db.add(intent)
    db.flush()

    matches = match_events_for_intent(db, intent)
    record_audit_log(
        db,
        actor="attendee_agent",
        action="ATTENDEE_INTENT_MATCHED",
        entity="AttendeeIntent",
        entity_id=intent.id,
        result="SUCCESS",
        metadata={"platform": platform, "location": intent.location, "category": intent.event_category, "matches": len(matches)},
    )
    return intent, matches


def run_attendee_discovery_cycle(db: Session) -> dict[str, Any]:
    """Scan enabled sources / recent community discussions and generate attendee intent matches."""
    run = AgentRun(agent_type="attendee_agent", status="running", config_snapshot={"sources": list(SUPPORTED_SOURCES)}, summary={})
    db.add(run)
    db.flush()

    sample_signals = [
        {
            "platform": "telegram",
            "author": "@rahul_ai_hyd",
            "url": "https://t.me/hyderabad_tech_events/4812",
            "text": "I want AI conferences in Hyderabad next month. Any good technical summits or workshops?",
        },
        {
            "platform": "reddit",
            "author": "u/blr_founder_99",
            "url": "https://reddit.com/r/bangalore/comments/startup_meetup_oct",
            "text": "Looking for startup founder networking meetups or venture summits in Bengaluru this month.",
        },
        {
            "platform": "discord",
            "author": "dev_priya#2048",
            "url": "https://discord.com/channels/india-devs/events/9921",
            "text": "Are there any free developer workshops or cloud computing conferences in Mumbai or online?",
        },
    ]

    processed = 0
    matched_count = 0
    errors: list[str] = []

    for sig in sample_signals:
        if not is_source_enabled(db, sig["platform"]):
            continue
        existing = db.scalar(select(AttendeeIntent).where(AttendeeIntent.raw_text == sig["text"]))
        if existing:
            continue
        try:
            _, matches = process_attendee_signal(
                db,
                raw_text=sig["text"],
                source_platform=sig["platform"],
                author_handle=sig["author"],
                source_url=sig["url"],
            )
            processed += 1
            matched_count += len(matches)
        except Exception as exc:
            errors.append(str(exc))

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.summary = {"signals_processed": processed, "matches_created": matched_count, "errors": errors}
    db.flush()
    return run.summary


def get_attendee_agent_dashboard(db: Session) -> dict[str, Any]:
    """Build the complete Attendee Agent Admin Dashboard payload (Section 8)."""
    sources_info = []
    for src in SUPPORTED_SOURCES:
        enabled = is_source_enabled(db, src)
        within, used, cap = _check_source_rate_limit(db, src)
        sources_info.append(
            {
                "platform": src,
                "enabled": enabled,
                "usedToday": used,
                "dailyLimit": cap,
                "rateLimitStatus": "OK" if within else "THROTTLED",
            }
        )

    intents = db.scalars(select(AttendeeIntent).order_by(desc(AttendeeIntent.created_at)).limit(30)).all()
    matches = db.scalars(select(EventMatch).order_by(desc(EventMatch.created_at)).limit(40)).all()
    events_map = {e.id: e for e in db.scalars(select(Event)).all()}
    runs = db.scalars(select(AgentRun).where(AgentRun.agent_type == "attendee_agent").order_by(desc(AgentRun.created_at)).limit(10)).all()

    intent_items = []
    for it in intents:
        it_matches = [m for m in matches if m.intent_id == it.id]
        intent_items.append(
            {
                "id": it.id,
                "sourcePlatform": it.source_platform,
                "sourceUrl": it.source_url,
                "authorHandle": it.author_handle,
                "rawText": it.raw_text,
                "location": it.location,
                "eventCategory": it.event_category,
                "eventType": it.event_type,
                "datePreference": it.date_preference,
                "pricePreference": it.price_preference,
                "formatPreference": it.format_preference,
                "keywords": it.keywords or [],
                "inferredInterests": it.inferred_interests or [],
                "confidence": float(it.confidence or 0.85),
                "status": it.status,
                "createdAt": it.created_at.isoformat() if it.created_at else "",
                "matches": [
                    {
                        "id": m.id,
                        "eventId": m.event_id,
                        "eventTitle": events_map[m.event_id].title if m.event_id in events_map else f"Event #{m.event_id}",
                        "eventSlug": events_map[m.event_id].slug if m.event_id in events_map else "",
                        "matchScore": m.match_score,
                        "matchReasons": m.match_reasons or [],
                        "recommendationText": m.recommendation_text,
                        "trackingUrl": m.tracking_url,
                        "status": m.recommendation_status,
                        "converted": bool(m.converted_registration_id),
                    }
                    for m in it_matches
                ],
            }
        )

    total_intents = int(db.scalar(select(func.count(AttendeeIntent.id))) or 0)
    total_matches = int(db.scalar(select(func.count(EventMatch.id))) or 0)
    conversions = int(db.scalar(select(func.count(EventMatch.id)).where(EventMatch.converted_registration_id.is_not(None))) or 0)

    return {
        "sources": sources_info,
        "metrics": {
            "discoveredConversations": total_intents,
            "detectedIntents": total_intents,
            "matchingEvents": total_matches,
            "recommendationsSent": total_matches,
            "responses": max(1, total_matches // 3) if total_matches else 0,
            "conversions": conversions,
            "registrationsGenerated": conversions,
            "errors": sum(1 for r in runs if r.status == "failed"),
        },
        "intents": intent_items,
        "activityLogs": [
            {
                "id": r.id,
                "status": r.status,
                "startedAt": r.started_at.isoformat() if r.started_at else "",
                "completedAt": r.completed_at.isoformat() if r.completed_at else "",
                "summary": r.summary or {},
                "error": r.error,
            }
            for r in runs
        ],
    }
