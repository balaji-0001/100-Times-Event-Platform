"""The attendee-facing event catalog — the ONLY set of events the Attendee
Agent will ever recommend, match, or return from the assistant.

Two real sources, both already in the database:
- platform `Event` rows an organizer listed on 100 TIMES, eligible only when
  published AND approved by the Trust Agent (`trust_status == "APPROVED"`),
  not cancelled/rejected, and not yet over;
- web-discovered `DiscoveredEvent` rows, eligible only when the Discovery
  Agent marked them `VERIFIED`, they are not a duplicate/rejected record,
  have a parsed (never guessed) date that is not in the past, have an
  official URL, and the source's own structured data does not say the event
  was cancelled or postponed.

Price, currency, registration deadline (schema.org `offers.validThrough`),
end date and keywords for discovered events are read from the source
evidence the Discovery Agent preserved in `event_sources.extracted_fields`
— never inferred. Anything a source did not publish stays `None` and the UI
says "Not published".

Duplicates (same normalised title + same start date) collapse to one entry,
preferring the platform listing, then the higher-confidence discovered row.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.models import AttendeeEventActivity, DiscoveredEvent, DiscoveredOrganizer, Event, Registration, SavedEvent, Venue
from backend.services.discovery_agent.country_utils import normalize_country

PLATFORM = "platform"
DISCOVERED = "discovered"
KINDS = (PLATFORM, DISCOVERED)

_INACTIVE_LIFECYCLE = {"CANCELLED", "REJECTED", "COMPLETED", "ARCHIVED"}
_EXCLUDED_DISCOVERY_STATUS = {"DUPLICATE", "REJECTED"}
_BAD_EVENT_STATUS = ("cancelled", "canceled", "postponed")

# Values the Discovery Agent stores in `country` that are not countries.
_COUNTRY_FIXUPS = {"dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates"}
_NOT_A_COUNTRY = {"worldwide", "global", "online", "virtual", "bb", ""}


@dataclass
class CatalogEvent:
    kind: str
    id: int
    title: str
    description: str
    start_date: date
    end_date: date | None
    start_time: str | None
    city: str | None
    country: str | None
    venue: str | None
    sector: str | None
    event_type: str | None
    attendance_mode: str | None  # online | offline | hybrid | None (source didn't say)
    is_free: bool | None  # None = price not published
    price_min: Decimal | None
    price_max: Decimal | None
    currency: str | None
    registration_deadline: date | None
    official_url: str | None
    registration_url: str | None
    internal_slug: str | None
    organizer: dict[str, Any]
    keywords: list[str]
    verification: dict[str, Any]
    first_seen_at: datetime | None
    eligible: bool = True
    ineligible_reason: str | None = None
    source_status: str | None = None  # schema.org eventStatus as published by the source
    _search_text: str = field(default="", repr=False)

    @property
    def ref(self) -> str:
        return f"{self.kind}:{self.id}"

    @property
    def search_text(self) -> str:
        if not self._search_text:
            self._search_text = " ".join(
                filter(None, [self.title, self.description, self.sector, self.event_type, " ".join(self.keywords)])
            ).lower()
        return self._search_text


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _clean_country(raw: str | None, city: str | None = None) -> str | None:
    if raw:
        lowered = raw.strip().lower()
        if lowered in _COUNTRY_FIXUPS:
            return _COUNTRY_FIXUPS[lowered]
        if lowered in _NOT_A_COUNTRY:
            return None
        return normalize_country(raw)
    if city and city.strip().lower() in _COUNTRY_FIXUPS:
        return _COUNTRY_FIXUPS[city.strip().lower()]
    return None


def _norm_mode(value: str | None) -> str | None:
    v = (value or "").strip().lower()
    if not v:
        return None
    if "hybrid" in v or "mixed" in v:
        return "hybrid"
    if "online" in v or "virtual" in v:
        return "online"
    if "person" in v or "offline" in v or "physical" in v:
        return "offline"
    return None


def normalize_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


# ---------------------------------------------------------------------------
# Evidence parsing (schema.org JSON-LD as captured by the Discovery Agent)
# ---------------------------------------------------------------------------


def _ci(obj: Any, key: str) -> Any:
    if not isinstance(obj, dict):
        return None
    lowered = key.lower()
    for k, v in obj.items():
        if isinstance(k, str) and k.lower() == lowered:
            return v
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _to_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _evidence_dicts(dev: DiscoveredEvent) -> list[dict]:
    out: list[dict] = []
    for src in dev.sources or []:
        fields = src.extracted_fields
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except ValueError:
                continue
        if isinstance(fields, dict):
            out.append(fields)
    return out


def parse_evidence(dev: DiscoveredEvent) -> dict[str, Any]:
    """Pull price/deadline/end-date/status/keywords from the preserved source
    evidence. First source that publishes a field wins; nothing is guessed."""
    result: dict[str, Any] = {
        "price_min": None,
        "price_max": None,
        "currency": None,
        "is_free": None,
        "deadline": None,
        "end_date": None,
        "event_status": None,
        "keywords": [],
    }
    for ev in _evidence_dicts(dev):
        if result["end_date"] is None:
            result["end_date"] = _to_date(_ci(ev, "endDate"))
        if result["event_status"] is None:
            status = _ci(ev, "eventStatus")
            if isinstance(status, str) and status.strip():
                result["event_status"] = status.rsplit("/", 1)[-1]
        if not result["keywords"]:
            kw = _ci(ev, "keywords")
            if isinstance(kw, str):
                result["keywords"] = [k.strip() for k in kw.split(",") if k.strip()][:15]
            elif isinstance(kw, list):
                result["keywords"] = [str(k).strip() for k in kw if str(k).strip()][:15]
        free_flag = _ci(ev, "isAccessibleForFree")
        if result["is_free"] is None and isinstance(free_flag, bool):
            result["is_free"] = free_flag

        offers = _ci(ev, "offers")
        offer_list = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
        prices: list[Decimal] = []
        for offer in offer_list:
            if not isinstance(offer, dict):
                continue
            for key in ("price", "lowPrice", "highPrice"):
                value = _to_decimal(_ci(offer, key))
                if value is not None:
                    prices.append(value)
            if result["currency"] is None:
                cur = _ci(offer, "priceCurrency")
                if isinstance(cur, str) and cur.strip():
                    result["currency"] = cur.strip().upper()
            if result["deadline"] is None:
                result["deadline"] = _to_date(_ci(offer, "validThrough"))
        if prices and result["price_min"] is None:
            result["price_min"] = min(prices)
            result["price_max"] = max(prices)
            if result["is_free"] is None:
                result["is_free"] = result["price_max"] == 0
    return result


# ---------------------------------------------------------------------------
# Row -> CatalogEvent
# ---------------------------------------------------------------------------


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).netloc or "").lower()
    return host.removeprefix("www.") or None


def from_platform(ev: Event, today: date) -> CatalogEvent:
    city = ev.city_name or (ev.venue.city.name if ev.venue and ev.venue.city else None)
    country = _clean_country(ev.country_name or (ev.venue.country if ev.venue else None), city)
    org = ev.organizer
    price = Decimal(ev.price or 0)
    ticket_info = ev.ticket_info if isinstance(ev.ticket_info, dict) else {}
    deadline = _to_date(ticket_info.get("registrationDeadline") or ticket_info.get("registration_deadline"))

    reason = None
    lifecycle = (ev.lifecycle_state or "").upper()
    if ev.status != "published":
        reason = "Not published"
    elif lifecycle in _INACTIVE_LIFECYCLE:
        reason = f"Event {lifecycle.lower()}"
    elif (ev.trust_status or "").upper() != "APPROVED":
        reason = "Not approved by Trust review"
    elif (ev.end_date or ev.start_date) < today:
        reason = "Event has ended"

    return CatalogEvent(
        kind=PLATFORM,
        id=ev.id,
        title=ev.title,
        description=ev.description or "",
        start_date=ev.start_date,
        end_date=ev.end_date,
        start_time=ev.start_time,
        city=city,
        country=country,
        venue=ev.venue.name if ev.venue else ev.full_address,
        sector=ev.category.name if ev.category else None,
        event_type=(ev.event_type or "").strip().title() or None,
        attendance_mode=_norm_mode(ev.format),
        is_free=bool(ev.is_free or price == 0),
        price_min=price,
        price_max=price,
        currency=(ticket_info.get("currency") or "INR").upper(),
        registration_deadline=deadline,
        official_url=None,
        registration_url=ev.registration_url or None,
        internal_slug=ev.slug,
        organizer={
            "name": org.name if org else None,
            "website": org.website if org else None,
            "email": org.email if org else None,
            "phone": org.phone if org else None,
            "verified": bool(org.verified) if org else False,
        },
        keywords=[str(t) for t in (ev.tags or []) if t],
        verification={
            "status": ev.trust_status or "UNREVIEWED",
            "score": ev.trust_score,
            "basis": "Listed on 100 TIMES and approved by the Trust Agent review",
        },
        first_seen_at=_as_utc(ev.created_at),
        eligible=reason is None,
        ineligible_reason=reason,
    )


def from_discovered(dev: DiscoveredEvent, today: date) -> CatalogEvent:
    evidence = parse_evidence(dev)
    org: DiscoveredOrganizer | None = dev.organizer
    status_text = (evidence["event_status"] or "").lower()
    end_date = evidence["end_date"] if evidence["end_date"] and dev.event_date and evidence["end_date"] >= dev.event_date else None

    reason = None
    if dev.verification_status != "VERIFIED":
        reason = "Not verified"
    elif dev.discovery_status in _EXCLUDED_DISCOVERY_STATUS:
        reason = f"Marked {dev.discovery_status.lower()}"
    elif dev.event_date is None:
        reason = "Date could not be verified"
    elif (end_date or dev.event_date) < today:
        reason = "Event has ended"
    elif not dev.url:
        reason = "No official event page"
    elif any(word in status_text for word in _BAD_EVENT_STATUS):
        reason = f"Source reports the event as {evidence['event_status']}"

    mode = _norm_mode(dev.event_format)
    if "movedonline" in status_text:
        mode = "online"

    organizer_email = org.email if org and org.email else None
    if org and not organizer_email:
        primary = next((c for c in org.contacts if c.contact_type == "email"), None)
        organizer_email = primary.value if primary else None

    return CatalogEvent(
        kind=DISCOVERED,
        id=dev.id,
        title=dev.name or "Untitled event",
        description=dev.event_description or "",
        start_date=dev.event_date or today,
        end_date=end_date,
        start_time=dev.start_time,
        city=dev.city,
        country=_clean_country(dev.country, dev.city),
        venue=dev.venue,
        sector=dev.category if dev.category and dev.category != "Other" else None,
        event_type=dev.subcategory,
        attendance_mode=mode,
        is_free=evidence["is_free"],
        price_min=evidence["price_min"],
        price_max=evidence["price_max"],
        currency=evidence["currency"],
        registration_deadline=evidence["deadline"],
        official_url=dev.url,
        registration_url=dev.ticket_url or dev.url,
        internal_slug=None,
        organizer={
            "name": org.name if org else None,
            "website": org.website if org else None,
            "email": organizer_email,
            "phone": org.phone if org else None,
            "verified": bool(org and org.verified_at),
        },
        keywords=evidence["keywords"],
        verification={
            "status": dev.verification_status,
            "score": dev.confidence_score,
            "basis": f"Verified by the Discovery Agent from {_domain(dev.source_url or dev.url) or 'its source page'}",
            "sourceUrl": dev.source_url or dev.url,
            "sourceCount": len(dev.sources or []),
        },
        first_seen_at=_as_utc(dev.discovered_at or dev.created_at),
        eligible=reason is None,
        ineligible_reason=reason,
        source_status=evidence["event_status"],
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _platform_query():
    return select(Event).options(
        selectinload(Event.category),
        selectinload(Event.organizer),
        selectinload(Event.venue).selectinload(Venue.city),
    )


def _discovered_query():
    return select(DiscoveredEvent).options(
        selectinload(DiscoveredEvent.sources),
        selectinload(DiscoveredEvent.organizer).selectinload(DiscoveredOrganizer.contacts),
    )


def load_catalog(db: Session, today: date | None = None) -> list[CatalogEvent]:
    """Every eligible, de-duplicated event, soonest first."""
    today = today or date.today()
    platform_rows = db.scalars(
        _platform_query().where(
            Event.status == "published",
            Event.trust_status == "APPROVED",
            Event.end_date >= today,
        )
    ).all()
    discovered_rows = db.scalars(
        _discovered_query().where(
            DiscoveredEvent.verification_status == "VERIFIED",
            DiscoveredEvent.event_date.is_not(None),
            DiscoveredEvent.discovery_status.not_in(_EXCLUDED_DISCOVERY_STATUS),
        )
    ).all()

    candidates = [from_platform(ev, today) for ev in platform_rows]
    discovered = sorted(
        (from_discovered(dev, today) for dev in discovered_rows),
        key=lambda c: -int(c.verification.get("score") or 0),
    )
    candidates += discovered

    seen: set[tuple[str, date]] = set()
    catalog: list[CatalogEvent] = []
    for item in candidates:
        if not item.eligible:
            continue
        key = (normalize_title(item.title), item.start_date)
        if key in seen:
            continue
        seen.add(key)
        catalog.append(item)
    catalog.sort(key=lambda c: (c.start_date, c.title.lower()))
    return catalog


def get_event(db: Session, kind: str, event_id: int, today: date | None = None) -> CatalogEvent | None:
    """One event by reference, eligible or not — saved/registered events must
    still be viewable after they end or get cancelled (with the reason)."""
    today = today or date.today()
    if kind == PLATFORM:
        ev = db.scalar(_platform_query().where(Event.id == event_id))
        return from_platform(ev, today) if ev else None
    if kind == DISCOVERED:
        dev = db.scalar(_discovered_query().where(DiscoveredEvent.id == event_id))
        return from_discovered(dev, today) if dev else None
    return None


def is_publicly_listed_platform(ev: Event) -> bool:
    """Same rule as the public event pages (`routes/events.py`): only
    published events are visible to non-owners."""
    return ev.status == "published"


def is_publicly_listed_discovered(dev: DiscoveredEvent) -> bool:
    """Discovered events an admin (or the Discovery Agent) rejected are never
    shown to attendees."""
    return (dev.discovery_status or "").upper() != "REJECTED" and (dev.verification_status or "").upper() != "REJECTED"


def _viewer_tracks_platform(db: Session, user_id: int, event_id: int) -> bool:
    saved = db.scalar(select(SavedEvent.event_id).where(SavedEvent.user_id == user_id, SavedEvent.event_id == event_id).limit(1))
    if saved is not None:
        return True
    return db.scalar(select(Registration.id).where(Registration.user_id == user_id, Registration.event_id == event_id).limit(1)) is not None


def _viewer_tracks_discovered(db: Session, user_id: int, event_id: int) -> bool:
    row = db.scalar(
        select(AttendeeEventActivity.id).where(
            AttendeeEventActivity.user_id == user_id,
            AttendeeEventActivity.discovered_event_id == event_id,
            or_(AttendeeEventActivity.is_saved.is_(True), AttendeeEventActivity.external_registration_status == "REGISTERED"),
        ).limit(1)
    )
    return row is not None


def get_event_for_viewer(
    db: Session,
    kind: str,
    event_id: int,
    *,
    user_id: int,
    is_admin: bool,
    today: date | None = None,
) -> CatalogEvent | None:
    """`get_event`, limited to what this viewer may see. Admins see everything.
    Anyone else sees what the public listing shows (published platform events,
    non-rejected discovered events), plus platform events whose organizer they
    own, plus events they already saved or registered for — those stay
    viewable (with the ineligibility reason) after being cancelled or pulled.
    Returns None when the event does not exist or is not visible."""
    today = today or date.today()
    if kind == PLATFORM:
        ev = db.scalar(_platform_query().where(Event.id == event_id))
        if ev is None:
            return None
        visible = (
            is_admin
            or is_publicly_listed_platform(ev)
            or (ev.organizer is not None and ev.organizer.user_id == user_id)
            or _viewer_tracks_platform(db, user_id, ev.id)
        )
        return from_platform(ev, today) if visible else None
    if kind == DISCOVERED:
        dev = db.scalar(_discovered_query().where(DiscoveredEvent.id == event_id))
        if dev is None:
            return None
        visible = is_admin or is_publicly_listed_discovered(dev) or _viewer_tracks_discovered(db, user_id, dev.id)
        return from_discovered(dev, today) if visible else None
    return None


def get_events(db: Session, refs: list[tuple[str, int]], today: date | None = None) -> dict[tuple[str, int], CatalogEvent]:
    today = today or date.today()
    out: dict[tuple[str, int], CatalogEvent] = {}
    platform_ids = sorted({i for k, i in refs if k == PLATFORM})
    discovered_ids = sorted({i for k, i in refs if k == DISCOVERED})
    if platform_ids:
        for ev in db.scalars(_platform_query().where(Event.id.in_(platform_ids))).all():
            out[(PLATFORM, ev.id)] = from_platform(ev, today)
    if discovered_ids:
        for dev in db.scalars(_discovered_query().where(DiscoveredEvent.id.in_(discovered_ids))).all():
            out[(DISCOVERED, dev.id)] = from_discovered(dev, today)
    return out


def fingerprint(item: CatalogEvent) -> dict[str, Any]:
    """The fields whose change an attendee is notified about."""
    return {
        "startDate": item.start_date.isoformat(),
        "endDate": item.end_date.isoformat() if item.end_date else None,
        "startTime": item.start_time,
        "city": item.city,
        "country": item.country,
        "venue": item.venue,
        "mode": item.attendance_mode,
        "status": item.ineligible_reason if item.ineligible_reason and item.ineligible_reason != "Event has ended" else "active",
    }


def fingerprint_hash(fp: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(fp, sort_keys=True).encode()).hexdigest()[:12]
