"""HTML Listing & Venue Calendar Source Adapter for 100 TIMES Global Event Discovery.

Reads a source's configured events page — `listing_template` (expanded per
city/country of the run), `calendar_url`, `listing_url` or `search_url`,
falling back to the homepage only when none is configured — and extracts its
events with the shared page extractor (schema.org JSON-LD, linked event
pages, then the page text). Used for exhibition organizers, venue calendars,
trade-show directories and government trade portals.

A page that cannot be read raises `SourceError` (with the HTTP status /
timeout reason) instead of returning [], so runs and probes report the
source as failed rather than as "no events".
"""

import logging
import time
from typing import Any

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.html_listing")


class HtmlListingAdapter(BaseSourceAdapter):
    """Adapter for HTML-based venue calendars, exhibition directories, and organizer portals."""

    access_method = "html_listing"

    def __init__(
        self,
        source_id: str,
        name: str,
        website_url: str,
        category: str = "Venue Calendar",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.category = category

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        """Events listed on this source's events page(s) for the run's places."""
        return self.read_pages(self.target_urls(config), limit, config.cities)

    def _probe_url(self, sample: str | None = None) -> str:
        if sample:
            return sample
        urls = self.target_urls(DiscoveryConfig(cities=["London"], countries=["United Kingdom"]), max_urls=1)
        return urls[0] if urls else self.website_url

    def check_health(self) -> dict[str, Any]:
        """Loads the events page itself (not just the homepage)."""
        from backend.services.social_agent.web_fetch import failure_reason, fetch

        url = self._probe_url()
        start = time.time()
        html = fetch(url)
        latency = round((time.time() - start) * 1000, 1)
        if not html:
            return {"status": "unreachable", "latency_ms": latency, "error": failure_reason(url) or "no response", "details": {"url": url}}
        return {"status": "healthy", "latency_ms": latency, "error": None, "details": {"url": url, "bytes": len(html)}}

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        """Reads the events page and returns what was extracted. `success`
        means the page was read; a readable page with no events is reported
        as such, not as a failure."""
        url = self._probe_url(sample_query_or_url)
        start = time.time()
        try:
            # Same depth as a run: calendars often list section/filter links before events.
            events = self.read_pages([url], limit=15)
        except SourceError as exc:
            return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": round((time.time() - start) * 1000, 1), "error": str(exc)}
        samples = [
            {"name": ev.name, "date": ev.date, "city": ev.city, "country": ev.country, "venue": ev.venue, "url": ev.url, "confidence": ev.extraction_confidence}
            for ev in events
        ]
        return {
            "success": True,
            "events_found": len(events),
            "sample_events": samples,
            "duration_ms": round((time.time() - start) * 1000, 1),
            "error": None,
            "note": None if events else f"Page read, but no events were recognised on {url}",
        }
