"""Search Engine & Research Tools Adapter for 100 TIMES Global Event Discovery.

Adapts supplementary discovery tools:
- Google Search
- Bing Search
- LinkedIn Events
- Google Maps Venue Listings
"""

import logging
import time
from typing import Any

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter
from backend.services.discovery_agent.page_extractor import extract_events_from_page
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate
from backend.services.discovery_agent.web_search import search as search_web
from backend.services.social_agent.web_fetch import fetch

logger = logging.getLogger("discovery_agent.adapters.search_tools")


class SearchToolAdapter(BaseSourceAdapter):
    """Adapter for open-web search and professional directory queries."""

    access_method = "search_engine"

    def __init__(
        self,
        source_id: str,
        name: str,
        website_url: str,
        search_prefix: str = "",
        category: str = "Search & Research Tool",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.search_prefix = search_prefix
        self.category = category

    def check_health(self) -> dict[str, Any]:
        """Probes search tool availability."""
        start = time.time()
        try:
            self._respect_rate_limit()
            res = fetch(self.website_url)
            latency = (time.time() - start) * 1000
            return {
                "status": "healthy" if res and res.status_code == 200 else "degraded",
                "latency_ms": round(latency, 1),
                "error": None if res and res.status_code == 200 else "Degraded connectivity",
                "details": {"status_code": getattr(res, "status_code", None)},
            }
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {
                "status": "unreachable",
                "latency_ms": round(latency, 1),
                "error": str(e),
                "details": {},
            }

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        """Runs targeted search queries and extracts events from result landing pages."""
        candidates: list[ExtractedEventCandidate] = []
        city = (config.cities[0] if config.cities else "Global")
        country = config.country or "Worldwide"
        category = config.categories[0] if config.categories else "conference"

        query = f"{self.search_prefix} {category} events exhibitions {city} {country}".strip()
        try:
            self._respect_rate_limit()
            urls = search_web(query, max_results=min(limit, 5))
            for url in urls:
                if len(candidates) >= limit:
                    break
                try:
                    events = extract_events_from_page(url, max_events=2)
                    for ev in events:
                        if ev.primary_source:
                            ev.primary_source.source_website = self.name
                            ev.primary_source.source_type = self.access_method
                        candidates.append(ev)
                except Exception as inner_e:
                    logger.debug("Failed extracting from search result %s: %s", url, inner_e)
        except Exception as e:
            logger.error("Search query failed on %s: %s", self.source_id, e)

        return candidates[:limit]

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        start = time.time()
        try:
            query = sample_query_or_url or f"{self.search_prefix} tech conference 2026"
            urls = search_web(query, max_results=3)
            duration = (time.time() - start) * 1000

            samples = [{"url": u, "source": self.name} for u in urls]
            return {
                "success": len(urls) > 0,
                "events_found": len(urls),
                "sample_events": samples,
                "duration_ms": round(duration, 1),
                "error": None if urls else "Search returned 0 results",
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
