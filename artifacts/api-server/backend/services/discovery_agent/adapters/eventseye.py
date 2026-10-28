"""EventsEye (www.eventseye.com) — worldwide trade-show directory.

How the site is laid out (checked 2026-10-27; it publishes no robots.txt):
- country pages      /fairs/c1_trade-shows_<country>.html          (+ _1, _2 … 50 rows each, by date)
- country x industry /fairs/cst1_trade-shows_<country>_<industry>.html (same table, same paging)
- industry worldwide /fairs/st1_trade-shows_<industry>.html
- one show           /fairs/f-<slug>-<id>-<n>.html — official website, the
  organizer(s) with their public phone / website / e-mail, the event e-mail.
Country slugs are irregular ("uae-united-arab-emirates",
"usa-united-states-of-america"), so they are read from the site's own location
index pages instead of guessed.

Every listing row is a `table.tradeshows` row: name + one-line description,
cycle, city + venue, date ("08/20/2026" + duration, or "Dec. 2026 (?)" when
EventsEye has only the month). A run reads, for each selected country, the
country x industry pages of the selected sectors (or the whole country list
when no sector maps to an EventsEye industry), keeps upcoming shows only, and
returns one candidate per show pointing at its EventsEye page; the organizer
step then reads that page's organizer block (`parse_detail`) — not the
venue's contact details, which the same page also lists.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.eventseye")

BASE = "https://www.eventseye.com/fairs/"
_INDEX_PAGES = (
    "trade-shows-by-location.html",
    "z1_trade-shows_europe.html",
    "z1_trade-shows_asia-pacific.html",
    "z1_trade-shows_africa-middle-east.html",
    "z1_trade-shows_america.html",
)
# Our sectors -> EventsEye industries (slugs verified on the site, 2026-10-27).
# A sector not listed here is searched through the whole country list and
# filtered by the run's own sector rules.
SECTOR_INDUSTRIES: dict[str, tuple[str, ...]] = {
    "Construction": (
        "building-construction", "architecture", "building-machinery", "roads-bridges-tunnels",
        "stone-marble-ceramics", "industrial-building", "heating-air-conditioning", "urban-equipment-engineering",
    ),
    "Energy and Power Generation": ("energy-production-transportation", "nuclear-power"),
    "Oil and Gas": ("oil-gas",),
    "Mining": ("mining-technologies",),
    "Packaging": ("packaging",),
    "Pharmaceuticals": ("pharmaceuticals-cosmetology",),
}
# Worldwide runs (no country selected) for sectors without an industry list
# above use EventsEye's broader theme pages (slugs from its homepage, 2026-10-27).
SECTOR_THEMES: dict[str, tuple[str, ...]] = {
    "Technology": ("ict-information-communications-technologies", "industrial-data-computing"),
    "Telecommunications": ("ict-information-communications-technologies",),
    "Finance": ("banks-insurance-investors",),
    "Healthcare": ("healthcare-pharmaceuticals",),
    "Manufacturing": ("industrial-fairs", "techniques-process-equipment"),
    "Transport and Logistics": ("logistics-transport-packaging", "shipping-railways-engineering"),
    "Textiles": ("fashion-apparel-textiles-leather-fur",),
}
_PAGE_ROWS = 50  # a full page means there may be a next one
_MAX_PAGES_PER_LIST = 4
_US_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_MONTH_ONLY = re.compile(r"^([A-Z][a-z]{2,8})\.? (\d{4})")
_DAYS = re.compile(r"(\d+)\s*days?")
_DETAIL_URL = re.compile(r"^https?://(www\.)?eventseye\.com/fairs/f-[^/]+\.html$", re.I)

_slug_lock = threading.Lock()
_country_slugs: tuple[float, list[str]] = (0.0, [])
_SLUG_TTL_SECONDS = 24 * 3600


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def is_detail_url(url: str | None) -> bool:
    return bool(url and _DETAIL_URL.match(url))


_pace_lock = threading.Lock()
_last_request = 0.0
_MIN_SECONDS_BETWEEN_REQUESTS = 1.0  # a polite visitor: one EventsEye page per second


def _fetch(url: str) -> str | None:
    """One EventsEye page (served from the shared page cache when fresh)."""
    global _last_request
    from backend.services.social_agent.web_fetch import fetch

    with _pace_lock:
        wait = _last_request + _MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
    return fetch(url)


def _failure(url: str) -> str:
    from backend.services.social_agent.web_fetch import failure_reason

    return failure_reason(url) or "no response"


def country_slugs() -> list[str]:
    """Every country slug EventsEye has a page for, from its own index pages."""
    global _country_slugs
    with _slug_lock:
        fetched_at, slugs = _country_slugs
        if slugs and time.time() - fetched_at < _SLUG_TTL_SECONDS:
            return slugs
    found: set[str] = set()
    errors: list[str] = []
    for page in _INDEX_PAGES:
        html = _fetch(BASE + page)
        if not html:
            errors.append(f"{page}: {_failure(BASE + page)}")
            continue
        found.update(re.findall(r'href="c1_trade-shows_([a-z0-9-]+)\.html"', html))
    if not found:
        raise SourceError("unreachable", "EventsEye location index could not be read: " + "; ".join(errors[:2]))
    with _slug_lock:
        _country_slugs = (time.time(), sorted(found))
    return sorted(found)


def slug_for_country(country: str, slugs: list[str]) -> str | None:
    """'United Arab Emirates' -> 'uae-united-arab-emirates', 'India' -> 'india'."""
    want = _slugify(country)
    if want in slugs:
        return want
    matches = [s for s in slugs if f"-{want}-" in f"-{s}-"]
    return min(matches, key=len) if matches else None


def parse_listing(html: str, page_url: str) -> tuple[list[dict[str, Any]], int]:
    """(rows, number of table rows) of one listing page."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.tradeshows")
    if table is None:
        return [], 0
    caption = table.find("caption")
    rows: list[dict[str, Any]] = []
    trs = table.select("tbody tr")
    for tr in trs:
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue
        link = cells[0].find("a", href=True)
        title = cells[0].find("b")
        if link is None or title is None:
            continue
        description = cells[0].find("i")
        place_links = cells[2].find_all("a", href=True)
        city = next((a.get_text(" ", strip=True) for a in place_links if a["href"].startswith("cy1_")), None)
        row_country = None
        place = re.match(r"^(.*?)\s*\(([^()]+)\)$", city or "")  # worldwide lists: "Istanbul (Turkey)"
        if place:
            city, row_country = place.group(1).strip() or None, place.group(2).strip()
        venue = next((a.get_text(" ", strip=True) for a in place_links if a["href"].startswith("pl1_")), None)
        date_cell = cells[3]
        date_text = date_cell.contents[0].strip() if date_cell.contents and isinstance(date_cell.contents[0], str) else date_cell.get_text(" ", strip=True)
        duration = _DAYS.search(date_cell.get_text(" ", strip=True))
        rows.append({
            "name": title.get_text(" ", strip=True),
            "description": description.get_text(" ", strip=True) if description else None,
            "cycle": cells[1].get_text(" ", strip=True) or None,
            "city": city,
            "country": row_country,
            "venue": venue,
            "date_text": date_text,
            "duration_days": int(duration.group(1)) if duration else None,
            "url": urljoin(page_url, link["href"]),
            "list_title": caption.get_text(" ", strip=True) if caption else None,
        })
    return rows, len(trs)


