"""RSS & iCalendar Feed Source Adapter for 100 TIMES Global Event Discovery.

Adapts Call for Papers (CFP) services, academic societies (WikiCFP, IEEE, ACM),
and iCal / RSS event syndication feeds.

The feed URL comes from the source's `feed_url` / `rss_url` config. A feed
item's publication date is NOT the event date, so it is never used as one:
dates and places come from the item text where the feed states them (WikiCFP
writes "[City, Country] [Dec 18, 2026 - Dec 20, 2026]"). A configured "feed"
that turns out to be an HTML page is read like any listing page.
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.rss_ical")

_ATOM = "{http://www.w3.org/2005/Atom}"
# "...name... [Nanchang, China] [Dec 18, 2026 - Dec 20, 2026]"
_BRACKETS_RE = re.compile(r"\[([^\[\]]+)\]")
_DATE_RANGE_RE = re.compile(r"^([A-Z][a-z]{2,8}\.? \d{1,2}, \d{4})(?:\s*-\s*[A-Z][a-z]{2,8}\.? \d{1,2}, \d{4})?$")


def _text(item: ET.Element, *tags: str) -> str | None:
    for tag in tags:
        el = item.find(tag)
        if el is not None:
            value = (el.text or el.get("href") or "").strip()
            if value:
                return value
    return None


def _looks_like_feed(text: str) -> bool:
    head = text.lstrip()[:400].lower()
    return head.startswith("<?xml") or "<rss" in head or "<feed" in head or head.startswith("begin:vcalendar")


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
        self.feed_url = feed_url or self.config.get("feed_url") or self.config.get("rss_url") or self.website_url
        self.category = category

    def _parse_feed(self, xml_text: str, limit: int = 25) -> list[ExtractedEventCandidate]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise SourceError("parse_error", f"{self.feed_url}: feed is not valid XML ({exc})") from exc
        items = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
        results: list[ExtractedEventCandidate] = []
        for item in items[:limit]:
            title = _text(item, "title", f"{_ATOM}title")
            if not title:
                continue
            description = _text(item, "description", f"{_ATOM}summary", f"{_ATOM}content")
            record: dict[str, Any] = {
                "name": title,
                "description": description,
                "url": _text(item, "link", f"{_ATOM}link") or self.website_url,
            }
            record.update(self._event_facts(title, description))
            results.append(self.normalize(record, fallback_url=self.website_url))
        return results

    @staticmethod
    def _event_facts(title: str, description: str | None) -> dict[str, Any]:
        """Name, place and dates the item text states (WikiCFP format); nothing guessed."""
        facts: dict[str, Any] = {}
        if " : " in title:  # "ICHBC 2026 : IEEE 2026 6th International Conference on ..."
            facts["name"] = title.split(" : ", 1)[1].strip() or title
        for part in _BRACKETS_RE.findall(description or ""):
            part = part.strip()
            date_match = _DATE_RANGE_RE.match(part)
            if date_match:
                facts["date"] = date_match.group(1)
            elif "," in part and not facts.get("city"):
                city, _, country = part.rpartition(",")
                facts["city"], facts["country"] = city.strip(), country.strip()
            elif part.lower() in ("online", "virtual"):
                facts["event_format"] = "online"
        return facts

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        from backend.services.social_agent.web_fetch import failure_reason, fetch

        self._respect_rate_limit()
        text = fetch(self.feed_url, allow_feed=True)
        if text is None:
            # Not a readable feed (or blocked): the rendered-page path may still work.
            try:
                return self.read_pages([self.feed_url], limit, config.cities)
            except SourceError:
                raise SourceError("unreachable", f"{self.feed_url}: {failure_reason(self.feed_url) or 'no response'}")
        if _looks_like_feed(text):
            return self._parse_feed(text, limit=limit)
        from backend.services.discovery_agent.page_extractor import events_from_html

        return events_from_html(self.feed_url, text, limit, config.cities, page_may_be_event=False)

    def check_health(self) -> dict[str, Any]:
        from backend.services.social_agent.web_fetch import failure_reason, fetch

        start = time.time()
        text = fetch(self.feed_url, allow_feed=True)
        latency = round((time.time() - start) * 1000, 1)
        if text is None:
            return {"status": "unreachable", "latency_ms": latency, "error": failure_reason(self.feed_url) or "no response", "details": {"url": self.feed_url}}
        return {"status": "healthy", "latency_ms": latency, "error": None, "details": {"url": self.feed_url, "is_feed": _looks_like_feed(text)}}

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        start = time.time()
        try:
            events = self.discover(DiscoveryConfig(), limit=5)
        except SourceError as exc:
            return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": round((time.time() - start) * 1000, 1), "error": str(exc)}
        samples = [{"name": ev.name, "date": ev.date, "city": ev.city, "country": ev.country, "url": ev.url} for ev in events]
        return {
            "success": True,
            "events_found": len(events),
            "sample_events": samples,
            "duration_ms": round((time.time() - start) * 1000, 1),
            "error": None,
            "note": None if events else "Feed read, but it lists no events",
        }
