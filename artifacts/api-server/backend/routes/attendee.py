"""Attendee Agent API — `/api/attendee/*`.

Every attendee endpoint requires a signed-in ATTENDEE account (organiser
accounts get 403; admins pass) and only ever reads or
writes that user's own rows (preferences, activity, notifications); the
`/attendee/admin/*` endpoints require ADMIN. Event data always comes from
`services/attendee_agent/catalog.py` (verified, de-duplicated, real).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.dependencies import require_attendee, require_roles
from backend.models import (
    AttendeeEventActivity,
    AttendeeIntent,
    AttendeeNotificationLog,
    AttendeePreference,
    AuditLog,
    Notification,
    Registration,
    SavedEvent,
    User,
)
from backend.services.attendee_agent import assistant, tracking
from backend.services.attendee_agent.auto_toggle import (
    is_attendee_notifications_auto_enabled,
    set_attendee_notifications_auto_enabled,
)
from backend.services.attendee_agent.catalog import DISCOVERED, PLATFORM, CatalogEvent, get_event_for_viewer, get_events, load_catalog
from backend.services.attendee_agent.matching import EVENT_TYPE_ALIASES, TOPIC_SYNONYMS, WEIGHTS, Preferences, rank, score_event
from backend.services.attendee_agent.notifier import run_attendee_notifications
from backend.services.attendee_agent.profile import get_or_create_attendee_profile, profile_out
from backend.services.attendee_agent.serialize import event_out
from backend.services.audit import record_audit_log
from backend.services.discovery_agent.categorizer import CATEGORIES
from backend.services.discovery_agent.country_utils import ALL_WORLD_COUNTRIES

router = APIRouter(prefix="/attendee", tags=["attendee"])

EventKind = Literal["platform", "discovered"]
_MODES = ("any", "online", "offline", "hybrid")
_COUNTRY_NAMES = {c.lower(): c for c in ALL_WORLD_COUNTRIES if c != "Dubai"}


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PreferencesIn(CamelModel):
    interests: list[str] = Field(default_factory=list, max_length=20)
    industries: list[str] = Field(default_factory=list, max_length=20)
    countries: list[str] = Field(default_factory=list, max_length=50)
    event_types: list[str] = Field(default_factory=list, max_length=12)
    budget_max: Decimal | None = Field(default=None, ge=0, le=10_000_000)
    budget_currency: str | None = Field(default=None, max_length=10)
    free_only: bool = False
    date_from: date | None = None
    date_to: date | None = None
    attendance_mode: str = "any"
    notify_consent: bool = False
    notify_event_reminders: bool = True
    notify_deadlines: bool = True
    notify_event_changes: bool = True
    notify_new_matches: bool = True
    notify_by_email: bool = False

    @field_validator("interests")
    @classmethod
    def _clean_interests(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip()[:60] for v in value if v and v.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("industries")
    @classmethod
    def _valid_industries(cls, value: list[str]) -> list[str]:
        allowed = {c.lower(): c for c in CATEGORIES if c != "Other"}
        bad = [v for v in value if v.strip().lower() not in allowed]
        if bad:
            raise ValueError(f"Unknown industries: {', '.join(bad)}")
        return list(dict.fromkeys(allowed[v.strip().lower()] for v in value))

    @field_validator("countries")
    @classmethod
    def _valid_countries(cls, value: list[str]) -> list[str]:
        bad = [v for v in value if v.strip().lower() not in _COUNTRY_NAMES]
        if bad:
            raise ValueError(f"Unknown countries: {', '.join(bad)}")
        return list(dict.fromkeys(_COUNTRY_NAMES[v.strip().lower()] for v in value))

    @field_validator("event_types")
    @classmethod
    def _valid_types(cls, value: list[str]) -> list[str]:
        bad = [v for v in value if v.strip().lower() not in EVENT_TYPE_ALIASES]
        if bad:
            raise ValueError(f"Unknown event types: {', '.join(bad)}")
        return list(dict.fromkeys(v.strip().lower() for v in value))

    @field_validator("attendance_mode")
    @classmethod
    def _valid_mode(cls, value: str) -> str:
        if value not in _MODES:
            raise ValueError(f"attendanceMode must be one of {', '.join(_MODES)}")
        return value

    @model_validator(mode="after")
    def _date_order(self) -> "PreferencesIn":
        if self.date_from and self.date_to and self.date_to < self.date_from:
            raise ValueError("dateTo must be on or after dateFrom")
        if self.budget_currency:
            self.budget_currency = self.budget_currency.strip().upper()
        return self


class AssistantIn(CamelModel):
    message: str = Field(min_length=2, max_length=1000)


class RegistrationIn(CamelModel):
    status: Literal["REGISTERED", "NOT_ATTENDING", "NONE"]
    # The attendee must tick "I have completed registration on the organizer's site".
    confirm: bool = False


class MatchIn(CamelModel):
    limit: int = Field(default=50, ge=1, le=500)
    min_percent: int = Field(default=0, ge=0, le=100)


class ToggleIn(CamelModel):
    enabled: bool


def _prefs_out(row: AttendeePreference | None) -> dict[str, Any]:
    if row is None:
        row = AttendeePreference(
            interests=[], industries=[], countries=[], event_types=[], attendance_mode="any",
            free_only=False, notify_consent=False, notify_event_reminders=True, notify_deadlines=True,
            notify_event_changes=True, notify_new_matches=True, notify_by_email=False,
        )
        saved = False
    else:
        saved = True
    return {
        "saved": saved,
        "interests": row.interests or [],
        "industries": row.industries or [],
        "countries": row.countries or [],
        "eventTypes": row.event_types or [],
        "budgetMax": float(row.budget_max) if row.budget_max is not None else None,
        "budgetCurrency": row.budget_currency,
        "freeOnly": bool(row.free_only),
        "dateFrom": row.date_from.isoformat() if row.date_from else None,
        "dateTo": row.date_to.isoformat() if row.date_to else None,
        "attendanceMode": row.attendance_mode or "any",
        "notifyConsent": bool(row.notify_consent),
        "notifyConsentAt": row.notify_consent_at.isoformat() if row.notify_consent_at else None,
        "notifyEventReminders": bool(row.notify_event_reminders),
        "notifyDeadlines": bool(row.notify_deadlines),
        "notifyEventChanges": bool(row.notify_event_changes),
        "notifyNewMatches": bool(row.notify_new_matches),
        "notifyByEmail": bool(row.notify_by_email),
        "updatedAt": row.updated_at.isoformat() if getattr(row, "updated_at", None) else None,
    }


def _load(db: Session, kind: str, event_id: int, user: User) -> CatalogEvent:
    """One event by id, but only if this user may see it: non-admins never get
    draft/unpublished platform events or rejected discovered events (or their
    organizer contacts) unless they own / already saved / registered for it.
    Not visible -> the same 404 as a missing event."""
    item = get_event_for_viewer(db, kind, event_id, user_id=user.id, is_admin=(user.role or "").upper() == "ADMIN")
    if item is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return item


def _prefs(db: Session, user: User) -> Preferences:
    return Preferences.from_model(db.get(AttendeePreference, user.id))


def _serialize_many(db: Session, user: User, items: list[CatalogEvent], prefs: Preferences) -> list[dict[str, Any]]:
    states = tracking.states_for(db, user.id, [(i.kind, i.id) for i in items])
    empty = prefs.is_empty()
    return [
        event_out(i, match=None if empty else score_event(i, prefs), state=states.get((i.kind, i.id)))
        for i in items
    ]


# ---------------------------------------------------------------------------
# Preferences & options
# ---------------------------------------------------------------------------


@router.get("/preferences")
def get_preferences(db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    return _prefs_out(db.get(AttendeePreference, user.id))


@router.put("/preferences")
def save_preferences(
    payload: PreferencesIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_attendee),
) -> dict[str, Any]:
    row = db.get(AttendeePreference, user.id)
    if row is None:
        row = AttendeePreference(user_id=user.id)
        db.add(row)
    consent_changed = bool(row.notify_consent) != payload.notify_consent
    for field in (
        "interests", "industries", "countries", "event_types", "budget_max", "budget_currency", "free_only",
        "date_from", "date_to", "attendance_mode", "notify_consent", "notify_event_reminders",
        "notify_deadlines", "notify_event_changes", "notify_new_matches", "notify_by_email",
    ):
        setattr(row, field, getattr(payload, field))
    if consent_changed:
        row.notify_consent_at = datetime.now(timezone.utc) if payload.notify_consent else None
        record_audit_log(
            db,
            actor="attendee",
            actor_id=user.id,
            action="ATTENDEE_NOTIFICATION_CONSENT_GRANTED" if payload.notify_consent else "ATTENDEE_NOTIFICATION_CONSENT_WITHDRAWN",
            entity="AttendeePreference",
            entity_id=user.id,
        )
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _prefs_out(row)


@router.get("/options")
def get_options(db: Session = Depends(get_db), _: User = Depends(require_attendee)) -> dict[str, Any]:
    """Choices for the preferences form, with how many verified upcoming
    events each one currently has — counted from the real catalog."""
    from backend.services.social_agent.outreach.senders import provider_status

    catalog = load_catalog(db)
    sector_counts = Counter(e.sector for e in catalog if e.sector)
    country_counts = Counter(e.country for e in catalog if e.country)
    mode_counts = Counter(e.attendance_mode or "not stated" for e in catalog)
    currency_counts = Counter(e.currency for e in catalog if e.currency)
    type_counts = {
        t: sum(1 for e in catalog if any(a in (e.event_type or "").lower() for a in aliases))
        for t, aliases in EVENT_TYPE_ALIASES.items()
    }
    return {
        "catalogSize": len(catalog),
        "industries": [{"value": c, "count": sector_counts.get(c, 0)} for c in CATEGORIES if c != "Other"],
        "countries": [{"value": c, "count": n} for c, n in country_counts.most_common()],
        "allCountries": [c for c in ALL_WORLD_COUNTRIES if c != "Dubai"],
        "eventTypes": [{"value": t, "count": type_counts[t]} for t in EVENT_TYPE_ALIASES],
        "attendanceModes": [{"value": m, "count": mode_counts.get(m, 0)} for m in ("online", "offline", "hybrid")]
        + [{"value": "not stated", "count": mode_counts.get("not stated", 0)}],
        "currencies": [{"value": c, "count": n} for c, n in currency_counts.most_common()],
        "interestSuggestions": list(TOPIC_SYNONYMS),
        "weights": WEIGHTS,
        "emailDelivery": provider_status(),
    }


# ---------------------------------------------------------------------------
# Attendee profile (personal details — separate from organiser profiles)
# ---------------------------------------------------------------------------


class ProfileIn(CamelModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, max_length=80)
    job_title: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=500)
    linkedin_url: str | None = Field(default=None, max_length=300)

    @field_validator("name", "phone", "city", "country", "job_title", "company", "bio", "linkedin_url")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("phone")
    @classmethod
    def _valid_phone(cls, value: str | None) -> str | None:
        if value and (not _PHONE_RE.fullmatch(value) or sum(c.isdigit() for c in value) < 6):
            raise ValueError("Enter a phone number using digits, spaces, +, - or brackets")
        return value

    @field_validator("country")
    @classmethod
    def _valid_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.lower() not in _COUNTRY_NAMES:
            raise ValueError(f"Unknown country: {value}")
        return _COUNTRY_NAMES[value.lower()]

    @field_validator("linkedin_url")
    @classmethod
    def _valid_linkedin(cls, value: str | None) -> str | None:
        if value and not _LINKEDIN_RE.match(value):
            raise ValueError("LinkedIn URL must start with https://www.linkedin.com/")
        return value


_PHONE_RE = re.compile(r"[+\d][\d\s\-()]{5,39}")
_LINKEDIN_RE = re.compile(r"^https://([a-z]{2,3}\.)?linkedin\.com/", re.IGNORECASE)


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    profile = get_or_create_attendee_profile(db, user)
    db.commit()
    return profile_out(user, profile)


@router.put("/profile")
def put_profile(payload: ProfileIn, db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    profile = get_or_create_attendee_profile(db, user)
    user.name = payload.name
    profile.phone = payload.phone
    profile.city = payload.city
    profile.country = payload.country
    profile.job_title = payload.job_title
    profile.company = payload.company
    profile.bio = payload.bio
    profile.linkedin_url = payload.linkedin_url
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile_out(user, profile)


# ---------------------------------------------------------------------------
# Discover: search & filter the verified catalog
# ---------------------------------------------------------------------------


@router.get("/events")
def search_events(
    q: str | None = Query(None, max_length=120),
    sector: str | None = Query(None, max_length=80),
    country: str | None = Query(None, max_length=80),
    mode: Literal["online", "offline", "hybrid"] | None = None,
    free: bool = False,
    date_from: date | None = Query(None, alias="dateFrom"),
    date_to: date | None = Query(None, alias="dateTo"),
    sort: Literal["soonest", "match"] = "soonest",
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=60, alias="pageSize"),
    db: Session = Depends(get_db),
    user: User = Depends(require_attendee),
) -> dict[str, Any]:
    """The same verified, upcoming catalog Match My Events ranks, filtered by
    what the attendee picks. Only facts the source published are filtered on:
    an event whose mode or price was not published never matches those filters."""
    catalog = load_catalog(db)
    terms = [t for t in (q or "").lower().split() if t]
    sector_l = (sector or "").strip().lower()
    country_l = (country or "").strip().lower()

    def keep(e: CatalogEvent) -> bool:
        if terms and not all(t in f"{e.search_text} {(e.city or '').lower()} {(e.country or '').lower()} {(e.organizer.get('name') or '').lower()}" for t in terms):
            return False
        if sector_l and (e.sector or "").lower() != sector_l:
            return False
        if country_l and (e.country or "").lower() != country_l:
            return False
        if mode and e.attendance_mode != mode:
            return False
        if free and e.is_free is not True:
            return False
        if date_from and (e.end_date or e.start_date) < date_from:
            return False
        if date_to and e.start_date > date_to:
            return False
        return True

    hits = [e for e in catalog if keep(e)]
    prefs = _prefs(db, user)
    if sort == "match" and not prefs.is_empty():
        hits = [e for e, _ in rank(hits, prefs)]
    else:
        hits.sort(key=lambda e: (e.start_date, e.title.lower()))
    start = (page - 1) * page_size
    return {
        "catalogSize": len(catalog),
        "total": len(hits),
        "page": page,
        "pageSize": page_size,
        "hasPreferences": not prefs.is_empty(),
        "results": _serialize_many(db, user, hits[start : start + page_size], prefs),
    }


# ---------------------------------------------------------------------------
# Matching & recommendations
# ---------------------------------------------------------------------------


@router.post("/match")
def match_my_events(
    payload: MatchIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_attendee),
) -> dict[str, Any]:
    payload = payload or MatchIn()
    prefs = _prefs(db, user)
    catalog = load_catalog(db)
    if prefs.is_empty():
        return {"hasPreferences": False, "catalogSize": len(catalog), "totalRanked": 0, "results": []}
    ranked = rank(catalog, prefs, min_percent=payload.min_percent)
    picked = ranked[: payload.limit]
    states = tracking.states_for(db, user.id, [(e.kind, e.id) for e, _ in picked])
    return {
        "hasPreferences": True,
        "catalogSize": len(catalog),
        "totalRanked": len(ranked),
        "weights": WEIGHTS,
        "results": [event_out(e, match=m, state=states.get((e.kind, e.id))) for e, m in picked],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _recommendations(db: Session, user: User, prefs: Preferences, catalog: list[CatalogEvent], limit: int) -> list[dict[str, Any]]:
    if prefs.is_empty():
        return []
    tracked = tracking.tracked_refs(db, user.id)
    exclude = {(k, i) for k, i, _ in tracked["registered"]}
    exclude |= {
        (DISCOVERED, a.discovered_event_id)
        for a in db.scalars(
            select(AttendeeEventActivity).where(
                AttendeeEventActivity.user_id == user.id, AttendeeEventActivity.external_registration_status == "NOT_ATTENDING"
            )
        ).all()
    }
    picked = rank(catalog, prefs, exclude=exclude, min_percent=50)[:limit]
    states = tracking.states_for(db, user.id, [(e.kind, e.id) for e, _ in picked])
    return [event_out(e, match=m, state=states.get((e.kind, e.id))) for e, m in picked]


@router.get("/recommendations")
def recommendations(
    limit: int = Query(6, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_attendee),
) -> dict[str, Any]:
    prefs = _prefs(db, user)
    catalog = load_catalog(db)
    return {"hasPreferences": not prefs.is_empty(), "results": _recommendations(db, user, prefs, catalog, limit)}


# ---------------------------------------------------------------------------
# Single event: details, favourites, registration
# ---------------------------------------------------------------------------


@router.get("/events/{kind}/{event_id}")
def event_detail(kind: EventKind, event_id: int, db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    item = _load(db, kind, event_id, user)
    tracking.record_view(db, user.id, item)
    db.commit()
    prefs = _prefs(db, user)
    state = tracking.states_for(db, user.id, [(kind, event_id)])[(kind, event_id)]
    return event_out(item, match=None if prefs.is_empty() else score_event(item, prefs), state=state, full=True)


@router.post("/events/{kind}/{event_id}/save")
def save_event(kind: EventKind, event_id: int, db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    item = _load(db, kind, event_id, user)
    if not item.eligible:
        raise HTTPException(status_code=400, detail=f"This event can't be saved: {item.ineligible_reason}")
    tracking.set_saved(db, user.id, item, True)
    db.commit()
    return tracking.states_for(db, user.id, [(kind, event_id)])[(kind, event_id)]


@router.delete("/events/{kind}/{event_id}/save")
def unsave_event(kind: EventKind, event_id: int, db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    item = _load(db, kind, event_id, user)
    tracking.set_saved(db, user.id, item, False)
    db.commit()
    return tracking.states_for(db, user.id, [(kind, event_id)])[(kind, event_id)]


@router.post("/events/{kind}/{event_id}/registration-opened")
def registration_opened(kind: EventKind, event_id: int, db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    """Records that the attendee opened the official registration page.
    This does NOT mark them registered."""
    item = _load(db, kind, event_id, user)
    tracking.mark_registration_opened(db, user.id, item)
    db.commit()
    target = item.registration_url or (f"/events/{item.internal_slug}/register" if item.internal_slug else None)
    return {"registrationUrl": target, "state": tracking.states_for(db, user.id, [(kind, event_id)])[(kind, event_id)]}


@router.post("/events/{kind}/{event_id}/registration")
def set_registration(
    kind: EventKind,
    event_id: int,
    payload: RegistrationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_attendee),
) -> dict[str, Any]:
    item = _load(db, kind, event_id, user)
    if kind == PLATFORM:
        raise HTTPException(
            status_code=400,
            detail="Registration for 100 TIMES events is done through the event's registration form, which issues your ticket.",
        )
    if payload.status == "REGISTERED" and not payload.confirm:
        raise HTTPException(status_code=400, detail="Please confirm you completed registration on the organizer's site.")
    tracking.set_external_registration(db, user.id, item, payload.status)
    record_audit_log(
        db,
        actor="attendee",
        actor_id=user.id,
        action=f"ATTENDEE_EXTERNAL_REGISTRATION_{payload.status}",
        entity="DiscoveredEvent",
        entity_id=event_id,
    )
    db.commit()
    return tracking.states_for(db, user.id, [(kind, event_id)])[(kind, event_id)]


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def _ts(value: datetime | None) -> float:
    if value is None:
        return 0.0
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    today = date.today()
    prefs = _prefs(db, user)
    catalog = load_catalog(db, today)
    tracked = tracking.tracked_refs(db, user.id)
    all_refs = sorted({(k, i) for group in tracked.values() for k, i, _ in group})
    items = get_events(db, all_refs, today)
    states = tracking.states_for(db, user.id, all_refs)
    empty = prefs.is_empty()

    def out(ref: tuple[str, int]) -> dict[str, Any] | None:
        item = items.get(ref)
        if item is None:
            return None
        return event_out(item, match=None if empty else score_event(item, prefs), state=states.get(ref))

    def section(group: str, *, by_date: bool) -> list[dict[str, Any]]:
        entries = tracked[group]
        if by_date:
            entries = sorted(entries, key=lambda e: items[(e[0], e[1])].start_date if (e[0], e[1]) in items else today)
        else:
            entries = sorted(entries, key=lambda e: -_ts(e[2]))
        seen: set[tuple[str, int]] = set()
        result = []
        for kind, event_id, _ in entries:
            if (kind, event_id) in seen:
                continue
            seen.add((kind, event_id))
            row = out((kind, event_id))
            if row:
                result.append(row)
        return result

    saved = section("saved", by_date=True)
    registered = section("registered", by_date=True)
    upcoming_refs = {
        ref for ref in {(k, i) for k, i, _ in tracked["registered"] + tracked["saved"]}
        if ref in items and (items[ref].end_date or items[ref].start_date) >= today and items[ref].eligible
    }
    upcoming = sorted((out(r) for r in upcoming_refs), key=lambda r: r["startDate"])
    open_refs = {(k, i) for k, i, _ in tracked["saved"]} - {(k, i) for k, i, _ in tracked["registered"]}
    with_deadline = [items[r] for r in open_refs if r in items and items[r].registration_deadline and items[r].registration_deadline >= today]
    deadlines = [out((i.kind, i.id)) for i in sorted(with_deadline, key=lambda i: i.registration_deadline)]
    no_deadline = sum(1 for r in open_refs if r in items and items[r].eligible and not items[r].registration_deadline)
    unread = int(db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id, Notification.is_read.is_(False))) or 0)
    pref_row = db.get(AttendeePreference, user.id)

    return {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "hasPreferences": not empty,
        "catalogSize": len(catalog),
        "recommended": _recommendations(db, user, prefs, catalog, 6),
        "saved": saved,
        "registered": registered,
        "upcoming": upcoming[:10],
        "deadlines": deadlines,
        "savedWithoutPublishedDeadline": no_deadline,
        "recentlyViewed": section("viewed", by_date=False)[:8],
        "counts": {
            "saved": len(saved),
            "registered": len(registered),
            "upcoming": len(upcoming),
            "unreadNotifications": unread,
        },
        "notificationsEnabled": bool(pref_row and pref_row.notify_consent),
    }


# ---------------------------------------------------------------------------
# Assistant & notifications
# ---------------------------------------------------------------------------


@router.post("/assistant")
def ask_assistant(payload: AssistantIn, db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, Any]:
    result = assistant.answer(db, user, payload.message.strip())
    db.commit()
    return result


@router.get("/notifications")
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_attendee),
) -> dict[str, Any]:
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(desc(Notification.created_at)).limit(limit)
    ).all()
    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "kind": (n.metadata_json or {}).get("kind") or n.template_key,
                "isRead": bool(n.is_read),
                "emailStatus": (n.metadata_json or {}).get("email_status"),
                "createdAt": n.created_at.isoformat() if n.created_at else None,
                "metadata": n.metadata_json or {},
            }
            for n in rows
        ],
        "unread": sum(1 for n in rows if not n.is_read),
    }


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, bool]:
    note = db.get(Notification, notification_id)
    if note is None or note.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    note.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(require_attendee)) -> dict[str, int]:
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))).all()
    for n in rows:
        n.is_read = True
    db.commit()
    return {"updated": len(rows)}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@router.get("/admin/overview")
def admin_overview(db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN"))) -> dict[str, Any]:
    catalog = load_catalog(db)
    kinds = Counter(e.kind for e in catalog)
    log_by_kind = dict(db.execute(select(AttendeeNotificationLog.kind, func.count()).group_by(AttendeeNotificationLog.kind)).all())
    email_by_status = dict(
        db.execute(select(AttendeeNotificationLog.email_status, func.count()).group_by(AttendeeNotificationLog.email_status)).all()
    )
    questions = db.scalars(
        select(AttendeeIntent).where(AttendeeIntent.source_platform == "assistant").order_by(desc(AttendeeIntent.created_at)).limit(25)
    ).all()
    last_sweep = db.scalar(
        select(AuditLog).where(AuditLog.action == "ATTENDEE_NOTIFICATION_SWEEP").order_by(desc(AuditLog.created_at)).limit(1)
    )
    from backend.services.social_agent.outreach.senders import provider_status

    return {
        "catalog": {"total": len(catalog), "platform": kinds.get(PLATFORM, 0), "discovered": kinds.get(DISCOVERED, 0)},
        "attendees": {
            "withPreferences": int(db.scalar(select(func.count(AttendeePreference.user_id))) or 0),
            "notificationConsent": int(
                db.scalar(select(func.count(AttendeePreference.user_id)).where(AttendeePreference.notify_consent.is_(True))) or 0
            ),
        },
        "engagement": {
            "savedPlatform": int(db.scalar(select(func.count()).select_from(SavedEvent)) or 0),
            "savedDiscovered": int(
                db.scalar(select(func.count(AttendeeEventActivity.id)).where(AttendeeEventActivity.is_saved.is_(True))) or 0
            ),
            "registrationPagesOpened": int(
                db.scalar(select(func.count(AttendeeEventActivity.id)).where(AttendeeEventActivity.registration_opened_at.is_not(None))) or 0
            ),
            "externalRegistrationsConfirmed": int(
                db.scalar(
                    select(func.count(AttendeeEventActivity.id)).where(AttendeeEventActivity.external_registration_status == "REGISTERED")
                )
                or 0
            ),
            "platformRegistrations": int(
                db.scalar(select(func.count(Registration.id)).where(func.lower(Registration.status).in_(("confirmed", "waitlisted")))) or 0
            ),
            "eventViews": int(db.scalar(select(func.coalesce(func.sum(AttendeeEventActivity.view_count), 0))) or 0),
        },
        "assistant": {
            "questionsAsked": int(
                db.scalar(select(func.count(AttendeeIntent.id)).where(AttendeeIntent.source_platform == "assistant")) or 0
            ),
            "recent": [
                {
                    "id": q.id,
                    "question": q.raw_text,
                    "status": q.status,
                    "location": q.location,
                    "sector": q.event_category,
                    "eventType": q.event_type,
                    "createdAt": q.created_at.isoformat() if q.created_at else None,
                }
                for q in questions
            ],
        },
        "notifications": {
            "autoEnabled": is_attendee_notifications_auto_enabled(db),
            "sentByKind": log_by_kind,
            "emailByStatus": email_by_status,
            "emailDelivery": provider_status(),
            "lastSweep": {
                "at": last_sweep.created_at.isoformat() if last_sweep else None,
                "result": last_sweep.result if last_sweep else None,
                "summary": last_sweep.metadata_json if last_sweep else None,
            },
        },
    }


@router.get("/admin/notifications/auto")
def get_notifications_auto(db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN"))) -> dict[str, bool]:
    return {"enabled": is_attendee_notifications_auto_enabled(db)}


@router.patch("/admin/notifications/auto")
def patch_notifications_auto(payload: ToggleIn, db: Session = Depends(get_db), admin: User = Depends(require_roles("ADMIN"))) -> dict[str, bool]:
    enabled = set_attendee_notifications_auto_enabled(db, payload.enabled)
    record_audit_log(db, actor="admin", actor_id=admin.id, action="ATTENDEE_NOTIFICATIONS_AUTO_TOGGLED", entity="AgentSetting",
                     entity_id="attendee_notifications_auto_enabled", metadata={"enabled": enabled})
    db.commit()
    return {"enabled": enabled}


@router.post("/admin/notifications/run")
def run_notifications_now(db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN"))) -> dict[str, Any]:
    summary = run_attendee_notifications(db)
    db.commit()
    return summary
