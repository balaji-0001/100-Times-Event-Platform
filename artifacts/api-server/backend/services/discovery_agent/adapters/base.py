"""Base Source Adapter Interface for 100 TIMES Global Event Discovery.

All modular source adapters implement this interface to support:
- Health checks with latency measurement
- Discovery of event listings
- Event detail retrieval & normalization to ExtractedEventCandidate
- Source attribution and provenance tracking
- Pagination and source-specific rate limiting
- Real data extraction testing
"""

import abc
import logging
import time
from typing import Any
from urllib.parse import urlparse

from backend.services.discovery_agent.country_utils import infer_country
from backend.services.discovery_agent.format_normalize import normalize_event_format
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters")


class SourceError(Exception):
    """The source could not be read. Raised instead of returning [] so a run
    reports the source as failed (with this reason), never as "no events".
    `kind`: not_configured | not_implemented | unreachable | parse_error."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# Config keys that name the page a source's events are listed on, most
# specific first. The site's homepage (`website_url`) is only the fallback.
_LISTING_URL_KEYS = ("listing_template", "calendar_url", "listing_url", "search_url")
# Section pages a calendar links to that are not events ("What's on" on ExCeL).
_GENERIC_PAGE_NAMES = {"events", "event", "whats on", "what s on", "calendar", "event calendar", "events calendar",
                       "exhibitions", "upcoming events", "all events", "home", "trade fairs", "conferences"}


def _is_generic_name(name: str | None) -> bool:
    import re as _re

    return " ".join(_re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split()) in _GENERIC_PAGE_NAMES


class BaseSourceAdapter(abc.ABC):
    """Abstract base class for all global event discovery source adapters."""

    source_id: str
    name: str
    category: str
    access_method: str  # schema_org | official_api | html_listing | rss_ical | search_engine
    website_url: str
    rate_limit_delay: float = 1.0  # seconds between requests to respect robots/servers
    # False for catalogue entries with no working discovery client: they are
    # never scheduled and never counted as available sources.
    implemented: bool = True

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self._last_request_time: float = 0.0

    def _respect_rate_limit(self) -> None:
        """Enforces friendly polite spacing between outbound queries."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    @abc.abstractmethod
    def check_health(self) -> dict[str, Any]:
        """Performs a live connectivity and availability probe.
        
        Returns:
            {
                "status": "healthy" | "degraded" | "unreachable",
                "latency_ms": float,
                "error": str | None,
                "details": dict[str, Any]
            }
        """
        raise NotImplementedError

    @abc.abstractmethod
    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        """Discovers and extracts upcoming events matching the DiscoveryConfig.
        
        Returns a list of ExtractedEventCandidate objects normalized to the platform schema.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        """Executes a real test probe against the source to verify extraction fidelity.
        
        Returns:
            {
                "success": bool,
                "events_found": int,
                "sample_events": list[dict],
                "duration_ms": float,
                "error": str | None
            }
        """
        raise NotImplementedError

    def listing_template(self) -> str:
        """The events page this source is configured with (may hold {city}/{country})."""
        for key in _LISTING_URL_KEYS:
            value = self.config.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        return self.website_url

    def target_urls(self, config: DiscoveryConfig | None, max_urls: int = 5) -> list[str]:
        """The concrete pages to read for this run: the configured events page,
        expanded for the run's cities/countries when it is a template."""
        template = self.listing_template()
        if "{city}" not in template and "{country}" not in template:
            return [template]
        from backend.services.discovery_agent import geo_scope, listing_sources

        geo = geo_scope.resolve(config) if config is not None else geo_scope.GeoScope()
        urls = listing_sources.build_listing_urls([template], [], countries=geo.countries, places=geo.anchor_places(max_urls))
        return urls[:max_urls]

    def read_pages(self, urls: list[str], limit: int, cities: list[str] | None = None) -> list[ExtractedEventCandidate]:
        """Read each page and extract its events (JSON-LD, linked event pages,
        then the page text). Raises `SourceError` only when NO page could be
        read; a page that loads but lists nothing just contributes nothing."""
        from backend.services.discovery_agent.page_extractor import events_from_html
        from backend.services.social_agent.browser_fetch import browser_fetch_enabled
        from backend.services.social_agent.web_fetch import failure_reason, fetch

        results: list[ExtractedEventCandidate] = []
        failures: list[str] = []
        read_any = False
        for url in urls:
            if len(results) >= limit:
                break
            self._respect_rate_limit()
            html = fetch(url, render_js=browser_fetch_enabled())
            if not html:
                failures.append(f"{url}: {failure_reason(url) or 'no response'}")
                continue
            read_any = True
            # A directory/calendar page: follow up to 15 of its event links.
            for event in events_from_html(url, html, limit - len(results), cities, page_may_be_event=False, max_event_links=15):
                if _is_generic_name(event.name):
                    continue
                if event.primary_source:
                    event.primary_source.source_website = self.name
                    event.primary_source.source_type = self.access_method
                results.append(event)
        if not read_any and failures:
            raise SourceError("unreachable", "; ".join(failures[:3]))
        return results[:limit]

    def build_candidate_source(self, url: str) -> CandidateSource:
        """Helper to create provenance source attribution."""
        return CandidateSource(
            url=url,
            source_type=self.access_method,
            source_website=self.name,
        )

    def normalize(
        self,
        raw_record: dict[str, Any],
        fallback_url: str | None = None,
    ) -> ExtractedEventCandidate:
        """Normalizes source-specific event dictionary into standard ExtractedEventCandidate."""
        event_url = raw_record.get("url") or fallback_url or self.website_url
        c_src = self.build_candidate_source(event_url)

        name = raw_record.get("name") or raw_record.get("title")
        description = raw_record.get("description") or raw_record.get("event_description")
        start_date = raw_record.get("start_date") or raw_record.get("date") or raw_record.get("startDate")
        end_date = raw_record.get("end_date") or raw_record.get("endDate")
        venue = raw_record.get("venue") or raw_record.get("venue_name")
        city = raw_record.get("city")
        state = raw_record.get("state") or raw_record.get("region")
        raw_country = raw_record.get("country")
        country = infer_country(raw_country, city=city, state=state, url=event_url, default="Worldwide")
        ticket_url = raw_record.get("ticket_url") or raw_record.get("registration_url") or raw_record.get("ticketUrl")
        organizer = raw_record.get("organizer") or raw_record.get("organizer_name")
        raw_format = raw_record.get("event_format") or raw_record.get("format")
        event_format = normalize_event_format(raw_format) if raw_format else None

        category = raw_record.get("category")
        subcategory = raw_record.get("subcategory") or raw_record.get("event_type")

        return ExtractedEventCandidate(
            name=name.strip() if isinstance(name, str) else None,
            event_description=description.strip() if isinstance(description, str) else None,
            category=category.strip() if isinstance(category, str) else None,
            subcategory=subcategory.strip() if isinstance(subcategory, str) else None,
            date=start_date.strip() if isinstance(start_date, str) else None,
            end_time=end_date.strip() if isinstance(end_date, str) else None,
            venue=venue.strip() if isinstance(venue, str) else None,
            city=city.strip() if isinstance(city, str) else None,
            state=state.strip() if isinstance(state, str) else None,
            country=country,
            url=event_url,
            ticket_url=ticket_url.strip() if isinstance(ticket_url, str) else None,
            event_format=event_format,
            organizer_name_hint=organizer.strip() if isinstance(organizer, str) else None,
            extraction_confidence=int(raw_record.get("confidence", 75)),
            primary_source=c_src,
            sources=[c_src],
            raw_evidence={
                "source_id": self.source_id,
                "source_name": self.name,
                "raw_fields": {k: v for k, v in raw_record.items() if k not in ("raw_evidence",)},
            },
            best_effort=bool(raw_record.get("best_effort", False)),
        )

