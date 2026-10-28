"""Multi-provider web search integration for the 100 TIMES Discovery Agent.

Dispatches through `MultiProviderSearchEngine` (SearXNG, Exa, Google via
Gemini grounding, Google Custom Search, Brave, Bing, DuckDuckGo fallback).

A discovery run wraps its worker jobs in `run_context(...)` so every search
made inside them — discovery queries and organizer lookups alike — uses only
the providers selected for that run and is recorded in the run's stats.
"""

import logging
import threading
from contextlib import contextmanager

from backend.services.discovery_agent.search_providers import search_engine
from backend.services.discovery_agent.search_providers.engine import SearchRunStats

logger = logging.getLogger("discovery_agent.web_search")

_context = threading.local()


class SearchBlocked(Exception):
    """The search engine refused the request (captcha / rate limit)."""


@contextmanager
def run_context(allowed_providers: set[str] | None, stats: SearchRunStats | None, purpose: str = "discovery"):
    """Searches on this thread use these providers and record into `stats`."""
    previous = getattr(_context, "value", None)
    _context.value = (allowed_providers, stats, purpose)
    try:
        yield
    finally:
        _context.value = previous


def search(
    query: str,
    max_results: int = 5,
    country: str | None = None,
    date_range: tuple[str | None, str | None] | None = None,
    requested_sources: set[str] | list[str] | None = None,
    specific_provider_id: str | None = None,
) -> list[str]:
    """Dispatches search query across configured modern search providers."""
    allowed, stats, purpose = getattr(_context, "value", None) or (None, None, "discovery")
    return search_engine.search(
        query=query,
        max_results=max_results,
        country=country,
        date_range=date_range,
        requested_sources=requested_sources,
        specific_provider_id=specific_provider_id,
        allowed_providers=allowed,
        stats=stats,
        purpose=purpose,
    )
