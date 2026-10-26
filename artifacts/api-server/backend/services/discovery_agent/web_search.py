"""Multi-provider web search integration for the 100 TIMES Discovery Agent.

Orchestrates searches across Google (Custom Search JSON API), Microsoft Bing,
Brave, Exa, and Web Fallback via `MultiProviderSearchEngine`.
"""

import logging
from backend.services.discovery_agent.search_providers import search_engine

logger = logging.getLogger("discovery_agent.web_search")


class SearchBlocked(Exception):
    """The search engine refused the request (captcha / rate limit)."""


def search(
    query: str,
    max_results: int = 5,
    country: str | None = None,
    date_range: tuple[str | None, str | None] | None = None,
    requested_sources: set[str] | list[str] | None = None,
    specific_provider_id: str | None = None,
) -> list[str]:
    """Dispatches search query across configured modern search providers."""
    return search_engine.search(
        query=query,
        max_results=max_results,
        country=country,
        date_range=date_range,
        requested_sources=requested_sources,
        specific_provider_id=specific_provider_id,
    )
