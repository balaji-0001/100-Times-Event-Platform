"""EventsEye adapter: listing rows, dates, country slugs, the organizer block
(never the venue's contacts), and a full discover() over stubbed pages whose
markup is copied from www.eventseye.com (checked 2026-10-27)."""

from datetime import date, timedelta

import pytest

from backend.services.discovery_agent import organizer_identifier
from backend.services.discovery_agent.adapters import SourceError, adapter_manager, eventseye
from backend.services.discovery_agent.types import DiscoveryConfig

NEXT_YEAR = date.today().year + 1


def _row(href, name, desc, city, venue, date_text):
    return f"""<tr><td><a href="{href}"><b>{name}</b><i>{desc}</i></a></td><td>once a year</td>
    <td><a href="cy1_trade-shows-{city.lower()}.html">{city}</a><a href="pl1_trade-shows_{city.lower()}_1.html">{venue}</a></td>
    <td>{date_text}</td></tr>"""


def _listing(caption, *rows):
    return f"""<html><body><table class="tradeshows"><caption>{caption}</caption>
    <thead><tr><th>Exhibition Name</th><th>Cycle</th><th>Venue</th><th>Date</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table></body></html>"""


UAE_CONSTRUCTION = _listing(
    "3 Trade Shows in UAE - United Arab Emirates related to Building & Construction",
    _row("f-big-5-global-5181-1.html", "BIG 5 GLOBAL", "International Exhibition for Building, Water Technology", "Dubai", "Dubai World Trade Centre", f"11/23/{NEXT_YEAR}<br><i>4 days</i>"),
    _row("f-old-show-1-1.html", "OLD SHOW", "Already happened", "Dubai", "DWTC", f"01/05/{date.today().year - 1}<br><i>2 days</i>"),
    _row("f-maybe-show-2-1.html", "MAYBE SHOW", "Month only", "Dubai", "DWTC", f"Dec. {NEXT_YEAR} (?)"),
)

DETAIL = """<html><body>
<div class="venues"><div class="venue"><div class="text"><a class="placelink" href="pl1_x.html">Dubai World Trade Centre</a>
  <a class="ev-web" href="https://www.dwtc.com">Web Site</a><a class="ev-mail" href="mailto:venue-info@dwtc.com">E-mail</a></div></div></div>
<div class="orgs"><div class="org"><div class="text"><a class="orglink" href="/fairs-organizers/dmg-1.html">dmg :: events Middle East</a><br>
  <div class="ev-phone">+971 4 438 0355</div><a class="ev-web" href="http://www.dmgeventsme.com">Web Site</a>
  <a class="ev-mail" href="mailto:info@dmgeventsme.com">E-mail</a></div></div></div>
<div class="more-info"><a class="ev-web" href="https://www.big5global.com">Official Web Site</a>
  <a class="ev-mail" href="mailto:big5@dmgeventsme.com">Event's E-mail</a><a class="ev-mail" href="mailto:">Event's E-mail for exhibitors only</a></div>
</body></html>"""


def test_listing_rows_dates_and_slugs():
    rows, count = eventseye.parse_listing(UAE_CONSTRUCTION, "https://www.eventseye.com/fairs/cst1_trade-shows_uae-united-arab-emirates_building-construction.html")
    assert count == 3 and rows[0]["name"] == "BIG 5 GLOBAL" and rows[0]["city"] == "Dubai" and rows[0]["venue"] == "Dubai World Trade Centre"
    assert rows[0]["url"] == "https://www.eventseye.com/fairs/f-big-5-global-5181-1.html" and rows[0]["duration_days"] == 4
    assert eventseye.row_date(f"11/23/{NEXT_YEAR}") == (date(NEXT_YEAR, 11, 23), True)
    assert eventseye.row_date(f"Dec. {NEXT_YEAR} (?)") == (date(NEXT_YEAR, 12, 1), False)

    slugs = ["india", "uae-united-arab-emirates", "usa-united-states-of-america", "uk-united-kingdom", "georgia"]
    assert eventseye.slug_for_country("United Arab Emirates", slugs) == "uae-united-arab-emirates"
    assert eventseye.slug_for_country("United States", slugs) == "usa-united-states-of-america"
    assert eventseye.slug_for_country("India", slugs) == "india"
    assert eventseye.slug_for_country("Japan", slugs) is None


