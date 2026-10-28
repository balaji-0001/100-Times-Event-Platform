"""Stage 5 (Find organizer): organizer name, e-mail, phone and website are
read from what the event's and organizer's pages actually publish — structured
data, links, attributes and visible text, the site's Contact/Imprint pages,
and (only when the plain reads find no e-mail) the page as a browser renders
it. Every detail keeps the URL it was read from; nothing is guessed, a stored
value is never blanked, and an unreachable page never ends the lookup."""

import socket
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import pytest
from bs4 import BeautifulSoup

from backend.models import DiscoveredEvent, DiscoveredOrganizer, OrganizerContact
from backend.services.discovery_agent import organizer_identifier, storage, web_search
from backend.services.discovery_agent.email_verifier import is_valid_organizer_email
from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate, OrganizerCandidate, RunSummary
from backend.services.social_agent import browser_fetch, web_fetch


def _candidate(url, *, source_type="official_event_site", name="Construction Expo 2099", hint=None):
    source = CandidateSource(url=url, source_type=source_type)
    return ExtractedEventCandidate(name=name, url=url, city="Pune", organizer_name_hint=hint, primary_source=source, sources=[source])


def _serve(monkeypatch, pages, *, browser=False, rendered=None, searches=None):
    """Plain reads come from `pages`; browser renders (when enabled) from `rendered`."""
    fetched, renders = [], []

    def fake_fetch(url, render_js=False):
        fetched.append(url)
        page = pages.get(url)
        if isinstance(page, Exception):
            raise page
        return page

    def fake_render(url, for_contacts=False):
        renders.append((url, for_contacts))
        page = (rendered or {}).get(url)
        if isinstance(page, Exception):
            raise page
        return page

    monkeypatch.setattr(organizer_identifier, "fetch", fake_fetch)
    monkeypatch.setattr(organizer_identifier, "browser_fetch_enabled", lambda: browser)
    monkeypatch.setattr(browser_fetch, "render", fake_render)
    monkeypatch.setattr(browser_fetch, "busy", lambda: False)
    monkeypatch.setattr(web_fetch, "was_rendered", lambda url: False)
    monkeypatch.setattr(web_search, "search", lambda query, max_results=5, **kw: list(searches or []))
    return fetched, renders


def _cf(email, key=0x5A):
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in email)


# --- Static HTML -----------------------------------------------------------------------


def test_cloudflare_protected_email_and_tel_link_are_read_with_their_source(monkeypatch):
    url = "https://buildexpo.test/"
    page = f"""<html><body><h1>Construction Expo 2099</h1><p>Organised by: BuildCorp Exhibitions Pvt. Ltd.</p>
    <footer><a href="/cdn-cgi/l/email-protection#{_cf('info@buildexpo.test')}">[email&#160;protected]</a>
    <a href="tel:+49%2089%20949-11248">Call us</a></footer></body></html>"""
    _serve(monkeypatch, {url: page})

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.found and organizer.email == "info@buildexpo.test"
    assert organizer.phone == "+49 89 949-11248"  # any country, from the tel: link
    assert organizer.name == "BuildCorp Exhibitions Pvt. Ltd."  # the page's own label, not its <title>
    assert organizer.email_source_url == url and organizer.field_sources["phone"] == url and organizer.field_sources["name"] == url


def test_json_ld_organizer_list_with_contact_point(monkeypatch):
    url = "https://events.example-venue.test/shows/textile-week"
    page = """<html><head><script type="application/ld+json">
    {"@type": "Event", "name": "Textile Week", "organizer": [{"@type": "Organization", "name": "Textile Council",
     "url": "https://textilecouncil.test", "contactPoint": {"email": "events@textilecouncil.test", "telephone": "+91 22 4000 1234"}}]}
    </script></head><body><a href="mailto:venue-desk@example-venue.test">Venue desk</a></body></html>"""
    _serve(monkeypatch, {url: page})

    organizer = organizer_identifier.identify_organizer(_candidate(url, name="Textile Week"))

    assert organizer.name == "Textile Council"
    assert organizer.email == "events@textilecouncil.test"  # declared organizer beats the venue's mailbox
    assert organizer.phone == "+91 22 4000 1234"
    assert organizer.website == "https://textilecouncil.test"


