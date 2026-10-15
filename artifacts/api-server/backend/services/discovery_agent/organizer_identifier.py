"""Organizer Identifier — generalizes Organizer Outreach's
`outreach/organizer_finder.py` 2-hop lookup to more hops, since the Event
Discovery Agent has a real web-search tool available (`organizer_finder.py`
is capped at 2 hops specifically because *it* has no search API).

Follows the priority chain from the spec: event page -> organizer/host link
-> organizer's own official site -> a contact page on that site. Every hop
that actually gets fetched is recorded as a `CandidateSource` so the final
`event_sources`/evidence trail shows exactly where each contact detail came
from — this never fabricates a contact "found" on a page that wasn't
actually read.
"""

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.services.discovery_agent.platforms import is_platform_url, same_host
from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate, OrganizerCandidate
from backend.services.social_agent.browser_fetch import browser_fetch_enabled
from backend.services.social_agent.web_fetch import extract_contact, extract_phone, fetch, from_json_ld_organizer

_MAX_HOPS = 3
_CONTACT_LINK_HINTS = ("contact", "about", "reach-us", "get-in-touch")

_ORGANIZER_TYPE_BY_SOURCE_TYPE = {
    "college_page": "college",
    "government": "government",
    "trade_association": "association",
}


def _contact_page_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        text = (anchor.get_text() or "").strip().lower()
        haystack = f"{href.lower()} {text}"
        if any(hint in haystack for hint in _CONTACT_LINK_HINTS):
            absolute = urljoin(base_url, href).split("#", 1)[0]
            if urlparse(absolute).scheme in ("http", "https"):
                links.append(absolute)
    return links


def _next_hop(website: str | None, soup: BeautifulSoup, current_url: str, visited: set[str], platform_url: str | None) -> str | None:
    """The organizer's own site first, then a contact/about page — skipping
    pages already read, and (for platform-hosted events) anything on the
    platform itself, whose contact page is the platform's, not the organizer's."""
    for url in ([website] if website else []) + _contact_page_links(soup, current_url):
        if url in visited:
            continue
        if platform_url and same_host(url, platform_url):
            continue
        return url
    return None


def identify_organizer(candidate: ExtractedEventCandidate) -> OrganizerCandidate:
    if not candidate.url:
        return OrganizerCandidate(found=False)

    sources: list[CandidateSource] = []
    name = website = email = linkedin = phone = None
    confidence = 0

    render_js = browser_fetch_enabled()
    event_html = fetch(candidate.url, render_js=render_js)
    if not event_html:
        return OrganizerCandidate(found=False)

    sources.append(candidate.primary_source or CandidateSource(url=candidate.url, source_type="event_listing"))
    soup = BeautifulSoup(event_html, "html.parser")
    on_platform = is_platform_url(candidate.url) or (
        candidate.primary_source is not None and candidate.primary_source.source_type == "aggregator"
    )
    if on_platform:
        # Only the organizer the page explicitly declares counts; everything
        # else on a ticketing/listing page (footer mailbox, helpline, social
        # links, site name) belongs to the platform.
        name, website, email = from_json_ld_organizer(soup)
        if website and same_host(website, candidate.url):
            website = None
    else:
        name, website, email, linkedin = extract_contact(event_html)
        phone = extract_phone(event_html)
    if candidate.raw_evidence is not None:
        confidence += 30  # this hop came from structured JSON-LD, not free text

    current_url = candidate.url
    current_soup = soup
    visited = {candidate.url}
    hops_used = 1

    while hops_used < _MAX_HOPS and not email:
        next_url = _next_hop(website, current_soup, current_url, visited, platform_url=candidate.url if on_platform else None)
        if not next_url:
            break

        html = fetch(next_url, render_js=render_js)
        visited.add(next_url)
        hops_used += 1
        if not html:
            break

        sources.append(CandidateSource(url=next_url, source_type="organizer_website"))
        hop_soup = BeautifulSoup(html, "html.parser")
        hop_name, hop_website, hop_email, hop_linkedin = extract_contact(html)
        name = name or hop_name
        email = email or hop_email
        linkedin = linkedin or hop_linkedin
        website = hop_website or website or next_url
        phone = phone or extract_phone(html)
        current_url = next_url
        current_soup = hop_soup

    if not name:
        name = candidate.organizer_name_hint

    if email:
        confidence += 40
    if phone:
        confidence += 15
    if linkedin:
        confidence += 10
    if website and website != candidate.url:
        confidence += 15
    confidence = min(confidence, 100)

    organizer_type = None
    if candidate.primary_source is not None:
        organizer_type = _ORGANIZER_TYPE_BY_SOURCE_TYPE.get(candidate.primary_source.source_type)

    return OrganizerCandidate(
        found=bool(email),
        name=name,
        email=email,
        phone=phone,
        website=website or (None if on_platform else candidate.url),
        linkedin=linkedin,
        organizer_type=organizer_type,
        confidence_score=confidence,
        sources=sources,
    )
