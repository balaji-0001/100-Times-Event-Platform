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

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.services.discovery_agent.email_verifier import is_valid_organizer_email
from backend.services.discovery_agent.platforms import is_platform_url, same_host
from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate, OrganizerCandidate
from backend.services.social_agent.browser_fetch import browser_fetch_enabled
from backend.services.social_agent.web_fetch import extract_contact, extract_phone, extract_social_links, fetch, from_json_ld_organizer

logger = logging.getLogger("discovery_agent.organizer_identifier")
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
    twitter = instagram = facebook = None
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
    email_source_url: str | None = None
    if on_platform:
        # Only the organizer the page explicitly declares counts; everything
        # else on a ticketing/listing page (footer mailbox, helpline, social
        # links, site name) belongs to the platform.
        name, website, raw_email = from_json_ld_organizer(soup)
        if raw_email:
            valid, norm_email, _ = is_valid_organizer_email(raw_email)
            if valid:
                email = norm_email
                email_source_url = candidate.url
        if website and same_host(website, candidate.url):
            website = None
    else:
        name, website, raw_email, linkedin = extract_contact(event_html)
        socials = extract_social_links(soup)
        linkedin = linkedin or socials.get("linkedin")
        twitter = socials.get("twitter")
        instagram = socials.get("instagram")
        facebook = socials.get("facebook")
        if raw_email:
            valid, norm_email, _ = is_valid_organizer_email(raw_email)
            if valid:
                email = norm_email
                email_source_url = candidate.url
        phone = extract_phone(event_html)

    # Check candidate raw structured evidence if available
    if candidate.raw_evidence and isinstance(candidate.raw_evidence, dict):
        raw_org = candidate.raw_evidence.get("organizer")
        if isinstance(raw_org, dict):
            name = name or raw_org.get("name")
            if not website and raw_org.get("url"):
                org_url = raw_org.get("url")
                if not same_host(org_url, candidate.url):
                    website = org_url
            if not email and raw_org.get("email"):
                valid, norm_email, _ = is_valid_organizer_email(raw_org.get("email"))
                if valid:
                    email = norm_email
                    email_source_url = candidate.url

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
        hop_name, hop_website, hop_raw_email, hop_linkedin = extract_contact(html)
        hop_socials = extract_social_links(hop_soup)
        name = name or hop_name
        if hop_raw_email and not email:
            valid, norm_email, _ = is_valid_organizer_email(hop_raw_email)
            if valid:
                email = norm_email
                email_source_url = next_url
        linkedin = linkedin or hop_linkedin or hop_socials.get("linkedin")
        twitter = twitter or hop_socials.get("twitter")
        instagram = instagram or hop_socials.get("instagram")
        facebook = facebook or hop_socials.get("facebook")
        website = hop_website or website or next_url
        phone = phone or extract_phone(html)
        current_url = next_url
        current_soup = hop_soup

    # Search fallback if direct links did not reveal a verified organizer email (only for direct organizer/event sites, not aggregators)
    if not email and not on_platform:
        target_name = name or candidate.organizer_name_hint
        org_search_query = None
        if target_name and len(target_name.strip()) > 3:
            loc = f" {candidate.city}" if candidate.city else ""
            org_search_query = f"{target_name.strip()}{loc} official website contact email"
        elif candidate.name and len(candidate.name.strip()) > 5:
            loc = f" {candidate.city}" if candidate.city else ""
            org_search_query = f"{candidate.name.strip()}{loc} organizer official contact"

        if org_search_query:
            try:
                from backend.services.discovery_agent import web_search
                found_urls = web_search.search(org_search_query, max_results=3)
                for res_url in found_urls:
                    if res_url in visited or is_platform_url(res_url):
                        continue
                    visited.add(res_url)
                    res_html = fetch(res_url, render_js=False)
                    if not res_html:
                        continue
                    res_soup = BeautifulSoup(res_html, "html.parser")
                    s_name, s_website, s_email, s_linkedin = extract_contact(res_html)
                    if s_email:
                        valid, norm_email, _ = is_valid_organizer_email(s_email)
                        if valid:
                            email = norm_email
                            email_source_url = res_url
                            name = name or s_name or target_name
                            website = website or s_website or res_url
                            linkedin = linkedin or s_linkedin
                            sources.append(CandidateSource(url=res_url, source_type="organizer_website"))
                            break

                    for sub_link in _contact_page_links(res_soup, res_url)[:2]:
                        if sub_link in visited:
                            continue
                        visited.add(sub_link)
                        sub_html = fetch(sub_link, render_js=False)
                        if not sub_html:
                            continue
                        _, sub_site, sub_email, sub_li = extract_contact(sub_html)
                        if sub_email:
                            valid, norm_email, _ = is_valid_organizer_email(sub_email)
                            if valid:
                                email = norm_email
                                email_source_url = sub_link
                                name = name or s_name or target_name
                                website = website or sub_site or res_url
                                linkedin = linkedin or sub_li
                                sources.append(CandidateSource(url=sub_link, source_type="organizer_website"))
                                break
                    if email:
                        break
            except Exception as exc:
                logger.debug("Organizer search lookup skipped: %s", exc)

    if not name:
        name = candidate.organizer_name_hint

    if email:
        confidence += 40
    if phone:
        confidence += 15
    if linkedin or twitter or instagram or facebook:
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
        twitter=twitter,
        instagram=instagram,
        facebook=facebook,
        organizer_type=organizer_type,
        confidence_score=confidence,
        sources=sources,
        email_source_url=email_source_url,
    )