def test_obfuscated_at_dot_address_in_visible_text(monkeypatch):
    url = "https://fair.test/en"
    _serve(monkeypatch, {url: "<html><body><p>Questions? Write to office [at] fair (dot) test</p></body></html>"})

    assert organizer_identifier.identify_organizer(_candidate(url)).email == "office@fair.test"


# --- Contact-page discovery ---------------------------------------------------------------


def test_imprint_page_is_found_and_unlabelled_outbound_links_are_not_followed(monkeypatch):
    url = "https://messe-fair.test/en/"
    pages = {
        url: """<html><body><h1>Messe Fair</h1>
            <a href="https://itunes.apple.com/app/fever">Get the app</a>
            <a href="https://news-site.test/story">In the news</a>
            <a href="/en/impressum/">Impressum</a></body></html>""",
        "https://messe-fair.test/en/impressum/": "<html><body><p>Veranstalter: Messe Fair GmbH</p><p>E-Mail: kontakt@messe-fair.test</p><p>Tel.: +49 30 1234 5678</p></body></html>",
        "https://news-site.test/story": '<html><body><a href="mailto:tips@news-site.test">Tips</a></body></html>',
    }
    fetched, _ = _serve(monkeypatch, pages)

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.email == "kontakt@messe-fair.test"
    assert organizer.email_source_url == "https://messe-fair.test/en/impressum/"
    assert organizer.name == "Messe Fair GmbH" and organizer.phone == "+49 30 1234 5678"
    assert "https://news-site.test/story" not in fetched and not any("apple.com" in u for u in fetched)


def test_same_site_is_not_read_twice_under_another_spelling_and_a_dead_link_does_not_end_the_lookup(monkeypatch):
    event = "https://www.venue.test/events/ev-world"
    pages = {
        event: """<html><head><script type="application/ld+json">{"@type": "Event", "name": "EV World",
            "organizer": {"name": "SMM Exhibitions", "url": "https://evworld.test/"}}</script></head><body></body></html>""",
        "https://evworld.test/": """<html><body><a href="https://www.evworld.test">Home</a>
            <a href="/contact-us">Contact</a><a href="/about">About us</a></body></html>""",
        "https://evworld.test/contact-us": None,  # unreachable
        "https://evworld.test/about": '<html><body><a href="mailto:hello@evworld.test">Email</a></body></html>',
    }
    fetched, _ = _serve(monkeypatch, pages)

    organizer = organizer_identifier.identify_organizer(_candidate(event, name="EV World"))

    assert organizer.email == "hello@evworld.test"
    assert fetched == [event, "https://evworld.test/", "https://evworld.test/contact-us", "https://evworld.test/about"]
    assert "https://www.venue.test/contact" not in fetched  # the venue's own contact page is not the organizer's


def test_after_the_email_one_contact_page_is_read_for_a_missing_phone(monkeypatch):
    url = "https://summit.test/"
    pages = {
        url: '<html><body><a href="mailto:team@summit.test">Mail</a><a href="/contact">Contact</a></body></html>',
        "https://summit.test/contact": "<html><body><p>Phone: +1 (415) 555-0100</p></body></html>",
    }
    _serve(monkeypatch, pages)

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.email == "team@summit.test" and organizer.email_source_url == url
    assert organizer.phone == "+1 (415) 555-0100" and organizer.field_sources["phone"] == "https://summit.test/contact"


# --- Missing and invalid contacts ----------------------------------------------------------


