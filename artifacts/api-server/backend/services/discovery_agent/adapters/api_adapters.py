"""Official Event Platform API Adapters for 100 TIMES Global Event Discovery.

Adapters for structured event discovery APIs:
- Ticketmaster Discovery API v2 (Fully Operational)
- Eventbrite Platform API v3 (Credential-Aware)
- Meetup GraphQL API (Credential-Aware)
- Pretalx / Pretix / Cvent / Bizzabo / Swoogo / Whova API integrations
"""

import logging
import os
import time
from typing import Any

import requests

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter, SourceError
from backend.services.discovery_agent.ticketmaster import (
    COUNTRY_CODE_MAP,
    TICKETMASTER_DISCOVERY_URL,
    fetch_ticketmaster_events,
    parse_ticketmaster_event,
    test_ticketmaster_connection,
)
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.api")


class TicketmasterAdapter(BaseSourceAdapter):
    """Adapter for official Ticketmaster Discovery API v2."""

    access_method = "official_api"

    def __init__(
        self,
        source_id: str = "ticketmaster_api",
        name: str = "Ticketmaster Discovery API",
        website_url: str = "https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/",
        category: str = "Event Platform & API",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.category = category
        self.rate_limit_delay = 0.2  # 5 requests/sec

    def _get_api_key(self, config: DiscoveryConfig | None = None) -> str:
        if config and config.ticketmaster_api_key:
            return config.ticketmaster_api_key.strip()
        return (os.getenv("TICKETMASTER_API_KEY") or self.config.get("api_key") or "").strip()

    def check_health(self) -> dict[str, Any]:
        """Probes Ticketmaster API v2 connectivity."""
        start = time.time()
        api_key = self._get_api_key()
        if not api_key:
            return {
                "status": "awaiting_credentials",
                "latency_ms": 0.0,
                "error": "Ticketmaster API Key required (TICKETMASTER_API_KEY).",
                "details": {"has_credentials": False},
            }
        result = test_ticketmaster_connection(api_key)
        latency = (time.time() - start) * 1000
        return {
            "status": "healthy" if result.get("success") else "unreachable",
            "latency_ms": round(latency, 1),
            "error": None if result.get("success") else result.get("message"),
            "details": {
                "total_available_events": result.get("totalEvents", 0),
                "has_credentials": True,
            },
        }

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        """Queries Ticketmaster API using platform helper."""
        api_key = self._get_api_key(config)
        if not api_key:
            raise SourceError("not_configured", "Ticketmaster API key not configured")

        candidates = fetch_ticketmaster_events(
            api_key=api_key,
            cities=config.cities,
            countries=config.countries,
            country=config.country,
            categories=config.categories,
            max_events_per_city=limit,
        )
        return candidates[:limit]

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        """Tests live Ticketmaster API querying and candidate normalization."""
        start = time.time()
        api_key = self._get_api_key()
        if not api_key:
            return {
                "success": False,
                "events_found": 0,
                "sample_events": [],
                "duration_ms": 0.0,
                "error": "Ticketmaster API Key not configured. Provide key in config or TICKETMASTER_API_KEY env.",
            }

        try:
            resp = requests.get(
                TICKETMASTER_DISCOVERY_URL,
                params={"apikey": api_key, "size": 3, "sort": "date,asc"},
                timeout=10,
            )
            duration = (time.time() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("_embedded", {}).get("events", [])
                samples = []
                for ev in events:
                    cand = parse_ticketmaster_event(ev)
                    if cand:
                        samples.append({
                            "name": cand.name,
                            "date": cand.date,
                            "city": cand.city,
                            "country": cand.country,
                            "venue": cand.venue,
                            "ticket_url": cand.ticket_url,
                        })
                return {
                    "success": len(events) > 0,
                    "events_found": len(events),
                    "sample_events": samples,
                    "duration_ms": round(duration, 1),
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "events_found": 0,
                    "sample_events": [],
                    "duration_ms": round(duration, 1),
                    "error": f"Ticketmaster API HTTP {resp.status_code}: {resp.text[:150]}",
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


class CredentialAwarePlatformAdapter(BaseSourceAdapter):
    """Catalogue entry for an official platform API (Eventbrite, Meetup,
    Sessionize, Pretalx, Pretix, Cvent, Bizzabo, Swoogo) that this app has
    NO discovery client for yet. It never pretends to work: discovery raises
    `SourceError("not_implemented")`, probes report `not_implemented`, and a
    run lists it as skipped with that reason — with or without a key.
    (Eventbrite and Meetup listings are still read through their public
    pages by the Consumer Aggregators channel.)"""

    access_method = "official_api"
    implemented = False

    def __init__(
        self,
        source_id: str,
        name: str,
        website_url: str,
        api_docs_url: str | None,
        auth_requirements: str,
        category: str = "Event Platform & API",
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(config=config)
        self.source_id = source_id
        self.name = name
        self.website_url = website_url
        self.api_docs_url = api_docs_url
        self.auth_requirements = auth_requirements
        self.category = category

    def _get_credential(self) -> str | None:
        env_var = f"{self.source_id.upper()}_KEY"
        return os.getenv(env_var) or self.config.get("api_key")

    def not_implemented_reason(self) -> str:
        return (
            f"No discovery client for the {self.name} API is implemented in this app "
            f"(it would need {self.auth_requirements}; docs: {self.api_docs_url or self.website_url})."
        )

    def check_health(self) -> dict[str, Any]:
        return {
            "status": "not_implemented",
            "latency_ms": 0.0,
            "error": self.not_implemented_reason(),
            "details": {"docs_url": self.api_docs_url, "has_credentials": bool(self._get_credential())},
        }

    def discover(
        self,
        config: DiscoveryConfig,
        limit: int = 25,
    ) -> list[ExtractedEventCandidate]:
        raise SourceError("not_implemented", self.not_implemented_reason())

    def test_extraction(
        self,
        sample_query_or_url: str | None = None,
    ) -> dict[str, Any]:
        return {"success": False, "events_found": 0, "sample_events": [], "duration_ms": 0.0, "error": self.not_implemented_reason()}
