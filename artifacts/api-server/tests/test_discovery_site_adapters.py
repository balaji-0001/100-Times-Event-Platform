"""Site-specific readers added after EventsEye: TradeFairDates (country pages),
dmg events (portfolio page) and the shared calendar-page reader used for
venue calendars like ExCeL London. Markup copied from the live sites
(checked 2026-10-27); no network."""

from datetime import date

import pytest

from backend.services.discovery_agent.adapters import SourceError, adapter_manager, dmg_events, tradefairdates
from backend.services.discovery_agent.types import DiscoveryConfig
from backend.services.social_agent import web_fetch

NEXT = date.today().year + 1


def _tile(href, name, when, city, venue="Dubai World Trade Center DWTC", desc="Trade fair for construction and contracting"):
    return f"""<div class="messeninfoTile active"><div class="inner"><div class="tileHeader">
    <div class="headBottom"><div class="time">  {when}  </div></div></div>
    <div class="tileMeta"><a class="title" href="{href}">{name}</a><div class="description"> {desc} </div>
    <div class="messeTerminLocation"><div class="messeTerminLocationOrtContainer">
    <span class="messeTerminZentrum"><a href="/v.html">{venue}</a></span><span class="messeTerminOrt">{city}</span><span class="messeTerminLand">, UAE</span>
    </div></div></div></div></div>"""


def test_tradefairdates_dates_and_tiles():
    assert tradefairdates.parse_date(f"25. - 27. October {NEXT}") == (date(NEXT, 10, 25), True)
    assert tradefairdates.parse_date(f"30 Oct. - 02 Nov. {NEXT}") == (date(NEXT, 10, 30), True)
    assert tradefairdates.parse_date(f"30 Dec. - 02 Jan. {NEXT}") == (date(NEXT - 1, 12, 30), True)
    assert tradefairdates.parse_date(f"October {NEXT}") == (date(NEXT, 10, 1), False)
    assert tradefairdates.parse_date("TBA") == (None, False)

    rows = tradefairdates.parse_listing(_tile("/Big-5-Global-M1/Dubai.html", "Big 5 Global", f"23. - 26. November {NEXT}", "Dubai"), "https://www.tradefairdates.com/Fairs-UAE-Z2-S1.html")
    assert rows == [{"name": "Big 5 Global", "url": "https://www.tradefairdates.com/Big-5-Global-M1/Dubai.html", "date_text": f"23. - 26. November {NEXT}",
                     "description": "Trade fair for construction and contracting", "venue": "Dubai World Trade Center DWTC", "city": "Dubai"}]

    pages = {"uae": "/Fairs-UAE-Z2-S1.html", "india": "/Fairs-India-Z103-S1.html", "usa": "/Fairs-USA-Z228-S1.html"}
    assert tradefairdates.page_for_country("United Arab Emirates", pages) == "/Fairs-UAE-Z2-S1.html"
    assert tradefairdates.page_for_country("United States", pages) == "/Fairs-USA-Z228-S1.html"
    assert tradefairdates.page_for_country("India", pages) == "/Fairs-India-Z103-S1.html"


def test_tradefairdates_reads_country_pages_and_keeps_upcoming_shows(monkeypatch):
    page1 = _tile("/Big-5-Global-M1/Dubai.html", "Big 5 Global", f"23. - 26. November {NEXT}", "Dubai") + _tile(
        "/Old-M2/Dubai.html", "Old Fair", f"01. - 02. March {date.today().year - 1}", "Dubai") + '<a href="/Fairs-UAE-Z2-S2.html">2</a>'
    page2 = _tile("/Heavy-M3/Dubai.html", "Heavy", f"23. - 26. November {NEXT}", "Dubai", desc="Trade fair for heavy construction machinery")
    site = {
        tradefairdates._COUNTRIES_PAGE: '<a href="/Fairs-UAE-Z2-S1.html"></a><a href="/Fairs-India-Z103-S1.html"></a>',
        "https://www.tradefairdates.com/Fairs-UAE-Z2-S1.html": page1,
        "https://www.tradefairdates.com/Fairs-UAE-Z2-S2.html": page2,
    }
    monkeypatch.setattr(tradefairdates, "_fetch", lambda url: site.get(url))
    monkeypatch.setattr(tradefairdates, "_countries", (0.0, {}))
    adapter = adapter_manager.get_adapter("tradefairdates")
    assert isinstance(adapter, tradefairdates.TradeFairDatesAdapter)
    events = adapter.discover(DiscoveryConfig(countries=["United Arab Emirates"]), limit=10)
    assert [(e.name, e.date, e.city, e.country) for e in events] == [
        ("Big 5 Global", f"{NEXT}-11-23", "Dubai", "United Arab Emirates"),
        ("Heavy", f"{NEXT}-11-23", "Dubai", "United Arab Emirates"),
    ]
    assert events[0].primary_source.source_website == "TradeFairDates"
    with pytest.raises(SourceError):
        adapter.discover(DiscoveryConfig(), limit=5)  # needs a country


