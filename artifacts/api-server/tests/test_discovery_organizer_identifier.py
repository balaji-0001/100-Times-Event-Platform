"""Organizer Identifier — must attribute contact details to the real event
organizer, never to the ticketing/listing platform hosting the event page,
and must not spend hops re-fetching a page it already read."""

from bs4 import BeautifulSoup

from backend.services.discovery_agent import organizer_identifier, page_extractor
from backend.services.discovery_agent.platforms import is_platform_url
from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate

# A ticketing-platform event page: the only contact details on it are the
# platform's own (support mailbox, helpline, LinkedIn, contact page).
_PLATFORM_EVENT_PAGE = """<html><head><meta property="og:site_name" content="SkillBox"></head><body>
<h1>HorrorCon India</h1>
<footer>
  <a href="mailto:support@skillboxes.com">Support</a> Call 9876543210
  <a href="https://www.linkedin.com/company/skillboxofficial/">LinkedIn</a>
  <a href="/contact-us">Contact us</a>
</footer></body></html>"""

_PLATFORM_EVENT_PAGE_WITH_ORGANIZER = """<html><head>
<script type="application/ld+json">
{"@type": "Event", "name": "HorrorCon India", "startDate": "2099-10-31",
 "organizer": {"name": "Fright Nights Collective", "url": "https://frightnights.example"}}
</script></head><body>
<a href="mailto:support@skillboxes.com">Support</a>
<a href="/contact-us">Contact us</a>
</body></html>"""

_ORGANIZER_SITE = """<html><body><h1>Fright Nights Collective</h1>
<a href="mailto:team@frightnights.example">Email us</a></body></html>"""


def _candidate(url: str, source_type: str = "event_listing", name_hint: str | None = None) -> ExtractedEventCandidate:
    source = CandidateSource(url=url, source_type=source_type)
    return ExtractedEventCandidate(name="HorrorCon India", url=url, organizer_name_hint=name_hint, primary_source=source, sources=[source])


def _serve(monkeypatch, pages: dict[str, str]) -> list[str]:
    fetched: list[str] = []

    def fake_fetch(url, render_js=False):
        fetched.append(url)
        return pages.get(url)

    monkeypatch.setattr(organizer_identifier, "fetch", fake_fetch)
    monkeypatch.setattr(organizer_identifier, "browser_fetch_enabled", lambda: False)
    return fetched


def test_platform_contact_details_are_not_attributed_to_the_organizer(monkeypatch):
    url = "https://www.skillboxes.com/events/horrorcon-india"
    fetched = _serve(monkeypatch, {url: _PLATFORM_EVENT_PAGE})

    organizer = organizer_identifier.identify_organizer(_candidate(url, name_hint="Fright Nights Collective"))

    assert not organizer.found
    assert organizer.email is None
    assert organizer.phone is None
    assert organizer.linkedin is None
    assert organizer.name == "Fright Nights Collective"
    assert organizer.website is None  # a platform URL would merge every organizer on it via domain dedup
    assert fetched == [url]  # never wanders into the platform's own contact page


def test_platform_page_with_unknown_organizer_has_no_name(monkeypatch):
    url = "https://www.skillboxes.com/events/horrorcon-india"
    _serve(monkeypatch, {url: _PLATFORM_EVENT_PAGE})

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.name is None  # not "SkillBox"


def test_platform_page_follows_declared_organizer_to_their_own_site(monkeypatch):
    url = "https://www.skillboxes.com/events/horrorcon-india"
    fetched = _serve(monkeypatch, {url: _PLATFORM_EVENT_PAGE_WITH_ORGANIZER, "https://frightnights.example": _ORGANIZER_SITE})

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.found
    assert organizer.name == "Fright Nights Collective"
    assert organizer.email == "team@frightnights.example"
    assert organizer.website == "https://frightnights.example"
    assert fetched == [url, "https://frightnights.example"]


def test_aggregator_source_type_is_treated_as_platform(monkeypatch):
    url = "https://events.unknown-ticketing.example/e/123"
    _serve(monkeypatch, {url: _PLATFORM_EVENT_PAGE})

    organizer = organizer_identifier.identify_organizer(_candidate(url, source_type="aggregator"))

    assert organizer.email is None
    assert organizer.linkedin is None


def test_organizer_own_site_still_uses_page_contacts(monkeypatch):
    url = "https://frightnights.example/horrorcon"
    _serve(monkeypatch, {url: _ORGANIZER_SITE})

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.found
    assert organizer.email == "team@frightnights.example"


def test_same_page_is_never_fetched_twice(monkeypatch):
    event_url = "https://frightnights.example/horrorcon"
    contact_url = "https://frightnights.example/contact-us"
    pages = {
        event_url: '<html><body><a href="/contact-us">Contact</a></body></html>',
        # The contact page links to itself and has no email.
        contact_url: '<html><body><a href="/contact-us">Contact</a> <a href="/about">About</a></body></html>',
        "https://frightnights.example/about": '<html><body><a href="mailto:team@frightnights.example">Mail</a></body></html>',
    }
    fetched = _serve(monkeypatch, pages)

    organizer = organizer_identifier.identify_organizer(_candidate(event_url))

    assert len(fetched) == len(set(fetched))
    assert fetched == [event_url, contact_url, "https://frightnights.example/about"]
    assert organizer.email == "team@frightnights.example"


def test_platform_detection():
    assert is_platform_url("https://www.skillboxes.com/events/x")
    assert is_platform_url("https://lu.ma/abc")
    assert is_platform_url("https://www.eventbrite.com/e/123")
    assert not is_platform_url("https://frightnights.example/horrorcon")
    assert not is_platform_url("https://ficci.in/events")


def test_json_ld_event_records_declared_organizer_name():
    soup = BeautifulSoup(_PLATFORM_EVENT_PAGE_WITH_ORGANIZER, "html.parser")
    source = CandidateSource(url="https://www.skillboxes.com/events/horrorcon-india", source_type="aggregator")

    event = page_extractor._from_json_ld(source, soup)

    assert event is not None
    assert event.organizer_name_hint == "Fright Nights Collective"
