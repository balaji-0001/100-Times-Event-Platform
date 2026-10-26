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


class BaseSourceAdapter(abc.ABC):
    """Abstract base class for all global event discovery source adapters."""

    source_id: str
    name: str
    category: str
    access_method: str  # schema_org | official_api | html_listing | rss_ical | search_engine
    website_url: str
    rate_limit_delay: float = 1.0  # seconds between requests to respect robots/servers

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

