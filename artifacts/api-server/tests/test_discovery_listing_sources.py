"""Event Discovery Agent — no-AI mode. Events are harvested from public
listing pages' schema.org data (rendered with Playwright when needed), so a
run still finds real events when no AI key is configured or the key fails."""

import json

from backend.models import AgentRun, DiscoveredEvent
from backend.services.discovery_agent import listing_sources, orchestrator, organizer_identifier, page_extractor
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, OrganizerCandidate
from backend.services.social_agent import web_fetch


def _ld(*nodes) -> str:
    return "".join(f'<script type="application/ld+json">{json.dumps(node)}</script>' for node in nodes)


def _event(name, url, date="2099-10-17", venue="Jio World Drive BKC", city="Mumbai", organizer=None):
    node = {
        "@type": "Event",
        "name": name,
        "url": url,
        "startDate": date,
        "location": {"@type": "Place", "name": venue, "address": {"addressLocality": city}},
    }
    if organizer:
        node["organizer"] = {"@type": "Organization", "name": organizer}
    return node


# allevents.in style: one Event node per event on the listing page.
_ALLEVENTS_LISTING = "<html><head>" + _ld(
    _event("Shubharambh 2026", "https://allevents.in/mumbai/shubharambh-2026/1"),
    _event("Durgotsav 2026", "https://allevents.in/mumbai/durgotsav-2026/2", venue="Country Club"),
    {"@type": "Organization", "name": "allevents"},
) + "</head><body></body></html>"

# Eventbrite style: events nested inside an ItemList.
_EVENTBRITE_LISTING = "<html><head>" + _ld({
    "@type": "ItemList",
    "itemListElement": [
        {"@type": "ListItem", "position": 1, "item": _event("Startup Stories by Bengaluru Founders", "https://www.eventbrite.com/e/startup-stories-1", city="Bengaluru")},
        {"@type": "ListItem", "position": 2, "item": _event("No URL Event", None, city="Bengaluru")},
    ],
}) + "</head><body></body></html>"

# skillboxes style: the listing has no structured data, only links to event
# pages — which do carry it.
_LINK_ONLY_LISTING = """<html><body>
<a href="/events/horrorcon-india-sbufizpt">HorrorCon</a>
<a href="/events/navraas-dandiya-sbpjjgja">Navraas</a>
<a href="/events">All events</a>
<a href="https://elsewhere.example/events/x">Off-site</a>
<a href="/about">About</a>
</body></html>"""

_EVENT_PAGES = {
    "https://www.skillboxes.com/events/horrorcon-india-sbufizpt": "<html><head>" + _ld(_event("HorrorCon India", None, date="2099-10-31", venue="NSIC Grounds", city="New Delhi")) + "</head></html>",
    "https://www.skillboxes.com/events/navraas-dandiya-sbpjjgja": "<html><head>" + _ld(_event("Navraas Dandiya", None, date="2099-10-16", venue="Leisure Valley", city="Gurugram")) + "</head></html>",
}


def _serve(monkeypatch, pages: dict[str, str]) -> list[str]:
    fetched: list[str] = []

    def fake_fetch(url, render_js=False):
        fetched.append(url)
        return pages.get(url)

    monkeypatch.setattr(page_extractor, "fetch", fake_fetch)
    monkeypatch.setattr(page_extractor, "browser_fetch_enabled", lambda: False)
    return fetched


# --- Listing URLs --------------------------------------------------------------


def test_listing_urls_are_built_per_city_with_site_spellings():
    templates = ["https://allevents.in/{city}", "https://www.eventbrite.com/d/india--{city}/events/"]

    urls = listing_sources.build_listing_urls(templates, ["Bengaluru", "Navi Mumbai", "Delhi"])

    assert "https://allevents.in/bangalore" in urls
    assert "https://allevents.in/new-delhi" in urls
    assert "https://allevents.in/navi-mumbai" in urls
    assert "https://www.eventbrite.com/d/india--bengaluru/events/" in urls
    assert len(urls) == len(set(urls)) == 6


def test_city_less_template_is_used_once():
    urls = listing_sources.build_listing_urls(["https://www.skillboxes.com/events"], ["Mumbai", "Pune"])

    assert urls == ["https://www.skillboxes.com/events"]


# --- Harvesting a listing page -------------------------------------------------


def test_every_event_on_a_listing_page_is_extracted(monkeypatch):
    _serve(monkeypatch, {"https://allevents.in/mumbai": _ALLEVENTS_LISTING})

    events = page_extractor.extract_events_from_page("https://allevents.in/mumbai", max_events=10)

    assert [e.name for e in events] == ["Shubharambh 2026", "Durgotsav 2026"]
    first = events[0]
    assert first.url == "https://allevents.in/mumbai/shubharambh-2026/1"
    assert first.primary_source.url == first.url
    assert first.primary_source.source_type == "aggregator"
    assert first.venue == "Jio World Drive BKC"
    assert first.city == "Mumbai"
    assert first.date == "2099-10-17"


def test_events_nested_in_an_item_list_are_extracted_and_url_less_ones_skipped(monkeypatch):
    listing = "https://www.eventbrite.com/d/india--bengaluru/events/"
    _serve(monkeypatch, {listing: _EVENTBRITE_LISTING})

    events = page_extractor.extract_events_from_page(listing, max_events=10)

    # An event without its own URL can't be traced to its own page (or its
    # organizer), so it's dropped rather than attributed to the listing.
    assert [e.name for e in events] == ["Startup Stories by Bengaluru Founders"]


