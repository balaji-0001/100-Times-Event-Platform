"""Modular source adapters package for 100 TIMES Global Event Discovery."""

from backend.services.discovery_agent.adapters.base import BaseSourceAdapter
from backend.services.discovery_agent.adapters.api_adapters import (
    CredentialAwarePlatformAdapter,
    TicketmasterAdapter,
)
from backend.services.discovery_agent.adapters.html_listing import HtmlListingAdapter
from backend.services.discovery_agent.adapters.rss_ical import RssIcalAdapter
from backend.services.discovery_agent.adapters.schema_org import SchemaOrgAdapter
from backend.services.discovery_agent.adapters.search_tools import SearchToolAdapter
from backend.services.discovery_agent.adapters.manager import SourceAdapterManager, adapter_manager

__all__ = [
    "BaseSourceAdapter",
    "TicketmasterAdapter",
    "CredentialAwarePlatformAdapter",
    "HtmlListingAdapter",
    "RssIcalAdapter",
    "SchemaOrgAdapter",
    "SearchToolAdapter",
    "SourceAdapterManager",
    "adapter_manager",
]
