"""Shared "fetch one public page and pull out whatever contact/structured-
data it publishes" helpers — used by both Organizer Outreach's
`outreach/organizer_finder.py` (2-hop event-page lookup) and the Event
Discovery Agent's `discovery_agent/organizer_identifier.py` (N-hop lookup
now that web search is available). Kept as one module so the scraping/
parsing logic isn't duplicated or allowed to drift between the two.

Only ever returns what a page actually contains — never guesses or
fabricates a name/email/website that isn't present in the fetched HTML.
"""

import json
import logging
import re
from html import unescape
import threading
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from backend.core.config import get_settings
from backend.core.ssrf_protection import validate_safe_url

logger = logging.getLogger("social_agent.web_fetch")
# Must stay linear on whole pages: the unanchored `[...]+@` form re-scanned a
# long run with no "@" (an inline base64 image, minified JS) from every start
# position — quadratic, minutes for a few hundred KB, all while holding the GIL
# and freezing every other discovery thread. A match may only start where the
# local part starts (lookbehind), and the local part is capped at RFC 5321's 64.
EMAIL_RE = re.compile(r"(?<![a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]{1,64}@[a-zA-Z0-9.-]{1,253}\.[a-zA-Z]{2,24}")
LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_\-%]+/?")
TWITTER_RE = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]{1,30}/?")
INSTAGRAM_RE = re.compile(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.-]{1,50}/?")
FACEBOOK_RE = re.compile(r"https?://(?:www\.)?facebook\.com/[A-Za-z0-9_.-]+/?")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Below this much visible text (and with no JSON-LD), a page is treated as
# an unrendered JavaScript shell.
_THIN_PAGE_TEXT_CHARS = 500

# Discovery reads many pages from the same few listing sites; space them out
# so the agent stays a polite visitor (allevents.in starts refusing bursts).
# Pacing is per host, so parallel discovery workers still fetch different
# sites concurrently while each single site sees at most one request per slot.
_MIN_SECONDS_BETWEEN_REQUESTS = 0.25
_last_request_at: dict[str, float] = {}
_host_lock = threading.Lock()

# Page cache: the same page is typically read twice in one discovery pass
# (event extraction, then the organizer lookup), and again on the next run.
# Successful reads live for _PAGE_TTL_SECONDS. Permanent failures (404/410/
# 451, non-HTML) are remembered for _FAILURE_TTL_SECONDS so they're never
# retried; transient ones (timeouts, 5xx, 429) are not cached at all. 401/403
# are NOT treated as permanent: they're usually bot walls that the headless
# browser fallback can still get through.
_PAGE_TTL_SECONDS = 30 * 60
_FAILURE_TTL_SECONDS = 6 * 60 * 60
_CACHE_MAX_ENTRIES = 3000
_PERMANENT_STATUSES = {400, 404, 405, 410, 451}
_cache_lock = threading.Lock()
_page_cache: dict[tuple[str, bool], tuple[float, str]] = {}
_failed_urls: dict[str, float] = {}
_cache_stats = {"hits": 0, "misses": 0, "permanent_failure_skips": 0}
# Why the latest read of a URL returned nothing ("HTTP 403", "timeout", …), so
# callers can report a real failure instead of "no events" (bounded, recent-first).
_failure_reasons: dict[str, str] = {}
_FAILURE_REASONS_MAX = 2000
# Feeds (RSS / Atom / iCal) are read only by callers that ask for them.
_FEED_TYPES = ("xml", "rss", "atom", "calendar")


def clear_cache() -> None:
    with _cache_lock:
        _page_cache.clear()
        _failed_urls.clear()
        _failure_reasons.clear()
        for key in _cache_stats:
            _cache_stats[key] = 0


def failure_reason(url: str) -> str | None:
    """Why the most recent fetch of `url` returned nothing, if it did."""
    with _cache_lock:
        return _failure_reasons.get(url)