DMG_PAGE = f"""<ul class="list-marquee">
<a href="https://www.adipec.com/" target="_blank"><li><p>ADIPEC | 2 - 5 November {NEXT} , United Arab Emirates</p></li></a>
<a href="https://www.big5global.com" target="_blank"><li><p>Big 5 Global | 23 – 26 November {NEXT} , United Arab Emirates</p></li></a>
<a href="https://www.adipec.com/" target="_blank"><li><p>ADIPEC | 2 - 5 November {NEXT} , United Arab Emirates</p></li></a>
<a href="https://www.saudi.test/" target="_blank"><li><p>bauma SAUDI ARABIA | 8 - 11 May, {NEXT} , Saudi Arabia</p></li></a>
<a href="https://www.old.test/" target="_blank"><li><p>Old Show | 1 - 2 March {date.today().year - 1} , United Arab Emirates</p></li></a>
</ul>"""


def test_dmg_portfolio_page_gives_official_sites_with_dmg_as_organizer(monkeypatch):
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: DMG_PAGE if url == dmg_events.EVENTS_PAGE else None)
    adapter = adapter_manager.get_adapter("dmg_events")
    assert isinstance(adapter, dmg_events.DmgEventsAdapter)
    assert dmg_events.start_date(f"8 - 11 May, {NEXT}") == (date(NEXT, 5, 8), True)

    uae = adapter.discover(DiscoveryConfig(countries=["United Arab Emirates"]), limit=10)
    assert [(e.name, e.date, e.url) for e in uae] == [
        ("ADIPEC", f"{NEXT}-11-02", "https://www.adipec.com/"),
        ("Big 5 Global", f"{NEXT}-11-23", "https://www.big5global.com"),
    ]  # duplicate entry merged, past show and other countries left out
    assert uae[0].raw_evidence["organizer"]["name"] == "dmg events" and uae[0].organizer_name_hint == "dmg events"
    assert len(adapter.discover(DiscoveryConfig(), limit=10)) == 3  # no country selected: the whole portfolio


def test_calendar_pages_follow_whats_on_links_and_skip_section_pages(monkeypatch):
    from backend.core.config import get_settings
    from backend.services.discovery_agent.adapters.html_listing import HtmlListingAdapter

    monkeypatch.setattr(get_settings(), "discovery_browser_fetch", False)
    event = lambda name: f"""<html><head><script type="application/ld+json">{{"@type": "Event", "name": "{name}", "startDate": "{NEXT}-11-11"}}</script></head><body>x</body></html>"""
    site = {
        "https://venue.test/whats-on": '<a href="/whats-on/business-show">a</a><a href="/whats-on/risk-europe">b</a><a href="/whats-on/all">c</a>' + "x" * 600,
        "https://venue.test/whats-on/business-show": event("The Business Show London"),
        "https://venue.test/whats-on/risk-europe": event("#RISK Europe"),
        "https://venue.test/whats-on/all": event("What’s on"),
    }
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: site.get(url))
    adapter = HtmlListingAdapter("venue", "Venue", "https://venue.test/", config={"calendar_url": "https://venue.test/whats-on"})
    names = sorted(e.name for e in adapter.discover(DiscoveryConfig(), limit=10))
    assert names == ["#RISK Europe", "The Business Show London"]


# --- Informa Markets (its event-listing page's own JSON feed) ----------------

