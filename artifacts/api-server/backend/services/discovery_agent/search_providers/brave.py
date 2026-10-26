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

logger = logging.getLogger("discovery_agent.search_providers.brave")

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider(BaseSearchProvider):
    """Brave Search API integration."""

    provider_id = "brave_search"
    provider_name = "Brave Search API"

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(
            self.settings.brave_search_api_key
            or os.getenv("BRAVE_SEARCH_API_KEY")
            or os.getenv("BRAVE_API_KEY")
        )

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        api_key = (
            self.settings.brave_search_api_key
            or os.getenv("BRAVE_SEARCH_API_KEY")
            or os.getenv("BRAVE_API_KEY")
        )
        if not api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is not configured in environment.")

        headers = {
            "X-Subscription-Token": api_key,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
        params: dict[str, Any] = {
            "q": query,
            "count": min(max(max_results, 1), 20),
        }
        if country and len(country) == 2:
            params["country"] = country.lower()

        r = httpx.get(BRAVE_ENDPOINT, headers=headers, params=params, timeout=12.0)
        if r.status_code != 200:
            raise RuntimeError(f"Brave Search API HTTP {r.status_code}: {r.text[:200]}")

        data = r.json()
        web_results = data.get("web", {}).get("results", [])
        results: list[SearchProviderResult] = []
        for item in web_results:
            url = item.get("url")
            if url and url.startswith(("http://", "https://")):
                results.append(
                    SearchProviderResult(
                        url=url,
                        title=item.get("title", ""),
                        snippet=item.get("description", ""),
                        source="Brave Search API",
                    )
                )
        return results[:max_results]

