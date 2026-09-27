"""Pre-insert duplicate detection for the Event Discovery Agent — run
BEFORE every `DiscoveredEvent`/`DiscoveredOrganizer` insert so a re-run (or
a run resumed after a crash) never creates duplicate records. Nothing here
dedups `OutreachMessage`s — that's `outreach/duplicate_check.py`'s job.

Events match on a combination of (event name + date/city) or an exact
event URL, per the spec's "event name, organizer, date, city, event URL"
rule. Organizers match on exact email, then domain, then normalized name.
"""

import re
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import DiscoveredEvent, DiscoveredOrganizer

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return _NON_ALNUM.sub(" ", name.lower()).strip()


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url if "://" in url else f"//{url}", "http").netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def find_duplicate_event(
    db: Session,
    *,
    name: str | None,
    organizer_name: str | None = None,
    date: str | None = None,
    city: str | None = None,
    url: str | None = None,
) -> DiscoveredEvent | None:
    if url:
        stmt = select(DiscoveredEvent).where((DiscoveredEvent.url == url) | (DiscoveredEvent.ticket_url == url))
        existing = db.execute(stmt).scalars().first()
        if existing is not None:
            return existing

    if not name:
        return None

    normalized_target = normalize_name(name)
    candidates = db.execute(select(DiscoveredEvent).where(DiscoveredEvent.name.isnot(None))).scalars().all()
    for candidate in candidates:
        if normalize_name(candidate.name) != normalized_target:
            continue
        same_date = bool(date) and candidate.date == date
        same_city = bool(city) and candidate.city and candidate.city.strip().lower() == city.strip().lower()
        same_organizer = (
            bool(organizer_name) and candidate.organizer is not None
            and normalize_name(candidate.organizer.name) == normalize_name(organizer_name)
        )
        if same_date or same_city or same_organizer:
            return candidate

    return None


def find_duplicate_organizer(
    db: Session,
    *,
    name: str | None,
    email: str | None = None,
    website: str | None = None,
) -> DiscoveredOrganizer | None:
    if email:
        existing = db.execute(select(DiscoveredOrganizer).where(DiscoveredOrganizer.email == email)).scalars().first()
        if existing is not None:
            return existing

    domain = extract_domain(website)
    if domain:
        candidates = db.execute(select(DiscoveredOrganizer).where(DiscoveredOrganizer.website.isnot(None))).scalars().all()
        for candidate in candidates:
            if extract_domain(candidate.website) == domain:
                return candidate

    if name:
        normalized_target = normalize_name(name)
        candidates = db.execute(select(DiscoveredOrganizer)).scalars().all()
        for candidate in candidates:
            if normalize_name(candidate.name) == normalized_target:
                return candidate

    return None
