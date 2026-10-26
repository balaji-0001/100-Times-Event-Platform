"""HTML Listing & Venue Calendar Source Adapter for 100 TIMES Global Event Discovery.

Adapts exhibition organizer websites, venue event calendars, trade show directories,
and government trade portals using structured DOM selectors and schema.org fallbacks.
"""

import logging
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter
from backend.services.discovery_agent.country_utils import infer_country
from backend.services.discovery_agent.format_normalize import normalize_event_format
from backend.services.discovery_agent.page_extractor import _event_nodes, _event_from_node
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate
from backend.services.social_agent.web_fetch import fetch, find_json_ld_nodes

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
        self.selectors = self.config.get("selectors") or {}
        self.listing_url = self.config.get("listing_url") or self.website_url

    def check_health(self) -> dict[str, Any]:
        """Probes listing page responsiveness and DOM accessibility."""
        start = time.time()
        try:
            self._respect_rate_limit()
            res = fetch(self.listing_url)
            latency = (time.time() - start) * 1000
            if not res or not isinstance(res, str):
                return {
                    "status": "unreachable",
                    "latency_ms": round(latency, 1),
                    "error": "Empty or unreachable response from server",
                    "details": {},
                }
            soup = BeautifulSoup(res, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else ""
            return {
                "status": "healthy",
                "latency_ms": round(latency, 1),
                "error": None,
                "details": {
                    "page_title": title[:80],
                },
            }
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {
                "status": "unreachable",
                "latency_ms": round(latency, 1),
                "error": str(e),
                "details": {},
            }

    def _extract_from_soup(self, soup: BeautifulSoup, base_url: str, limit: int = 25) -> list[ExtractedEventCandidate]:
        results: list[ExtractedEventCandidate] = []

        # 1. First priority: Check for embedded schema.org Event nodes on the page
        schema_nodes = _event_nodes(soup)
        if schema_nodes:
            c_src = self.build_candidate_source(base_url)
            for node in schema_nodes[:limit]:
                cand = _event_from_node(c_src, node)
                cand.primary_source.source_website = self.name
                cand.primary_source.source_type = self.access_method
                results.append(cand)
            if results:
                return results

        # 2. Second priority: Structured DOM selector parsing
        card_sel = self.selectors.get("event_card") or self.selectors.get("item")
        if card_sel:
            cards = soup.select(card_sel)
            for card in cards[:limit]:
                name = None
                date_str = None
                venue = None
                link = base_url

                name_sel = self.selectors.get("name") or self.selectors.get("title")
                if name_sel:
                    el = card.select_one(name_sel)
                    if el:
                        name = el.get_text(strip=True)

                date_sel = self.selectors.get("date")
                if date_sel:
                    el = card.select_one(date_sel)
                    if el:
                        date_str = el.get_text(strip=True)

                venue_sel = self.selectors.get("venue")
                if venue_sel:
                    el = card.select_one(venue_sel)
                    if el:
                        venue = el.get_text(strip=True)

                link_sel = self.selectors.get("link")
                if link_sel:
                    el = card.select_one(link_sel)
                    if el and el.get("href"):
                        link = urljoin(base_url, el["href"])

                if name:
                    cand = self.normalize({
                        "name": name,
                        "date": date_str,
                        "venue": venue or self.name,
                        "url": link,
                    }, fallback_url=base_url)
                    results.append(cand)

        return results

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        """Discovers events from venue calendar or listing URL."""
        target_url = self.listing_url
        try:
            self._respect_rate_limit()
            res = fetch(target_url)
            if not res or not isinstance(res, str):
                return []
            soup = BeautifulSoup(res, "html.parser")
            return self._extract_from_soup(soup, target_url, limit=limit)
        except Exception as e:
            logger.error("Error discovering from %s: %s", self.source_id, e)
            return []

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        """Runs test extraction on listing page and returns sample extracted records."""
        start = time.time()
        target_url = sample_query_or_url or self.listing_url
        try:
            self._respect_rate_limit()
            res = fetch(target_url)
            duration = (time.time() - start) * 1000
            if not res or not isinstance(res, str):
                return {
                    "success": False,
                    "events_found": 0,
                    "sample_events": [],
                    "duration_ms": round(duration, 1),
                    "error": "Failed to fetch listing page",
                }
            soup = BeautifulSoup(res, "html.parser")
            events = self._extract_from_soup(soup, target_url, limit=5)

            samples = []
            for ev in events:
                samples.append({
                    "name": ev.name,
                    "date": ev.date,
                    "city": ev.city,
                    "country": ev.country,
                    "venue": ev.venue,
                    "url": ev.url,
                    "confidence": ev.extraction_confidence,
                })

            return {
                "success": len(events) > 0,
                "events_found": len(events),
                "sample_events": samples,
                "duration_ms": round(duration, 1),
                "error": None if events else "Page reachable but no structured event cards recognized",
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

