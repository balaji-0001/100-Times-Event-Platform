"""Repairs of failing discovery sources: IEEE through its official vTools API
(within its one-request-a-minute rule), CMT read from its new domain's
conference cards, sites that refuse automated requests or no longer exist
removed from the catalogue, and a page that refused us is never retried in
the browser to get around it."""

from datetime import date, timedelta

import pytest

from backend.services.discovery_agent import catalog, organizer_identifier
from backend.services.discovery_agent.adapters import fair_calendars, ieee_vtools
from backend.services.discovery_agent.adapters.base import SourceError
from backend.services.discovery_agent.types import DiscoveryConfig
from backend.services.social_agent import browser_fetch, web_fetch

SOON = (date.today() + timedelta(days=20)).isoformat()
LATER = (date.today() + timedelta(days=200)).isoformat()


def _event(eid, title, start, city, country_id, *, cancelled=False, email="chair@ieee-section.test"):
    return {
        "id": eid, "type": "events",
        "attributes": {"title": title, "description": "<p>Talk on <b>power</b> systems</p>", "start-time": f"{start}T15:00:00.000Z",
                       "time-zone": {"name": "CET", "utc-offset": 1}, "primary-host": {"name": "IEEE Germany Section"},
                       "contact-email": email, "city": city, "building": "TU Munich", "link": f"https://events.vtools.ieee.org/m/{eid}",
                       "registration-url": None, "location-type": "physical", "virtual": False, "cancelled": cancelled, "publish": True},
        "relationships": {"country": {"data": {"type": "countries", "id": country_id}}, "state": {"data": {"type": "states", "id": "9"}}},
    }


PAYLOAD = {
    "data": [
        _event(1, "Power Electronics Symposium", SOON, "Munich", "82"),
        _event(2, "Grid Workshop", SOON, "Austin", "221"),
        _event(3, "Cancelled Meetup", SOON, "Munich", "82", cancelled=True),
        _event(4, "Far Future Forum", LATER, "Berlin", "82"),
    ],
    "included": [
        {"type": "countries", "id": "82", "attributes": {"name": "Germany"}},
        {"type": "countries", "id": "221", "attributes": {"name": "United States"}},
        {"type": "states", "id": "9", "attributes": {"name": "Bavaria"}},
    ],
}


@pytest.fixture()
def vtools(monkeypatch):
    calls = []

    class _Resp:
        status_code = 200

        def json(self):
            return PAYLOAD

    def fake_get(url, params=None, **kwargs):
        calls.append((url, params))
        return _Resp()

    monkeypatch.setattr(ieee_vtools.httpx, "get", fake_get)
    monkeypatch.setattr(ieee_vtools, "_cache", {"at": 0.0, "payload": None})
    monkeypatch.setattr(ieee_vtools, "_last_request", 0.0)
    return calls


def test_ieee_events_come_from_the_official_api_with_place_and_organizer(vtools):
    adapter = ieee_vtools.IeeeVToolsAdapter()
    config = DiscoveryConfig(countries=["Germany"], date_to=(date.today() + timedelta(days=90)).isoformat())

    events = adapter.discover(config, limit=10)

    assert [e.name for e in events] == ["Power Electronics Symposium"]  # other country, cancelled and out-of-window dropped
    e = events[0]
    assert (e.country, e.state, e.city, e.venue, e.date) == ("Germany", "Bavaria", "Munich", "TU Munich", SOON)
    assert e.primary_source.source_type == "official_api" and e.url == "https://events.vtools.ieee.org/m/1"
    assert e.raw_evidence["organizer"] == {"name": "IEEE Germany Section", "email": "chair@ieee-section.test"}
    assert "<p>" not in e.event_description
    assert vtools[0][1]["span"] == "now~"  # only events that haven't started


def test_vtools_is_asked_at_most_once_a_minute(vtools, monkeypatch):
    ieee_vtools.fetch_upcoming()
    ieee_vtools.fetch_upcoming()  # cached
    monkeypatch.setattr(ieee_vtools, "_cache", {"at": 0.0, "payload": None})
    with pytest.raises(SourceError) as exc:
        ieee_vtools.fetch_upcoming()  # cache gone but < 60 s since the last request
    assert exc.value.kind == "rate_limited"
    assert len(vtools) == 1


def test_official_api_organizer_is_used_without_opening_the_event_page(vtools, monkeypatch):
    event = ieee_vtools.IeeeVToolsAdapter().discover(DiscoveryConfig(countries=["Germany"]), limit=5)[0]
    monkeypatch.setattr(organizer_identifier, "fetch", lambda *a, **k: pytest.fail("vTools pages must not be fetched per event"))

    organizer = organizer_identifier.identify_organizer(event)

    assert organizer.found and organizer.email == "chair@ieee-section.test" and organizer.name == "IEEE Germany Section"
    assert organizer.email_source_url == event.url


REMOVED = {"10times", "biztradeshows", "all_conference_alert", "conferencedb", "himss", "globalsources", "exhibition_directory", "worldwide_trade_shows"}


def test_sites_that_cannot_be_read_are_not_in_the_catalogue():
    # 403 bot walls / 429 (10Times, BizTradeShows → 10Times, All Conference Alert,
    # ConferenceDB, HIMSS, Global Sources) and dead domains (Exhibition Directory,
    # Worldwide Trade Shows).
    from backend.services.discovery_agent import listing_sources, query_seeds

    assert not REMOVED & {s["id"] for s in catalog.ALL_CANDIDATE_SOURCES}
    assert not REMOVED & {s["id"] for s in catalog.build_catalog(None, ticketmaster_key_set=False)["sources"]}
    assert "10times" not in catalog.AGGREGATOR_IDS
    assert not any("10times" in u for u in listing_sources.DEFAULT_LISTING_URLS)
    queries = query_seeds.build_expanded_queries(DiscoveryConfig(countries=["India"], cities=["Mumbai"], categories=["Technology"]))
    assert queries and not any("10times" in q for q in queries)