def _note_failure(url: str, reason: str | None) -> None:
    with _cache_lock:
        if reason is None:
            _failure_reasons.pop(url, None)
            return
        if len(_failure_reasons) >= _FAILURE_REASONS_MAX:
            for key in list(_failure_reasons)[: _FAILURE_REASONS_MAX // 10]:
                _failure_reasons.pop(key, None)
        _failure_reasons[url] = reason


def cache_stats() -> dict[str, int]:
    with _cache_lock:
        return dict(_cache_stats)


def is_known_permanent_failure(url: str) -> bool:
    with _cache_lock:
        expires = _failed_urls.get(url)
        return expires is not None and expires > time.time()


def _remember_failure(url: str) -> None:
    with _cache_lock:
        _failed_urls[url] = time.time() + _FAILURE_TTL_SECONDS


def _cache_get(url: str, render_js: bool) -> tuple[bool, str | None]:
    now = time.time()
    with _cache_lock:
        failed_until = _failed_urls.get(url)
        if failed_until is not None and failed_until > now:
            _cache_stats["permanent_failure_skips"] += 1
            return True, None
        entry = _page_cache.get((url, render_js))
        if entry is not None and entry[0] > now:
            _cache_stats["hits"] += 1
            return True, entry[1]
        _cache_stats["misses"] += 1
        return False, None


def _peek(url: str, render_js: bool) -> str | None:
    with _cache_lock:
        entry = _page_cache.get((url, render_js))
        if entry is not None and entry[0] > time.time():
            _cache_stats["hits"] += 1
            return entry[1]
    return None


def _cache_put(url: str, render_js: bool, html: str) -> None:
    with _cache_lock:
        if len(_page_cache) >= _CACHE_MAX_ENTRIES:
            now = time.time()
            for key in [k for k, (exp, _) in _page_cache.items() if exp <= now] or list(_page_cache)[: _CACHE_MAX_ENTRIES // 10]:
                _page_cache.pop(key, None)
        _page_cache[(url, render_js)] = (time.time() + _PAGE_TTL_SECONDS, html)


def fetch(url: str, render_js: bool = False, allow_feed: bool = False) -> str | None:
    """Plain HTTP fetch. With `render_js=True` (Event Discovery Agent only),
    a failed or thin result is retried in a headless browser — see
    `browser_fetch.py`; if that fails too, the HTTP result is kept.
    `allow_feed=True` also accepts RSS/Atom/iCal/XML responses (feed adapters).
    Results are served from the page cache when fresh. When nothing is
    returned, `failure_reason(url)` says why."""
    allow_dev = get_settings().environment.lower() != "production"
    try:
        url = validate_safe_url(url, allow_private_in_dev=allow_dev)
    except ValueError as exc:
        logger.warning("SSRF protection blocked fetch for %s: %s", url, exc)
        _note_failure(url, "blocked by SSRF protection")
        return None

    cached, cached_html = _cache_get(url, render_js)
    if cached:
        if cached_html is None:
            _note_failure(url, failure_reason(url) or "skipped: this URL failed permanently earlier (cached for 6h)")
        return cached_html
    # The other mode's copy is just as good when it's what this call would
    # return anyway: a rendered page for a plain read, or a plain page that
    # isn't a thin JS shell for a render_js read.
    other = _peek(url, not render_js)
    if other is not None and (not render_js or not is_thin_page(other)):
        _cache_put(url, render_js, other)
        return other

    if render_js:
        _wait_for_host(url)
    html = _http_get(url, allow_feed=True) if allow_feed else _http_get(url)
    if render_js and not allow_feed and (html is None or is_thin_page(html)) and not is_known_permanent_failure(url):
        from backend.services.social_agent import browser_fetch

        rendered = browser_fetch.render(url)
        if rendered:
            html = rendered
    if html is not None:
        _note_failure(url, None)
        _cache_put(url, render_js, html)
    return html


def _wait_for_host(url: str) -> None:
    """Reserve this host's next request slot under a lock, then sleep
    outside it — so concurrent workers queue per host, not globally."""
    host = (urlparse(url).netloc or "").lower()
    with _host_lock:
        now = time.monotonic()
        last = _last_request_at.get(host)
        slot = now if last is None else max(now, last + _MIN_SECONDS_BETWEEN_REQUESTS)
        _last_request_at[host] = slot
    if slot > now:
        time.sleep(slot - now)


_LD_JSON_BLOCK_RE = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
_NON_TEXT_BLOCK_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def is_thin_page(html: str) -> bool:
    """True when a page has no usable JSON-LD and under _THIN_PAGE_TEXT_CHARS
    of visible text (an unrendered JavaScript shell). Regex-based: it runs on
    every discovery fetch, and a full BeautifulSoup parse here was the single
    biggest CPU cost in the pipeline."""
    for block in _LD_JSON_BLOCK_RE.findall(html):
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) or (isinstance(data, list) and any(isinstance(item, dict) for item in data)):
            return False
    visible = _TAG_RE.sub(" ", _NON_TEXT_BLOCK_RE.sub(" ", html))
    return len(" ".join(unescape(visible).split())) < _THIN_PAGE_TEXT_CHARS


def _http_get(url: str, allow_feed: bool = False) -> str | None:
    allow_dev = get_settings().environment.lower() != "production"
    try:
        url = validate_safe_url(url, allow_private_in_dev=allow_dev)
    except ValueError as exc:
        logger.warning("SSRF protection blocked HTTP get for %s: %s", url, exc)
        _note_failure(url, "blocked by SSRF protection")
        return None
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True, headers=DEFAULT_HEADERS)
    except httpx.TimeoutException:
        _note_failure(url, "timed out after 10s")
        return None  # transient, may be retried later
    except Exception as exc:
        _note_failure(url, f"network error ({type(exc).__name__})")
        return None
    if response.status_code != 200:
        _note_failure(url, f"HTTP {response.status_code}" + (" (bot wall / access denied)" if response.status_code in (401, 403) else ""))
        if response.status_code in _PERMANENT_STATUSES:
            _remember_failure(url)
        return None
    content_type = response.headers.get("content-type", "").lower()
    is_html = "text/html" in content_type or "application/xhtml" in content_type
    if not is_html and not (allow_feed and any(kind in content_type for kind in _FEED_TYPES)):
        _note_failure(url, f"not a web page ({content_type.split(';')[0] or 'unknown type'})")
        if not allow_feed:
            _remember_failure(url)
        return None
    return response.text


