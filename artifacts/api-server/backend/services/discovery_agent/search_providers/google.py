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

logger = logging.getLogger("discovery_agent.search_providers.google")


class GoogleSearchProvider(BaseSearchProvider):
    """Google Search provider using the official Google Custom Search JSON API (Programmable Search Engine).

    Does NOT use Google Gemini for web searching. Directly queries the Google Custom Search REST API.
    """

    provider_id = "google_search"
    provider_name = "Google Custom Search JSON API"

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        """Configured if GOOGLE_SEARCH_API_KEY and GOOGLE_CSE_ID are set."""
        key = self.settings.google_search_api_key or os.getenv("GOOGLE_SEARCH_API_KEY")
        cx = self.settings.google_cse_id or os.getenv("GOOGLE_CSE_ID")
        return bool(key and cx)

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        """Queries Google Custom Search JSON API."""
        api_key = self.settings.google_search_api_key or os.getenv("GOOGLE_SEARCH_API_KEY")
        cx = self.settings.google_cse_id or os.getenv("GOOGLE_CSE_ID")

        if not api_key or not cx:
            raise RuntimeError(
                "Google Custom Search API requires GOOGLE_SEARCH_API_KEY and GOOGLE_CSE_ID in environment."
            )

        url = "https://www.googleapis.com/customsearch/v1"
        params: dict[str, Any] = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": min(max(max_results, 1), 10),
        }
        if country and len(country) == 2:
            params["gl"] = country.lower()

        r = httpx.get(url, params=params, timeout=12.0)
        if r.status_code != 200:
            raise RuntimeError(f"Google Custom Search API HTTP {r.status_code}: {r.text[:200]}")

        data = r.json()
        items = data.get("items", [])
        results: list[SearchProviderResult] = []
        for it in items:
            link = it.get("link")
            if link and link.startswith(("http://", "https://")):
                results.append(
                    SearchProviderResult(
                        url=link,
                        title=it.get("title", ""),
                        snippet=it.get("snippet", ""),
                        source="Google Custom Search API",
                    )
                )
        return results[:max_results]
