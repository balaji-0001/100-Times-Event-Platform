"""The single event-matching algorithm for attendees.

Used by "Match My Events", dashboard recommendations, the assistant's
"matching my profile" answers and new-match notifications — there is no
second scoring system anywhere (the old `/ai/recommendations` and
`/ai/concierge` baseline-score heuristics were removed in favour of this).

Deterministic and explainable. Each preference the attendee actually set is
one criterion with a fixed weight:

    industry 30 · interests 25 · country 15 · event type 10 ·
    attendance mode 10 · budget 5 · dates 5

A criterion earns its full weight when the event satisfies it, a fraction
for partial interest overlap, and 0 when the event clearly does not. When
the event's own data cannot answer the question (e.g. the source never
published a price) the criterion is reported as "not checked" and left out
of BOTH sides of the ratio, so missing data never inflates or deflates a
score. Match % = earned / possible over the criteria that were checked.
Criteria the attendee left empty are not scored at all — with no
preferences set there is no match percentage, never a made-up baseline.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from backend.services.attendee_agent.catalog import CatalogEvent

WEIGHTS: dict[str, int] = {
    "industry": 30,
    "interests": 25,
    "country": 15,
    "event_type": 10,
    "mode": 10,
    "budget": 5,
    "dates": 5,
}

LABELS = {
    "industry": "Industry",
    "interests": "Interests",
    "country": "Country",
    "event_type": "Event type",
    "mode": "Attendance mode",
    "budget": "Budget",
    "dates": "Dates",
}

# Interest -> extra phrases that mean the same thing in event copy.
TOPIC_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ai": ("ai", "artificial intelligence", "machine learning", "generative ai", "genai", "llm", "llms", "deep learning", "ml"),
    "artificial intelligence": ("ai", "artificial intelligence", "machine learning", "generative ai", "genai", "llm"),
    "machine learning": ("machine learning", "ml", "deep learning", "ai"),
    "data": ("data", "analytics", "data science", "big data"),
    "data science": ("data science", "analytics", "machine learning", "big data"),
    "cloud": ("cloud", "aws", "azure", "gcp", "kubernetes", "devops"),
    "cybersecurity": ("cybersecurity", "cyber security", "infosec", "security"),
    "security": ("security", "cybersecurity", "cyber security", "infosec"),
    "blockchain": ("blockchain", "web3", "crypto", "cryptocurrency"),
    "web3": ("web3", "blockchain", "crypto"),
    "startup": ("startup", "startups", "founder", "founders", "entrepreneur", "entrepreneurs", "venture"),
    "startups": ("startup", "startups", "founder", "founders", "entrepreneur"),
    "fintech": ("fintech", "payments", "banking", "digital finance"),
    "healthtech": ("healthtech", "digital health", "health tech", "medtech"),
    "marketing": ("marketing", "growth", "brand", "advertising"),
    "design": ("design", "ux", "ui", "product design"),
    "sustainability": ("sustainability", "climate", "esg", "net zero", "clean energy"),
    "robotics": ("robotics", "robots", "automation"),
    "iot": ("iot", "internet of things", "connected devices"),
}

EVENT_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "exhibition": ("exhibition", "expo", "trade show", "trade fair", "fair"),
    "conference": ("conference", "congress", "symposium", "forum", "conclave"),
    "summit": ("summit",),
    "workshop": ("workshop", "bootcamp", "masterclass", "training"),
    "webinar": ("webinar",),
    "meetup": ("meetup", "meet-up"),
    "hackathon": ("hackathon",),
    "seminar": ("seminar", "lecture", "talk"),
    "networking": ("networking", "mixer"),
}


@dataclass
class Preferences:
    interests: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)
    budget_max: Decimal | None = None
    budget_currency: str | None = None
    free_only: bool = False
    date_from: date | None = None
    date_to: date | None = None
    attendance_mode: str = "any"

    @classmethod
    def from_model(cls, row: Any | None) -> "Preferences":
        if row is None:
            return cls()
        return cls(
            interests=list(row.interests or []),
            industries=list(row.industries or []),
            countries=list(row.countries or []),
            event_types=list(row.event_types or []),
            budget_max=Decimal(row.budget_max) if row.budget_max is not None else None,
            budget_currency=(row.budget_currency or None),
            free_only=bool(row.free_only),
            date_from=row.date_from,
            date_to=row.date_to,
            attendance_mode=row.attendance_mode or "any",
        )

    def is_empty(self) -> bool:
        return not (
            self.interests
            or self.industries
            or self.countries
            or self.event_types
            or self.budget_max is not None
            or self.free_only
            or self.date_from
            or self.date_to
            or (self.attendance_mode or "any") != "any"
        )


@dataclass
class Criterion:
    key: str
    label: str
    weight: int
    earned: float
    status: str  # matched | partial | missed | not_checked
    detail: str


@dataclass
class MatchResult:
    percent: int
    earned: float
    possible: int
    reasons: list[str]
    gaps: list[str]
    criteria: list[Criterion]

    def as_dict(self) -> dict[str, Any]:
        return {
            "percent": self.percent,
            "earned": round(self.earned, 2),
            "possible": self.possible,
            "reasons": self.reasons,
            "gaps": self.gaps,
            "criteria": [asdict(c) for c in self.criteria],
            "criteriaChecked": sum(1 for c in self.criteria if c.status != "not_checked"),
        }


def _phrase_pattern(phrase: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])")


def interest_phrases(interest: str) -> tuple[str, ...]:
    key = interest.strip().lower()
    return TOPIC_SYNONYMS.get(key, (key,))


def text_mentions(text: str, interest: str) -> bool:
    return any(_phrase_pattern(p).search(text) for p in interest_phrases(interest) if p)


def event_type_matches(event_type: str | None, wanted: str, text: str = "") -> bool:
    wanted_key = wanted.strip().lower()
    aliases = EVENT_TYPE_ALIASES.get(wanted_key, (wanted_key,))
    et = (event_type or "").lower()
    if et and any(a == et or a in et for a in aliases):
        return True
    # Title fallback only when the event has no classified type at all.
    return not et and bool(text) and any(_phrase_pattern(a).search(text) for a in aliases)


def _same(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.strip().lower() == b.strip().lower())


def score_event(item: CatalogEvent, prefs: Preferences) -> MatchResult | None:
    """Score one event against the attendee's preferences, or None when the
    attendee has set nothing to score against."""
    criteria: list[Criterion] = []

    def add(key: str, earned_fraction: float | None, status: str, detail: str) -> None:
        weight = WEIGHTS[key]
        earned = 0.0 if earned_fraction is None else round(weight * earned_fraction, 2)
        criteria.append(Criterion(key, LABELS[key], weight, earned, status, detail))

    text = item.search_text

    if prefs.industries:
        if item.sector and any(_same(item.sector, ind) for ind in prefs.industries):
            add("industry", 1.0, "matched", f"{item.sector} is one of your industries")
        elif item.sector:
            add("industry", 0.0, "missed", f"Sector is {item.sector}")
        else:
            add("industry", 0.0, "missed", "Sector could not be identified from the event's details")

    if prefs.interests:
        hits = [i for i in prefs.interests if text_mentions(text, i)]
        target = min(len(prefs.interests), 3)
        fraction = min(len(hits), target) / target
        if hits:
            add("interests", fraction, "matched" if fraction >= 1 else "partial", "Mentions " + ", ".join(hits[:4]))
        else:
            add("interests", 0.0, "missed", "None of your interests are mentioned")

    if prefs.countries:
        if item.country and any(_same(item.country, c) for c in prefs.countries):
            add("country", 1.0, "matched", f"Takes place in {item.country}")
        elif item.attendance_mode == "online":
            add("country", 1.0, "matched", "Online — can be joined from your countries")
        elif item.country:
            add("country", 0.0, "missed", f"Takes place in {item.country}")
        else:
            add("country", None, "not_checked", "The source did not publish a country")

    if prefs.event_types:
        hit = next((t for t in prefs.event_types if event_type_matches(item.event_type, t, item.title.lower())), None)
        if hit:
            add("event_type", 1.0, "matched", f"It's a {(item.event_type or hit).lower()}")
        elif item.event_type:
            add("event_type", 0.0, "missed", f"It's a {item.event_type.lower()}")
        else:
            add("event_type", None, "not_checked", "Event type not stated by the source")

    mode = (prefs.attendance_mode or "any").lower()
    if mode != "any":
        if item.attendance_mode == mode or item.attendance_mode == "hybrid":
            add("mode", 1.0, "matched", f"{(item.attendance_mode or '').title()} event")
        elif item.attendance_mode:
            add("mode", 0.0, "missed", f"{item.attendance_mode.title()} event")
        else:
            add("mode", None, "not_checked", "Attendance mode not stated by the source")

    if prefs.free_only:
        if item.is_free is True:
            add("budget", 1.0, "matched", "Free to attend")
        elif item.is_free is False:
            add("budget", 0.0, "missed", _price_text(item))
        else:
            add("budget", None, "not_checked", "Price not published by the source")
    elif prefs.budget_max is not None:
        if item.is_free is True:
            add("budget", 1.0, "matched", "Free to attend")
        elif item.price_min is None:
            add("budget", None, "not_checked", "Price not published by the source")
        elif prefs.budget_currency and item.currency and not _same(prefs.budget_currency, item.currency):
            add("budget", None, "not_checked", f"Priced in {item.currency}; your budget is in {prefs.budget_currency.upper()}")
        elif item.price_min <= prefs.budget_max:
            add("budget", 1.0, "matched", f"{_price_text(item)} — within your budget")
        else:
            add("budget", 0.0, "missed", f"{_price_text(item)} — above your budget")

    if prefs.date_from or prefs.date_to:
        start, end = item.start_date, item.end_date or item.start_date
        after_from = prefs.date_from is None or end >= prefs.date_from
        before_to = prefs.date_to is None or start <= prefs.date_to
        if after_from and before_to:
            add("dates", 1.0, "matched", f"On {start.isoformat()}, inside your dates")
        else:
            add("dates", 0.0, "missed", f"On {start.isoformat()}, outside your dates")

    checked = [c for c in criteria if c.status != "not_checked"]
    if not checked:
        return None
    possible = sum(c.weight for c in checked)
    earned = sum(c.earned for c in checked)
    return MatchResult(
        percent=round(100 * earned / possible),
        earned=earned,
        possible=possible,
        reasons=[c.detail for c in checked if c.status in ("matched", "partial")],
        gaps=[c.detail for c in criteria if c.status in ("missed", "not_checked")],
        criteria=criteria,
    )


def _price_text(item: CatalogEvent) -> str:
    if item.is_free:
        return "Free"
    if item.price_min is None:
        return "Price not published"
    cur = f"{item.currency} " if item.currency else ""
    if item.price_max is not None and item.price_max != item.price_min:
        return f"{cur}{item.price_min:,.0f}–{item.price_max:,.0f}"
    return f"{cur}{item.price_min:,.0f}"


def price_text(item: CatalogEvent) -> str:
    return _price_text(item)


def rank(
    catalog: Iterable[CatalogEvent],
    prefs: Preferences,
    *,
    exclude: set[tuple[str, int]] | None = None,
    min_percent: int = 0,
) -> list[tuple[CatalogEvent, MatchResult]]:
    exclude = exclude or set()
    ranked: list[tuple[CatalogEvent, MatchResult]] = []
    for item in catalog:
        if (item.kind, item.id) in exclude:
            continue
        result = score_event(item, prefs)
        if result is None or result.percent < min_percent:
            continue
        ranked.append((item, result))
    ranked.sort(key=lambda pair: (-pair[1].percent, -pair[1].possible, pair[0].start_date))
    return ranked
