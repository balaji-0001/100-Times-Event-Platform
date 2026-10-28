"""Thread-safe multi-tier caching layer for 100 TIMES Event Discovery.

Provides bounded, thread-safe in-memory caching with TTL expiration for:
1. Page HTML fetches & dead/blocked URL avoidance.
2. Extracted Organizer Candidates (keyed by normalized domain/URL).
3. Search provider query results.
4. Fast URL deduplication sets for live discovery runs.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("discovery_agent.cache")


class ThreadSafeTTLCache:
    """Thread-safe bounded in-memory cache with time-to-live expiration."""

    def __init__(self, max_size: int = 1000, default_ttl_sec: float = 3600.0) -> None:
        self._max_size = max_size
        self._default_ttl = default_ttl_sec
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            expires_at, value = entry
            if time.time() > expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl_sec: float | None = None) -> None:
        ttl = ttl_sec if ttl_sec is not None else self._default_ttl
        expires_at = time.time() + ttl
        with self._lock:
            if len(self._store) >= self._max_size:
                # Evict expired first, or oldest
                now = time.time()
                expired_keys = [k for k, (exp, _) in self._store.items() if exp < now]
                if expired_keys:
                    for k in expired_keys:
                        del self._store[k]
                elif len(self._store) >= self._max_size:
                    # Remove first 10% oldest entries
                    evict_count = max(1, self._max_size // 10)
                    for k in list(self._store.keys())[:evict_count]:
                        del self._store[k]
            self._store[key] = (expires_at, value)

    def contains(self, key: str) -> bool:
        return self.get(key) is not None

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
            }

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0


def _normalize_host(url: str) -> str:
    """Extracts clean lowercase domain from URL."""
    try:
        raw = url if "://" in url else f"http://{url}"
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower().split(":")[0]
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return url.lower()


class DiscoveryCacheManager:
    """Centralized high-performance cache for all discovery operations."""

    def __init__(self) -> None:
        # Page HTML Cache: 500 pages, 2 hour TTL
        self.pages = ThreadSafeTTLCache(max_size=500, default_ttl_sec=7200.0)
        # Dead / Unreachable URLs Cache: 1000 items, 1 hour TTL
        self.dead_urls = ThreadSafeTTLCache(max_size=1000, default_ttl_sec=3600.0)
        # Identified Organizer Candidate Cache: 2000 organizers, 24 hour TTL
        self.organizers = ThreadSafeTTLCache(max_size=2000, default_ttl_sec=86400.0)
        # Search Queries Cache: 500 queries, 1 hour TTL
        self.searches = ThreadSafeTTLCache(max_size=500, default_ttl_sec=3600.0)

    # 1. Page Caching
    def get_page(self, url: str) -> str | None:
        return self.pages.get(url)

    def set_page(self, url: str, html: str, ttl_sec: float = 7200.0) -> None:
        if html:
            self.pages.set(url, html, ttl_sec)

    def is_dead_url(self, url: str) -> bool:
        return self.dead_urls.contains(url)

    def mark_dead_url(self, url: str, ttl_sec: float = 3600.0) -> None:
        self.dead_urls.set(url, True, ttl_sec)

    # 2. Organizer Caching (by domain or organizer homepage)
    def get_organizer(self, org_key: str) -> Any | None:
        host = _normalize_host(org_key)
        return self.organizers.get(host) if host else None

    def set_organizer(self, org_key: str, organizer_candidate: Any) -> None:
        host = _normalize_host(org_key)
        if host and organizer_candidate:
            self.organizers.set(host, organizer_candidate, 86400.0)

    # 3. Search Results Caching
    def get_search_results(self, query: str) -> list[str] | None:
        return self.searches.get(query.strip().lower())

    def set_search_results(self, query: str, urls: list[str]) -> None:
        if urls:
            self.searches.set(query.strip().lower(), urls, 3600.0)

    def get_summary_stats(self) -> dict[str, Any]:
        return {
            "pages": self.pages.stats(),
            "dead_urls": self.dead_urls.stats(),
            "organizers": self.organizers.stats(),
            "searches": self.searches.stats(),
        }


# Global singleton instance
discovery_cache = DiscoveryCacheManager()
