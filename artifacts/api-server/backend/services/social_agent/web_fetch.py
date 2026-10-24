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
import time
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from backend.core.config import get_settings
from backend.core.ssrf_protection import validate_safe_url

logger = logging.getLogger("social_agent.web_fetch")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
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
_MIN_SECONDS_BETWEEN_REQUESTS = 1.5
_last_request_at: dict[str, float] = {}


def fetch(url: str, render_js: bool = False) -> str | None:
    """Plain HTTP fetch. With `render_js=True` (Event Discovery Agent only),
    a failed or thin result is retried in a headless browser — see
    `browser_fetch.py`; if that fails too, the HTTP result is kept."""
    allow_dev = get_settings().environment.lower() != "production"
    try:
        url = validate_safe_url(url, allow_private_in_dev=allow_dev)
    except ValueError as exc:
        logger.warning("SSRF protection blocked fetch for %s: %s", url, exc)
        return None

    if render_js:
        _wait_for_host(url)
    html = _http_get(url)
    if not render_js or (html is not None and not is_thin_page(html)):
        return html

    from backend.services.social_agent import browser_fetch

    return browser_fetch.render(url) or html


def _wait_for_host(url: str) -> None:
    host = (urlparse(url).netloc or "").lower()
    last = _last_request_at.get(host)
    now = time.monotonic()
    if last is not None and now - last < _MIN_SECONDS_BETWEEN_REQUESTS:
        time.sleep(_MIN_SECONDS_BETWEEN_REQUESTS - (now - last))
    _last_request_at[host] = time.monotonic()


def is_thin_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    if find_json_ld_nodes(soup):
        return False
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return len(" ".join(soup.get_text(separator=" ").split())) < _THIN_PAGE_TEXT_CHARS


def _http_get(url: str) -> str | None:
    allow_dev = get_settings().environment.lower() != "production"
    try:
        url = validate_safe_url(url, allow_private_in_dev=allow_dev)
    except ValueError as exc:
        logger.warning("SSRF protection blocked HTTP get for %s: %s", url, exc)
        return None
    try:
        response = httpx.get(url, timeout=10, follow_redirects=True, headers=DEFAULT_HEADERS)
    except Exception:
        return None
    if response.status_code != 200:
        return None
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
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


def extract_contact(html: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Returns (name, website, email, linkedin) found on one already-fetched page."""
    from backend.services.discovery_agent.email_verifier import is_valid_organizer_email

    soup = BeautifulSoup(html, "html.parser")

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
