"""Discovery Strategy toggles end to end: every selected provider / adapter /
aggregator is either executed (and its real outcome recorded) or skipped with
a stated reason; unselected ones are never called; failures are isolated;
zero results are not failures; budgets hold; credentials never reach the
browser. All network is stubbed with deterministic responses."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import AgentRun, DiscoveredEvent, EventDiscoverySource, User
from backend.routes import discovery as discovery_routes
from backend.services.discovery_agent import catalog, orchestrator
from backend.services.discovery_agent.adapters import SourceError, adapter_manager
from backend.services.discovery_agent.adapters.api_adapters import CredentialAwarePlatformAdapter
from backend.services.discovery_agent.adapters.html_listing import HtmlListingAdapter
from backend.services.discovery_agent.adapters.rss_ical import RssIcalAdapter
from backend.services.discovery_agent.search_providers import search_engine
from backend.services.discovery_agent.search_providers.base import SearchProviderResult
from backend.services.discovery_agent.search_providers.engine import SearchRunStats
from backend.services.discovery_agent.types import DiscoveryConfig
from backend.services.social_agent import web_fetch
from tests.test_discovery_pipeline import _candidate, _organizer


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: User(id=1, name="Admin", email="a@x.test", password_hash="x", role="ADMIN")
    return TestClient(app)


@pytest.fixture()
def no_browser(monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "discovery_browser_fetch", False)


def _only_configured(monkeypatch, *ids):
    for provider in search_engine.providers.values():
        monkeypatch.setattr(type(provider), "is_configured", lambda self: self.provider_id in ids)


def _stub(monkeypatch, provider_id, fn):
    monkeypatch.setattr(type(search_engine.providers[provider_id]), "search", fn)


# ---------------------------------------------------------------------------
# 1, 3, 15: the registry the UI shows
# ---------------------------------------------------------------------------


def test_catalog_lists_every_channel_provider_and_source_with_real_states(client, monkeypatch):
    _only_configured(monkeypatch, "searxng", "exa_search")
    data = client.get("/api/discovery/catalog").json()

    assert [c["id"] for c in data["channels"]] == ["web", "directories", "aggregators", "apis"]
    providers = {p["id"]: p for p in data["providers"]}
    assert set(providers) == {"searxng", "exa_search", "google_gemini", "google_search", "brave_search", "bing_search", "web_fallback"}
    assert providers["searxng"]["tier"] == "free" and providers["web_fallback"]["tier"] == "last_resort"
    # Missing credentials: exact variables named, never "available".
    assert providers["google_gemini"]["configured"] is False and "GEMINI_API_KEY" in providers["google_gemini"]["unavailable_reason"]
    assert "retired" in providers["bing_search"]["unavailable_reason"]

    sources = {s["id"]: s for s in data["sources"]}
    assert {"dev_events", "wikicfp", "dwtc_events", "rx_global"} <= {sid for sid, s in sources.items() if s["channel"] == "directories"}
    assert {"eventbrite", "meetup", "allevents", "skillboxes"} <= {sid for sid, s in sources.items() if s["channel"] == "aggregators"}
    # Placeholder API adapters are listed as what they are, never as active sources.
    assert sources["eventbrite_api"]["implemented"] is False and sources["eventbrite_api"]["health"]["status"] == "not_implemented"
    assert sources["ticketmaster_api"]["configured"] is False
    # Nothing was ever executed in this DB: no source claims to be healthy.
    assert {s["health"]["status"] for s in sources.values() if s["implemented"] and s["configured"]} == {"untested"}
    assert not any(s["channel"] == "web" for s in data["sources"])


def test_catalog_never_contains_credential_values(client, monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "exa_api_key", "exa-secret-value-123")
    monkeypatch.setattr(get_settings(), "gemini_api_key", "gemini-secret-value-456")
    text = client.get("/api/discovery/catalog").text + client.get("/api/discovery/search-providers").text
    assert "exa-secret-value-123" not in text and "gemini-secret-value-456" not in text


# ---------------------------------------------------------------------------
# 2, 4, 8, 12, 13: provider orchestration
# ---------------------------------------------------------------------------


def test_disabled_provider_is_never_called_even_as_last_resort(monkeypatch):
    _only_configured(monkeypatch, "searxng", "exa_search")
    calls = []
    _stub(monkeypatch, "searxng", lambda self, query, **kw: calls.append("searxng") or [])
    _stub(monkeypatch, "exa_search", lambda self, query, **kw: calls.append("exa") or [])
    _stub(monkeypatch, "web_fallback", lambda self, query, **kw: calls.append("ddg") or [])

    stats = SearchRunStats(allowed={"searxng"})
    assert search_engine.search("expo", max_results=5, stats=stats) == []
    assert calls == ["searxng"]  # Exa and DuckDuckGo were not selected: never called


def test_a_failing_provider_does_not_stop_the_others(monkeypatch):
    _only_configured(monkeypatch, "searxng", "exa_search")

    def broken(self, query, **kw):
        raise RuntimeError("SearXNG HTTP 502")

    _stub(monkeypatch, "searxng", broken)
    _stub(monkeypatch, "exa_search", lambda self, query, max_results=5, **kw: [SearchProviderResult(url=f"https://exa.test/{i}") for i in range(3)])
    stats = SearchRunStats()
    urls = search_engine.search("expo", max_results=5, stats=stats)

    assert urls == [f"https://exa.test/{i}" for i in range(3)]
    snap = stats.snapshot()
    assert snap["searxng"]["failures"] == 1 and "502" in snap["searxng"]["last_error"]
    assert snap["exa_search"]["successes"] == 1 and snap["exa_search"]["results"] == 3
    assert stats.origin_of("https://exa.test/0") == "exa_search"


def test_zero_results_is_a_successful_call_not_a_failure(monkeypatch):
    _only_configured(monkeypatch, "searxng")
    _stub(monkeypatch, "searxng", lambda self, query, **kw: [])
    stats = SearchRunStats(allowed={"searxng"})
    search_engine.search("nothing matches this", max_results=5, stats=stats)
    row = stats.snapshot()["searxng"]
    assert row["calls"] == 1 and row["successes"] == 1 and row["zero_result_calls"] == 1 and row["failures"] == 0


def test_paid_providers_top_up_cheapest_first_and_respect_the_budget(monkeypatch):
    _only_configured(monkeypatch, "searxng", "exa_search", "google_gemini")
    calls = []
    _stub(monkeypatch, "searxng", lambda self, query, **kw: calls.append("searxng") or [])
    _stub(monkeypatch, "exa_search", lambda self, query, max_results=5, **kw: calls.append("exa") or [SearchProviderResult(url=f"https://exa.test/{query}/{i}") for i in range(5)])
    _stub(monkeypatch, "google_gemini", lambda self, query, **kw: calls.append("google") or [])

    stats = SearchRunStats(paid_budget=1)
    search_engine.search("q1", max_results=5, stats=stats)
    assert calls == ["searxng", "exa"]  # Exa filled the gap: Google was not bought too
    assert stats.snapshot()["google_gemini"]["skipped"] == {"not_needed": 1}

    calls.clear()
    search_engine.search("q2", max_results=5, stats=stats)
    assert calls == ["searxng"]  # paid budget (1 call) already spent
    assert stats.snapshot()["exa_search"]["skipped"]["paid_budget_exhausted"] == 1


def test_a_provider_out_of_quota_is_paused_with_the_reason(monkeypatch):
    _only_configured(monkeypatch, "searxng", "google_gemini")
    calls = []
    _stub(monkeypatch, "searxng", lambda self, query, **kw: [])

    def out_of_quota(self, query, **kw):
        calls.append(query)
        raise RuntimeError("Gemini API call failed: 429 RESOURCE_EXHAUSTED: You exceeded your current quota, please check your plan and billing details.")

    _stub(monkeypatch, "google_gemini", out_of_quota)
    stats = SearchRunStats()
    search_engine.search("q1", max_results=5, stats=stats)
    search_engine.search("q2", max_results=5, stats=stats)

    assert calls == ["q1"]  # not retried on every query
    status = search_engine.get_providers_status()["google_gemini"]
    assert status["cooling_down_seconds"] > 3000 and status["cooldown_reason"].startswith("Quota or billing limit")
    row = stats.snapshot()["google_gemini"]
    assert row["rate_limited"] == 1 and row["skipped"]["cooling_down"] == 1


def test_same_url_from_two_providers_is_returned_once(monkeypatch):
    from backend.core.config import get_settings

    _only_configured(monkeypatch, "searxng", "exa_search")
    monkeypatch.setattr(get_settings(), "search_strategy", "parallel")
    _stub(monkeypatch, "searxng", lambda self, query, **kw: [SearchProviderResult(url="https://expo.test/a"), SearchProviderResult(url="https://expo.test/b")])
    _stub(monkeypatch, "exa_search", lambda self, query, **kw: [SearchProviderResult(url="https://expo.test/a")])
    assert sorted(search_engine.search("dup", max_results=5)) == ["https://expo.test/a", "https://expo.test/b"]


def test_google_via_gemini_returns_only_grounding_sources(monkeypatch):
    from backend.core.config import get_settings
    from backend.services.social_agent import ai_client

    provider = search_engine.providers["google_gemini"]
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    assert provider.is_configured() is False and "GEMINI_API_KEY" in provider.unavailable_reason()

    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(ai_client.GeminiAIClient, "generate_with_web_search", lambda self, system, user, max_tokens=512, max_uses=5: {
        "text": "See https://made-up-by-model.test/expo",  # model text is never used as a result
        "citations": [{"url": "https://bigexpo.test/2027", "title": "Big Expo 2027"}, {"url": "ftp://bad.test", "title": "x"}],
    })
    # conftest stubs every provider class's search(); a reloaded module gives the real code.
    import importlib

    from backend.services.discovery_agent.search_providers import google_gemini

    real = importlib.reload(google_gemini).GeminiGoogleSearchProvider()
    results = real.search("construction expo dubai 2027")
    assert [r.url for r in results] == ["https://bigexpo.test/2027"]


# ---------------------------------------------------------------------------
# Adapters: real events page, honest failures (5, 6)
# ---------------------------------------------------------------------------

_EVENT_PAGE = """<html><head><script type="application/ld+json">{"@context": "https://schema.org", "@type": "Event",
"name": "Big Construction Expo 2027", "startDate": "2027-03-01", "url": "https://venue.test/events/big-expo",
"location": {"@type": "Place", "name": "Expo Hall", "address": {"addressLocality": "Mumbai", "addressCountry": "India"}}}</script></head>
<body><h1>What's on</h1></body></html>"""


