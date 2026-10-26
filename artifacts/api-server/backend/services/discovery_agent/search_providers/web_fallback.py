from __future__ import annotations

import logging
import threading
import time
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.services.discovery_agent.search_providers.base import (
    BaseSearchProvider,
    SearchProviderResult,
)

logger = logging.getLogger("discovery_agent.search_providers.fallback")

SEARCH_URL = "https://lite.duckduckgo.com/lite/"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_lock = threading.Lock()
_last_search_at: float | None = None


class WebFallbackProvider(BaseSearchProvider):
    """Keyless open-web fallback provider (DuckDuckGo Lite). Transparently identified in logs and UI."""

    provider_id = "web_fallback"
    provider_name = "Keyless Web Fallback (DuckDuckGo)"

    def is_configured(self) -> bool:
        return True

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        self._wait_turn()
        try:
            r = httpx.post(
                SEARCH_URL,
                data={"q": query, "kl": "wt-wt"},
                headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
                timeout=5.0,
                follow_redirects=True,
            )
            if r.status_code != 200 or "anomaly" in r.text:
                raise RuntimeError(f"DuckDuckGo search blocked or unavailable (HTTP {r.status_code})")

            soup = BeautifulSoup(r.text, "html.parser")
            results: list[SearchProviderResult] = []
            seen: set[str] = set()

            for anchor in soup.select("a.result-link"):
                href = anchor.get("href")
                if not href:
                    continue
                unwrapped = self._unwrap(href)
                if unwrapped and unwrapped not in seen:
                    seen.add(unwrapped)
                    title = anchor.get_text(strip=True)
                    results.append(
                        SearchProviderResult(
                            url=unwrapped,
                            title=title,
                            snippet=title,
                            source="Keyless Web Fallback (DuckDuckGo)",
                        )
                    )

            for result in soup.select("div.result"):
                anchor = result.select_one("a.result__a")
                if anchor is None or not anchor.get("href"):
                    continue
                unwrapped = self._unwrap(anchor["href"])
                if unwrapped and unwrapped not in seen:
                    seen.add(unwrapped)
                    title = anchor.get_text(strip=True)
                    results.append(
                        SearchProviderResult(
                            url=unwrapped,
                            title=title,
                            snippet=title,
                            source="Keyless Web Fallback (DuckDuckGo)",
                        )
                    )

            return results[:max_results]
        except Exception as e:
            logger.warning("Web fallback provider encountered an error: %s", e)
            raise

    def _unwrap(self, href: str) -> str | None:
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if parsed.netloc.endswith("duckduckgo.com"):
            target = parse_qs(parsed.query).get("uddg", [None])[0]
            return target if target and target.startswith(("http://", "https://")) else None
        return href if parsed.scheme in ("http", "https") else None

    def _wait_turn(self) -> None:
        global _last_search_at
        with _lock:
            now = time.monotonic()
            if _last_search_at is not None and now - _last_search_at < 1.0:
                time.sleep(1.0 - (now - _last_search_at))
            _last_search_at = time.monotonic()
