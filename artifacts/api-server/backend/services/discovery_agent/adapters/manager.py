"""Source Adapter Manager for 100 TIMES Global Event Discovery.

Manages lifecycles, health monitoring, test executions, and discovery queries
across all 74+ global source adapters.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from backend.services.discovery_agent.adapters.api_adapters import (
    CredentialAwarePlatformAdapter,
    TicketmasterAdapter,
)
from backend.services.discovery_agent.adapters.base import BaseSourceAdapter
from backend.services.discovery_agent.adapters.dmg_events import DmgEventsAdapter
from backend.services.discovery_agent.adapters.eventseye import EventsEyeAdapter
from backend.services.discovery_agent.adapters.fair_calendars import CmtEventsAdapter, ExpolyaAdapter, KoelnmesseAdapter, MesseDuesseldorfAdapter
from backend.services.discovery_agent.adapters.ieee_vtools import IeeeVToolsAdapter
from backend.services.discovery_agent.adapters.informa import InformaMarketsAdapter
from backend.services.discovery_agent.adapters.tradefairdates import TradeFairDatesAdapter
from backend.services.discovery_agent.adapters.html_listing import HtmlListingAdapter
from backend.services.discovery_agent.adapters.rss_ical import RssIcalAdapter
from backend.services.discovery_agent.adapters.schema_org import SchemaOrgAdapter
from backend.services.discovery_agent.adapters.search_tools import SearchToolAdapter
from backend.services.discovery_agent.source_registry import ALL_CANDIDATE_SOURCES, record_source_execution
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.adapters.manager")

# Calendars with their own site-specific reader (see fair_calendars.py).
_CALENDAR_ADAPTERS = {"expolya": ExpolyaAdapter, "messe_duesseldorf": MesseDuesseldorfAdapter, "koelnmesse": KoelnmesseAdapter, "cmt_events": CmtEventsAdapter}


class SourceAdapterManager:
    """Central registry and execution dispatcher for all modular source adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseSourceAdapter] = {}
        self._init_all_adapters()

    def _init_all_adapters(self) -> None:
        """Instantiates adapters for all catalogued sources based on access_method."""
        for src in ALL_CANDIDATE_SOURCES:
            sid = src["id"]
            name = src["name"]
            url = src["website_url"]
            cat = src["source_category"]
            method = src["access_method"]
            cfg = src.get("config", {})

            # Site-specific readers first.
            if sid == "eventseye":
                self._adapters[sid] = EventsEyeAdapter(source_id=sid, name=name, website_url=url, category=cat, config=cfg)
            elif sid == "tradefairdates":
                self._adapters[sid] = TradeFairDatesAdapter(source_id=sid, name=name, website_url=url, category=cat, config=cfg)
            elif sid == "dmg_events":
                self._adapters[sid] = DmgEventsAdapter(source_id=sid, name=name, website_url=url, category=cat, config=cfg)
            elif sid == "ieee_events":
                self._adapters[sid] = IeeeVToolsAdapter(source_id=sid, name=name, website_url=url, category=cat, config=cfg)
            elif sid == "informa_markets":
                self._adapters[sid] = InformaMarketsAdapter(source_id=sid, name=name, website_url=url, category=cat, config=cfg)
            elif sid in _CALENDAR_ADAPTERS:
                self._adapters[sid] = _CALENDAR_ADAPTERS[sid](source_id=sid, name=name, website_url=url, category=cat, config=cfg)
            # Special case: Ticketmaster API
            elif sid == "ticketmaster_api":
                self._adapters[sid] = TicketmasterAdapter(
                    source_id=sid, name=name, website_url=url, category=cat, config=cfg
                )
            # Other official APIs (Eventbrite, Meetup, Pretalx, Pretix, Cvent, etc.)
            elif method == "official_api":
                self._adapters[sid] = CredentialAwarePlatformAdapter(
                    source_id=sid,
                    name=name,
                    website_url=url,
                    api_docs_url=src.get("api_docs_url"),
                    auth_requirements=src.get("api_auth_requirements") or "API Key",
                    category=cat,
                    config=cfg,
                )
            # Schema.org structured data directories
            elif method == "schema_org":
                self._adapters[sid] = SchemaOrgAdapter(
                    source_id=sid, name=name, website_url=url, category=cat, config=cfg
                )
            # RSS / Atom / iCalendar feeds
            elif method == "rss_ical":
                self._adapters[sid] = RssIcalAdapter(
                    source_id=sid,
                    name=name,
                    website_url=url,
                    feed_url=cfg.get("feed_url"),
                    category=cat,
                    config=cfg,
                )
            # Search engines and research tools
            elif method in ("search_engine", "interactive_search"):
                self._adapters[sid] = SearchToolAdapter(
                    source_id=sid,
                    name=name,
                    website_url=url,
                    search_prefix=cfg.get("search_prefix", ""),
                    category=cat,
                    config=cfg,
                )
            # Default HTML listings and venue calendars
            else:
                self._adapters[sid] = HtmlListingAdapter(
                    source_id=sid, name=name, website_url=url, category=cat, config=cfg
                )

    def get_adapter(self, source_id: str) -> BaseSourceAdapter | None:
        """Looks up adapter by source ID."""
        return self._adapters.get(source_id)

    def list_adapters(self) -> list[BaseSourceAdapter]:
        """Returns all registered adapters."""
        return list(self._adapters.values())

    def check_health(self, source_id: str, db: Session | None = None) -> dict[str, Any]:
        """Probes live health for a given source ID and updates registry database."""
        adapter = self.get_adapter(source_id)
        if not adapter:
            return {"status": "unsupported", "error": f"Adapter '{source_id}' not found", "latency_ms": 0}

        res = adapter.check_health()
        if db:
            try:
                record_source_execution(
                    db,
                    source_id=source_id,
                    success=(res.get("status") == "healthy"),
                    error=res.get("error"),
                    health_status=res.get("status", "untested"),
                )
            except Exception as e:
                logger.warning("Failed saving health execution to DB: %s", e)

        return res

    def test_extraction(
        self,
        source_id: str,
        sample: str | None = None,
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Executes a test extraction probe and updates source execution stats."""
        adapter = self.get_adapter(source_id)
        if not adapter:
            return {"success": False, "events_found": 0, "sample_events": [], "error": f"Adapter '{source_id}' not found"}

        res = adapter.test_extraction(sample_query_or_url=sample)
        if db:
            try:
                record_source_execution(
                    db,
                    source_id=source_id,
                    events_discovered=res.get("events_found", 0),
                    events_extracted=res.get("events_found", 0),
                    unique_events=res.get("events_found", 0),
                    success=res.get("success", False),
                    error=res.get("error"),
                    health_status="healthy" if res.get("success") else "degraded",
                )
            except Exception as e:
                logger.warning("Failed updating test stats in DB: %s", e)

        return res

    def discover_from_sources(
        self,
        source_ids: list[str],
        config: DiscoveryConfig,
        limit_per_source: int = 15,
        db: Session | None = None,
    ) -> list[ExtractedEventCandidate]:
        """Queries multiple selected sources and collects normalized event candidates."""
        all_candidates: list[ExtractedEventCandidate] = []

        for sid in source_ids:
            adapter = self.get_adapter(sid)
            if not adapter:
                continue
            try:
                candidates = adapter.discover(config, limit=limit_per_source)
                all_candidates.extend(candidates)
                if db:
                    record_source_execution(
                        db,
                        source_id=sid,
                        events_discovered=len(candidates),
                        events_extracted=len(candidates),
                        unique_events=len(candidates),
                        success=True,
                        health_status="healthy",
                    )
            except Exception as e:
                logger.error("Discovery error on source %s: %s", sid, e)
                if db:
                    record_source_execution(
                        db,
                        source_id=sid,
                        success=False,
                        error=str(e),
                        health_status="degraded",
                    )

        return all_candidates


# Singleton manager instance
adapter_manager = SourceAdapterManager()

