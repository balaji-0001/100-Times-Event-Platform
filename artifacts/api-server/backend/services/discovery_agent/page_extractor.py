"""Turns web pages into structured event facts — fixed rules, no AI.

Cheapest/most-trustworthy first:
  1. schema.org JSON-LD `Event` data the page publishes — machine-authored by
     the site itself. A listing page yields every event on it.
  2. A listing without structured data: the same-site event pages it links
     to, each read the same way.
  3. Otherwise the best-effort text reader (`text_extractor.py`): title, first
     upcoming date and venue by fixed rules, always held for review.

Any field a page doesn't state stays `None` — never guessed.
"""

from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.services.discovery_agent.country_utils import infer_country
from backend.services.discovery_agent.format_normalize import normalize_event_format
from backend.services.discovery_agent.platforms import is_platform_url, same_host
from backend.services.discovery_agent.text_extractor import extract_best_effort
from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate
from backend.services.social_agent.browser_fetch import browser_fetch_enabled
from backend.services.social_agent.web_fetch import fetch, find_json_ld_nodes

# A page needs at least this many same-site event links to be treated as a
# listing; fewer are usually "related events" links on a single event page.
_MIN_LISTING_LINKS = 2
# Path segments that mark a same-site link as an event page on venue /
# organizer calendars ("/events/x", "/whats-on/x" on ExCeL London, …).
_EVENT_PATH_HINTS = ("/event", "/whats-on/", "/exhibitions/", "/trade-fairs/", "/fairs/", "/shows/")


def _event_nodes(soup: BeautifulSoup) -> list[dict]:
    """Every schema.org Event on the page, including ones nested in an
    `ItemList` (how Eventbrite's listing pages publish theirs)."""
    nodes: list[dict] = []
    for node in find_json_ld_nodes(soup):
        elements = node.get("itemListElement")
        if isinstance(elements, list):
            for element in elements:
                if isinstance(element, dict):
                    nodes.append(element["item"] if isinstance(element.get("item"), dict) else element)
        nodes.append(node)

    events = []
    for node in nodes:
        types = node.get("@type")
        type_names = types if isinstance(types, list) else [types]
        if any(isinstance(t, str) and "event" in t.lower() for t in type_names) and isinstance(node.get("name"), str) and node["name"]:
            events.append(node)
    return events


def _from_json_ld(source: CandidateSource, soup: BeautifulSoup) -> ExtractedEventCandidate | None:
    nodes = _event_nodes(soup)
    return _event_from_node(source, nodes[0]) if nodes else None


def _event_from_node(source: CandidateSource, node: dict) -> ExtractedEventCandidate:
    name = node["name"]

    location = node.get("location")
    venue = city = state = country = None
    if isinstance(location, dict):
        venue = location.get("name") if isinstance(location.get("name"), str) else None
        address = location.get("address")
        if isinstance(address, dict):
            city = address.get("addressLocality")
            state = address.get("addressRegion")
            addr_country = address.get("addressCountry")
            if isinstance(addr_country, dict):
                country = addr_country.get("name")
            elif isinstance(addr_country, str):
                country = addr_country
        elif isinstance(address, str):
            venue = venue or address

    resolved_country = infer_country(country, city=city, state=state, url=source.url, default="Worldwide")

    offers = node.get("offers")
    ticket_url = None
    if isinstance(offers, dict):
        ticket_url = offers.get("url")
    elif isinstance(offers, list) and offers and isinstance(offers[0], dict):
        ticket_url = offers[0].get("url")

    organizer = node.get("organizer")
    organizer_name = organizer.get("name") if isinstance(organizer, dict) else None

    attendance_mode = node.get("eventAttendanceMode")
    event_format = normalize_event_format(attendance_mode) if isinstance(attendance_mode, str) else None

    # Some sites HTML-encode their structured data ("Rock &amp; Roll").
    name, venue, city, state = (unescape(v).strip() if isinstance(v, str) else None for v in (name, venue, city, state))
    description = node.get("description")

    return ExtractedEventCandidate(
        name=name,
        event_description=unescape(description) if isinstance(description, str) else None,
        date=node.get("startDate") if isinstance(node.get("startDate"), str) else None,
        venue=venue,
        city=city,
        state=state,
        country=resolved_country,
        url=source.url,
        ticket_url=ticket_url,
        event_format=event_format,
        organizer_name_hint=organizer_name if isinstance(organizer_name, str) else None,
        extraction_confidence=90,  # structured data — high trust
        primary_source=source,
        sources=[source],
        raw_evidence=node,
    )