def find_json_ld_nodes(soup: BeautifulSoup) -> list[dict]:
    """All parsed schema.org JSON-LD objects on the page, flattened out of
    top-level lists/`@graph` wrappers. Malformed blocks are skipped, not
    raised on — one bad script tag shouldn't break extraction of the rest."""
    nodes: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if isinstance(candidate, dict):
                nodes.append(candidate)
                graph = candidate.get("@graph")
                if isinstance(graph, list):
                    nodes.extend(node for node in graph if isinstance(node, dict))
    return nodes


def from_json_ld_organizer(soup: BeautifulSoup) -> tuple[str | None, str | None, str | None]:
    """Returns (name, website, email) if the page has schema.org Event/
    Organization structured data with an `organizer`."""
    for node in find_json_ld_nodes(soup):
        organizer_node = node.get("organizer")
        if isinstance(organizer_node, dict):
            name = organizer_node.get("name")
            website = organizer_node.get("url")
            email = organizer_node.get("email")
            if isinstance(email, str):
                email = email.replace("mailto:", "").strip()
            if name or website or email:
                return name, website, email
    return None, None, None


def extract_contact(html: str, soup: BeautifulSoup | None = None) -> tuple[str | None, str | None, str | None, str | None]:
    """Returns (name, website, email, linkedin) found on one already-fetched page.
    Pass the page's already-parsed `soup` (read-only here) to skip a second parse."""
    from backend.services.discovery_agent.email_verifier import is_valid_organizer_email

    soup = soup if soup is not None else BeautifulSoup(html, "html.parser")

    name, website, raw_email = from_json_ld_organizer(soup)
    email: str | None = None
    if raw_email:
        valid, norm, _ = is_valid_organizer_email(raw_email)
        if valid:
            email = norm

    if not email:
        mailto_hrefs = [a["href"] for a in soup.find_all("a", href=True) if a["href"].lower().startswith("mailto:")]
        for href in mailto_hrefs:
            candidate_email = href.split(":", 1)[1].split("?")[0].strip()
            valid, norm, _ = is_valid_organizer_email(candidate_email)
            if valid:
                email = norm
                break

    if not email:
        for match in EMAIL_RE.finditer(html):
            valid, norm, _ = is_valid_organizer_email(match.group(0))
            if valid:
                email = norm
                break

    linkedin = None
    for anchor in soup.find_all("a", href=True):
        if LINKEDIN_RE.match(anchor["href"]):
            linkedin = anchor["href"]
            break

    if not name:
        site_name_tag = soup.find("meta", attrs={"property": "og:site_name"})
        if site_name_tag and site_name_tag.get("content"):
            name = site_name_tag["content"].strip()
        elif soup.title and soup.title.get_text(strip=True):
            name = soup.title.get_text(strip=True)

    return name, website, email, linkedin


def extract_social_links(soup: BeautifulSoup) -> dict[str, str]:
    """Extracts public organizer social channels (LinkedIn, Twitter/X, Instagram, Facebook)."""
    socials: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if "linkedin" not in socials and LINKEDIN_RE.match(href):
            socials["linkedin"] = href
        elif "twitter" not in socials and TWITTER_RE.match(href):
            socials["twitter"] = href
        elif "instagram" not in socials and INSTAGRAM_RE.match(href):
            socials["instagram"] = href
        elif "facebook" not in socials and FACEBOOK_RE.match(href):
            if "sharer" not in href.lower() and "share.php" not in href.lower():
                socials["facebook"] = href
    return socials


def extract_phone(html: str) -> str | None:
    """Best-effort Indian phone number extraction (10-digit mobile, or
    +91-prefixed) — never invented, `None` when nothing matches."""
    match = re.search(r"(?:\+?91[\s-]?)?[6-9]\d{9}\b", html)
    return match.group(0).strip() if match else None