def test_a_page_that_refused_us_is_not_retried_in_the_browser(monkeypatch):
    web_fetch.clear_cache()

    def refused(url, allow_feed=False):
        web_fetch._note_failure(url, "HTTP 403 (bot wall / access denied)")
        return None

    monkeypatch.setattr(web_fetch, "_http_get", refused)
    monkeypatch.setattr(browser_fetch, "render", lambda url, for_contacts=False: pytest.fail("must not render a refused page"))
    assert web_fetch.fetch("https://blocked.test/events", render_js=True) is None


def test_a_network_failure_may_still_render(monkeypatch):
    web_fetch.clear_cache()

    def down(url, allow_feed=False):
        web_fetch._note_failure(url, "timed out after 10s")
        return None

    monkeypatch.setattr(web_fetch, "_http_get", down)
    monkeypatch.setattr(browser_fetch, "render", lambda url, for_contacts=False: "<html><body>rendered</body></html>")
    assert "rendered" in web_fetch.fetch("https://slow.test/events", render_js=True)


def _cmt_card(eid, title, when, place):
    return f"""
    <div class="col-12 col-lg-8 text-start border-left ps-xl-4">
      <h2 class="mb-0 fw-bold"><a class="text-primary1-dark eventtitle" href="aboutevent.aspx?ev={eid}&amp;">{title}</a></h2>
      <p class="mb-2 text-left"><strong>Circular economy summit</strong></p>
      <p class="h5 figtree fw-medium mt-1 text-primary1-dark">{when} - {place}</p>
      <div><a class="a-link-blue" href="register.aspx?ev={eid}&amp;">Register</a></div>
    </div>"""


def _cmt_page(*cards):
    return f"<html><body>{''.join(cards)}<footer>Centre for Management Technology Pte. Ltd. All rights reserved</footer></body></html>"


def _when(d):
    return f"{d.day:02d}-{(d + timedelta(days=1)).day:02d} {d.strftime('%b')}, {d.year}"


def test_cmt_cards_give_dates_place_link_and_the_named_organizer():
    soon = date.today() + timedelta(days=30)
    html = _cmt_page(_cmt_card(261122, "15th Asia PET Series – Circular Plastics Packaging", _when(soon), "Jakarta<span>, INDONESIA</span>"))

    rows = fair_calendars.CmtEventsAdapter().parse(html, "https://www.cmtevents.com/main.aspx")

    assert len(rows) == 1
    row = rows[0]
    assert (row["start"], row["city"], row["country"]) == (soon, "Jakarta", "Indonesia")
    assert row["url"] == "https://www.cmtevents.com/aboutevent.aspx?ev=261122"
    assert row["organizer"] == "Centre for Management Technology Pte. Ltd" and row["description"] == "Circular economy summit"


def test_cmt_organizer_is_only_set_when_the_page_names_it():
    html = f"<html><body>{_cmt_card(1, 'Biomass Asia', '17-19 Nov, 2099', 'Ho Chi Minh City, VIETNAM')}</body></html>"
    assert fair_calendars.CmtEventsAdapter().parse(html, "https://www.cmtevents.com/main.aspx")[0]["organizer"] is None


@pytest.mark.parametrize("text, start, end", [
    ("27-28 Oct, 2026 - Mexico City, MEXICO", date(2026, 10, 27), date(2026, 10, 28)),
    ("30 Nov - 02 Dec, 2026 - Dubai, UAE", date(2026, 11, 30), date(2026, 12, 2)),
    ("29 Dec - 02 Jan, 2027 - Bangkok, THAILAND", date(2026, 12, 29), date(2027, 1, 2)),
    ("5 Mar, 2027 - Paris, FRANCE", date(2027, 3, 5), None),
    ("Dates to be announced", None, None),
])
def test_cmt_date_lines(text, start, end):
    assert fair_calendars._cmt_dates(text) == (start, end)


def test_cmt_keeps_upcoming_events_in_the_selected_countries(monkeypatch):
    soon, past = date.today() + timedelta(days=30), date.today() - timedelta(days=30)
    html = _cmt_page(
        _cmt_card(1, "DeCarbon Tokyo", _when(soon), "Tokyo<span>, JAPAN</span>"),
        _cmt_card(2, "Africa Cementrade Summit", _when(soon), "Casablanca<span>, MOROCCO</span>"),
        _cmt_card(3, "Last Year's Summit", _when(past), "Tokyo<span>, JAPAN</span>"),
    )
    adapter = fair_calendars.CmtEventsAdapter()
    monkeypatch.setattr(adapter, "_read", lambda url: adapter.parse(html, url))

    events = adapter.discover(DiscoveryConfig(countries=["Japan"]), limit=10)

    assert [e.name for e in events] == ["DeCarbon Tokyo"]
    assert events[0].organizer_name_hint == "Centre for Management Technology Pte. Ltd"
    assert events[0].primary_source.source_type == "official_event_site"


def test_cmt_is_read_by_its_own_reader_from_the_new_domain():
    from backend.services.discovery_agent.adapters.manager import adapter_manager

    adapter = adapter_manager.get_adapter("cmt_events")
    assert isinstance(adapter, fair_calendars.CmtEventsAdapter)
    assert adapter.target_urls(None) == ["https://www.cmtevents.com/main.aspx"]
    assert catalog.is_implemented("cmt_events")
