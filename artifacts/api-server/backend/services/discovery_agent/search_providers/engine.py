from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from collections import Counter
from datetime import datetime, timezone
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
from backend.services.discovery_agent.search_providers.google_gemini import GeminiGoogleSearchProvider
from backend.services.discovery_agent.search_providers.searxng import SearXNGSearchProvider
from backend.services.discovery_agent.search_providers.web_fallback import WebFallbackProvider
from backend.services.social_agent import ai_client

logger = logging.getLogger("discovery_agent.search_providers.engine")

# Source ids in a run's `sources` that mean "the General Web Search channel"
# rather than one provider (older saved settings list google/bing this way).
_CHANNEL_TOKENS = {"web", "all", "all_sources", "all_operational", "search_research_tool", "google_search", "bing_search", "linkedin_search"}


class SearchRunStats:
    """One discovery run's search accounting, shared by every search the run
    makes (discovery queries and organizer lookups), across worker threads:
    per-provider calls / successes / zero-result calls / failures / skips
    (with reasons) / results / latency / reported cost, the paid-call budget,
    which provider first returned each URL, and a bounded per-query log."""

    _LOG_LIMIT = 300

    def __init__(self, allowed: set[str] | None = None, paid_budget: int | None = None) -> None:
        self.allowed = set(allowed) if allowed is not None else None
        self.paid_budget = paid_budget
        self.paid_calls = 0
        self._lock = threading.Lock()
        self.providers: dict[str, dict[str, Any]] = {}
        self.url_origin: dict[str, str] = {}
        self.log: list[dict[str, Any]] = []
        # One search request from the pipeline = one query, however many
        # providers answered it; a provider request = one call (see `providers`).
        self.queries: Counter = Counter()
        # AI model requests made by providers (Google via Gemini grounding),
        # with the token counts the model API reported.
        self.ai_models: dict[str, dict[str, Any]] = {}

    def record_query(self, outcome: str) -> None:
        """`outcome`: with_results | no_results | served_from_cache | no_provider
        (not sent: no provider selected, or all cooling down / over the paid budget)."""
        with self._lock:
            self.queries["attempted"] += 1
            self.queries[outcome] += 1

    def record_ai_usage(self, provider_id: str, calls: list[dict[str, Any]]) -> None:
        with self._lock:
            for c in calls:
                row = self.ai_models.setdefault(c["model"], {
                    "provider": c["provider"], "calls": 0, "failed_calls": 0, "prompt_tokens": 0,
                    "completion_tokens": 0, "total_tokens": 0, "used_by": Counter(),
                })
                row["calls"] += 1
                row["failed_calls"] += 0 if c["ok"] else 1
                row["prompt_tokens"] += c["prompt_tokens"]
                row["completion_tokens"] += c["completion_tokens"]
                row["total_tokens"] += c["total_tokens"]
                row["used_by"][provider_id] += 1

    def usage_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "queries": dict(self.queries),
                "ai_models": {m: {**row, "used_by": dict(row["used_by"])} for m, row in self.ai_models.items()},
            }

    def _row(self, provider_id: str) -> dict[str, Any]:
        return self.providers.setdefault(provider_id, {
            "calls": 0, "successes": 0, "zero_result_calls": 0, "failures": 0, "rate_limited": 0,
            "results": 0, "latency_ms": 0.0, "cost_usd": 0.0, "cost_reported": False,
            "skipped": Counter(), "last_error": None, "first_call_at": None, "last_call_at": None,
            "purposes": Counter(),
        })

    def try_spend_paid(self) -> bool:
        with self._lock:
            if self.paid_budget is not None and self.paid_calls >= self.paid_budget:
                return False
            self.paid_calls += 1
            return True

    def record_call(self, log: ProviderExecutionLog, purpose: str, cost: float | None) -> None:
        with self._lock:
            row = self._row(log.provider_id)
            row["calls"] += 1
            row["purposes"][purpose] += 1
            row["latency_ms"] += log.latency_ms
            row["first_call_at"] = row["first_call_at"] or log.timestamp
            row["last_call_at"] = log.timestamp
            if log.status == "SUCCESS":
                row["successes"] += 1
                row["results"] += log.result_count
                if log.result_count == 0:
                    row["zero_result_calls"] += 1
            else:
                row["failures"] += 1
                if log.status == "RATE_LIMITED":
                    row["rate_limited"] += 1
                row["last_error"] = log.error
            if cost is not None:
                row["cost_usd"] += cost
                row["cost_reported"] = True
            if len(self.log) < self._LOG_LIMIT:
                self.log.append({**log.as_dict(), "purpose": purpose, "cost_usd": cost})

    def record_skip(self, provider_id: str, reason: str) -> None:
        with self._lock:
            self._row(provider_id)["skipped"][reason] += 1

    def note_urls(self, provider_id: str, urls: list[str]) -> None:
        with self._lock:
            for url in urls:
                self.url_origin.setdefault(url, provider_id)

    def origin_of(self, url: str) -> str | None:
        with self._lock:
            return self.url_origin.get(url)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                pid: {**row, "skipped": dict(row["skipped"]), "purposes": dict(row["purposes"]),
                      "latency_ms": round(row["latency_ms"], 1), "cost_usd": round(row["cost_usd"], 4) if row["cost_reported"] else None}
                for pid, row in self.providers.items()
            }


