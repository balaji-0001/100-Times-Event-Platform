from __future__ import annotations

import logging
import os
import threading
from typing import Any

import httpx

from backend.core.config import get_settings
from backend.services.discovery_agent.search_providers.base import (
    BaseSearchProvider,
    SearchProviderResult,
)

logger = logging.getLogger("discovery_agent.search_providers.exa")

EXA_ENDPOINT = "https://api.exa.ai/search"


class ExaSearchProvider(BaseSearchProvider):
    """Exa AI Neural Search API integration."""

    provider_id = "exa_search"
    provider_name = "Exa AI Search API"
    display_name = "Exa"
    cost_rank = 10  # ~$0.007/search (measured) — the cheapest paid top-up
    setup_env = ("EXA_API_KEY",)
    docs_url = "https://docs.exa.ai/reference/search"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._local = threading.local()

    def consume_cost(self) -> float | None:
        cost, self._local.cost = getattr(self._local, "cost", None), None
        return cost

    def is_configured(self) -> bool:
        return bool(
            self.settings.exa_api_key
            or os.getenv("EXA_API_KEY")
        )

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        api_key = self.settings.exa_api_key or os.getenv("EXA_API_KEY")
        if not api_key:
            raise RuntimeError("EXA_API_KEY is not configured in environment.")

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # "fast" returns the same results as "auto"/"neural" at the same price
        # ($0.007/search, measured) in about half the time. Only URLs/titles are
        # requested — page contents are billed extra and read by the pipeline anyway.
        payload: dict[str, Any] = {
            "query": query,
            "numResults": min(max(max_results, 1), 20),
            "type": "fast",
        }

        r = httpx.post(EXA_ENDPOINT, headers=headers, json=payload, timeout=12.0)
        if r.status_code != 200:
            raise RuntimeError(f"Exa Search API HTTP {r.status_code}: {r.text[:200]}")

        data = r.json()
        # Exa reports the billed amount per request; recorded per run.
        total = (data.get("costDollars") or {}).get("total")
        self._local.cost = float(total) if isinstance(total, (int, float)) else None
        results_data = data.get("results", [])
        results: list[SearchProviderResult] = []
        for item in results_data:
            url = item.get("url")
            if url and url.startswith(("http://", "https://")):
                results.append(
                    SearchProviderResult(
                        url=url,
                        title=item.get("title", ""),
                        snippet=item.get("text", "")[:300] if item.get("text") else "",
                        published_date=item.get("publishedDate"),
                        source="Exa AI Search API",
                    )
                )
        return results[:max_results]

