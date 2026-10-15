"""Event Discovery Agent — headless-browser (Playwright) fallback for
JavaScript-rendered pages. The plain HTTP fetch stays the first choice;
the browser is only used when a discovery fetch fails or comes back thin,
and never for callers that don't ask for it (Organizer Outreach)."""

import socket
import sys
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import pytest

from backend.services.discovery_agent import organizer_identifier, page_extractor
from backend.services.discovery_agent.types import CandidateSource
from backend.services.social_agent import browser_fetch, web_fetch

_RICH_HTML = """<html><head><script type="application/ld+json">
{"@type": "Event", "name": "Pune Tech Summit", "startDate": "2099-01-01"}
</script></head><body><p>Pune Tech Summit</p></body></html>"""

_THIN_HTML = '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'

_RENDERED_HTML = "<html><body><h1>Rendered event</h1></body></html>"


def _fail_render(url):
    pytest.fail("the browser should not have been used")


def test_rich_page_does_not_use_browser(monkeypatch):
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: _RICH_HTML)
    monkeypatch.setattr(browser_fetch, "render", _fail_render)

    assert web_fetch.fetch("https://example.test/event", render_js=True) == _RICH_HTML


def test_thin_page_is_rendered_in_browser(monkeypatch):
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: _THIN_HTML)
    monkeypatch.setattr(browser_fetch, "render", lambda url: _RENDERED_HTML)

    assert web_fetch.fetch("https://example.test/event", render_js=True) == _RENDERED_HTML


def test_failed_http_fetch_falls_back_to_browser(monkeypatch):
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: None)
    monkeypatch.setattr(browser_fetch, "render", lambda url: _RENDERED_HTML)

    assert web_fetch.fetch("https://example.test/event", render_js=True) == _RENDERED_HTML


def test_browser_failure_keeps_the_http_result(monkeypatch):
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: _THIN_HTML)
    monkeypatch.setattr(browser_fetch, "render", lambda url: None)

    assert web_fetch.fetch("https://example.test/event", render_js=True) == _THIN_HTML


def test_plain_fetch_never_uses_browser(monkeypatch):
    """Organizer Outreach calls `fetch(url)` — it must behave exactly as before."""
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: _THIN_HTML)
    monkeypatch.setattr(browser_fetch, "render", _fail_render)

    assert web_fetch.fetch("https://example.test/event") == _THIN_HTML


def test_discovery_respects_browser_setting_off(monkeypatch):
    monkeypatch.setattr(web_fetch, "_http_get", lambda url: _THIN_HTML)
    monkeypatch.setattr(browser_fetch, "render", _fail_render)
    monkeypatch.setattr(page_extractor, "browser_fetch_enabled", lambda: False)

    source = CandidateSource(url="https://example.test/event", source_type="event_listing")
    page_extractor.extract_event_from_page(source)


def test_render_without_playwright_installed_returns_none(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    assert browser_fetch.render("https://example.test/event") is None


def test_render_rejects_non_http_urls():
    assert browser_fetch.render("file:///etc/passwd") is None
    assert browser_fetch.render("javascript:alert(1)") is None


# --- Real browser, local page ------------------------------------------------

# Event facts and the organizer's contact only exist after JavaScript runs,
# so the plain HTTP fetch sees an empty shell.
_JS_ONLY_EVENT_PAGE = """<!doctype html><html><head><title>Loading</title></head>
<body><div id="root"></div>
<script>
const ld = document.createElement("script");
ld.type = "application/ld+json";
ld.textContent = JSON.stringify({
  "@type": "Event",
  "name": "Bengaluru Founders Meetup",
  "startDate": "2099-03-14",
  "location": {"name": "Koramangala Hall", "address": {"addressLocality": "Bengaluru", "addressRegion": "Karnataka"}},
  "organizer": {"name": "Founders Circle", "url": "https://founders.example", "email": "mailto:hello@founders.example"}
});
document.head.appendChild(ld);
document.getElementById("root").innerHTML =
  '<h1>Bengaluru Founders Meetup</h1><a href="mailto:hello@founders.example">Contact the organizer</a>';
</script></body></html>"""


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
def js_event_site(tmp_path_factory):
    if not _browser_available():
        pytest.skip("Playwright Chromium is not installed")
    root = tmp_path_factory.mktemp("site")
    (root / "event.html").write_text(_JS_ONLY_EVENT_PAGE, encoding="utf-8")

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    handler = partial(_QuietHandler, directory=str(root))
    server = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/event.html"
    server.shutdown()


def test_real_browser_extracts_js_rendered_event_and_organizer(js_event_site):
    # Without the browser the agent only sees an empty JavaScript shell.
    assert web_fetch.is_thin_page(web_fetch.fetch(js_event_site))

    source = CandidateSource(url=js_event_site, source_type="event_listing")
    event = page_extractor.extract_event_from_page(source)

    assert event is not None
    assert event.name == "Bengaluru Founders Meetup"
    assert event.date == "2099-03-14"
    assert event.venue == "Koramangala Hall"
    assert event.city == "Bengaluru"

    organizer = organizer_identifier.identify_organizer(event)

    assert organizer.found
    assert organizer.name == "Founders Circle"
    assert organizer.email == "hello@founders.example"