def test_informa_feed_gives_official_sites_sector_labels_and_informa_as_organizer(monkeypatch):
    from types import SimpleNamespace

    from backend.services.discovery_agent.adapters import informa

    feed = {"total": 3, "count": 3, "items": [
        {"eventEditionLongName": "Middle East Energy 2027", "eventStartDate": f"{NEXT}-05-11", "eventEndDate": f"{NEXT}-05-13",
         "cityFreeText": "Dubai", "locationCountry": "United Arab Emirates", "venueName": "Dubai World Trade Centre", "URL": "https://www.middleeast-energy.com",
         "eventSeriesName": "Middle East Energy", "eventSeriesSubSectors": [{"sectorName": "Energy, Utilities & Resources", "subSectorName": "Power Generation"}]},
        {"eventEditionLongName": "Feira Brasil 2027", "eventStartDate": f"{NEXT}-03-01", "locationCountry": "Brasil", "URL": "https://feira.test"},
        {"eventEditionLongName": "Old Show", "eventStartDate": f"{date.today().year - 1}-01-01", "locationCountry": "United Arab Emirates", "URL": "https://old.test"},
    ]}
    calls = []
    monkeypatch.setattr(informa.httpx, "get", lambda url, **kw: calls.append(url) or SimpleNamespace(status_code=200, json=lambda: feed))
    adapter = adapter_manager.get_adapter("informa_markets")
    assert isinstance(adapter, informa.InformaMarketsAdapter)

    [mee] = adapter.discover(DiscoveryConfig(countries=["United Arab Emirates"]), limit=10)
    assert (mee.name, mee.date, mee.city, mee.country, mee.url) == ("Middle East Energy 2027", f"{NEXT}-05-11", "Dubai", "United Arab Emirates", "https://www.middleeast-energy.com")
    assert "Power Generation" in mee.event_description and mee.raw_evidence["organizer"]["name"] == "Informa Markets"
    assert calls and "eventEditions.expanded.json" in calls[0]
    assert {e.country for e in adapter.discover(DiscoveryConfig(), limit=10)} == {"United Arab Emirates", "Brazil"}

    monkeypatch.setattr(informa.httpx, "get", lambda url, **kw: SimpleNamespace(status_code=503, json=lambda: {}))
    with pytest.raises(SourceError) as exc:
        adapter.discover(DiscoveryConfig(), limit=5)
    assert "HTTP 503" in str(exc.value)


# --- Expolya / Messe Düsseldorf calendars ------------------------------------

EXPOLYA = f"""<div class="ann-list">
<a class="salon-card" data-secteurs="Construction &amp; Architecture" data-pays="AE" data-date="{NEXT}-11-23" href="/expo/big-5-global">
 <p class="salon-card-date"><span>Nov 23–26, {NEXT}</span></p><h3 class="salon-card-name">Big 5 Global</h3>
 <p class="salon-card-desc">The construction industry's largest event.</p>
 <span class="salon-card-lieu">Dubai, United Arab Emirates · Dubai World Trade Centre</span></a>
<a class="salon-card" data-secteurs="Agriculture" data-pays="IT" data-date="{NEXT}-02-01" href="/expo/fieragricola">
 <h3 class="salon-card-name">Fieragricola</h3><span class="salon-card-lieu">Verona, Italy · Veronafiere</span></a>
</div>"""

DUESSELDORF = f"""<ul class="dim-list">
<li class="dim-list-item" id="event-1" data-title="METEC India" data-date-from="{NEXT}-11-30" data-date-to="{NEXT}-12-02" data-location="Mumbai">
 <div class="dim-chapter_subtitle"><p>International Metallurgy Trade Fair</p></div>
 <div class="dim-list_col">Organizer: Messe Düsseldorf India Pvt. Ltd. Location: Mumbai / Bombay Exhibition Centre Cycle: annual</div>
 <a href="https://www.metec-india.com">Website</a><a href="https://db.messe-duesseldorf.com/kati-cgi/kati/x.ics">iCal</a></li>
</ul>"""

@pytest.mark.parametrize("sid, html, config, expected", [
    ("expolya", EXPOLYA, DiscoveryConfig(countries=["United Arab Emirates"]),
     [("Big 5 Global", f"{NEXT}-11-23", "Dubai", "United Arab Emirates", "https://expolya.com/expo/big-5-global")]),
    ("messe_duesseldorf", DUESSELDORF, DiscoveryConfig(countries=["India"]),
     [("METEC India", f"{NEXT}-11-30", "Mumbai", "India", "https://www.metec-india.com")]),
])
def test_fair_calendar_readers(monkeypatch, sid, html, config, expected):
    adapter = adapter_manager.get_adapter(sid)
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: html if url in adapter.PAGES else None)
    events = adapter.discover(config, limit=10)
    assert [(e.name, e.date, e.city, e.country, e.url) for e in events] == expected
    if sid == "messe_duesseldorf":
        assert events[0].organizer_name_hint == "Messe Düsseldorf India Pvt. Ltd." and events[0].raw_evidence["end_date"] == f"{NEXT}-12-02"
    if sid == "expolya":
        assert "Construction & Architecture" in events[0].event_description