class MultiProviderSearchEngine:
    """Orchestrates multi-provider search across SearXNG, Exa, Google (via
    Gemini grounding), Google Custom Search, Brave, Bing and the keyless
    DuckDuckGo fallback.

    Which providers may run: the run's provider selection (`allowed`), else
    every configured one. Routing (`settings.search_strategy`, default
    "free_first"): free providers (self-hosted SearXNG) are asked first; paid
    ones top up one at a time, cheapest first (`cost_rank`), only while the
    results are still short, and only within the run's paid-call budget, so
    the same query is not bought from every provider. "parallel" calls every
    eligible provider at once. DuckDuckGo is the last resort when nothing
    else returned anything — and only if it is allowed. Every call and every
    skip (with its reason) is recorded in the run's `SearchRunStats`."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseSearchProvider] = {
            "searxng": SearXNGSearchProvider(),
            "exa_search": ExaSearchProvider(),
            "google_gemini": GeminiGoogleSearchProvider(),
            "google_search": GoogleSearchProvider(),
            "brave_search": BraveSearchProvider(),
            "bing_search": BingSearchProvider(),
            "web_fallback": WebFallbackProvider(),
        }
        self._telemetry_lock = threading.Lock()
        self._execution_logs: list[ProviderExecutionLog] = []
        self._cache_lock = threading.Lock()
        self._cache: dict[str, tuple[float, list[SearchProviderResult]]] = {}
        self._cache_ttl_seconds = 3600  # 1 hour
        # Circuit breaker: a provider that fails this many times in a row
        # (timeouts, blocks, quota) is skipped for _BREAKER_COOLDOWN_SECONDS
        # instead of burning a full timeout on every remaining query.
        self._breaker_lock = threading.Lock()
        self._consecutive_failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}
        self._open_reason: dict[str, str] = {}

    _BREAKER_THRESHOLD = 5
    _BREAKER_COOLDOWN_SECONDS = 300
    # Rejected credentials / no API access won't fix themselves within a run.
    _PERMANENT_COOLDOWN_SECONDS = 6 * 60 * 60
    _PERMANENT_MARKERS = ("HTTP 401", "HTTP 403", "PERMISSION_DENIED", "API key not valid", "invalid api key", "401 UNAUTHENTICATED")
    # An exhausted quota / billing limit does not recover within a run either.
    _QUOTA_MARKERS = ("exceeded your current quota", "quota exceeded", "insufficient_quota", "check your plan and billing")
    _QUOTA_COOLDOWN_SECONDS = 60 * 60

    # ------------------------------------------------------------- registry
    @property
    def providers(self) -> dict[str, BaseSearchProvider]:
        return dict(self._providers)

    def _breaker_open(self, provider_id: str) -> bool:
        with self._breaker_lock:
            return self._open_until.get(provider_id, 0.0) > time.time()

    def _breaker_record(self, provider_id: str, ok: bool, permanent: bool = False, error: str | None = None, quota: bool = False) -> None:
        with self._breaker_lock:
            if ok:
                self._consecutive_failures[provider_id] = 0
                self._open_until.pop(provider_id, None)
                self._open_reason.pop(provider_id, None)
                return
            if quota:
                self._open_until[provider_id] = time.time() + self._QUOTA_COOLDOWN_SECONDS
                self._open_reason[provider_id] = f"Quota or billing limit reached: {error}"
                logger.warning("Search provider [%s] is out of quota — skipping it for 1h.", provider_id)
                return
            if permanent:
                self._open_until[provider_id] = time.time() + self._PERMANENT_COOLDOWN_SECONDS
                self._open_reason[provider_id] = f"Credentials or access rejected: {error}"
                logger.warning(
                    "Search provider [%s] rejected our credentials/access — skipping it for %dh.",
                    provider_id, self._PERMANENT_COOLDOWN_SECONDS // 3600,
                )
                return
            count = self._consecutive_failures.get(provider_id, 0) + 1
            self._consecutive_failures[provider_id] = count
            if count >= self._BREAKER_THRESHOLD:
                self._open_until[provider_id] = time.time() + self._BREAKER_COOLDOWN_SECONDS
                self._open_reason[provider_id] = f"Failed {count} times in a row: {error}"
                logger.warning(
                    "Search provider [%s] failed %d times in a row — skipping it for %ds.",
                    provider_id, count, self._BREAKER_COOLDOWN_SECONDS,
                )

    def reset_breakers(self) -> None:
        with self._breaker_lock:
            self._consecutive_failures.clear()
            self._open_until.clear()
            self._open_reason.clear()

    def is_provider_available(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        return bool(provider and provider.unavailable_reason() is None)

    def get_providers_status(self) -> dict[str, dict[str, Any]]:
        """Live status of every search provider — never any credential value:
        configured or why not, tier, whether the circuit breaker is holding it
        off (and why), and its most recent real call."""
        now = time.time()
        with self._breaker_lock:
            open_until = dict(self._open_until)
            open_reason = dict(self._open_reason)
        with self._telemetry_lock:
            last_by_provider: dict[str, ProviderExecutionLog] = {}
            for log in self._execution_logs:
                if log.status not in ("NO_KEY", "SKIPPED_CIRCUIT_OPEN"):
                    last_by_provider[log.provider_id] = log
        status = {}
        for pid, p in self._providers.items():
            last = last_by_provider.get(pid)
            cooldown = max(0, int(open_until.get(pid, 0) - now))
            unavailable = p.unavailable_reason()
            status[pid] = {
                "name": p.provider_name,
                "display_name": p.display_name or p.provider_name,
                "configured": p.is_configured() and not p.retired_reason,
                "unavailable_reason": unavailable,
                "free": bool(p.is_free),
                "tier": "last_resort" if p.last_resort else ("free" if p.is_free else "paid"),
                "cost_rank": p.cost_rank,
                "setup_env": list(p.setup_env),
                "docs_url": p.docs_url,
                "cooling_down_seconds": cooldown,
                "cooldown_reason": open_reason.get(pid) if cooldown else None,
                "last_status": last.status if last else None,
                "last_error": last.error if last else None,
                "last_result_count": last.result_count if last else None,
                "last_at": last.timestamp if last else None,
            }
        return status

    # ---------------------------------------------------------------- search
    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
        requested_sources: set[str] | list[str] | None = None,
        specific_provider_id: str | None = None,
        allowed_providers: set[str] | None = None,
        stats: SearchRunStats | None = None,
        purpose: str = "discovery",
    ) -> list[str]:
        """Dispatches search to eligible providers and returns deduplicated official URLs."""
        results = self.search_details(
            query=query,
            max_results=max_results,
            country=country,
            date_range=date_range,
            requested_sources=requested_sources,
            specific_provider_id=specific_provider_id,
            allowed_providers=allowed_providers,
            stats=stats,
            purpose=purpose,
        )
        return [r.url for r in results]

    def _allowed_set(self, requested_sources, allowed_providers, stats) -> set[str] | None:
        if allowed_providers is not None:
            return set(allowed_providers)
        if stats is not None and stats.allowed is not None:
            return set(stats.allowed)
        req = set(requested_sources or [])
        explicit = req & set(self._providers)
        # An explicit provider list without the channel token (e.g. {"searxng"})
        # selects exactly those providers.
        if explicit and not (req & {"web", "all", "all_sources", "all_operational"}):
            return explicit
        return None

    def search_details(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
        requested_sources: set[str] | list[str] | None = None,
        specific_provider_id: str | None = None,
        allowed_providers: set[str] | None = None,
        stats: SearchRunStats | None = None,
        purpose: str = "discovery",
    ) -> list[SearchProviderResult]:
        """Queries eligible search providers and records detailed telemetry."""
        query = query.strip()
        if not query:
            return []

        allowed = self._allowed_set(requested_sources, allowed_providers, stats)
        if specific_provider_id:
            allowed = {specific_provider_id} if (allowed is None or specific_provider_id in allowed) else set()

        primary: list[BaseSearchProvider] = []
        fallback: BaseSearchProvider | None = None
        for pid, provider in self._providers.items():
            if allowed is not None and pid not in allowed:
                continue  # not selected for this run: never called, not even as a fallback
            reason = provider.unavailable_reason()
            if reason:
                if stats is not None:
                    stats.record_skip(pid, "retired" if provider.retired_reason else "not_configured")
                continue
            if provider.last_resort and not specific_provider_id:
                fallback = provider
            else:
                primary.append(provider)

        if not primary and fallback is None:
            logger.info("Search requested for %r but no selected search provider is available.", query)
            if stats is not None:
                stats.record_query("no_provider")
            return []

        cache_key = f"{query}|{country}|{date_range}|{sorted(p.provider_id for p in primary)}|{fallback and fallback.provider_id}"
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and (time.time() - cached[0] < self._cache_ttl_seconds):
                if stats is not None:
                    for r in cached[1]:
                        if r.metadata.get("provider_id"):
                            stats.note_urls(r.metadata["provider_id"], [r.url])
                    for pid in {r.metadata.get("provider_id") for r in cached[1]} - {None}:
                        stats.record_skip(pid, "served_from_cache")
                    stats.record_query("served_from_cache")
                return cached[1][:max_results]

        aggregated_results: list[SearchProviderResult] = []
        seen_urls: set[str] = set()
        merge_lock = threading.Lock()
        sent_to: list[str] = []  # providers that actually received this query

        def _execute_provider(provider: BaseSearchProvider) -> list[SearchProviderResult]:
            if self._breaker_open(provider.provider_id):
                self._record_log(
                    ProviderExecutionLog(
                        provider_id=provider.provider_id,
                        provider_name=provider.provider_name,
                        query=query,
                        status="SKIPPED_CIRCUIT_OPEN",
                        error="Skipped: provider failed repeatedly and is cooling down",
                    )
                )
                if stats is not None:
                    stats.record_skip(provider.provider_id, "cooling_down")
                return []

            start_t = time.time()
            sent_to.append(provider.provider_id)
            ai_client.drain_usage()  # this thread's earlier, unattributed requests aren't this call's
            try:
                res = provider.search(query=query, max_results=max_results, country=country, date_range=date_range)
                latency = (time.time() - start_t) * 1000
                if stats is not None:
                    stats.record_ai_usage(provider.provider_id, ai_client.drain_usage())
                log = ProviderExecutionLog(
                    provider_id=provider.provider_id,
                    provider_name=provider.provider_name,
                    query=query,
                    status="SUCCESS",
                    result_count=len(res),
                    latency_ms=latency,
                )
                self._record_log(log)
                if stats is not None:
                    stats.record_call(log, purpose, provider.consume_cost())
                    stats.note_urls(provider.provider_id, [r.url for r in res])
                self._breaker_record(provider.provider_id, ok=True)
                for r in res:
                    r.metadata.setdefault("provider_id", provider.provider_id)
                logger.info("Search provider [%s] returned %d results in %.1fms for query: %s", provider.provider_id, len(res), latency, query)
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
                    latency_ms=latency,
                    error=err_msg[:300],
                )
                self._record_log(log)
                if stats is not None:
                    stats.record_call(log, purpose, provider.consume_cost())
                    stats.record_ai_usage(provider.provider_id, ai_client.drain_usage())
                permanent =any(m.lower() in err_msg.lower() for m in self._PERMANENT_MARKERS)
                quota = any(m.lower() in err_msg.lower() for m in self._QUOTA_MARKERS)
                self._breaker_record(provider.provider_id, ok=False, permanent=permanent, error=err_msg[:160], quota=quota and not permanent)
                logger.warning("Search provider [%s] failed (%s) in %.1fms: %s", provider.provider_id, status, latency, err_msg[:200])
                return []

        def _merge(results: list[SearchProviderResult]) -> None:
            with merge_lock:
                for r in results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        aggregated_results.append(r)

        def _run_parallel(providers: list[BaseSearchProvider]) -> None:
            if not providers:
                return
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(providers), 4)) as executor:
                for future in concurrent.futures.as_completed([executor.submit(_execute_provider, p) for p in providers]):
                    try:
                        _merge(future.result())
                    except Exception as e:
                        logger.exception("Provider worker exception: %s", e)

        def _spend(provider: BaseSearchProvider) -> bool:
            if stats is None or provider.is_free or stats.try_spend_paid():
                return True
            stats.record_skip(provider.provider_id, "paid_budget_exhausted")
            return False

        strategy = (getattr(self._settings(), "search_strategy", "free_first") or "free_first").lower()
        free = [p for p in primary if p.is_free]
        paid = sorted((p for p in primary if not p.is_free), key=lambda p: p.cost_rank)
        if strategy == "parallel" or not free or specific_provider_id:
            if free or specific_provider_id:
                _run_parallel([p for p in primary if _spend(p)])
            else:
                for provider in paid:  # no free tier: still top up one at a time
                    if len(aggregated_results) >= max_results:
                        if stats is not None:
                            stats.record_skip(provider.provider_id, "not_needed")
                        continue
                    if _spend(provider):
                        _merge(_execute_provider(provider))
        else:
            _run_parallel(free)
            for provider in paid:
                if len(aggregated_results) >= max_results:
                    if stats is not None:
                        stats.record_skip(provider.provider_id, "not_needed")
                    continue
                if _spend(provider):
                    _merge(_execute_provider(provider))

        # Last resort: only when every other selected provider returned nothing.
        if not aggregated_results and fallback is not None:
            logger.info("Selected providers returned 0 results. Executing %s...", fallback.provider_name)
            _merge(_execute_provider(fallback))
        elif fallback is not None and stats is not None:
            stats.record_skip(fallback.provider_id, "not_needed")

        # Cache only real results. An empty list is usually a failed or
        # timed-out provider, which must stay retryable once it recovers.
        if aggregated_results:
            with self._cache_lock:
                self._cache[cache_key] = (time.time(), aggregated_results)
        if stats is not None:
            # Every provider cooling down or over the paid budget: nothing was asked.
            stats.record_query("with_results" if aggregated_results else ("no_results" if sent_to else "no_provider"))

        return aggregated_results[:max_results]

    @staticmethod
    def _settings():
        from backend.core.config import get_settings

        return get_settings()

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

    def check_provider(self, provider_id: str) -> dict[str, Any]:
        """One real, minimal search to verify a provider works right now.
        Paid providers are billed for it, so this only runs when an admin
        asks (Discovery settings -> Check sources)."""
        provider = self._providers.get(provider_id)
        if provider is None:
            return {"id": provider_id, "status": "unknown"}
        reason = provider.unavailable_reason()
        checked_at = datetime.now(timezone.utc).isoformat()
        if reason:
            return {"id": provider_id, "status": "unavailable", "error": reason, "checked_at": checked_at}
        stats = SearchRunStats(allowed={provider_id})
        self.reset_breaker(provider_id)
        results = self.search_details("upcoming trade show 2027", max_results=3, specific_provider_id=provider_id, stats=stats, purpose="health_check")
        row = stats.snapshot().get(provider_id, {})
        if row.get("failures"):
            return {"id": provider_id, "status": "failed", "error": row.get("last_error"), "checked_at": checked_at}
        return {"id": provider_id, "status": "ok", "results": len(results), "latency_ms": row.get("latency_ms"), "cost_usd": row.get("cost_usd"), "checked_at": checked_at}

    def reset_breaker(self, provider_id: str) -> None:
        with self._breaker_lock:
            self._consecutive_failures.pop(provider_id, None)
            self._open_until.pop(provider_id, None)
            self._open_reason.pop(provider_id, None)


# Global Singleton Instance
search_engine = MultiProviderSearchEngine()