def test_adapter_reads_its_configured_events_page_not_the_homepage(monkeypatch, no_browser):
    fetched = []

    def http_get(url):
        fetched.append(url)
        return _EVENT_PAGE if url == "https://venue.test/whats-on/" else "<html><body>" + "home " * 200 + "</body></html>"

    monkeypatch.setattr(web_fetch, "_http_get", http_get)
    adapter = HtmlListingAdapter("venue_x", "Venue X", "https://venue.test/", config={"calendar_url": "https://venue.test/whats-on/"})
    events = adapter.discover(DiscoveryConfig(countries=["India"]), limit=5)

    assert fetched == ["https://venue.test/whats-on/"]
    assert [(e.name, e.date, e.city) for e in events] == [("Big Construction Expo 2027", "2027-03-01", "Mumbai")]


def test_unreadable_page_is_a_failure_with_its_reason_and_an_empty_page_is_not(monkeypatch, no_browser):
    def http_get(url):
        if "broken" in url:
            web_fetch._note_failure(url, "HTTP 404")
            return None
        return "<html><body>" + "no events listed here " * 40 + "</body></html>"

    monkeypatch.setattr(web_fetch, "_http_get", http_get)
    broken = HtmlListingAdapter("b", "Broken", "https://broken.test/", config={"calendar_url": "https://broken.test/events"})
    with pytest.raises(SourceError) as exc:
        broken.discover(DiscoveryConfig(), limit=5)
    assert exc.value.kind == "unreachable" and "HTTP 404" in str(exc.value)

    empty = HtmlListingAdapter("e", "Empty", "https://empty.test/", config={"calendar_url": "https://empty.test/events"})
    assert empty.discover(DiscoveryConfig(), limit=5) == []  # read fine, nothing listed: not an error, and no fake "event"


