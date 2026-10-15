"""Keyless web search for the Discovery automation — DuckDuckGo's HTML
results page, which needs no API key and no AI. (Bing and Google serve
automated clients degraded results or captchas; DuckDuckGo's HTML endpoint
returns the real ranking.)

Only URLs DuckDuckGo actually returned are used; ads are skipped. Searches
are spaced out, and a block (captcha / rate limit) raises `SearchBlocked`
so the run can stop searching and keep everything else it found.
"""

import threading
import time
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

SEARCH_URL = "https://html.duckduckgo.com/html/"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_MIN_SECONDS_BETWEEN_SEARCHES = 3.0

_lock = threading.Lock()
_last_search_at: float | None = None


class SearchBlocked(Exception):
    """The search engine refused the request (captcha / rate limit)."""


def search(query: str, max_results: int) -> list[str]:
    _wait_turn()
    try:
        response = _post(query)
    except httpx.HTTPError as exc:
        raise SearchBlocked(f"DuckDuckGo search could not be reached: {exc}") from exc
    if response.status_code != 200 or "anomaly-modal" in response.text:
        raise SearchBlocked(f"DuckDuckGo refused the search (HTTP {response.status_code}) — it may be rate-limiting this server.")
    return parse_results(response.text)[:max_results]


def parse_results(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for result in soup.select("div.result"):
        if "result--ad" in (result.get("class") or []):
            continue
        anchor = result.select_one("a.result__a")
        if anchor is None or not anchor.get("href"):
            continue
        url = _unwrap(anchor["href"])
        if url and url not in urls:
            urls.append(url)
    return urls


def _unwrap(href: str) -> str | None:
    """DuckDuckGo GET results wrap links as //duckduckgo.com/l/?uddg=<url>."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        return target if target and target.startswith(("http://", "https://")) else None
    return href if parsed.scheme in ("http", "https") else None


def _post(query: str) -> httpx.Response:
    return httpx.post(
        SEARCH_URL,
        data={"q": query, "kl": "in-en"},
        headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"},
        timeout=15,
        follow_redirects=True,
    )


def _wait_turn() -> None:
    global _last_search_at
    with _lock:
        now = time.monotonic()
        if _last_search_at is not None and now - _last_search_at < _MIN_SECONDS_BETWEEN_SEARCHES:
            time.sleep(_MIN_SECONDS_BETWEEN_SEARCHES - (now - _last_search_at))
        _last_search_at = time.monotonic()