def test_no_published_contact_means_nothing_is_invented(monkeypatch):
    url = "https://quiet-expo.test/"
    _serve(monkeypatch, {url: "<html><head><title>Quiet Expo 2099</title></head><body><p>Dates: 2099-10-28</p></body></html>"})

    organizer = organizer_identifier.identify_organizer(_candidate(url, hint="Quiet Expo Org"))

    assert not organizer.found
    assert organizer.email is None and organizer.phone is None and organizer.email_source_url is None


@pytest.mark.parametrize("address", ["name@email.com", "you@domain.com", "noreply@fair.test", "logo@2x.png", "info@example.com"])
def test_placeholder_and_system_addresses_are_rejected(address):
    assert not is_valid_organizer_email(address)[0]


def test_invalid_contacts_on_a_page_are_skipped_for_real_ones(monkeypatch):
    url = "https://realfair.test/"
    page = """<html><body><form><input placeholder="name@email.com"></form><p>Event dates 2099 10 28 11 22</p>
        <img src="logo@2x.png"><a href="mailto:noreply@realfair.test">x</a><a href="mailto:sales@realfair.test">Sales</a></body></html>"""
    _serve(monkeypatch, {url: page})

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.email == "sales@realfair.test"
    assert organizer.phone is None  # a row of dates is not a phone number


def test_search_result_that_does_not_name_the_organizer_is_not_used(monkeypatch):
    url = "https://www.eventbrite.com/e/finance-forum-1"
    platform_page = '<html><head><script type="application/ld+json">{"@type": "Event", "name": "Finance Forum", "organizer": {"name": "Future Forums Group"}}</script></head></html>'
    pages = {
        url: platform_page,
        "https://unrelated.test/": '<html><body><h1>Gadget reviews</h1><a href="mailto:tips@unrelated.test">Tips</a></body></html>',
        "https://futureforums.test/": '<html><body><h1>Future Forums Group</h1><a href="mailto:hello@futureforums.test">Mail</a></body></html>',
    }
    _serve(monkeypatch, pages, searches=["https://unrelated.test/", "https://futureforums.test/"])

    organizer = organizer_identifier.identify_organizer(_candidate(url, source_type="aggregator", name="Finance Forum"))

    assert organizer.email == "hello@futureforums.test"
    assert organizer.email_source_url == "https://futureforums.test/"


def test_a_listing_directory_s_own_contacts_are_not_the_organizer_s(monkeypatch):
    url = "https://globaltradefairs.com/tradefairs/event-details/india-chem-2099"
    page = """<html><body><h1>India Chem 2099</h1><p>Call +91-7867892000</p><a href="mailto:gtradefairs@gmail.com">Mail us</a>
        <a href="/contact-us">Contact</a><a href="https://indiachem.test/">Official website</a></body></html>"""
    pages = {url: page, "https://indiachem.test/": '<html><body><a href="mailto:info@indiachem.test">Mail</a></body></html>'}
    fetched, _ = _serve(monkeypatch, pages)

    organizer = organizer_identifier.identify_organizer(_candidate(url, source_type="event_listing", name="India Chem 2099"))

    assert organizer.email == "info@indiachem.test" and organizer.phone is None
    assert "https://globaltradefairs.com/contact-us" not in fetched


def test_a_news_article_that_mentions_the_organizer_is_not_their_site(monkeypatch):
    url = "https://www.eventbrite.com/e/energy-week-1"
    pages = {
        url: '<script type="application/ld+json">{"@type": "Event", "name": "Energy Week", "organizer": {"name": "Energy Institute"}}</script>',
        "https://dailynews.test/story": "<html><body><p>The Energy Institute announced …</p><a href='mailto:desk@dailynews.test'>Desk</a></body></html>",
    }
    _serve(monkeypatch, pages, searches=["https://dailynews.test/story"])

    organizer = organizer_identifier.identify_organizer(_candidate(url, source_type="aggregator", name="Energy Week"))

    assert organizer.email is None and organizer.name == "Energy Institute"


# --- JavaScript-rendered pages (browser fallback) ------------------------------------------


