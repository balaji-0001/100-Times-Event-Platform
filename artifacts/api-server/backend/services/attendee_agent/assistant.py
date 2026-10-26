"""Attendee chat assistant — answers questions like "Find 10 AI conferences
in India" from the real, verified catalog.

Flow: parse the question into filters (`query_parser`, rules + optional AI
for parsing only) -> apply every filter strictly to `catalog.load_catalog`
-> rank (by the attendee's match % when they asked for "my profile",
otherwise soonest first) -> return exactly the number requested, or fewer
with an honest note when the catalog doesn't have that many. When nothing
fits, it says which single filter is the bottleneck instead of quietly
loosening the request. Every question is logged as an `AttendeeIntent`
(source_platform="assistant") for the admin view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Attendee, AttendeeIntent, AttendeePreference, User
from backend.services.attendee_agent import tracking
from backend.services.attendee_agent.catalog import CatalogEvent, load_catalog
from backend.services.attendee_agent.matching import Preferences, event_type_matches, score_event, text_mentions
from backend.services.attendee_agent.query_parser import ParsedQuery, parse_query
from backend.services.attendee_agent.serialize import event_out
from backend.services.social_agent import ai_client as ai_client_module

EXAMPLE_QUESTIONS = [
    "Find 10 AI conferences in India",
    "Show free technology events worldwide next month",
    "Find healthcare exhibitions in the USA",
    "Recommend events matching my profile",
    "Find online workshops this weekend",
]


@dataclass
class _Filter:
    key: str
    label: str
    test: Callable[[CatalogEvent], bool]


def _same(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.strip().lower() == b.strip().lower())


def build_filters(parsed: ParsedQuery, message: str) -> list[_Filter]:
    filters: list[_Filter] = []
    lowered = message.lower()
    if parsed.topics:
        topics = list(parsed.topics)
        filters.append(_Filter("topics", "about " + " / ".join(t.upper() if len(t) <= 3 else t for t in topics),
                               lambda e: any(text_mentions(e.search_text, t) for t in topics)))
    # A sector the categorizer merely inferred from a topic word ("ai" -> Technology)
    # is not applied on top of the topic itself; a sector the user named is.
    sectors = [s for s in parsed.sectors if not parsed.topics or s.lower() in lowered]
    if sectors:
        filters.append(_Filter("sectors", "in " + " / ".join(sectors), lambda e: any(_same(e.sector, s) for s in sectors)))
    if parsed.event_types:
        types = list(parsed.event_types)
        filters.append(_Filter("event_types", " / ".join(types),
                               lambda e: any(event_type_matches(e.event_type, t, e.title.lower()) for t in types)))
    if parsed.cities:
        cities = list(parsed.cities)
        filters.append(_Filter("cities", "in " + " / ".join(cities),
                               lambda e: bool(e.city) and any(c.lower() in e.city.lower() for c in cities)))
    if parsed.countries and not parsed.cities:
        countries = list(parsed.countries)
        filters.append(_Filter("countries", "in " + " / ".join(countries), lambda e: any(_same(e.country, c) for c in countries)))
    if parsed.mode:
        mode = parsed.mode
        filters.append(_Filter("mode", mode, lambda e: e.attendance_mode == mode or e.attendance_mode == "hybrid"))
    if parsed.free_only:
        filters.append(_Filter("free", "free", lambda e: e.is_free is True))
    elif parsed.max_price is not None:
        cap, cur = parsed.max_price, parsed.currency

        def within(e: CatalogEvent) -> bool:
            if e.is_free is True:
                return True
            if e.price_min is None:
                return False
            if cur and e.currency and not _same(cur, e.currency):
                return False
            return e.price_min <= cap

        filters.append(_Filter("price", f"under {cur + ' ' if cur else ''}{cap:,.0f}", within))
    if parsed.date_from or parsed.date_to:
        start, end = parsed.date_from, parsed.date_to
        filters.append(_Filter("dates", parsed.date_label or "in your dates",
                               lambda e: (start is None or (e.end_date or e.start_date) >= start) and (end is None or e.start_date <= end)))
    return filters


def _apply(catalog: list[CatalogEvent], filters: list[_Filter]) -> list[CatalogEvent]:
    return [e for e in catalog if all(f.test(e) for f in filters)]


def _describe(parsed: ParsedQuery, filters: list[_Filter]) -> str:
    by_key = {f.key: f.label for f in filters}
    noun = by_key.get("event_types") or "events"
    noun = noun if noun.endswith("s") or noun == "events" else noun + "s"
    parts = []
    if "free" in by_key:
        parts.append("free")
    if "mode" in by_key:
        parts.append(by_key["mode"])
    subject = " ".join(parts + [noun])
    tail = [by_key[k] for k in ("topics", "sectors", "cities", "countries", "price", "dates") if k in by_key]
    if parsed.worldwide and "countries" not in by_key and "cities" not in by_key:
        tail.append("worldwide")
    return " ".join([subject] + tail)


def _log_intent(db: Session, user: User, message: str, parsed: ParsedQuery, returned: int) -> None:
    attendee = db.scalar(select(Attendee).where(Attendee.user_id == user.id))
    if attendee is None:
        attendee = Attendee(user_id=user.id, name=user.name, email=user.email, platform="100times", interests=[])
        db.add(attendee)
        db.flush()
    db.add(
        AttendeeIntent(
            attendee_id=attendee.id,
            source_platform="assistant",
            author_handle=user.email,
            raw_text=message[:2000],
            location=", ".join(parsed.cities or parsed.countries) or ("Worldwide" if parsed.worldwide else None),
            event_category=", ".join(parsed.sectors) or None,
            event_type=", ".join(parsed.event_types) or None,
            date_preference=parsed.date_label,
            price_preference="free" if parsed.free_only else (f"under {parsed.max_price}" if parsed.max_price is not None else "any"),
            format_preference=parsed.mode or "any",
            keywords=parsed.topics,
            inferred_interests=parsed.sectors,
            confidence=1,
            status="ANSWERED" if returned else "NO_RESULTS",
        )
    )
    db.flush()


def answer(db: Session, user: User, message: str, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    catalog = load_catalog(db, today)
    known_cities = {e.city for e in catalog if e.city}
    parsed = parse_query(message, today, known_cities, ai_client=ai_client_module.get_ai_client())
    filters = build_filters(parsed, message)
    matches = _apply(catalog, filters)

    prefs = Preferences.from_model(db.get(AttendeePreference, user.id))
    notes: list[str] = []
    scored: list[tuple[CatalogEvent, Any]] = [(e, score_event(e, prefs) if not prefs.is_empty() else None) for e in matches]
    if parsed.use_profile:
        if prefs.is_empty():
            notes.append("You haven't set any preferences yet, so these are sorted by date rather than by match. Set them under Preferences.")
        else:
            scored.sort(key=lambda pair: (-(pair[1].percent if pair[1] else -1), pair[0].start_date))
    total = len(scored)
    picked = scored[: parsed.count]

    description = _describe(parsed, filters)
    if not filters and not parsed.use_profile:
        notes.append("I couldn't pick out a topic, place, date or type from that, so these are the soonest verified events.")
    if total == 0:
        reply = f"I found no verified upcoming {description}."
        alternatives = []
        for f in filters:
            without = len(_apply(catalog, [g for g in filters if g is not f]))
            if without:
                alternatives.append((without, f))
        if alternatives:
            without, f = max(alternatives, key=lambda pair: pair[0])
            reply += f" Dropping \"{f.label}\" would give {without} result{'s' if without != 1 else ''}."
    elif parsed.count_requested and total < parsed.count:
        reply = (
            f"You asked for {parsed.count}, but only {total} verified upcoming {description} "
            f"{'is' if total == 1 else 'are'} in the catalog — here {'it is' if total == 1 else 'they all are'}."
        )
    elif parsed.use_profile and not prefs.is_empty():
        scope = f"{description} " if filters else ""
        reply = (
            f"Here are your {len(picked)} best-matching verified upcoming {scope or 'events '}"
            f"ranked by match with your preferences (out of {total}{' that fit' if filters else ' in the catalog'})."
        )
    else:
        reply = f"Here {'is' if len(picked) == 1 else 'are'} {len(picked)} verified upcoming {description}"
        reply += f" (of {total} that fit)." if total > len(picked) else "."

    states = tracking.states_for(db, user.id, [(e.kind, e.id) for e, _ in picked])
    _log_intent(db, user, message, parsed, len(picked))
    return {
        "reply": reply,
        "notes": notes,
        "filters": parsed.as_dict(),
        "appliedFilters": [f.label for f in filters],
        "requestedCount": parsed.count,
        "totalMatching": total,
        "results": [event_out(e, match=m, state=states.get((e.kind, e.id))) for e, m in picked],
        "examples": EXAMPLE_QUESTIONS,
        "catalogSize": len(catalog),
    }
