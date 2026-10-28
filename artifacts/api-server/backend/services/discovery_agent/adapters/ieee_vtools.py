"""IEEE Events via vTools Events' official public API.

events.ieee.org is IEEE's marketing site; the actual event listings live in
vTools Events, which publishes a documented public JSON API
(https://events.vtools.ieee.org/api/doc/events) — no login. One request
returns upcoming events (`span=now~`, sorted by start time) with title,
dates, time zone, venue/city, country and state (as linked records), the
hosting IEEE section/chapter and the event's published contact e-mail.

vTools' robots.txt asks for at most one request per minute (Crawl-delay 60),
so the response is cached for 30 minutes and never re-requested sooner than
60 s; the organizer step uses the API's host and contact e-mail and does not
open each event page.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Any

import httpx

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.ieee_vtools")

API_URL = "https://events.vtools.ieee.org/RST/events/api/public/v8/events/list"
SITE = "https://events.vtools.ieee.org/"
SOURCE_NAME = "IEEE vTools Events"
_CRAWL_DELAY_SECONDS = 60
_CACHE_SECONDS = 30 * 60
_PAGE_LIMIT = 1000
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json",
}
_TAG_RE = re.compile(r"<[^>]+>")

_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "payload": None}
_last_request = 0.0


def _text(html: str | None) -> str:
    return " ".join(unescape(_TAG_RE.sub(" ", html or "")).split())


def fetch_upcoming() -> dict[str, Any]:
    """The API's upcoming-events page (cached; never more than one request a minute)."""
    global _last_request
    with _lock:
        if _cache["payload"] is not None and time.time() - _cache["at"] < _CACHE_SECONDS:
            return _cache["payload"]
        wait = _CRAWL_DELAY_SECONDS - (time.time() - _last_request)
        if wait > 0 and _cache["payload"] is not None:
            return _cache["payload"]  # too soon for a new request: keep the last answer
        if wait > 0:
            raise SourceError("rate_limited", f"IEEE vTools asks for one request a minute; next allowed in {round(wait)}s")
        _last_request = time.time()
        try:
            response = httpx.get(API_URL, params={"span": "now~", "sort": "start-time", "limit": _PAGE_LIMIT},
                                 headers=_HEADERS, timeout=30, follow_redirects=True)
        except httpx.TimeoutException:
            raise SourceError("unreachable", "IEEE vTools events API timed out after 30s")
        except httpx.HTTPError as exc:
            raise SourceError("unreachable", f"IEEE vTools events API: network error ({type(exc).__name__})")
        if response.status_code != 200:
            raise SourceError("unreachable", f"IEEE vTools events API: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise SourceError("parse_error", "IEEE vTools events API did not return JSON (format changed?)")
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise SourceError("parse_error", "IEEE vTools events API has no event list (format changed?)")
        _cache.update(at=time.time(), payload=payload)
        return payload


def _included(payload: dict[str, Any], kind: str) -> dict[str, str]:
    return {str(i.get("id")): (i.get("attributes") or {}).get("name") for i in payload.get("included") or [] if i.get("type") == kind}


def _local_start(attrs: dict[str, Any]) -> datetime | None:
    try:
        start = datetime.fromisoformat(str(attrs.get("start-time")).replace("Z", "+00:00"))
    except ValueError:
        return None
    offset = (attrs.get("time-zone") or {}).get("utc-offset")
    return start + timedelta(hours=offset) if isinstance(offset, (int, float)) else start


class IeeeVToolsAdapter(BaseSourceAdapter):
    """Reads IEEE events from the vTools Events public API (see module docstring)."""

    access_method = "official_api"

    def __init__(self, source_id: str = "ieee_events", name: str = "IEEE Events", website_url: str = SITE,
                 category: str = "Industry Association", config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.category = category

    def listing_template(self) -> str:
        return SITE

    def target_urls(self, config: DiscoveryConfig | None, max_urls: int = 5) -> list[str]:
        return [API_URL]

    def discover(self, config: DiscoveryConfig, limit: int = 25) -> list[ExtractedEventCandidate]:
        from backend.services.discovery_agent import geo_scope

        payload = fetch_upcoming()
        countries, states = _included(payload, "countries"), _included(payload, "states")
        wanted = {c.lower() for c in geo_scope.resolve(config).countries}
        today = date.today()
        since = _day(getattr(config, "date_from", None)) or today
        until = _day(getattr(config, "date_to", None))
        per_country: dict[str | None, list[ExtractedEventCandidate]] = {}
        for item in payload["data"]:
            attrs = item.get("attributes") or {}
            if attrs.get("cancelled") or attrs.get("publish") is False:
                continue
            start = _local_start(attrs)
            title = _text(attrs.get("title"))
            if not title or start is None or start.date() < max(since, today) or (until and start.date() > until):
                continue
            rel = item.get("relationships") or {}
            country_name = countries.get(str(((rel.get("country") or {}).get("data") or {}).get("id")))
            country = geo_scope.canonical_country(country_name) if country_name else None
            if wanted and (country or "").lower() not in wanted:
                continue
            state = states.get(str(((rel.get("state") or {}).get("data") or {}).get("id")))
            per_country.setdefault(country, []).append(self._candidate(item, attrs, title, start, country or country_name, state))
        ordered: list[ExtractedEventCandidate] = []
        queues = list(per_country.values())
        limit = max(limit, 100)  # one request covers them all
        while queues and len(ordered) < limit:
            for queue in list(queues):
                if queue:
                    ordered.append(queue.pop(0))
                if not queue:
                    queues.remove(queue)
        return ordered[:limit]

    def _candidate(self, item: dict[str, Any], attrs: dict[str, Any], title: str, start: datetime, country: str | None,
                   state: str | None) -> ExtractedEventCandidate:
        link = attrs.get("link") or f"{SITE}m/{item.get('id')}"
        host = (attrs.get("primary-host") or {}).get("name")
        location_type = (attrs.get("location-type") or "").lower()
        fmt = "online" if attrs.get("virtual") or location_type == "virtual" else ("hybrid" if location_type == "hybrid" else "offline")
        source = CandidateSource(url=link, source_type="official_api", source_website=SOURCE_NAME)
        keywords = ", ".join(filter(None, [_text(attrs.get("keywords")), _text(attrs.get("tags")) if isinstance(attrs.get("tags"), str) else None]))
        description = " ".join(filter(None, [_text(attrs.get("description"))[:1500], f"(IEEE keywords: {keywords})" if keywords else None])) or None
        return ExtractedEventCandidate(
            name=title,
            event_description=description,
            date=start.date().isoformat(),
            start_time=start.strftime("%H:%M"),
            venue=_text(attrs.get("building")) or _text(attrs.get("address1")) or None,
            city=_text(attrs.get("city")) or None,
            state=state,
            country=country,
            url=link,
            ticket_url=attrs.get("registration-url") or None,
            event_format=fmt,
            organizer_name_hint=host,
            extraction_confidence=85,
            primary_source=source,
            sources=[source],
            raw_evidence={
                "source_id": self.source_id,
                # Published by IEEE in the public API for this event: the hosting
                # section/chapter and the event's contact address.
                "organizer": {"name": host, "email": attrs.get("contact-email") or None},
                "vtools_event_id": item.get("id"),
            },
        )

    def check_health(self) -> dict[str, Any]:
        start = time.time()
        try:
            payload = fetch_upcoming()
        except SourceError as exc:
            return {"status": "unreachable", "latency_ms": round((time.time() - start) * 1000, 1), "error": str(exc), "details": {}}
        return {"status": "healthy", "latency_ms": round((time.time() - start) * 1000, 1), "error": None, "details": {"events": len(payload["data"])}}

    def test_extraction(self, sample_query_or_url: str | None = None) -> dict[str, Any]:
        start = time.time()
        try:
            events = self.discover(DiscoveryConfig(), limit=10)
        except SourceError as exc:
            return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": round((time.time() - start) * 1000, 1), "error": str(exc)}
        samples = [{"name": e.name, "date": e.date, "city": e.city, "country": e.country, "url": e.url} for e in events[:5]]
        return {"success": True, "events_found": len(events), "sample_events": samples, "duration_ms": round((time.time() - start) * 1000, 1), "error": None,
                "note": None if events else "IEEE vTools API answered, but lists no upcoming events"}


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None
