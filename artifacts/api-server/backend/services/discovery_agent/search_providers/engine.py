from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from typing import Any

from backend.services.discovery_agent.search_providers.base import (
    BaseSearchProvider,
    ProviderExecutionLog,
    SearchProviderResult,
)
from backend.services.discovery_agent.search_providers.bing import BingSearchProvider
from backend.services.discovery_agent.search_providers.brave import BraveSearchProvider
from backend.services.discovery_agent.search_providers.exa import ExaSearchProvider
from backend.services.discovery_agent.search_providers.google import GoogleSearchProvider
from backend.services.discovery_agent.search_providers.web_fallback import WebFallbackProvider

logger = logging.getLogger("discovery_agent.search_providers.engine")


class MultiProviderSearchEngine:
    """Orchestrates multi-provider search across Google, Bing, Brave, Exa, and Web Fallback."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseSearchProvider] = {
            "google_search": GoogleSearchProvider(),
            "bing_search": BingSearchProvider(),
            "brave_search": BraveSearchProvider(),
            "exa_search": ExaSearchProvider(),
            "web_fallback": WebFallbackProvider(),
        }
        self._telemetry_lock = threading.Lock()
        self._execution_logs: list[ProviderExecutionLog] = []
        self._cache_lock = threading.Lock()
        self._cache: dict[str, tuple[float, list[SearchProviderResult]]] = {}
        self._cache_ttl_seconds = 3600  # 1 hour

    def is_provider_available(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        return bool(provider and provider.is_configured())

    def get_providers_status(self) -> dict[str, dict[str, Any]]:
        """Returns live configuration status of all search providers."""
        status = {}
        for pid, p in self._providers.items():
            status[pid] = {
                "name": p.provider_name,
                "configured": p.is_configured(),
            }
        return status

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
        requested_sources: set[str] | list[str] | None = None,
        specific_provider_id: str | None = None,
    ) -> list[str]:
        """Dispatches search to eligible providers and returns deduplicated official URLs."""
        results = self.search_details(
            query=query,
            max_results=max_results,
            country=country,
            date_range=date_range,
            requested_sources=requested_sources,
            specific_provider_id=specific_provider_id,
        )
        return [r.url for r in results]

    def search_details(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
        requested_sources: set[str] | list[str] | None = None,
        specific_provider_id: str | None = None,
    ) -> list[SearchProviderResult]:
        """Queries eligible search providers in parallel and records detailed telemetry."""
        query = query.strip()
        if not query:
            return []

        # 1. Determine active providers based on configuration and requested sources
        req = set(requested_sources or [])
        target_providers: list[BaseSearchProvider] = []

        if specific_provider_id:
            # Explicit provider request (e.g. from SearchToolAdapter for google_search or bing_search)
            p = self._providers.get(specific_provider_id)
            if p:
                target_providers.append(p)
        else:
            # General web search: check user selections
            # Broad search or explicit web/engine selection
            is_broad = not req or "all" in req or "all_sources" in req or "web" in req

            if is_broad or "google_search" in req:
                target_providers.append(self._providers["google_search"])
            if is_broad or "bing_search" in req:
                target_providers.append(self._providers["bing_search"])
            if "brave_search" in req:
                target_providers.append(self._providers["brave_search"])
            if "exa_search" in req:
                target_providers.append(self._providers["exa_search"])

        # If no specialized provider is enabled, return empty (disabling prevents execution)
        if not target_providers:
            logger.info("Search requested for %r but no search providers are enabled in sources.", query)
            return []

        # Check Cache
        cache_key = f"{query}|{country}|{date_range}|{[p.provider_id for p in target_providers]}"
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and (time.time() - cached[0] < self._cache_ttl_seconds):
                return cached[1][:max_results]

        # 2. Parallel Search Execution across enabled providers
        aggregated_results: list[SearchProviderResult] = []
        seen_urls: set[str] = set()

        def _execute_provider(provider: BaseSearchProvider) -> list[SearchProviderResult]:
            start_t = time.time()
            if not provider.is_configured():
                log = ProviderExecutionLog(
                    provider_id=provider.provider_id,
                    provider_name=provider.provider_name,
                    query=query,
                    status="NO_KEY",
                    result_count=0,
                    latency_ms=0.0,
                    error=f"API key or credentials not configured for {provider.provider_name}",
                )
                self._record_log(log)
                return []

            try:
                res = provider.search(
                    query=query,
                    max_results=max_results,
                    country=country,
                    date_range=date_range,
                )
                latency = (time.time() - start_t) * 1000
                log = ProviderExecutionLog(
                    provider_id=provider.provider_id,
                    provider_name=provider.provider_name,
                    query=query,
                    status="SUCCESS",
                    result_count=len(res),
                    latency_ms=latency,
                    error=None,
                )
                self._record_log(log)
                logger.info(
                    "Search provider [%s] returned %d results in %.1fms for query: %s",
                    provider.provider_id,
                    len(res),
                    latency,
                    query,
                )
                return res
            except Exception as exc:
                latency = (time.time() - start_t) * 1000
                err_msg = str(exc)
                status = "RATE_LIMITED" if ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg) else "FAILED"
                log = ProviderExecutionLog(
                    provider_id=provider.provider_id,
                    provider_name=provider.provider_name,
                    query=query,
                    status=status,
                    result_count=0,
                    latency_ms=latency,
                    error=err_msg[:300],
                )
                self._record_log(log)
                logger.warning(
                    "Search provider [%s] failed (%s) in %.1fms: %s",
                    provider.provider_id,
                    status,
                    latency,
                    err_msg[:200],
                )
                return []

        # Run configured primary providers concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(target_providers), 4)) as executor:
            future_to_provider = {
                executor.submit(_execute_provider, p): p for p in target_providers
            }
            for future in concurrent.futures.as_completed(future_to_provider):
                try:
                    p_results = future.result()
                    for r in p_results:
                        if r.url not in seen_urls:
                            seen_urls.add(r.url)
                            aggregated_results.append(r)
                except Exception as e:
                    logger.exception("Provider worker exception: %s", e)

        # 3. Fallback Tier: If all specialized providers produced 0 results (due to 429 quota or no key),
        # transparently query the open-web fallback provider to keep discovery progressing
        if not aggregated_results and not specific_provider_id:
            fallback = self._providers["web_fallback"]
            logger.info("Specialized providers returned 0 results. Executing %s...", fallback.provider_name)
            fallback_res = _execute_provider(fallback)
            for r in fallback_res:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    aggregated_results.append(r)

        # Update Cache
        with self._cache_lock:
            self._cache[cache_key] = (time.time(), aggregated_results)

        return aggregated_results[:max_results]

    def _record_log(self, log: ProviderExecutionLog) -> None:
        with self._telemetry_lock:
            self._execution_logs.append(log)
            # Keep rolling buffer of last 200 logs
            if len(self._execution_logs) > 200:
                self._execution_logs = self._execution_logs[-200:]

    def get_recent_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._telemetry_lock:
            return [l.as_dict() for l in self._execution_logs[-limit:]]

    def clear_logs(self) -> None:
        with self._telemetry_lock:
            self._execution_logs.clear()


# Global Singleton Instance
search_engine = MultiProviderSearchEngine()