def test_wikicfp_feed_gives_event_dates_and_places_not_publish_dates(monkeypatch):
    feed = """<?xml version="1.0"?><rss version="2.0"><channel><item>
      <title>ICHBC 2026 : IEEE 2026 6th International Conference on High Performance Computing</title>
      <link>http://www.wikicfp.com/cfp/servlet/event.showcfp?eventid=1</link>
      <description>IEEE 2026 6th International Conference [Nanchang, China] [Dec 18, 2026 - Dec 20, 2026]</description>
      <pubDate>Mon, 01 Sep 2025 00:00:00 GMT</pubDate></item></channel></rss>"""
    monkeypatch.setattr(web_fetch, "_http_get", lambda url, allow_feed=False: feed if allow_feed else None)
    adapter = RssIcalAdapter("wikicfp", "WikiCFP", "http://www.wikicfp.com/", config={"rss_url": "http://www.wikicfp.com/cfp/rss"})
    [event] = adapter.discover(DiscoveryConfig(), limit=5)
    assert event.name == "IEEE 2026 6th International Conference on High Performance Computing"
    assert (event.date, event.city, event.country) == ("Dec 18, 2026", "Nanchang", "China")


def test_placeholder_api_adapter_never_reports_success_even_with_a_key(monkeypatch):
    monkeypatch.setenv("EVENTBRITE_API_KEY", "anything")
    adapter = adapter_manager.get_adapter("eventbrite_api")
    assert isinstance(adapter, CredentialAwarePlatformAdapter)
    assert adapter.test_extraction()["success"] is False
    with pytest.raises(SourceError) as exc:
        adapter.discover(DiscoveryConfig())
    assert exc.value.kind == "not_implemented"