def test_max_events_caps_a_listing(monkeypatch):
    _serve(monkeypatch, {"https://allevents.in/mumbai": _ALLEVENTS_LISTING})

    assert len(page_extractor.extract_events_from_page("https://allevents.in/mumbai", max_events=1)) == 1


def test_listing_without_structured_data_follows_its_event_links(monkeypatch):
    listing = "https://www.skillboxes.com/events"
    fetched = _serve(monkeypatch, {listing: _LINK_ONLY_LISTING, **_EVENT_PAGES})

    events = page_extractor.extract_events_from_page(listing, max_events=10)

    assert [e.name for e in events] == ["HorrorCon India", "Navraas Dandiya"]
    assert events[0].url == "https://www.skillboxes.com/events/horrorcon-india-sbufizpt"
    assert events[0].primary_source.source_type == "aggregator"
    # Only same-site event pages are opened; never the listing itself again,
    # off-site links, or non-event pages.
    assert fetched == [listing, *_EVENT_PAGES]


def test_single_page_without_structured_data_or_a_date_returns_none(monkeypatch):
    _serve(monkeypatch, {"https://example.test/e": "<html><body>Some event</body></html>"})

    assert page_extractor.extract_event_from_page(CandidateSource(url="https://example.test/e", source_type="event_listing")) is None


# --- Polite fetching -----------------------------------------------------------


def test_discovery_fetches_wait_between_requests_to_the_same_site(monkeypatch):
    sleeps: list[float] = []
    # Clock reads: first request (check, stamp), second request (check, stamp).
    clock = iter([100.0, 100.0, 100.2, 101.7])
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: "<html>" + "x" * 600 + "</html>")
    monkeypatch.setattr(web_fetch.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(web_fetch.time, "sleep", sleeps.append)
    web_fetch._last_request_at.clear()

    web_fetch.fetch("https://allevents.in/a", render_js=True)
    web_fetch.fetch("https://allevents.in/b", render_js=True)

    assert sleeps and abs(sleeps[0] - (web_fetch._MIN_SECONDS_BETWEEN_REQUESTS - 0.2)) < 1e-9


# --- Orchestrator --------------------------------------------------------------


def _config(**overrides) -> DiscoveryConfig:
    values = dict(
        cities=["Mumbai"], states=[], categories=["Technology"], search_depth=1, sources_per_query=1,
        daily_limit=200, confidence_threshold=60,
        listing_urls=["https://allevents.in/{city}"], events_per_listing=10,
    )
    values.update(overrides)
    return DiscoveryConfig(**values)


def _patch_listing_pipeline(monkeypatch):
    _serve(monkeypatch, {"https://allevents.in/mumbai": _ALLEVENTS_LISTING})
    monkeypatch.setattr(
        orchestrator.organizer_identifier,
        "identify_organizer",
        lambda candidate: OrganizerCandidate(found=False),
    )


def test_run_stores_events_from_listing_pages(db_session, monkeypatch):
    _patch_listing_pipeline(monkeypatch)

    summary = orchestrator.run_discovery_agent(db_session, _config())

    assert summary.new_events == 2
    assert {e.name for e in db_session.query(DiscoveredEvent).all()} == {"Shubharambh 2026", "Durgotsav 2026"}
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "discovery").one()
    assert run.status == "completed"


def test_listing_page_events_get_the_real_organizer_lookup(db_session, monkeypatch):
    """End to end without AI: listing -> event -> organizer from the event's own page."""
    event_url = "https://allevents.in/mumbai/shubharambh-2026/1"
    listing = "<html><head>" + _ld(_event("Shubharambh 2026", event_url)) + "</head></html>"
    event_page = "<html><head>" + _ld({**_event("Shubharambh 2026", event_url), "organizer": {"name": "Shubh Events", "url": "https://shubh.example"}}) + "</head></html>"
    pages = {"https://allevents.in/mumbai": listing, event_url: event_page, "https://shubh.example": '<a href="mailto:hi@shubh.example">mail</a>'}
    _serve(monkeypatch, pages)
    monkeypatch.setattr(organizer_identifier, "fetch", lambda url, render_js=False: pages.get(url))
    monkeypatch.setattr(organizer_identifier, "browser_fetch_enabled", lambda: False)

    summary = orchestrator.run_discovery_agent(db_session, _config())

    assert summary.new_events == 1
    assert summary.contacts_found >= 1
    event = db_session.query(DiscoveredEvent).one()
    assert event.organizer is not None
    assert event.organizer.name == "Shubh Events"
    assert event.organizer.email == "hi@shubh.example"


def test_named_organizer_without_email_is_stored_but_not_outreach_ready(db_session, monkeypatch):
    """Meetup names every organizer but never shows an email: keep the name
    with the event, while outreach (which needs FOUND + email) still skips it."""
    from backend.models import DiscoveredOrganizer

    _serve(monkeypatch, {"https://allevents.in/mumbai": _ALLEVENTS_LISTING})
    monkeypatch.setattr(
        orchestrator.organizer_identifier,
        "identify_organizer",
        lambda candidate: OrganizerCandidate(found=False, name=f"{candidate.name} Collective", confidence_score=30),
    )

    summary = orchestrator.run_discovery_agent(db_session, _config())

    assert summary.organizers_found == 2
    assert db_session.query(DiscoveredOrganizer).count() == 2
    event = db_session.query(DiscoveredEvent).filter(DiscoveredEvent.name == "Shubharambh 2026").one()
    assert event.organizer.name == "Shubharambh 2026 Collective"
    assert event.organizer.email is None
    assert event.organizer_status == "NOT_FOUND"
