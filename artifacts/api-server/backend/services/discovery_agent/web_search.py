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

SEARCH_URL = "https://lite.duckduckgo.com/lite/"
FALLBACK_URL = "https://html.duckduckgo.com/html/"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_MIN_SECONDS_BETWEEN_SEARCHES = 1.0

_lock = threading.Lock()
_last_search_at: float | None = None
_ddg_unresponsive = False


class SearchBlocked(Exception):
    """The search engine refused the request (captcha / rate limit)."""


def search(query: str, max_results: int) -> list[str]:
    global _ddg_unresponsive
    _wait_turn()

    if not _ddg_unresponsive:
        try:
            response = _post(query)
            if response.status_code == 200 and "anomaly" not in response.text:
                results = parse_results(response.text)
                if results:
                    return results[:max_results]
            else:
                _ddg_unresponsive = True
        except Exception:
            _ddg_unresponsive = True

    # Fast keyless fallback: Bing returns structured search results in < 1 second
    return _search_bing(query, max_results)


def _search_bing(query: str, max_results: int) -> list[str]:
    import base64
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = httpx.get("https://www.bing.com/search", params={"q": query}, headers=headers, timeout=12)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        urls: list[str] = []
        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href", "")
            if "bing.com/ck/a" in href:
                u = parse_qs(urlparse(href).query).get("u", [""])[0]
                if u.startswith("a1"):
                    raw_b64 = u[2:]
                    padded = raw_b64 + "=" * (-len(raw_b64) % 4)
                    try:
                        decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
                        if decoded.startswith(("http://", "https://")) and decoded not in urls:
                            urls.append(decoded)
                    except Exception:
                        pass
            elif href.startswith(("http://", "https://")) and href not in urls:
                urls.append(href)
        return urls[:max_results]
    except Exception:
        return []


def parse_results(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a.result-link"):
        href = anchor.get("href")
        if not href:
            continue
        url = _unwrap(href)
        if url and url not in urls:
            urls.append(url)
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


def _post(query: str, url: str | None = None, **kwargs) -> httpx.Response:
    target_url = url or SEARCH_URL
    return httpx.post(
        target_url,
        data={"q": query, "kl": "wt-wt"},
        headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        timeout=3.5,
        follow_redirects=True,
    )


def _wait_turn() -> None:
    global _last_search_at
    with _lock:
        now = time.monotonic()
        if _last_search_at is not None and now - _last_search_at < _MIN_SECONDS_BETWEEN_SEARCHES:
            time.sleep(_MIN_SECONDS_BETWEEN_SEARCHES - (now - _last_search_at))
        _last_search_at = time.monotonic()