def test_detail_page_gives_the_show_and_organizer_contacts_not_the_venue():
    detail = eventseye.parse_detail(DETAIL)
    assert detail["event_website"] == "https://www.big5global.com" and detail["event_email"] == "big5@dmgeventsme.com"
    assert detail["organizers"] == [{"name": "dmg :: events Middle East", "website": "http://www.dmgeventsme.com", "email": "info@dmgeventsme.com", "phone": "+971 4 438 0355"}]


@pytest.fixture()
def eventseye_site(monkeypatch):
    pages = {
        eventseye.BASE + "trade-shows-by-location.html": '<a href="c1_trade-shows_india.html"></a>',
        eventseye.BASE + "z1_trade-shows_africa-middle-east.html": '<a href="c1_trade-shows_uae-united-arab-emirates.html"></a>',
        eventseye.BASE + "cst1_trade-shows_uae-united-arab-emirates_building-construction.html": UAE_CONSTRUCTION,
    }
    fetched = []

    def fetch(url):
        fetched.append(url)
        return pages.get(url)

    monkeypatch.setattr(eventseye, "_fetch", fetch)
    monkeypatch.setattr(eventseye, "_country_slugs", (0.0, []))
    return fetched


def test_discover_reads_country_x_industry_lists_and_keeps_upcoming_shows(eventseye_site):
    adapter = adapter_manager.get_adapter("eventseye")
    assert isinstance(adapter, eventseye.EventsEyeAdapter)
    config = DiscoveryConfig(countries=["United Arab Emirates"], categories=["Construction"])
    config.sector_scoped = True
    events = adapter.discover(config, limit=10)

    assert [e.name for e in events] == ["BIG 5 GLOBAL", "MAYBE SHOW"]  # the past show is dropped
    big5, maybe = events
    assert (big5.date, big5.city, big5.country, big5.venue) == (f"{NEXT_YEAR}-11-23", "Dubai", "United Arab Emirates", "Dubai World Trade Centre")
    assert "EventsEye industry: Building & Construction" in big5.event_description
    assert big5.primary_source.source_website == "EventsEye" and big5.raw_evidence["end_date"] == f"{NEXT_YEAR}-11-26"
    assert maybe.best_effort is True and maybe.date == f"December {NEXT_YEAR}"  # month-only: a person confirms it
    assert eventseye.BASE + "cst1_trade-shows_uae-united-arab-emirates_building-construction.html" in eventseye_site
    assert not any("c1_trade-shows_uae-united-arab-emirates.html" == u.rsplit("/", 1)[-1] for u in eventseye_site)  # sector list, not the whole country


def test_unknown_country_or_unreachable_site_is_reported_not_hidden(eventseye_site, monkeypatch):
    adapter = adapter_manager.get_adapter("eventseye")
    with pytest.raises(SourceError) as exc:
        adapter.discover(DiscoveryConfig(countries=["Atlantis"], categories=["Construction"]), limit=5)
    assert exc.value.kind == "not_configured"

    monkeypatch.setattr(eventseye, "_fetch", lambda url: None)
    monkeypatch.setattr(eventseye, "_country_slugs", (0.0, []))
    with pytest.raises(SourceError) as exc:
        adapter.discover(DiscoveryConfig(countries=["India"]), limit=5)
    assert exc.value.kind == "unreachable"


def test_organizer_step_uses_the_eventseye_organizer_block(monkeypatch):
    from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate

    url = "https://www.eventseye.com/fairs/f-big-5-global-5181-1.html"
    monkeypatch.setattr(organizer_identifier, "fetch", lambda u, render_js=False: DETAIL if u == url else None)
    monkeypatch.setattr(organizer_identifier, "is_valid_organizer_email", lambda e: (True, e.lower(), None))
    source = CandidateSource(url=url, source_type="event_directory", source_website="EventsEye")
    candidate = ExtractedEventCandidate(name="BIG 5 GLOBAL", url=url, city="Dubai", country="United Arab Emirates",
                                        date=(date.today() + timedelta(days=30)).isoformat(), primary_source=source, sources=[source])
    org = organizer_identifier.identify_organizer(candidate)

    assert org.found and org.email == "big5@dmgeventsme.com" and org.name == "dmg :: events Middle East"
    assert org.website == "http://www.dmgeventsme.com" and org.email_source_url == url
    assert "venue-info@dwtc.com" not in (org.email or "")  # the venue's mailbox is never the organizer's