def test_browser_fallback_reads_contacts_only_the_rendered_page_shows(monkeypatch):
    url = "https://spa-expo.test/"
    static = "<html><body><div id=app>" + "Expo details " * 60 + "</div></body></html>"
    rendered = '<html><body><footer><a href="mailto:hello@spa-expo.test">Email</a><a href="tel:+971 4 123 4567">Call</a></footer></body></html>'
    fetched, renders = _serve(monkeypatch, {url: static}, browser=True, rendered={url: rendered})

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.email == "hello@spa-expo.test" and organizer.email_source_url == url
    assert organizer.phone == "+971 4 123 4567"
    assert renders == [(url, True)]


def test_browser_is_not_used_when_the_plain_read_found_the_email(monkeypatch):
    url = "https://plain.test/"
    _, renders = _serve(monkeypatch, {url: '<a href="mailto:a@plain.test">a</a>'}, browser=True, rendered={url: "<p>x</p>"})

    organizer_identifier.identify_organizer(_candidate(url))

    assert renders == []


def test_rendered_navigation_leads_to_the_contact_page(monkeypatch):
    url = "https://navapp.test/"
    pages = {url: "<html><body>" + "content " * 80 + "</body></html>",
             "https://navapp.test/contact": '<html><body><a href="mailto:office@navapp.test">Office</a></body></html>'}
    rendered = {url: '<html><body><nav><a href="/contact">Contact</a></nav></body></html>'}
    fetched, renders = _serve(monkeypatch, pages, browser=True, rendered=rendered)

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.email == "office@navapp.test"
    assert organizer.email_source_url == "https://navapp.test/contact"


@pytest.mark.parametrize("render_result", [None, RuntimeError("browser crashed")])
def test_browser_failure_keeps_the_lookup_alive(monkeypatch, render_result):
    url = "https://flaky.test/"
    _serve(monkeypatch, {url: "<html><body><p>Organizer: Flaky Fairs Ltd</p></body></html>"}, browser=True, rendered={url: render_result})

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.name == "Flaky Fairs Ltd" and organizer.email is None


def test_render_budget_and_busy_browser(monkeypatch):
    url = "https://many.test/"
    pages = {url: '<a href="/contact">C</a><a href="/impressum">I</a><a href="/about">A</a>',
             "https://many.test/contact": "<p>none</p>", "https://many.test/impressum": "<p>none</p>", "https://many.test/about": "<p>none</p>"}
    _, renders = _serve(monkeypatch, pages, browser=True, rendered={})
    organizer_identifier.identify_organizer(_candidate(url))
    assert len(renders) == organizer_identifier._MAX_RENDERS

    _, renders = _serve(monkeypatch, pages, browser=True, rendered={})
    monkeypatch.setattr(browser_fetch, "busy", lambda: True)
    organizer_identifier.identify_organizer(_candidate(url))
    assert renders == []  # never queues behind a saturated browser


# --- Timeouts / unreachable sites -----------------------------------------------------------


def test_timeouts_and_errors_on_followed_pages_do_not_crash(monkeypatch):
    url = "https://slowfair.test/"
    pages = {url: '<a href="/contact">Contact</a><a href="/impressum">Imprint</a>',
             "https://slowfair.test/contact": TimeoutError("read timed out"),
             "https://slowfair.test/impressum": '<a href="mailto:info@slowfair.test">Mail</a>'}
    _serve(monkeypatch, pages)

    organizer = organizer_identifier.identify_organizer(_candidate(url))

    assert organizer.email == "info@slowfair.test"


def test_unreachable_event_page_returns_not_found(monkeypatch):
    _serve(monkeypatch, {})
    assert organizer_identifier.identify_organizer(_candidate("https://down.test/")).found is False


# --- Preserving stored data -----------------------------------------------------------------


