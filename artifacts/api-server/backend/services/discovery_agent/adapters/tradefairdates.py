"""TradeFairDates (www.tradefairdates.com, the English site of messeninfo.de)
— worldwide trade-fair directory.

How the site is laid out (checked 2026-10-27; robots.txt only disallows its
hotel pages):
- countries index /trade-shows-by-countries.php -> /Fairs-<Name>-Z<id>-S1.html
  (S2, S3 … next pages; names like "UAE", "USA", "India")
- each listing tile (.messeninfoTile): name + one-line description, dates
  ("25. - 27. October 2026", "30 Oct. - 02 Nov. 2026"), venue, city, country
- each show page (/<Name>-M<id>/<City>.html) carries a schema.org Event with
  start/end dates, venue address and the organizer's name + website.
It has no per-country industry lists, so a run reads the country pages and
the run's own sector rules keep the matching shows. The organizer step reads
the show page's declared organizer (it is a directory host, see platforms.py)
and follows its website for a public e-mail.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.tradefairdates")

BASE = "https://www.tradefairdates.com"
_COUNTRIES_PAGE = BASE + "/trade-shows-by-countries.php"
_MAX_PAGES = 6
# Our country names -> the site's (only where they differ beyond spelling).
_ALIASES = {
    "united arab emirates": "uae",
    "united states": "usa",
    "united kingdom": "united-kingdom-of-great-britain-and-northern-ireland",
    "bosnia and herzegovina": "bosniaherzegovina",
    "syria": "syrian",
    "korea, republic of": "south-korea",
}
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
# "25. - 27. October 2026" | "30 Oct. - 02 Nov. 2026" | "25. October 2026" | "October 2026"
_RANGE_SAME_MONTH = re.compile(r"^(\d{1,2})\.?\s*-\s*\d{1,2}\.?\s+([A-Za-z]+)\.?\s+(\d{4})")
_RANGE_TWO_MONTHS = re.compile(r"^(\d{1,2})\.?\s+([A-Za-z]+)\.?\s*-\s*\d{1,2}\.?\s+([A-Za-z]+)\.?\s+(\d{4})")
_SINGLE_DAY = re.compile(r"^(\d{1,2})\.?\s+([A-Za-z]+)\.?\s+(\d{4})")
_MONTH_ONLY = re.compile(r"^([A-Za-z]+)\.?\s+(\d{4})$")

_lock = threading.Lock()
_countries: tuple[float, dict[str, str]] = (0.0, {})
_TTL_SECONDS = 24 * 3600
_last_request = 0.0
_MIN_SECONDS_BETWEEN_REQUESTS = 1.0


def _fetch(url: str) -> str | None:
    global _last_request
    from backend.services.social_agent.web_fetch import fetch

    with _lock:
        wait = _last_request + _MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
    return fetch(url)


def _failure(url: str) -> str:
    from backend.services.social_agent.web_fetch import failure_reason

    return failure_reason(url) or "no response"


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def country_pages() -> dict[str, str]:
    """{site country name (normalised): first listing page path} from its index."""
    global _countries
    with _lock:
        fetched_at, pages = _countries
        if pages and time.time() - fetched_at < _TTL_SECONDS:
            return pages
    html = _fetch(_COUNTRIES_PAGE)
    if not html:
        raise SourceError("unreachable", f"{_COUNTRIES_PAGE}: {_failure(_COUNTRIES_PAGE)}")
    pages = {_key(name): f"/Fairs-{name}-Z{zid}-S1.html" for name, zid in re.findall(r'/Fairs-([^"/]+?)-Z(\d+)-S1\.html', html)}
    if not pages:
        raise SourceError("parse_error", "TradeFairDates countries index lists no countries (layout changed?)")
    with _lock:
        _countries = (time.time(), pages)
    return pages


def page_for_country(country: str, pages: dict[str, str]) -> str | None:
    key = _key(country)
    return pages.get(_ALIASES.get(country.strip().lower(), key)) or pages.get(key)


def parse_date(text: str) -> tuple[date | None, bool]:
    """(start date, exact day?) from a tile's date line."""
    text = " ".join((text or "").split())

    def month(name: str) -> int | None:
        return _MONTHS.get(name[:3].lower())

    for pattern, kind in ((_RANGE_TWO_MONTHS, "two"), (_RANGE_SAME_MONTH, "same"), (_SINGLE_DAY, "single")):
        m = pattern.match(text)
        if not m:
            continue
        try:
            if kind == "two":
                day, m1, m2, year = int(m.group(1)), month(m.group(2)), month(m.group(3)), int(m.group(4))
                if not m1 or not m2:
                    return None, False
                return date(year - 1 if m1 > m2 else year, m1, day), True  # "30 Dec. - 02 Jan. 2027"
            day, mon, year = int(m.group(1)), month(m.group(2)), int(m.group(3))
            return (date(year, mon, day), True) if mon else (None, False)
        except ValueError:
            return None, False
    m = _MONTH_ONLY.match(text)
    if m and month(m.group(1)):
        return date(int(m.group(2)), month(m.group(1)), 1), False
    return None, False


