"""JSON shape of a catalog event for the attendee API (camelCase, like the
rest of the API). Absent facts stay null — the UI renders "Not published"."""

from __future__ import annotations

from typing import Any

from backend.services.attendee_agent.catalog import PLATFORM, CatalogEvent
from backend.services.attendee_agent.matching import MatchResult, price_text


def _location(item: CatalogEvent) -> str | None:
    if item.attendance_mode == "online" and not item.city:
        return "Online"
    parts = [p for p in (item.city, item.country) if p]
    return ", ".join(dict.fromkeys(parts)) or None


def event_out(
    item: CatalogEvent,
    *,
    match: MatchResult | None = None,
    state: dict[str, Any] | None = None,
    full: bool = False,
) -> dict[str, Any]:
    description = item.description or ""
    if not full and len(description) > 320:
        description = description[:317].rstrip() + "…"
    return {
        "ref": item.ref,
        "kind": item.kind,
        "id": item.id,
        "title": item.title,
        "description": description or None,
        "startDate": item.start_date.isoformat(),
        "endDate": item.end_date.isoformat() if item.end_date else None,
        "startTime": item.start_time,
        "city": item.city,
        "country": item.country,
        "venue": item.venue,
        "location": _location(item),
        "sector": item.sector,
        "eventType": item.event_type,
        "attendanceMode": item.attendance_mode,
        "price": {
            "isFree": item.is_free,
            "min": float(item.price_min) if item.price_min is not None else None,
            "max": float(item.price_max) if item.price_max is not None else None,
            "currency": item.currency,
            "display": price_text(item),
        },
        "registrationDeadline": item.registration_deadline.isoformat() if item.registration_deadline else None,
        "officialUrl": item.official_url,
        "registrationUrl": item.registration_url,
        "internalUrl": f"/events/{item.internal_slug}" if item.kind == PLATFORM and item.internal_slug else None,
        "registerOnPlatform": item.kind == PLATFORM,
        "organizer": item.organizer,
        "verification": item.verification,
        "eligible": item.eligible,
        "ineligibleReason": item.ineligible_reason,
        "match": match.as_dict() if match else None,
        "state": state,
    }
