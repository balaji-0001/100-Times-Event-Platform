"""Search Engine & Research Tools Adapter for 100 TIMES Global Event Discovery.

Adapts modern search providers:
- Google Search (Gemini Search Grounding / Google Custom Search JSON API)
- Microsoft Bing Web Search API v7
- LinkedIn Events & Posts
"""

import logging
import time
from typing import Any

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter
from backend.services.discovery_agent.page_extractor import extract_events_from_page
from backend.services.discovery_agent.query_seeds import _date_hint_for_config, SECTOR_SYNONYMS
from backend.services.discovery_agent.search_providers import search_engine
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.search_tools")


class SearchToolAdapter(BaseSourceAdapter):
    """Adapter for open-web search and professional research tools."""

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
        """Probes search tool availability and API configuration."""
        start = time.time()
        configured = search_engine.is_provider_available(self.source_id)
        latency = (time.time() - start) * 1000
        return {
            "status": "healthy" if configured else "degraded",
            "latency_ms": round(latency, 1),
            "error": None if configured else f"No active API credentials configured for {self.name}",
            "details": {
                "provider_id": self.source_id,
                "configured": configured,
                "access_method": self.access_method,
            },
        }

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        """Runs targeted search queries using the specific search provider and extracts events from result landing pages."""
        candidates: list[ExtractedEventCandidate] = []
        city = (config.cities[0] if config.cities else "")
        target_country = config.country or (config.countries[0] if config.countries else "Worldwide")
        categories = config.categories or ["Technology", "Construction"]
        time_hint = _date_hint_for_config(config)

        # Build smart queries covering selected sectors, synonyms, locations, and date ranges
        queries: list[str] = []
        for cat in categories[:3]:
            synonyms = SECTOR_SYNONYMS.get(cat, (cat,))
            primary_term = synonyms[0] if synonyms else cat
            c_label = f" in {city}" if city else f" in {target_country}"
            q = f"{self.search_prefix} {primary_term} conference expo summit{c_label} {time_hint}".strip()
            queries.append(q)

        # Date range tuple
        date_range = (config.date_from, config.date_to)

        for query in queries:
            if len(candidates) >= limit:
                break
            try:
                self._respect_rate_limit()
                provider_results = search_engine.search_details(
                    query=query,
                    max_results=min(limit, 5),
                    country=target_country,
                    date_range=date_range,
                    specific_provider_id=self.source_id,
                )
                for res in provider_results:
                    if len(candidates) >= limit:
                        break
                    try:
                        events = extract_events_from_page(res.url, max_events=2)
                        for ev in events:
                            if ev.primary_source:
                                ev.primary_source.source_website = self.name
                                ev.primary_source.source_type = self.access_method
                            candidates.append(ev)
                    except Exception as inner_e:
                        logger.debug("Failed extracting from search result %s: %s", res.url, inner_e)
            except Exception as e:
                logger.error("Search query failed on provider %s: %s", self.source_id, e)

        return candidates[:limit]

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        start = time.time()
        try:
            query = sample_query_or_url or f"{self.search_prefix} tech conference 2026"
            results = search_engine.search_details(
                query=query,
                max_results=3,
                specific_provider_id=self.source_id,
            )
            duration = (time.time() - start) * 1000

            samples = [{"url": r.url, "title": r.title, "source": r.source} for r in results]
            return {
                "success": len(results) > 0,
                "events_found": len(results),
                "sample_events": samples,
                "duration_ms": round(duration, 1),
                "error": None if results else f"Search provider {self.name} returned 0 results",
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
