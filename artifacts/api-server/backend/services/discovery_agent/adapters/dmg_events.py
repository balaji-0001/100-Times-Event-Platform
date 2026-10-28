"""dmg events (www.dmgevents.com) — organizer of ADIPEC, Big 5 Global and
other large Middle East / Africa construction and energy shows.

Its /events/ page (checked 2026-10-27; robots.txt allows it) lists the whole
upcoming portfolio as `ul.list-marquee > a` items, each linking to the show's
official website with the text "Name | 2 - 5 November 2026 , Country". A run
keeps the shows in the selected countries (all of them when none is
selected) with upcoming dates. Each candidate points at the show's official
website — the organizer step reads that site for its public contact e-mail —
and declares dmg events as the organizer.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.adapters.tradefairdates import parse_date
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.dmg_events")

EVENTS_PAGE = "https://www.dmgevents.com/events/"
ORGANIZER = {"name": "dmg events", "url": "https://www.dmgevents.com/"}


def parse_events(html: str) -> list[dict[str, Any]]:
    """[{name, url, date_text, country}] from the /events/ page."""
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for a in soup.select("ul.list-marquee > a[href]"):
        text = a.get_text(" ", strip=True)
        if "|" not in text or not a["href"].startswith(("http://", "https://")):
            continue
        name, _, rest = text.partition("|")
        when, _, country = rest.rpartition(",")
        key = (name.strip().lower(), when.strip())
        if key in seen:
            continue
        seen.add(key)
        rows.append({"name": " ".join(name.split()), "url": a["href"].strip(), "date_text": when.strip(), "country": country.strip()})
    return rows


def start_date(text: str) -> tuple[date | None, bool]:
    """'26 – 29 October 2026', '8 - 11 May, 2027', '10-12 January 2027' -> start."""
    cleaned = text.replace("–", "-").replace("—", "-").replace(",", " ")
    return parse_date(" ".join(cleaned.split()))


class DmgEventsAdapter(BaseSourceAdapter):
    """Site-specific reader for dmg events' portfolio page."""

    access_method = "html_listing"

    def __init__(self, source_id: str = "dmg_events", name: str = "dmg events", website_url: str = "https://www.dmgevents.com/",
                 category: str = "International Exhibition Organizer", config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.category = category

    def listing_template(self) -> str:
        return EVENTS_PAGE

    def target_urls(self, config: DiscoveryConfig | None, max_urls: int = 5) -> list[str]:
        return [EVENTS_PAGE]

    def discover(self, config: DiscoveryConfig, limit: int = 25) -> list[ExtractedEventCandidate]:
        from backend.services.discovery_agent import geo_scope
        from backend.services.social_agent.web_fetch import failure_reason, fetch

        self._respect_rate_limit()
        html = fetch(EVENTS_PAGE)
        if not html:
            raise SourceError("unreachable", f"{EVENTS_PAGE}: {failure_reason(EVENTS_PAGE) or 'no response'}")
        rows = parse_events(html)
        if not rows:
            raise SourceError("parse_error", f"{EVENTS_PAGE}: no event list found (page layout changed?)")
        wanted = {c.lower() for c in geo_scope.resolve(config).countries}
        today = date.today()
        results: list[ExtractedEventCandidate] = []
        for row in rows:
            country = geo_scope.canonical_country(row["country"]) or row["country"] or None
            if wanted and (country or "").lower() not in wanted:
                continue
            start, exact = start_date(row["date_text"])
            if start is None or start < today:
                continue
            results.append(self._candidate(row, start, exact, country))
            if len(results) >= limit:
                break
        return results

    def _candidate(self, row: dict[str, Any], start: date, exact: bool, country: str | None) -> ExtractedEventCandidate:
        listing = CandidateSource(url=EVENTS_PAGE, source_type="organizer_portfolio", source_website=self.name)
        official = CandidateSource(url=row["url"], source_type="official_event_site", source_website=self.name)
        return ExtractedEventCandidate(
            name=row["name"],
            date=start.isoformat() if exact else start.strftime("%B %Y"),
            country=country,
            url=row["url"],
            event_format="offline",
            organizer_name_hint=ORGANIZER["name"],
            extraction_confidence=80 if exact else 55,
            primary_source=official,
            sources=[official, listing],
            raw_evidence={"source_id": self.source_id, "organizer": dict(ORGANIZER), "dmg_listing": f"{row['name']} | {row['date_text']}, {row['country']}"},
            best_effort=not exact,
        )

    def check_health(self) -> dict[str, Any]:
        from backend.services.social_agent.web_fetch import failure_reason, fetch

        start = time.time()
        html = fetch(EVENTS_PAGE)
        latency = round((time.time() - start) * 1000, 1)
        if not html:
            return {"status": "unreachable", "latency_ms": latency, "error": failure_reason(EVENTS_PAGE) or "no response", "details": {}}
        return {"status": "healthy", "latency_ms": latency, "error": None, "details": {"events_listed": len(parse_events(html))}}

    def test_extraction(self, sample_query_or_url: str | None = None) -> dict[str, Any]:
        start = time.time()
        try:
            events = self.discover(DiscoveryConfig(), limit=10)
        except SourceError as exc:
            return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": round((time.time() - start) * 1000, 1), "error": str(exc)}
        samples = [{"name": e.name, "date": e.date, "country": e.country, "url": e.url} for e in events[:5]]
        return {"success": True, "events_found": len(events), "sample_events": samples, "duration_ms": round((time.time() - start) * 1000, 1), "error": None,
                "note": None if events else "dmg events page read, but it lists no upcoming shows"}