# ---------------------------------------------------------------------------
# Selection: channels and individual ticks (2, 14)
# ---------------------------------------------------------------------------


def test_only_ticked_sources_run_inside_an_enabled_channel():
    plan = catalog.plan_sources({"global_adapters", "dev_events", "consumer_aggregators", "meetup"}, ["India"])
    assert plan.adapters == ["dev_events"] and plan.aggregators == ["meetup"]


def test_a_disabled_channel_runs_none_of_its_sources_even_if_ticked():
    plan = catalog.plan_sources({"web", "dev_events", "wikicfp", "allevents"}, ["India"])
    assert plan.adapters == [] and plan.aggregators == [] and plan.channels == {"web": True, "directories": False, "aggregators": False}


def test_channel_token_alone_means_its_default_sources():
    plan = catalog.plan_sources({"global_adapters"}, [])
    assert "dev_events" in plan.adapters and "eventbrite_api" not in plan.adapters


# ---------------------------------------------------------------------------
# A full run: every state recorded, results verified and saved (7, 9, 10, 11, 16)
# ---------------------------------------------------------------------------


def _run_config(**overrides):
    values = dict(
        cities=["Pune"], countries=["India"], country="India", categories=["Construction"],
        sources=["web", "global_adapters", "dev_events", "wikicfp", "eventseye", "consumer_aggregators", "allevents"],
        listing_urls=["https://allevents.in/{city}"], search_depth=2, sources_per_query=2, daily_limit=500,
        require_organizer_email=True, reject_no_organizer=True, min_confidence_score=0, target_valid_events=None,
    )
    values.update(overrides)
    return DiscoveryConfig(**values)


