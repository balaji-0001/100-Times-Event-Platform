"""Informa Markets (www.informamarkets.com) — one of the largest trade-show
organizers (Middle East Energy, Arab Health, CPHI …).

Its event-listing page (/en/event-listing.html) fills itself from a public
JSON feed of event editions; this reader uses that same feed (approved by the
admin on 2026-10-27; informamarkets.com publishes no robots.txt). One request
returns every upcoming edition with its dates, city, country, venue, official
website and Informa's own sector / sub-sector labels. A run keeps the shows
in the selected countries (all when none is selected), puts the sector labels
in the description so the run's sector rules can read them, and points each
candidate at the show's official website (the organizer step reads that site
for a public contact), with Informa Markets declared as the organizer.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any
from urllib.parse import quote

import httpx

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.informa")

LISTING_PAGE = "https://www.informamarkets.com/en/event-listing.html"
FEED = "https://www.informamarkets.com/content/data/informa/lov/data.eventEditions.expanded.json"
ORGANIZER = {"name": "Informa Markets", "url": "https://www.informamarkets.com/"}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json",
}
# The feed's country spellings that our country normaliser doesn't know.
_COUNTRY_ALIASES = {"brasil": "Brazil", "hong kong, s.a.r., china": "Hong Kong", "türkiye": "Turkey", "turkiye": "Turkey"}


def feed_url(today: date) -> str:
    """The same query the listing page sends: editions ending today or later, shown on the site."""
    query = f"$[?(@.eventEndDate>='{today.isoformat()}' && @.infcomDisplay=~/^Y[es]?$/i)]"
    return f"{FEED}?filter={quote(query, safe='')}&limit=1000"


def fetch_editions(today: date | None = None) -> list[dict[str, Any]]:
    url = feed_url(today or date.today())
    try:
        response = httpx.get(url, headers=_HEADERS, timeout=20, follow_redirects=True)
    except httpx.TimeoutException:
        raise SourceError("unreachable", "Informa event feed timed out after 20s")
    except httpx.HTTPError as exc:
        raise SourceError("unreachable", f"Informa event feed: network error ({type(exc).__name__})")
    if response.status_code != 200:
        raise SourceError("unreachable", f"Informa event feed: HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise SourceError("parse_error", "Informa event feed did not return JSON (format changed?)")
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SourceError("parse_error", "Informa event feed has no item list (format changed?)")
    return [item for item in items if isinstance(item, dict)]


def _country(item: dict[str, Any]) -> str | None:
    from backend.services.discovery_agent import geo_scope

    raw = (item.get("locationCountry") or "").strip()
    raw = _COUNTRY_ALIASES.get(raw.lower(), raw)
    return geo_scope.canonical_country(raw) or raw or None


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class InformaMarketsAdapter(BaseSourceAdapter):
    """Reads Informa Markets' public event-edition feed (see module docstring)."""

    access_method = "official_feed"

    def __init__(self, source_id: str = "informa_markets", name: str = "Informa Markets", website_url: str = "https://www.informamarkets.com/",
                 category: str = "International Exhibition Organizer", config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.category = category

    def listing_template(self) -> str:
        return LISTING_PAGE

    def target_urls(self, config: DiscoveryConfig | None, max_urls: int = 5) -> list[str]:
        return [LISTING_PAGE]

    def discover(self, config: DiscoveryConfig, limit: int = 25) -> list[ExtractedEventCandidate]:
        from backend.services.discovery_agent import geo_scope

        self._respect_rate_limit()
        today = date.today()
        items = fetch_editions(today)
        wanted = {c.lower() for c in geo_scope.resolve(config).countries}
        until = _day(getattr(config, "date_to", None)) if getattr(config, "date_to", None) else None
        per_country: dict[str | None, list[ExtractedEventCandidate]] = {}
        for item in items:
            start = _day(item.get("eventStartDate"))
            name = (item.get("eventEditionLongName") or item.get("text") or "").strip()
            if not name or start is None or start < today or (until and start > until):
                continue
            country = _country(item)
            if wanted and (country or "").lower() not in wanted:
                continue
            per_country.setdefault(country, []).append(self._candidate(item, name, start, country))
        ordered: list[ExtractedEventCandidate] = []
        queues = [sorted(v, key=lambda c: c.date or "") for v in per_country.values()]
        limit = max(limit, 100)  # one request, no per-show cost
        while queues and len(ordered) < limit:
            for queue in list(queues):
                if queue:
                    ordered.append(queue.pop(0))
                if not queue:
                    queues.remove(queue)
        return ordered[:limit]

    def _candidate(self, item: dict[str, Any], name: str, start: date, country: str | None) -> ExtractedEventCandidate:
        official_url = (item.get("URL") or "").strip()
        if not official_url.startswith(("http://", "https://")):
            official_url = LISTING_PAGE
        labels = []
        for sub in item.get("eventSeriesSubSectors") or []:
            for key in ("sectorName", "subSectorName"):
                value = (sub.get(key) or "").strip()
                if value and value not in labels:
                    labels.append(value)
        description = " ".join(filter(None, [
            item.get("eventSeriesName"),
            f"(Informa Markets sectors: {', '.join(labels)})" if labels else None,
        ])) or None
        official = CandidateSource(url=official_url, source_type="official_event_site", source_website=self.name)
        listing = CandidateSource(url=LISTING_PAGE, source_type="organizer_portfolio", source_website=self.name)
        return ExtractedEventCandidate(
            name=name,
            event_description=description,
            date=start.isoformat(),
            venue=(item.get("venueName") or "").strip() or None,
            city=(item.get("cityFreeText") or "").strip() or None,
            state=(item.get("stateFreeText") or "").strip() or None,
            country=country,
            url=official_url,
            event_format="offline",
            organizer_name_hint=ORGANIZER["name"],
            extraction_confidence=85,
            primary_source=official,
            sources=[official, listing],
            raw_evidence={
                "source_id": self.source_id,
                "organizer": dict(ORGANIZER),
                "end_date": item.get("eventEndDate"),
                "informa_edition_code": item.get("eventEditionCode"),
            },
        )

    def check_health(self) -> dict[str, Any]:
        start = time.time()
        try:
            items = fetch_editions()
        except SourceError as exc:
            return {"status": "unreachable", "latency_ms": round((time.time() - start) * 1000, 1), "error": str(exc), "details": {}}
        return {"status": "healthy", "latency_ms": round((time.time() - start) * 1000, 1), "error": None, "details": {"editions": len(items)}}

    def test_extraction(self, sample_query_or_url: str | None = None) -> dict[str, Any]:
        start = time.time()
        try:
            events = self.discover(DiscoveryConfig(), limit=10)
        except SourceError as exc:
            return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": round((time.time() - start) * 1000, 1), "error": str(exc)}
        samples = [{"name": e.name, "date": e.date, "city": e.city, "country": e.country, "url": e.url} for e in events[:5]]
        return {"success": True, "events_found": len(events), "sample_events": samples, "duration_ms": round((time.time() - start) * 1000, 1), "error": None,
                "note": None if events else "Informa feed read, but it lists no upcoming editions"}