def test_existing_organizer_keeps_its_values_and_gains_missing_ones(db_session):
    stored = DiscoveredOrganizer(name="Messe Group", email="info@messe.test", website="https://messe.test")
    db_session.add(stored)
    db_session.flush()
    found = OrganizerCandidate(found=True, name="Messe Group", email="sales@messe.test", phone="+49 89 1234 567", website=None,
                               sources=[CandidateSource(url="https://messe.test/event", source_type="official_event_site")],
                               email_source_url="https://messe.test/contact", field_sources={"phone": "https://messe.test/impressum"})

    organizer = storage.get_or_create_organizer(db_session, found, RunSummary())

    assert organizer.id == stored.id
    assert organizer.email == "info@messe.test"  # a stored value is never replaced
    assert organizer.website == "https://messe.test"  # nor blanked by an empty one
    assert organizer.phone == "+49 89 1234 567"  # a missing one is filled in
    contacts = {c.contact_type + ":" + c.value: c.source_url for c in db_session.query(OrganizerContact).all()}
    assert contacts["email:sales@messe.test"] == "https://messe.test/contact"
    assert contacts["phone:+49 89 1234 567"] == "https://messe.test/impressum"


def test_upgrading_a_rejected_event_keeps_details_the_new_read_lacks(db_session):
    old = DiscoveredEvent(name="Textile Week", date="2099-03-01", city="Pune", venue="Expo Hall 2", url="https://tw.test",
                          verification_status="REJECTED", discovery_status="REJECTED", discovered_by="web_discovery_agent",
                          verification_notes=["REJECTION_REASON: MISSING_ORGANIZER_EMAIL"])
    db_session.add(old)
    db_session.flush()
    source = CandidateSource(url="https://tw.test", source_type="official_event_site")
    candidate = ExtractedEventCandidate(name="Textile Week", date="2099-03-01", city="Pune", venue=None, url="https://tw.test",
                                        primary_source=source, sources=[source])

    event = storage.persist_event(db_session, candidate=candidate, organizer=None, verification_status="NEEDS_REVIEW",
                                  verification_notes=[], confidence_score=70, event_date=None, summary=RunSummary())

    assert event.id == old.id and event.verification_status == "NEEDS_REVIEW"
    assert event.venue == "Expo Hall 2"


# --- A real headless browser on a local page ---------------------------------------------------

# The page has plenty of static text (so the plain read is not a "thin" JS shell
# and the generic fetch never renders it), but the organizer's contact is only
# added by a script a moment after load.
_LATE_CONTACT_PAGE = """<!doctype html><html><head><title>Late Contact Expo</title></head><body>
<main>""" + "<p>Late Contact Expo brings builders, architects and suppliers together for three days.</p>" * 12 + """</main>
<footer id="f"></footer>
<script>setTimeout(function () {
  var address = ["expo-team", "late-contact.example"].join("@");
  document.getElementById("f").innerHTML = '<a href="mailto:' + address + '">Write to the organizers</a>';
}, 400);</script></body></html>"""


def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def late_contact_site(tmp_path_factory):
    if not _browser_available():
        pytest.skip("Playwright Chromium is not installed")
    root = tmp_path_factory.mktemp("late")
    (root / "expo.html").write_text(_LATE_CONTACT_PAGE, encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = HTTPServer(("127.0.0.1", port), partial(_QuietHandler, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/expo.html"
    server.shutdown()


def test_real_browser_fallback_finds_a_contact_added_by_javascript(late_contact_site, monkeypatch):
    web_fetch.clear_cache()
    monkeypatch.setattr(organizer_identifier, "browser_fetch_enabled", lambda: True)
    monkeypatch.setattr(web_search, "search", lambda *a, **k: [])
    plain = web_fetch.fetch(late_contact_site)
    assert not web_fetch.is_thin_page(plain) and "expo-team@" not in plain  # invisible to a plain read

    organizer = organizer_identifier.identify_organizer(_candidate(late_contact_site, name="Late Contact Expo"))

    assert organizer.email == "expo-team@late-contact.example"
    assert organizer.email_source_url == late_contact_site
