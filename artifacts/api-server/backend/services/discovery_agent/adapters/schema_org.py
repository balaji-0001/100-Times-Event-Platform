"""Schema.org / JSON-LD Source Adapter for 100 TIMES Global Event Discovery.

Reads machine-readable schema.org Event metadata from event discovery websites
like 10Times, Clocate, dev.events, AllEvents, Skillboxes, etc.
"""

import logging
import time
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter
from backend.services.discovery_agent.page_extractor import extract_events_from_page
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate
from backend.services.social_agent.web_fetch import fetch, find_json_ld_nodes

logger = logging.getLogger("discovery_agent.adapters.schema_org")


class SchemaOrgAdapter(BaseSourceAdapter):
    """Adapter for websites exposing schema.org / JSON-LD Event metadata."""

    access_method = "schema_org"

    def __init__(
        self,
        source_id: str,
        name: str,
        website_url: str,
        category: str = "Global Event Discovery",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.category = category
        self.listing_template = self.config.get("listing_template") or self.website_url

    def check_health(self) -> dict[str, Any]:
        """Probes endpoint availability and checks if JSON-LD or HTML responds."""
        start = time.time()
        try:
            self._respect_rate_limit()
            res = fetch(self.website_url)
            latency = (time.time() - start) * 1000
            if not res or not isinstance(res, str):
                return {
                    "status": "unreachable",
                    "latency_ms": round(latency, 1),
                    "error": "Empty or unreachable response from server",
                    "details": {},
                }
            soup = BeautifulSoup(res, "html.parser")
            ld_nodes = find_json_ld_nodes(soup)
            return {
                "status": "healthy",
                "latency_ms": round(latency, 1),
                "error": None,
                "details": {
                    "json_ld_nodes_found": len(ld_nodes),
                },
            }
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.warning("Health check failed for %s: %s", self.source_id, e)
            return {
                "status": "unreachable",
                "latency_ms": round(latency, 1),
                "error": str(e),
                "details": {},
            }

    def _resolve_urls(self, config: DiscoveryConfig) -> list[str]:
        """Expands listing_template with configured cities/countries."""
        template = self.listing_template
        has_city = "{city}" in template
        has_country = "{country}" in template

        if not has_city and not has_country:
            return [template]

        urls: list[str] = []
        cities = config.cities or [""]
        country = (config.country or "India").lower().replace(" ", "-")

        for city in cities:
            c_slug = city.strip().lower().replace(" ", "-") if city else ""
            url = template
            if has_city:
                url = url.replace("{city}", c_slug or "global")
            if has_country:
                url = url.replace("{country}", country)
            if url not in urls:
                urls.append(url)
        return urls[:5]

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        """Fetches listing pages and parses all embedded schema.org events."""
        results: list[ExtractedEventCandidate] = []
        urls = self._resolve_urls(config)

        for target_url in urls:
            if len(results) >= limit:
                break
            try:
                self._respect_rate_limit()
                events = extract_events_from_page(target_url, max_events=limit - len(results), cities=config.cities)
                for ev in events:
                    # Enrich with source attribution
                    if ev.primary_source:
                        ev.primary_source.source_website = self.name
                        ev.primary_source.source_type = self.access_method
                    results.append(ev)
            except Exception as e:
                logger.error("Error discovering from %s (%s): %s", self.source_id, target_url, e)

        return results[:limit]

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        """Live test execution verifying schema.org parsing."""
        start = time.time()
        target_url = sample_query_or_url or self.website_url
        try:
            self._respect_rate_limit()
            candidates = extract_events_from_page(target_url, max_events=5)
            duration = (time.time() - start) * 1000

            samples = []
            for c in candidates:
                samples.append({
                    "name": c.name,
                    "date": c.date,
                    "city": c.city,
                    "country": c.country,
                    "venue": c.venue,
                    "ticket_url": c.ticket_url,
                    "url": c.url,
                    "confidence": c.extraction_confidence,
                })

            return {
                "success": len(candidates) > 0,
                "events_found": len(candidates),
                "sample_events": samples,
                "duration_ms": round(duration, 1),
                "error": None if candidates else "No schema.org Event nodes found at target URL",
            }
        except Exception as e:
            duration = (time.time() - start) * 1000
            return {
                "success": False,
                "events_found": 0,
                "sample_events": [],
                "duration_ms": round(duration, 1),
                "error": str(e),
            }
