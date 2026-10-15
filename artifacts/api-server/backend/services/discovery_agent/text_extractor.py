"""Best-effort event reader for pages that publish no schema.org data —
fixed rules, no AI. Takes the page title, the first *upcoming* date written
in the page text, and a labelled venue ("Venue: …"). Returns nothing unless
both a title and a real future date are found, and every event it returns
is flagged `best_effort`, which validation always routes to NEEDS_REVIEW.
"""

import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_RANGE_END = r"(?:\s*(?:-|–|to)\s*\d{1,2}(?:st|nd|rd|th)?)?"
_YEAR = r"(20\d{2})"

# day-first: "18 Nov 2026", "18-20 November, 2026"; month-first: "November 18, 2026", "Nov 18th - 20th, 2026"; ISO.
_DAY_FIRST = re.compile(rf"\b{_DAY}{_RANGE_END}\s+{_MONTH},?\s+{_YEAR}\b", re.IGNORECASE)
_MONTH_FIRST = re.compile(rf"\b{_MONTH}\s+{_DAY}{_RANGE_END},?\s+{_YEAR}\b", re.IGNORECASE)
_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})(?!\d)")  # also inside "2026-11-17T09:00"

_VENUE = re.compile(r"\b(?:venue|location|where)\s*[:\-–]\s*([^\n|]{4,120})", re.IGNORECASE)

# Listing/index pages ("Business events in Mumbai") are not one event.
_LISTING_TITLE = re.compile(
    r"^\s*upcoming\b|^\s*all\s+\w+s\b|\bworldwide\b"
    r"|\b(events|conferences|summits|webinars|workshops|meetups|exhibitions|fairs|festivals|hackathons|seminars|expos)\s+(in|near|list|calendar|around)\b"
    r"|\b(list of|all upcoming|upcoming events)\b",
    re.IGNORECASE,
)

# Navigation words that a "Location:" label sometimes points at (breadcrumbs).
_NOT_A_VENUE = {"home", "menu", "contact", "about", "events", "n/a", "na", "tba", "tbd"}

_CITY_ALIASES = {"bengaluru": ("bangalore",), "mumbai": ("bombay",), "gurugram": ("gurgaon",), "delhi": ("new delhi",)}

_MAX_DAYS_AHEAD = 540


def extract_best_effort(source: CandidateSource, html: str, cities: list[str], today: date | None = None) -> ExtractedEventCandidate | None:
    soup = BeautifulSoup(html, "html.parser")
    title = _title(soup)
    if not title or _LISTING_TITLE.search(title):
        return None

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    event_date = _first_upcoming_date(text, today or date.today())
    if event_date is None:
        return None

    venue_match = _VENUE.search(text)
    venue = " ".join(venue_match.group(1).split()) if venue_match else None
    if venue and venue.lower().strip(" .") in _NOT_A_VENUE:
        venue = None

    return ExtractedEventCandidate(
        name=title,
        date=event_date.isoformat(),
        venue=venue,
        city=_find_city(" ".join(filter(None, [title, venue, text])), cities),
        country="India",
        url=source.url,
        extraction_confidence=30,
        primary_source=source,
        sources=[source],
        best_effort=True,
    )


def _title(soup: BeautifulSoup) -> str | None:
    og = soup.find("meta", attrs={"property": "og:title"})
    candidates = [og.get("content") if og else None]
    h1 = soup.find("h1")
    candidates.append(h1.get_text(" ", strip=True) if h1 else None)
    candidates.append(soup.title.get_text(" ", strip=True) if soup.title else None)
    for candidate in candidates:
        if candidate:
            # "Event Name | Site" / "Event Name - Site" -> "Event Name"
            first = re.split(r"\s+[|–—]\s+|\s+-\s+", candidate.strip())[0].strip()
            if len(first) >= 4:
                return first[:200]
    return None


def parse_written_date(raw: str) -> date | None:
    """The first date written in `raw` (any year): "22nd - 24th Dec 2026",
    "August 26-30, 2026", "2026-11-17T09:00:00+05:30"… Ranges give their first day."""
    found = _dates_in(raw)
    return min(found, key=lambda item: item[0])[1] if found else None


def _first_upcoming_date(text: str, today: date) -> date | None:
    found = _dates_in(text)
    latest = today + timedelta(days=_MAX_DAYS_AHEAD)
    for _, value in sorted(found, key=lambda item: item[0]):
        if today <= value <= latest:
            return value
    return None


def _dates_in(text: str) -> list[tuple[int, date]]:
    found: list[tuple[int, date | None]] = []
    for match in _DAY_FIRST.finditer(text):
        found.append((match.start(), _make_date(match.group(3), match.group(2), match.group(1))))
    for match in _MONTH_FIRST.finditer(text):
        found.append((match.start(), _make_date(match.group(3), match.group(1), match.group(2))))
    for match in _ISO.finditer(text):
        try:
            found.append((match.start(), date(int(match.group(1)), int(match.group(2)), int(match.group(3)))))
        except ValueError:
            continue
    return [(position, value) for position, value in found if value is not None]


def _make_date(year: str, month: str, day: str) -> date | None:
    month_number = _MONTHS.get(month.lower().rstrip(".")[:4]) or _MONTHS.get(month.lower().rstrip(".")[:3])
    try:
        return date(int(year), month_number, int(day)) if month_number else None
    except ValueError:
        return None


def _find_city(text: str, cities: list[str]) -> str | None:
    lowered = text.lower()
    for city in cities:
        names = (city.lower(), *_CITY_ALIASES.get(city.lower(), ()))
        if any(re.search(rf"\b{re.escape(name)}\b", lowered) for name in names):
            return city
    return None