def _wire_run(monkeypatch, db_session=None):
    monkeypatch.setattr(orchestrator, "_select_adapter_ids", orchestrator.real_select_adapter_ids)
    _only_configured(monkeypatch, "searxng", "exa_search")
    calls = {"exa": 0}
    # A full page of results (sources_per_query=2), so free search is enough and Exa is not needed.
    _stub(monkeypatch, "searxng", lambda self, query, max_results=5, **kw: [SearchProviderResult(url="https://results.test/expo"), SearchProviderResult(url="https://results.test/other")])

    def exa(self, query, **kw):
        calls["exa"] += 1
        return []

    _stub(monkeypatch, "exa_search", exa)
    dev, cfp, eye = (adapter_manager.get_adapter(s) for s in ("dev_events", "wikicfp", "eventseye"))
    monkeypatch.setattr(dev, "discover", lambda config, limit=25: [_candidate(1), _candidate(2), _candidate(1)])  # #1 twice

    def cfp_down(config, limit=25):
        raise SourceError("unreachable", "http://www.wikicfp.com/cfp/rss: HTTP 403 (bot wall / access denied)")

    monkeypatch.setattr(cfp, "discover", cfp_down)
    monkeypatch.setattr(eye, "discover", lambda config, limit=25: [])
    pages = {"https://results.test/expo": [_candidate(3)]}
    monkeypatch.setattr(orchestrator.page_extractor, "extract_events_from_page", lambda url, max_events, cities: list(pages.get(url, [])))
    monkeypatch.setattr(orchestrator.organizer_identifier, "identify_organizer", _organizer)
    return calls


def test_a_run_records_every_selected_source_and_saves_verified_results(db_session, monkeypatch):
    calls = _wire_run(monkeypatch)
    summary = orchestrator.run_discovery_agent(db_session, _run_config())
    report = summary.sources
    rows = {r["id"]: r for r in report["sources"]}

    # Directories: success with candidates / failure with the reason / success with zero results.
    assert rows["dev_events"]["status"] == "succeeded" and rows["dev_events"]["candidates"] == 3
    assert rows["dev_events"]["verified"] == 2 and rows["dev_events"]["duplicates"] == 1
    assert rows["wikicfp"]["status"] == "failed" and "HTTP 403" in rows["wikicfp"]["errors"][0]
    assert rows["eventseye"]["status"] == "succeeded" and rows["eventseye"]["candidates"] == 0
    # Aggregator page read OK but listed nothing.
    assert rows["allevents"]["status"] == "succeeded" and rows["allevents"]["jobs"] == 1 and rows["allevents"]["candidates"] == 0
    # Web: SearXNG found the result page; its event is credited to SearXNG.
    assert rows["searxng"]["status"] == "succeeded" and rows["searxng"]["verified"] == 1
    # Exa: configured, but SearXNG never fell short -> never bought.
    assert calls["exa"] == 0 and rows["exa_search"]["status"] == "skipped"
    # Google via Gemini etc.: selected (all configured by default) but not configured.
    assert rows["google_gemini"]["status"] == "skipped" and rows["google_gemini"]["configured"] is False

    counts = report["counts"]
    assert counts["executed"] == sum(1 for r in rows.values() if r["jobs"])
    assert counts["failed"] == 1 and counts["successful"] == counts["executed"] - 1
    assert counts["returned_candidates"] == sum(r["candidates"] for r in rows.values())
    assert counts["verified"] == summary.verified_events == 3
    assert not any(r["status"] == "succeeded" and not r["jobs"] for r in rows.values())  # nothing "successful" without executing

    # Partial failure (WikiCFP) did not stop verified results being saved.
    assert db_session.query(DiscoveredEvent).filter_by(verification_status="VERIFIED").count() == 3
    # Real outcomes are stored as source health for the settings page.
    assert catalog.health_of(db_session.get(EventDiscoverySource, "wikicfp"))["status"] == "failed"
    assert catalog.health_of(db_session.get(EventDiscoverySource, "dev_events"))["status"] == "ok"
    assert catalog.health_of(db_session.get(EventDiscoverySource, "eventseye"))["status"] == "no_events"