def extract_event_from_page(source: CandidateSource, cities: list[str] | None = None, render_js: bool | None = None) -> ExtractedEventCandidate | None:
    """One event page: its structured data, else the best-effort reader."""
    use_js = browser_fetch_enabled() if render_js is None else render_js
    html = fetch(source.url, render_js=use_js)
    if not html:
        return None
    from_structured = _from_json_ld(source, BeautifulSoup(html, "html.parser"))
    return from_structured or extract_best_effort(source, html, cities or [])


def _source_for(url: str) -> CandidateSource:
    return CandidateSource(
        url=url,
        source_type="aggregator" if is_platform_url(url) else "event_listing",
        source_website=urlparse(url).netloc or None,
    )


def _event_page_links(soup: BeautifulSoup, listing_url: str) -> list[str]:
    """Same-site links that look like individual event pages."""
    listing_path = urlparse(listing_url).path.rstrip("/")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        url = urljoin(listing_url, anchor["href"]).split("#", 1)[0]
        path = urlparse(url).path.rstrip("/")
        if not same_host(url, listing_url) or not any(hint in path.lower() + "/" for hint in _EVENT_PATH_HINTS):
            continue
        if path == listing_path or path.count("/") < 2:
            continue  # the listing itself, or a section index like /events
        if url not in links:
            links.append(url)
    return links


def extract_events_from_page(page_url: str, max_events: int, cities: list[str] | None = None) -> list[ExtractedEventCandidate]:
    """Every event one page (a listing, a search result, an event page)
    publishes. Structured events are attributed to their own URL so the
    organizer lookup reads the right page; a lone event without one is
    attributed to this page."""
    html = fetch(page_url, render_js=browser_fetch_enabled())
    if not html:
        return []
    return events_from_html(page_url, html, max_events, cities)


def events_from_html(
    page_url: str,
    html: str,
    max_events: int,
    cities: list[str] | None = None,
    page_may_be_event: bool = True,
    max_event_links: int = 6,
) -> list[ExtractedEventCandidate]:
    """`extract_events_from_page` for HTML already fetched — lets a source
    adapter tell "the page could not be read" from "the page lists no events".
    A directory's calendar page is never itself an event: adapters pass
    `page_may_be_event=False` so its title ("Events", "Calendar") is not read
    as one when the page has no structured or linked events."""
    soup = BeautifulSoup(html, "html.parser")

    nodes = _event_nodes(soup)
    if nodes:
        events: list[ExtractedEventCandidate] = []
        for node in nodes:
            event_url = node.get("url")
            if not isinstance(event_url, str) or not event_url.startswith(("http://", "https://")):
                if len(nodes) > 1:
                    continue  # one of many, can't be traced to its own page or organizer
                event_url = page_url
            events.append(_event_from_node(_source_for(event_url), node))
            if len(events) >= max_events:
                break
        return events

    links = _event_page_links(soup, page_url)
    if len(links) >= _MIN_LISTING_LINKS:
        sublink_cap = min(max_events, max_event_links)
        events = [event for event in (extract_event_from_page(_source_for(url), cities, render_js=False) for url in links[:sublink_cap]) if event is not None]
        if events:
            return events

    if not page_may_be_event:
        return []
    best_effort = extract_best_effort(_source_for(page_url), html, cities or [])
    return [best_effort] if best_effort else []
