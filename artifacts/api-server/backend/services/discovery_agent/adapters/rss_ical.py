"""RSS & iCalendar Feed Source Adapter for 100 TIMES Global Event Discovery.

Adapts Call for Papers (CFP) services, academic societies (WikiCFP, IEEE, ACM),
and iCal / RSS event syndication feeds.
"""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate
from backend.services.social_agent.web_fetch import fetch

logger = logging.getLogger("discovery_agent.adapters.rss_ical")


class RssIcalAdapter(BaseSourceAdapter):
    """Adapter for RSS, Atom, and iCalendar syndication feeds."""

    access_method = "rss_ical"

    def __init__(
        self,
        source_id: str,
        name: str,
        website_url: str,
        feed_url: str | None = None,
        category: str = "Industry Association",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.feed_url = feed_url or self.config.get("feed_url") or self.website_url
        self.category = category

    def check_health(self) -> dict[str, Any]:
        """Probes feed endpoint accessibility and valid XML structure."""
        start = time.time()
        try:
            self._respect_rate_limit()
            res = fetch(self.feed_url)
            latency = (time.time() - start) * 1000
            if not res or not res.text:
                return {
                    "status": "unreachable",
                    "latency_ms": round(latency, 1),
                    "error": "Empty response from feed",
                    "details": {},
                }
            # Test parse XML
            root = ET.fromstring(res.text)
            items = root.findall(".//item") or root.findall(".//entry")
            return {
                "status": "healthy" if res.status_code == 200 else "degraded",
                "latency_ms": round(latency, 1),
                "error": None,
                "details": {
                    "status_code": res.status_code,
                    "feed_items_count": len(items),
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

    def _parse_feed(self, xml_text: str, limit: int = 25) -> list[ExtractedEventCandidate]:
        results: list[ExtractedEventCandidate] = []
        try:
            root = ET.fromstring(xml_text)
            # Support RSS 2.0 and Atom feeds
            items = root.findall(".//item")
            if not items:
                items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

            for item in items[:limit]:
                title = None
                link = self.website_url
                desc = None
                pub_date = None

                title_el = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()

                link_el = item.find("link") or item.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    link = link_el.text or link_el.get("href") or self.website_url

                desc_el = item.find("description") or item.find("{http://www.w3.org/2005/Atom}summary")
                if desc_el is not None and desc_el.text:
                    desc = desc_el.text.strip()

                date_el = item.find("pubDate") or item.find("{http://www.w3.org/2005/Atom}updated")
                if date_el is not None and date_el.text:
                    pub_date = date_el.text.strip()

                if title:
                    cand = self.normalize({
                        "name": title,
                        "description": desc,
                        "date": pub_date,
                        "url": link,
                        "category": self.category,
                    }, fallback_url=self.website_url)
                    results.append(cand)
        except Exception as e:
            logger.error("XML parse error in %s: %s", self.source_id, e)

        return results

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        try:
            self._respect_rate_limit()
            res = fetch(self.feed_url)
            if not res or not res.text:
                return []
            return self._parse_feed(res.text, limit=limit)
        except Exception as e:
            logger.error("Discover error in %s: %s", self.source_id, e)
            return []

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        start = time.time()
        url = sample_query_or_url or self.feed_url
        try:
            self._respect_rate_limit()
            res = fetch(url)
            duration = (time.time() - start) * 1000
            if not res or not res.text:
                return {
                    "success": False,
                    "events_found": 0,
                    "sample_events": [],
                    "duration_ms": round(duration, 1),
                    "error": "Failed to fetch feed",
                }
            events = self._parse_feed(res.text, limit=5)
            samples = []
            for ev in events:
                samples.append({
                    "name": ev.name,
                    "date": ev.date,
                    "url": ev.url,
                    "description": (ev.event_description or "")[:120],
                })
            return {
                "success": len(events) > 0,
                "events_found": len(events),
                "sample_events": samples,
                "duration_ms": round(duration, 1),
                "error": None if events else "No events parsed from feed",
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