def test_admin_disabled_source_is_skipped_with_the_reason(db_session, monkeypatch):
    from backend.services.discovery_agent.source_registry import seed_or_sync_source_registry

    _wire_run(monkeypatch)
    seed_or_sync_source_registry(db_session)
    db_session.get(EventDiscoverySource, "dev_events").is_enabled = False
    db_session.commit()
    summary = orchestrator.run_discovery_agent(db_session, _run_config())
    row = next(r for r in summary.sources["sources"] if r["id"] == "dev_events")
    assert row["status"] == "skipped" and "Source Registry" in row["reason"] and row["jobs"] == 0


def test_manual_run_route_uses_exactly_the_providers_ticked_in_the_ui(client, db_session, monkeypatch):
    calls = _wire_run(monkeypatch)
    _stub(monkeypatch, "searxng", lambda self, query, **kw: [])  # SearXNG short -> Exa would top up, if allowed
    response = client.post("/api/discovery/run", json={
        "countries": ["India"], "categories": ["Construction"], "sources": ["web"], "searchProviders": ["searxng"],
        "searchDepth": 2, "background": False,
    })
    assert response.status_code == 200, response.text
    assert calls["exa"] == 0  # unticked in the UI: never called
    rows = {r["id"]: r for r in response.json()["sources"]["sources"]}
    assert set(rows) == {"searxng"} and rows["searxng"]["calls"] >= 2


# ---------------------------------------------------------------------------
# 15: credentials never reach the browser
# ---------------------------------------------------------------------------


def test_ticketmaster_key_is_never_returned_by_the_api(client, db_session, monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ticketmaster_api_key", None)
    secret = "tm-secret-key-987654"
    saved = client.patch("/api/discovery/auto", json={"ticketmasterApiKey": secret}).json()
    assert saved["ticketmasterApiKeySet"] is True and saved["ticketmasterApiKeyHint"] == "…7654"
    assert secret not in json.dumps(saved) and secret not in client.get("/api/discovery/auto").text

    # The background worker opens backend.db.SessionLocal (the app's REAL
    # database) and calls the route module's own run_discovery_agent: replace
    # both, so the thread it starts can never run discovery or touch a real DB.
    import backend.db

    class _NoDb:
        def get(self, *args, **kwargs):
            return None

        def close(self):
            pass

    monkeypatch.setattr(backend.db, "SessionLocal", _NoDb)
    monkeypatch.setattr(discovery_routes, "run_discovery_agent", lambda db, config, run=None: orchestrator.RunSummary())
    run = client.post("/api/discovery/run", json={"sources": ["web"], "background": True}).json()
    assert secret not in json.dumps(run) and run["config"]["ticketmaster_api_key"] == "(set)"
    stored = db_session.query(AgentRun).order_by(AgentRun.id.desc()).first()
    assert secret not in json.dumps(stored.config_snapshot)
    assert secret not in client.get("/api/discovery/runs").text

    removed = client.patch("/api/discovery/auto", json={"ticketmasterApiKey": ""}).json()
    assert removed["ticketmasterApiKeySet"] is False


def test_queued_reads_take_turns_across_sources(db_session, monkeypatch):
    from backend.services.discovery_agent.types import RunSummary

    monkeypatch.setattr(orchestrator, "_select_adapter_ids", lambda requested, countries=None: ["dev_events"])
    run = AgentRun(agent_type="discovery", status="running", config_snapshot={}, summary={})
    db_session.add(run)
    db_session.commit()
    cfg = _run_config(cities=["Pune", "Mumbai", "Delhi"], sources=["global_adapters", "dev_events", "consumer_aggregators", "eventbrite", "meetup"],
                      listing_urls=["https://www.eventbrite.com/d/{country}--{city}/events/", "https://www.meetup.com/find/?location={city}"])
    pipe = orchestrator._DiscoveryPipeline(db_session, run, cfg, RunSummary(), ["Construction"], 0)
    pipe.plan()
    first_three = [origin for _, origin, _ in list(pipe.source_jobs)[:3]]
    assert sorted(first_three) == ["dev_events", "eventbrite", "meetup"]  # one each before any repeats
