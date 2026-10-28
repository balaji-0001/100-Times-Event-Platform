from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from backend.core.config import get_settings
from backend.services.discovery_agent.search_providers.base import (
    BaseSearchProvider,
    SearchProviderResult,
)

logger = logging.getLogger("discovery_agent.search_providers.searxng")


class SearXNGSearchProvider(BaseSearchProvider):
    """Self-hosted SearXNG meta-search (see infra/searxng/settings.yml).

    Keyless and free: SearXNG queries several public engines (Google, Bing,
    Brave, Startpage, …) itself and merges their results, so a block on one
    engine (e.g. DuckDuckGo's captcha) doesn't empty the result list. Only
    the JSON API is used.
    """

    provider_id = "searxng"
    provider_name = "SearXNG (self-hosted meta-search)"
    display_name = "SearXNG"
    is_free = True
    setup_env = ("SEARXNG_URL",)
    docs_url = "https://docs.searxng.org/admin/installation-docker.html"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _base_url(self) -> str | None:
        url = self.settings.searxng_url or os.getenv("SEARXNG_URL")
        return url.rstrip("/") if url else None

    def is_configured(self) -> bool:
        return bool(self._base_url())

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        base = self._base_url()
        if not base:
            raise RuntimeError("SEARXNG_URL is not configured.")
        return query_searxng(base, query, max_results)


def query_searxng(base_url: str, query: str, max_results: int = 5) -> list[SearchProviderResult]:
    """One SearXNG JSON search: de-duplicated http(s) results, at most `max_results`."""
    params: dict[str, Any] = {"q": query, "format": "json", "categories": "general", "language": "en", "pageno": 1}
    r = httpx.get(f"{base_url.rstrip('/')}/search", params=params, timeout=10.0)
    if r.status_code != 200:
        raise RuntimeError(f"SearXNG HTTP {r.status_code}: {r.text[:200]}")

    data = r.json()
    items = data.get("results") or []
    if not items and data.get("unresponsive_engines"):
        # Every upstream engine failed (blocked / timed out) — report it as a
        # failure so the engine's circuit breaker and paid fallback kick in.
        failed = ", ".join(str(e[0]) for e in data["unresponsive_engines"] if e)
        raise RuntimeError(f"SearXNG: all upstream engines unresponsive ({failed})")

    results: list[SearchProviderResult] = []
    seen: set[str] = set()
    for item in items:
        url = item.get("url")
        if not url or not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        results.append(
            SearchProviderResult(
                url=url,
                title=item.get("title") or "",
                snippet=(item.get("content") or "")[:300],
                published_date=item.get("publishedDate"),
                source=f"SearXNG ({', '.join(item.get('engines') or [item.get('engine') or '?'])})",
            )
        )
        if len(results) >= max_results:
            break
    return results
