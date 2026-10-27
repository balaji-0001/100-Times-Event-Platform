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

from sqlalchemy import func, select
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


class DedupIndex:
    """One discovery run's in-memory view of existing events and organizers.

    Applies exactly the same matching rules as `find_duplicate_event` /
    `find_duplicate_organizer`, but loads the rows once per run (only the
    columns the rules need) instead of reading every row for every
    candidate, which grew linearly with the table. Rows inserted during the
    run are added via `add_event` / `add_organizer`. Not thread-safe — used
    only on the run's DB thread."""

    def __init__(self, db: Session) -> None:
        self.events_by_url: dict[str, list[int]] = {}
        self.events_by_name: dict[str, list[tuple[int, str | None, str | None, str]]] = {}
        # Rejected rows still dedup rejected re-finds, but never block an event
        # that now passes (a different run's scope may have rejected it).
        self.rejected_ids: set[int] = set()
        self.orgs_by_email: dict[str, int] = {}
        self.orgs_by_domain: dict[str, int] = {}
        self.orgs_by_name: dict[str, int] = {}
        org_names: dict[int, str] = {}
        for org_id, name, email, website in db.execute(
            select(DiscoveredOrganizer.id, DiscoveredOrganizer.name, DiscoveredOrganizer.email, DiscoveredOrganizer.website)
            .order_by(DiscoveredOrganizer.id)
        ).all():
            org_names[org_id] = name or ""
            self._index_organizer(org_id, name, email, website)
        for ev_id, name, date, city, url, ticket_url, organizer_id, status in db.execute(
            select(
                DiscoveredEvent.id, DiscoveredEvent.name, DiscoveredEvent.date, DiscoveredEvent.city,
                DiscoveredEvent.url, DiscoveredEvent.ticket_url, DiscoveredEvent.organizer_id, DiscoveredEvent.verification_status,
            ).order_by(DiscoveredEvent.id)
        ).all():
            self._index_event(ev_id, name, date, city, url, ticket_url, org_names.get(organizer_id, "") if organizer_id else "")
            if status == "REJECTED":
                self.rejected_ids.add(ev_id)

    def _index_event(self, ev_id, name, date, city, url, ticket_url, organizer_name) -> None:
        for u in (url, ticket_url):
            if u and ev_id not in self.events_by_url.setdefault(u, []):
                self.events_by_url[u].append(ev_id)
        if name:
            self.events_by_name.setdefault(normalize_name(name), []).append(
                (ev_id, date, (city or "").strip().lower() or None, normalize_name(organizer_name))
            )

    def _index_organizer(self, org_id, name, email, website) -> None:
        if email:
            self.orgs_by_email.setdefault(email, org_id)
        domain = extract_domain(website)
        if domain:
            self.orgs_by_domain.setdefault(domain, org_id)
        if name:
            self.orgs_by_name.setdefault(normalize_name(name), org_id)

    def add_event(self, event: DiscoveredEvent, organizer_name: str | None) -> None:
        self._index_event(event.id, event.name, event.date, event.city, event.url, event.ticket_url, organizer_name or "")
        if event.verification_status == "REJECTED":
            self.rejected_ids.add(event.id)
        else:
            self.rejected_ids.discard(event.id)

    def add_organizer(self, organizer: DiscoveredOrganizer) -> None:
        self._index_organizer(organizer.id, organizer.name, organizer.email, organizer.website)

    def find_event_id(self, *, name, organizer_name=None, date=None, city=None, url=None, skip_rejected=False) -> int | None:
        def usable(ev_id: int) -> bool:
            return not (skip_rejected and ev_id in self.rejected_ids)

        for ev_id in self.events_by_url.get(url, []) if url else []:
            if usable(ev_id):
                return ev_id
        if not name:
            return None
        target_org = normalize_name(organizer_name) if organizer_name else ""
        target_city = city.strip().lower() if city else None
        for ev_id, ev_date, ev_city, ev_org in self.events_by_name.get(normalize_name(name), []):
            if usable(ev_id) and ((date and ev_date == date) or (target_city and ev_city == target_city) or (target_org and ev_org == target_org)):
                return ev_id
        return None

    def find_organizer_id(self, *, name, email=None, website=None) -> int | None:
        if email and email in self.orgs_by_email:
            return self.orgs_by_email[email]
        domain = extract_domain(website)
        if domain and domain in self.orgs_by_domain:
            return self.orgs_by_domain[domain]
        if name:
            return self.orgs_by_name.get(normalize_name(name))
        return None


def find_duplicate_event(
    db: Session,
    *,
    name: str | None,
    organizer_name: str | None = None,
    date: str | None = None,
    city: str | None = None,
    url: str | None = None,
    index: DedupIndex | None = None,
    skip_rejected: bool = False,
) -> DiscoveredEvent | None:
    if index is not None:
        found = index.find_event_id(name=name, organizer_name=organizer_name, date=date, city=city, url=url, skip_rejected=skip_rejected)
        return db.get(DiscoveredEvent, found) if found is not None else None

    not_rejected = (DiscoveredEvent.verification_status != "REJECTED") if skip_rejected else True
    if url:
        stmt = select(DiscoveredEvent).where((DiscoveredEvent.url == url) | (DiscoveredEvent.ticket_url == url)).where(not_rejected)
        existing = db.execute(stmt).scalars().first()
        if existing is not None:
            return existing

    if not name:
        return None

    normalized_target = normalize_name(name)
    clean_prefix = name.strip()[:30].lower()
    stmt = (
        select(DiscoveredEvent)
        .where(DiscoveredEvent.name.isnot(None))
        .where(func.lower(DiscoveredEvent.name).like(f"{clean_prefix}%") | (func.lower(DiscoveredEvent.name) == name.strip().lower()))
        .where(not_rejected)
        .limit(30)
    )
    candidates = db.execute(stmt).scalars().all()
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
    index: DedupIndex | None = None,
) -> DiscoveredOrganizer | None:
    if index is not None:
        found = index.find_organizer_id(name=name, email=email, website=website)
        return db.get(DiscoveredOrganizer, found) if found is not None else None

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
