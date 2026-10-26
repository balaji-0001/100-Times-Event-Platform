"""Turn an attendee's natural-language question into structured filters.

"Find 10 AI conferences in India" -> count=10, topics=[ai],
event_types=[conference], countries=[India].

Rule-based parsing always runs and is authoritative for whatever it
detects. When an AI provider is configured, the model is asked for the
SAME filter fields (never for events) and may only fill fields the rules
left empty; every AI-supplied value is validated against known
vocabularies (real country names, the categorizer's sectors, known event
types) and dropped if it doesn't validate. The assistant then answers from
the real catalog with these filters — the model never sees, writes or
ranks events.
"""

from __future__ import annotations

import calendar
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from backend.services.attendee_agent.matching import EVENT_TYPE_ALIASES, TOPIC_SYNONYMS
from backend.services.discovery_agent import categorizer
from backend.services.discovery_agent.country_utils import ALL_WORLD_COUNTRIES, MAJOR_CITY_TO_COUNTRY

logger = logging.getLogger("attendee_agent.query_parser")

DEFAULT_COUNT = 10
MAX_COUNT = 50
SECTORS = tuple(c for c in categorizer.CATEGORIES if c != "Other")

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
}
_COUNTRY_PHRASES: dict[str, str] = {
    "usa": "United States", "u.s.a.": "United States", "u.s.": "United States", "america": "United States",
    "united states of america": "United States", "the us": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "britain": "United Kingdom", "great britain": "United Kingdom",
    "england": "United Kingdom", "uae": "United Arab Emirates", "emirates": "United Arab Emirates",
    "dubai": "United Arab Emirates", "ksa": "Saudi Arabia", "bharat": "India",
}
_WORLDWIDE = re.compile(r"\b(worldwide|world ?wide|global(?:ly)?|anywhere|international(?:ly)?|around the world|all countries)\b")
_PROFILE = re.compile(r"\b(my profile|my preferences|my interests|for me|matching me|match me|recommend(?:ed|ations?)?|suggest(?:ions)?)\b")
_FREE = re.compile(r"\b(free|no cost|zero cost|complimentary)\b")
_PRICE = re.compile(
    r"\b(?:under|below|less than|cheaper than|up ?to|max(?:imum)?|within)\s*"
    r"(rs\.?|inr|₹|\$|usd|€|eur|£|gbp)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?\s*(rs|inr|rupees|usd|dollars|eur|euros|gbp|pounds)?",
)
_CURRENCY_MAP = {
    "rs": "INR", "rs.": "INR", "inr": "INR", "₹": "INR", "rupees": "INR",
    "$": "USD", "usd": "USD", "dollars": "USD",
    "€": "EUR", "eur": "EUR", "euros": "EUR",
    "£": "GBP", "gbp": "GBP", "pounds": "GBP",
}
_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_MONTHS.pop("may", None)  # handled separately — "may" is also a verb
_MONTHS["may"] = 5


@dataclass
class ParsedQuery:
    count: int = DEFAULT_COUNT
    count_requested: bool = False
    sectors: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    worldwide: bool = False
    event_types: list[str] = field(default_factory=list)
    mode: str | None = None
    free_only: bool = False
    max_price: Decimal | None = None
    currency: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    date_label: str | None = None
    use_profile: bool = False
    parser: str = "rules"

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["max_price"] = float(self.max_price) if self.max_price is not None else None
        out["date_from"] = self.date_from.isoformat() if self.date_from else None
        out["date_to"] = self.date_to.isoformat() if self.date_to else None
        return out


