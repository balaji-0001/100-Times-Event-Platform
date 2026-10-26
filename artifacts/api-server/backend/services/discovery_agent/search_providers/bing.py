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

logger = logging.getLogger("discovery_agent.search_providers.bing")

BING_ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"


class BingSearchProvider(BaseSearchProvider):
    """Official Microsoft Bing Web Search API v7 integration."""

    provider_id = "bing_search"
    provider_name = "Microsoft Bing Web Search API v7"

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        """Configured if a legitimate Bing Search API key is present."""
        return bool(
            self.settings.bing_search_api_key
            or os.getenv("BING_SEARCH_API_KEY")
            or os.getenv("AZURE_BING_API_KEY")
            or os.getenv("BING_API_KEY")
        )

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        """Dispatches search to Microsoft Bing Web Search API."""
        api_key = (
            self.settings.bing_search_api_key
            or os.getenv("BING_SEARCH_API_KEY")
            or os.getenv("AZURE_BING_API_KEY")
            or os.getenv("BING_API_KEY")
        )
        if not api_key:
            raise RuntimeError(
                "BING_SEARCH_API_KEY is not configured in environment. "
                "Add your Microsoft Azure Bing Search v7 key to .env to use official Bing Search."
            )

        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Accept": "application/json",
        }
        params: dict[str, Any] = {
            "q": query,
            "count": min(max(max_results, 1), 20),
            "responseFilter": "Webpages",
            "textFormat": "Raw",
        }
        if country and len(country) == 2:
            params["cc"] = country.upper()

        r = httpx.get(BING_ENDPOINT, headers=headers, params=params, timeout=12.0)
        if r.status_code != 200:
            raise RuntimeError(f"Bing Web Search API HTTP {r.status_code}: {r.text[:200]}")

        data = r.json()
        web_pages = data.get("webPages", {}).get("value", [])
        results: list[SearchProviderResult] = []
        for page in web_pages:
            url = page.get("url")
            if url and url.startswith(("http://", "https://")):
                results.append(
                    SearchProviderResult(
                        url=url,
                        title=page.get("name", ""),
                        snippet=page.get("snippet", ""),
                        source="Microsoft Bing Web Search API",
                    )
                )
        return results[:max_results]