def parse_listing(html: str, page_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tile in soup.select(".messeninfoTile"):
        title = tile.select_one(".tileMeta a.title")
        if title is None or not title.get("href"):
            continue
        when = tile.select_one(".headBottom .time")
        venue = tile.select_one(".messeTerminZentrum a")
        city = tile.select_one(".messeTerminOrt")
        description = tile.select_one(".tileMeta .description")
        rows.append({
            "name": title.get_text(" ", strip=True),
            "url": urljoin(page_url, title["href"]),
            "date_text": when.get_text(" ", strip=True) if when else "",
            "description": description.get_text(" ", strip=True) if description else None,
            "venue": venue.get_text(" ", strip=True) if venue else None,
            "city": city.get_text(" ", strip=True) if city else None,
        })
    return rows


class TradeFairDatesAdapter(BaseSourceAdapter):
    """Site-specific reader for www.tradefairdates.com (see module docstring)."""

    access_method = "html_listing"

    def __init__(self, source_id: str = "tradefairdates", name: str = "TradeFairDates", website_url: str = "https://www.tradefairdates.com/",
                 category: str = "Global Event Discovery", config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.category = category

    def listing_template(self) -> str:
        return BASE + "/Fairs-{country}-Z<id>-S1.html"

    def _country_lists(self, config: DiscoveryConfig) -> list[tuple[str, str]]:
        from backend.services.discovery_agent import geo_scope

        geo = geo_scope.resolve(config)
        if not geo.countries:
            return []
        pages = country_pages()
        return [(country, BASE + path) for country in geo.countries if (path := page_for_country(country, pages))]

    def target_urls(self, config: DiscoveryConfig | None, max_urls: int = 5) -> list[str]:
        try:
            return [url for _, url in self._country_lists(config or DiscoveryConfig())][:max_urls]
        except SourceError:
            return []

    def discover(self, config: DiscoveryConfig, limit: int = 25) -> list[ExtractedEventCandidate]:
        lists = self._country_lists(config)
        if not lists:
            raise SourceError("not_configured", "TradeFairDates lists shows by country: select a country it covers")
        today = date.today()
        until = _iso(getattr(config, "date_to", None))
        limit = max(limit, 120)  # rows are cheap; the sector rules filter them next
        per_country: dict[str, list[ExtractedEventCandidate]] = {}
        failures: list[str] = []
        read_any = False
        for country, first_page in lists:
            for page in range(1, _MAX_PAGES + 1):
                url = re.sub(r"-S\d+\.html$", f"-S{page}.html", first_page)
                html = _fetch(url)
                if not html:
                    if page == 1:
                        failures.append(f"{url}: {_failure(url)}")
                    break
                read_any = True
                rows = parse_listing(html, url)
                if not rows:
                    break
                for row in rows:
                    start, exact = parse_date(row["date_text"])
                    if start is None or (exact and start < today) or (not exact and (start.year, start.month) < (today.year, today.month)):
                        continue
                    if until and start > until:
                        continue
                    per_country.setdefault(country, []).append(self._candidate(row, start, exact, country))
                if f"-S{page + 1}.html" not in html:
                    break  # no link to a next page
        if not read_any and failures:
            raise SourceError("unreachable", "; ".join(failures[:3]))
        ordered: list[ExtractedEventCandidate] = []
        queues = [list(v) for v in per_country.values()]
        while queues and len(ordered) < limit:
            for queue in list(queues):
                if queue:
                    ordered.append(queue.pop(0))
                if not queue:
                    queues.remove(queue)
        return ordered[:limit]

    def _candidate(self, row: dict[str, Any], start: date, exact: bool, country: str) -> ExtractedEventCandidate:
        source = CandidateSource(url=row["url"], source_type="event_directory", source_website=self.name)
        return ExtractedEventCandidate(
            name=row["name"],
            event_description=row.get("description"),
            date=start.isoformat() if exact else start.strftime("%B %Y"),
            venue=row.get("venue"),
            city=row.get("city"),
            country=country,
            url=row["url"],
            event_format="offline",
            extraction_confidence=85 if exact else 60,
            primary_source=source,
            sources=[source],
            raw_evidence={"source_id": self.source_id, "tradefairdates_date": row.get("date_text")},
            best_effort=not exact,
        )

    def check_health(self) -> dict[str, Any]:
        start = time.time()
        try:
            pages = country_pages()
        except SourceError as exc:
            return {"status": "unreachable", "latency_ms": round((time.time() - start) * 1000, 1), "error": str(exc), "details": {}}
        return {"status": "healthy", "latency_ms": round((time.time() - start) * 1000, 1), "error": None, "details": {"countries": len(pages)}}

    def test_extraction(self, sample_query_or_url: str | None = None) -> dict[str, Any]:
        start = time.time()
        try:
            events = self.discover(DiscoveryConfig(countries=["United Arab Emirates"]), limit=10)
        except SourceError as exc:
            return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": round((time.time() - start) * 1000, 1), "error": str(exc)}
        samples = [{"name": e.name, "date": e.date, "city": e.city, "country": e.country, "venue": e.venue, "url": e.url} for e in events[:5]]
        return {"success": True, "events_found": len(events), "sample_events": samples, "duration_ms": round((time.time() - start) * 1000, 1), "error": None,
                "note": None if events else "TradeFairDates read, but it lists no upcoming shows for the sample country"}


def _iso(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None