def row_date(date_text: str) -> tuple[date | None, bool]:
    """(start date, exact?) — '08/20/2026' is exact; 'Dec. 2026 (?)' is month-only."""
    text = (date_text or "").strip()
    match = _US_DATE.match(text)
    if match:
        month, day, year = (int(g) for g in match.groups())
        try:
            return date(year, month, day), True
        except ValueError:
            return None, False
    match = _MONTH_ONLY.match(text)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)[:3]} {match.group(2)}", "%b %Y").date(), False
        except ValueError:
            return None, False
    return None, False


def parse_detail(html: str) -> dict[str, Any]:
    """The show's own contacts (official site, event e-mail) and its
    organizers' public contacts. The venue block is ignored."""
    soup = BeautifulSoup(html, "html.parser")

    def mail(node) -> str | None:
        for a in node.select("a.ev-mail[href^='mailto:']"):
            address = a["href"][len("mailto:"):].split("?", 1)[0].strip()
            if "@" in address:
                return address
        return None

    def web(node) -> str | None:
        a = node.select_one("a.ev-web[href^='http']")
        return a["href"].strip() if a else None

    def phone(node) -> str | None:
        el = node.select_one(".ev-phone")
        value = el.get_text(" ", strip=True) if el else ""
        return value or None

    organizers = []
    for org in soup.select(".orgs .org"):
        name = org.select_one("a.orglink")
        organizers.append({
            "name": name.get_text(" ", strip=True) if name else None,
            "website": web(org),
            "email": mail(org),
            "phone": phone(org),
        })
    info = soup.select_one(".more-info")
    return {
        "event_website": web(info) if info else None,
        "event_email": mail(info) if info else None,
        "event_phone": phone(info) if info else None,
        "organizers": organizers,
    }