def _word(phrase: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")


def _parse_count(text: str) -> int | None:
    # Strip price phrases and years first so "under 500" / "2027" never read as a count.
    cleaned = _PRICE.sub(" ", text)
    cleaned = re.sub(r"\b(19|20)\d{2}\b", " ", cleaned)
    cleaned = re.sub(r"\bnext \d+ (?:days?|weeks?|months?)\b", " ", cleaned)
    m = re.search(r"(?<![\d.])\b(\d{1,3})\b(?!\s*(?:%|days?|weeks?|months?|am|pm|st|nd|rd|th)\b)", cleaned)
    if m:
        value = int(m.group(1))
        if 1 <= value <= 500:
            return min(value, MAX_COUNT)
    for word, value in _NUMBER_WORDS.items():
        if re.search(rf"\b(?:find|show|list|top|get|give me|recommend|suggest)\s+{word}\b", cleaned):
            return value
    return None


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _parse_dates(text: str, today: date) -> tuple[date | None, date | None, str | None]:
    if re.search(r"\btoday\b", text):
        return today, today, "today"
    if re.search(r"\btomorrow\b", text):
        d = today + timedelta(days=1)
        return d, d, "tomorrow"
    if re.search(r"\b(this|coming) weekend\b", text) or re.search(r"\bweekend\b", text) and "next weekend" not in text:
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        if today.weekday() == 6:
            saturday = today - timedelta(days=1)
        start = max(today, saturday)
        return start, saturday + timedelta(days=1), "this weekend"
    if re.search(r"\bnext weekend\b", text):
        saturday = today + timedelta(days=(5 - today.weekday()) % 7 + 7)
        return saturday, saturday + timedelta(days=1), "next weekend"
    if re.search(r"\bthis week\b", text):
        return today, today + timedelta(days=6 - today.weekday()), "this week"
    if re.search(r"\bnext week\b", text):
        start = today + timedelta(days=7 - today.weekday())
        return start, start + timedelta(days=6), "next week"
    m = re.search(r"\bnext (\d{1,3}) (day|week|month)s?\b", text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = n * {"day": 1, "week": 7, "month": 30}[unit]
        return today, today + timedelta(days=days), f"next {n} {unit}s"
    if re.search(r"\bthis month\b", text):
        _, end = _month_range(today.year, today.month)
        return today, end, "this month"
    if re.search(r"\bnext month\b", text):
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        start, end = _month_range(year, month)
        return start, end, "next month"
    if re.search(r"\bthis year\b", text):
        return today, date(today.year, 12, 31), "this year"
    if re.search(r"\bnext year\b", text):
        return date(today.year + 1, 1, 1), date(today.year + 1, 12, 31), "next year"
    for name, month in _MONTHS.items():
        if name == "may" and not re.search(r"\b(in|during|this|next|for)\s+may\b|\bmay\s+(19|20)\d{2}\b", text):
            continue
        m = re.search(rf"\b{name}\b\.?\s*((?:19|20)\d{{2}})?", text)
        if m:
            year = int(m.group(1)) if m.group(1) else (today.year if month >= today.month else today.year + 1)
            start, end = _month_range(year, month)
            return max(start, today) if year == today.year and month == today.month else start, end, f"{calendar.month_name[month]} {year}"
    m = re.search(r"\b(?:in|during)\s+((?:19|20)\d{2})\b", text)
    if m:
        year = int(m.group(1))
        return max(date(year, 1, 1), today), date(year, 12, 31), str(year)
    return None, None, None


def _parse_price(text: str) -> tuple[Decimal | None, str | None]:
    m = _PRICE.search(text)
    if not m:
        return None, None
    try:
        value = Decimal(m.group(2).replace(",", ""))
    except InvalidOperation:
        return None, None
    if m.group(3):
        value *= 1000
    cur = _CURRENCY_MAP.get((m.group(1) or m.group(4) or "").lower())
    return value, cur


def _parse_countries(text: str, original: str) -> list[str]:
    found: list[str] = []
    for phrase, country in _COUNTRY_PHRASES.items():
        if _word(phrase).search(text) and country not in found:
            found.append(country)
    if re.search(r"(?<![A-Za-z])US(?![A-Za-z])", original) and "United States" not in found:
        found.append("United States")
    for country in ALL_WORLD_COUNTRIES:
        if country == "Dubai":
            continue
        if _word(country.lower()).search(text) and country not in found:
            found.append(country)
    return found


def _parse_cities(text: str, known_cities: Iterable[str]) -> list[str]:
    names = {c.strip(): None for c in known_cities if c and len(c.strip()) > 2}
    for city in MAJOR_CITY_TO_COUNTRY:
        names.setdefault(city.title(), None)
    out: list[str] = []
    for city in names:
        if city.lower() == "dubai":
            continue  # treated as a country alias (UAE) — the data stores it both ways
        if _word(city.lower()).search(text) and city not in out:
            out.append(city)
    return out


def _parse_topics(text: str) -> list[str]:
    return [topic for topic in TOPIC_SYNONYMS if _word(topic).search(text)]


def _parse_event_types(text: str) -> list[str]:
    types: list[str] = []
    for canonical, aliases in EVENT_TYPE_ALIASES.items():
        if any(re.search(rf"(?<![a-z]){re.escape(a)}(?:e?s)?(?![a-z])", text) for a in aliases):
            types.append(canonical)
    return types


def _parse_sectors(text: str) -> list[str]:
    direct = [s for s in SECTORS if _word(s.lower()).search(text)]
    if direct:
        return direct
    # Event-type words ("trade show", "expo") would otherwise read as sector
    # keywords ("trade" -> Finance), so strip them before categorizing.
    for aliases in EVENT_TYPE_ALIASES.values():
        for alias in aliases:
            text = re.sub(rf"(?<![a-z]){re.escape(alias)}(?:e?s)?(?![a-z])", " ", text)
    sector, _ = categorizer.categorize(text, supported_categories=categorizer.CATEGORIES)
    return [sector] if sector in SECTORS else []


def _parse_mode(text: str) -> str | None:
    if re.search(r"\bhybrid\b", text):
        return "hybrid"
    if re.search(r"\b(online|virtual|remote|webinars?|livestream)\b", text):
        return "online"
    if re.search(r"\b(in[- ]person|offline|physical|on[- ]site)\b", text):
        return "offline"
    return None


def parse_rules(message: str, today: date, known_cities: Iterable[str] = ()) -> ParsedQuery:
    text = re.sub(r"\s+", " ", message.lower()).strip()
    parsed = ParsedQuery()
    count = _parse_count(text)
    if count:
        parsed.count, parsed.count_requested = count, True
    parsed.worldwide = bool(_WORLDWIDE.search(text))
    parsed.cities = _parse_cities(text, known_cities)
    parsed.countries = [] if parsed.worldwide else _parse_countries(text, message)
    parsed.topics = _parse_topics(text)
    parsed.event_types = _parse_event_types(text)
    parsed.sectors = _parse_sectors(text)
    parsed.mode = _parse_mode(text)
    if "webinar" in parsed.event_types and parsed.mode is None:
        parsed.mode = "online"
    parsed.free_only = bool(_FREE.search(text))
    if not parsed.free_only:
        parsed.max_price, parsed.currency = _parse_price(text)
    parsed.date_from, parsed.date_to, parsed.date_label = _parse_dates(text, today)
    parsed.use_profile = bool(_PROFILE.search(text))
    return parsed


_AI_SCHEMA = {
    "type": "object",
    "properties": {
        "count": {"type": "integer", "description": "How many events the user asked for; 0 if not stated"},
        "sectors": {"type": "array", "items": {"type": "string"}, "description": f"Industry sectors, only from: {', '.join(SECTORS)}"},
        "topics": {"type": "array", "items": {"type": "string"}, "description": "Specific subject keywords, e.g. 'ai', 'blockchain'"},
        "countries": {"type": "array", "items": {"type": "string"}, "description": "Full English country names"},
        "cities": {"type": "array", "items": {"type": "string"}},
        "worldwide": {"type": "boolean"},
        "event_types": {"type": "array", "items": {"type": "string"}, "description": f"Only from: {', '.join(EVENT_TYPE_ALIASES)}"},
        "mode": {"type": "string", "description": "online, offline, hybrid, or empty"},
        "free_only": {"type": "boolean"},
        "date_from": {"type": "string", "description": "YYYY-MM-DD or empty"},
        "date_to": {"type": "string", "description": "YYYY-MM-DD or empty"},
        "use_profile": {"type": "boolean", "description": "True if the user wants results matched to their own profile"},
    },
    "required": ["count", "sectors", "topics", "countries", "cities", "worldwide", "event_types", "mode", "free_only", "date_from", "date_to", "use_profile"],
}


def _iso(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _merge_ai(parsed: ParsedQuery, data: dict[str, Any], today: date) -> None:
    valid_countries = {c.lower(): c for c in ALL_WORLD_COUNTRIES if c != "Dubai"}
    if not parsed.count_requested:
        try:
            count = int(data.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if 1 <= count <= 500:
            parsed.count, parsed.count_requested = min(count, MAX_COUNT), True
    if not parsed.sectors:
        parsed.sectors = [s for s in SECTORS if any(str(x).strip().lower() == s.lower() for x in data.get("sectors") or [])]
    if not parsed.topics:
        parsed.topics = [str(t).strip().lower() for t in data.get("topics") or [] if 1 < len(str(t).strip()) <= 40][:5]
    if not parsed.countries and not parsed.worldwide:
        if data.get("worldwide") is True:
            parsed.worldwide = True
        else:
            parsed.countries = [valid_countries[str(c).strip().lower()] for c in data.get("countries") or [] if str(c).strip().lower() in valid_countries]
    if not parsed.event_types:
        parsed.event_types = [t for t in EVENT_TYPE_ALIASES if any(str(x).strip().lower() == t for x in data.get("event_types") or [])]
    if parsed.mode is None and str(data.get("mode") or "").lower() in ("online", "offline", "hybrid"):
        parsed.mode = str(data["mode"]).lower()
    if not parsed.free_only and data.get("free_only") is True:
        parsed.free_only = True
    if parsed.date_from is None and parsed.date_to is None:
        start, end = _iso(data.get("date_from")), _iso(data.get("date_to"))
        if start or end:
            if not (start and end and end < start):
                parsed.date_from, parsed.date_to = start, end
                parsed.date_label = f"{start.isoformat() if start else '…'} to {end.isoformat() if end else '…'}"
    if not parsed.use_profile and data.get("use_profile") is True:
        parsed.use_profile = True


def parse_query(message: str, today: date | None = None, known_cities: Iterable[str] = (), ai_client: Any | None = None) -> ParsedQuery:
    today = today or date.today()
    parsed = parse_rules(message, today, known_cities)
    if ai_client is None or not getattr(ai_client, "is_configured", False):
        return parsed
    try:
        data = ai_client.generate_structured(
            system=(
                f"Today is {today.isoformat()}. Convert the user's event-search request into filter fields. "
                "Only extract what the user actually said; leave everything else empty. Never suggest or name events."
            ),
            user=message,
            tool_name="event_search_filters",
            tool_description="Structured filters for searching a verified event catalog",
            input_schema=_AI_SCHEMA,
            max_tokens=400,
        )
    except Exception as exc:  # any provider/network/quota failure -> rules only
        logger.warning("AI query parsing unavailable, using rules only: %s", exc)
        return parsed
    if isinstance(data, dict):
        _merge_ai(parsed, data, today)
        parsed.parser = "rules+ai"
    return parsed
