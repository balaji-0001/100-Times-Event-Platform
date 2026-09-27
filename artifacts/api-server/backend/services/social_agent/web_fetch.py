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
import re

import httpx
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_\-%]+/?")
USER_AGENT = "100TimesAgentBot/1.0 (+https://100times.in; event/organizer discovery)"


def fetch(url: str) -> str | None:
    try:
        response = httpx.get(url, timeout=8, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError:
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
    soup = BeautifulSoup(html, "html.parser")

    name, website, email = from_json_ld_organizer(soup)

    if not email:
        mailto_hrefs = [a["href"] for a in soup.find_all("a", href=True) if a["href"].lower().startswith("mailto:")]
        if mailto_hrefs:
            email = mailto_hrefs[0].split(":", 1)[1].split("?")[0].strip()

    if not email:
        match = EMAIL_RE.search(html)
        if match:
            email = match.group(0)

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


def extract_phone(html: str) -> str | None:
    """Best-effort Indian phone number extraction (10-digit mobile, or
    +91-prefixed) — never invented, `None` when nothing matches."""
    match = re.search(r"(?:\+?91[\s-]?)?[6-9]\d{9}\b", html)
    return match.group(0).strip() if match else None