class EventsEyeAdapter(BaseSourceAdapter):
    """Site-specific reader for www.eventseye.com (see module docstring)."""

    access_method = "html_listing"

    def __init__(self, source_id: str = "eventseye", name: str = "EventsEye", website_url: str = "https://www.eventseye.com/",
                 category: str = "Global Event Discovery", config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.category = category

    def listing_template(self) -> str:
        return BASE + "c1_trade-shows_{country}.html"

    def _lists(self, config: DiscoveryConfig) -> list[tuple[str, str, str | None]]:
        """(country, list base URL without .html, industry label) for this run."""
        from backend.services.discovery_agent import geo_scope

        geo = geo_scope.resolve(config)
        industries: list[str] = []
        if getattr(config, "sector_scoped", False) or (config.categories and len(config.categories) < 6):
            for sector in config.categories or []:
                industries.extend(SECTOR_INDUSTRIES.get(sector, ()))
            if any(sector not in SECTOR_INDUSTRIES for sector in config.categories or []):
                industries = []  # an unmapped sector: read whole-country lists, filtered later
        lists: list[tuple[str, str, str | None]] = []
        if geo.countries:
            slugs = country_slugs()
            for country in geo.countries:
                slug = slug_for_country(country, slugs)
                if not slug:
                    continue
                if industries:
                    lists.extend((country, f"{BASE}cst1_trade-shows_{slug}_{ind}", ind) for ind in dict.fromkeys(industries))
                else:
                    lists.append((country, f"{BASE}c1_trade-shows_{slug}", None))
        elif config.categories and len(config.categories) < 6:
            # Worldwide: each selected sector's industry lists, else its theme pages.
            for sector in config.categories:
                for ind in SECTOR_INDUSTRIES.get(sector, ()):
                    lists.append((None, f"{BASE}st1_trade-shows_{ind}", ind))
                if sector not in SECTOR_INDUSTRIES:
                    lists.extend((None, f"{BASE}t1_trade-shows_{theme}", theme) for theme in SECTOR_THEMES.get(sector, ()))
            lists = list(dict.fromkeys(lists))
        return lists

    def target_urls(self, config: DiscoveryConfig | None, max_urls: int = 5) -> list[str]:
        return [f"{base}.html" for _, base, _ in self._lists(config or DiscoveryConfig())][:max_urls]

    def discover(self, config: DiscoveryConfig, limit: int = 25) -> list[ExtractedEventCandidate]:
        lists = self._lists(config)
        if not lists:
            countries = ", ".join(config.countries or []) or "worldwide"
            raise SourceError("not_configured", f"EventsEye has no list for this selection ({countries}); pick a country it covers or a sector it maps")
        today = date.today()
        until = _parse_iso(getattr(config, "date_to", None))
        limit = max(limit, 60)  # rows are cheap: no extra request per show
        per_country: dict[str | None, list[ExtractedEventCandidate]] = {}
        seen: set[str] = set()
        failures: list[str] = []
        read_any = False
        for country, base, industry in lists:
            for page in range(_MAX_PAGES_PER_LIST):
                url = f"{base}.html" if page == 0 else f"{base}_{page}.html"
                html = _fetch(url)
                if not html:
                    if page == 0:
                        failures.append(f"{url}: {_failure(url)}")
                    break
                read_any = True
                rows, row_count = parse_listing(html, url)
                for row in rows:
                    if row["url"] in seen:
                        continue
                    start, exact = row_date(row["date_text"])
                    if start is None or (exact and start < today) or (not exact and (start.year, start.month) < (today.year, today.month)):
                        continue
                    if until and start > until:
                        continue
                    seen.add(row["url"])
                    # Worldwide lists name only the city: its country when the city is unambiguous.
                    row_country = country or _canonical(row.get("country")) or _country_of_city(row.get("city"))
                    per_country.setdefault(country, []).append(self._candidate(row, start, exact, row_country, industry))
                if row_count < _PAGE_ROWS:
                    break
        if not read_any and failures:
            raise SourceError("unreachable", "; ".join(failures[:3]))
        # Interleave countries so one big country can't fill the limit alone.
        ordered: list[ExtractedEventCandidate] = []
        queues = [list(v) for v in per_country.values()]
        while queues and len(ordered) < limit:
            for queue in list(queues):
                if queue:
                    ordered.append(queue.pop(0))
                if not queue:
                    queues.remove(queue)
        return ordered[:limit]

    def _candidate(self, row: dict[str, Any], start: date, exact: bool, country: str | None, industry: str | None) -> ExtractedEventCandidate:
        source = CandidateSource(url=row["url"], source_type="event_directory", source_website=self.name)
        # The directory's own industry label helps the sector rules read short rows.
        label = (row.get("list_title") or "").split(" related to ", 1)[-1] if industry else None
        description = " ".join(filter(None, [row.get("description"), f"(EventsEye industry: {label})" if label else None])) or None
        return ExtractedEventCandidate(
            name=row["name"],
            event_description=description,
            date=start.isoformat() if exact else start.strftime("%B %Y"),
            venue=row.get("venue"),
            city=row.get("city"),
            country=country,
            url=row["url"],
            event_format="offline",
            extraction_confidence=85 if exact else 60,
            primary_source=source,
            sources=[source],
            raw_evidence={
                "source_id": self.source_id,
                "cycle": row.get("cycle"),
                "duration_days": row.get("duration_days"),
                "end_date": (start + timedelta(days=row["duration_days"] - 1)).isoformat() if exact and row.get("duration_days") else None,
                "eventseye_date": row.get("date_text"),
            },
            # EventsEye marks month-only dates "(?)": a person confirms those.
            best_effort=not exact,
        )

    def check_health(self) -> dict[str, Any]:
        start = time.time()
        try:
            slugs = country_slugs()
        except SourceError as exc:
            return {"status": "unreachable", "latency_ms": round((time.time() - start) * 1000, 1), "error": str(exc), "details": {}}
        return {"status": "healthy", "latency_ms": round((time.time() - start) * 1000, 1), "error": None, "details": {"countries": len(slugs)}}

    def test_extraction(self, sample_query_or_url: str | None = None) -> dict[str, Any]:
        start = time.time()
        config = DiscoveryConfig(countries=["India", "United Arab Emirates"], categories=["Construction"])
        config.sector_scoped = True
        try:
            events = self.discover(config, limit=10)
        except SourceError as exc:
            return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": round((time.time() - start) * 1000, 1), "error": str(exc)}
        samples = [{"name": e.name, "date": e.date, "city": e.city, "country": e.country, "venue": e.venue, "url": e.url} for e in events[:5]]
        return {"success": True, "events_found": len(events), "sample_events": samples, "duration_ms": round((time.time() - start) * 1000, 1), "error": None,
                "note": None if events else "EventsEye read, but it lists no upcoming shows for the sample selection"}


def _canonical(country: str | None) -> str | None:
    from backend.services.discovery_agent import geo_scope

    if not country:
        return None
    if country.lower().startswith(("uk -", "usa -", "uae -")):  # "UK - United Kingdom"
        country = country.split("-", 1)[1]
    return geo_scope.canonical_country(country.strip()) or country.strip()


def _country_of_city(city: str | None) -> str | None:
    from backend.services.discovery_agent import geo_scope
    from backend.services.discovery_agent.country_utils import MAJOR_CITY_TO_COUNTRY

    known = MAJOR_CITY_TO_COUNTRY.get((city or "").strip().lower())
    return geo_scope.canonical_country(known) if known else None


def _parse_iso(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
