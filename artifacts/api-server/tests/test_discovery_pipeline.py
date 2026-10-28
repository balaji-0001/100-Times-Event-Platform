"""Concurrent discovery pipeline: parallel work, adaptive stopping on
VERIFIED events only, cheap filtering before organizer lookups, time budget,
page caching, dedup-index parity and honest run metrics. Network is fully
stubbed; latencies are simulated with sleeps."""

import threading
import time
from datetime import date, timedelta

from backend.models import AgentExecutionMetric, AgentRun, DiscoveredEvent, DiscoveredOrganizer
from backend.services.discovery_agent import discovery_dedup, orchestrator, query_seeds
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate, OrganizerCandidate
from backend.services.social_agent import web_fetch

FUTURE = (date.today() + timedelta(days=60)).isoformat()
PAST = (date.today() - timedelta(days=10)).isoformat()


def _candidate(i: int, *, country="India", city="Pune", when=FUTURE, best_effort=False) -> ExtractedEventCandidate:
    source = CandidateSource(url=f"https://events.test/e/{i}", source_type="event_listing", source_website="events.test")
    return ExtractedEventCandidate(
        name=f"Construction & Building Materials Expo {i}",
        event_description="Annual construction and infrastructure exhibition for builders.",
        date=when,
        venue="Expo Centre",
        city=city,
        country=country,
        url=source.url,
        extraction_confidence=90,
        primary_source=source,
        sources=[source],
        best_effort=best_effort,
    )


def _organizer(candidate) -> OrganizerCandidate:
    return OrganizerCandidate(
        found=True, name=f"Organizer of {candidate.name}", email=f"info{abs(hash(candidate.url)) % 10_000}@expo-org.com",
        website="https://expo-org.com", confidence_score=70, sources=[candidate.primary_source],
    )


def _config(**overrides) -> DiscoveryConfig:
    values = dict(
        cities=["Pune"], categories=["Construction"], countries=["India"], country="India",
        sources=["web"], search_depth=6, sources_per_query=2, listing_urls=[], daily_limit=500,
        confidence_threshold=60, require_organizer_email=True, reject_no_organizer=True,
        reject_unmatched_category=True, fallback_to_other_sector=False, min_confidence_score=0,
        target_valid_events=None, max_parallel_searches=4, max_parallel_fetches=8, max_parallel_organizer_lookups=8,
    )
    values.update(overrides)
    return DiscoveryConfig(**values)


def _wire(monkeypatch, pages: dict[str, list], *, page_delay=0.0, org_delay=0.0, search_delay=0.0, org_calls=None, queries=None):
    """Every query returns its own result page; each page yields the listed candidates."""
    urls = list(pages)
    lock = threading.Lock()  # searches run concurrently: append + index must be atomic

    def search(query, max_results=5, **kwargs):
        time.sleep(search_delay)
        with lock:
            if queries is not None:
                queries.append(query)
            index = len(queries) - 1 if queries is not None else 0
        return [urls[index % len(urls)]] if urls else []

    def extract(url, max_events, cities):
        time.sleep(page_delay)
        return list(pages.get(url, []))

    def identify(candidate):
        time.sleep(org_delay)
        if org_calls is not None:
            org_calls.append(candidate.url)
        return _organizer(candidate)

    monkeypatch.setattr(orchestrator.web_search, "search", search)
    monkeypatch.setattr(orchestrator.page_extractor, "extract_events_from_page", extract)
    monkeypatch.setattr(orchestrator.organizer_identifier, "identify_organizer", identify)
    monkeypatch.setattr(orchestrator.query_seeds, "build_expanded_queries", lambda config: [])


def _off_sector(i: int, name: str) -> ExtractedEventCandidate:
    candidate = _candidate(i)
    candidate.name, candidate.event_description = name, "An evening out in the city."
    return candidate


def test_selected_sectors_are_a_hard_filter_even_with_the_other_fallback_on(db_session, monkeypatch):
    # Run 143/144: Construction selected, but "Add unmatched events to 'Other'"
    # (copied from the Automatic settings) let concerts and trips through as VERIFIED.
    page = [_off_sector(1, "Music Performance by ADIGA"), _off_sector(2, "Georgia Country Trip"), _candidate(3)]
    _wire(monkeypatch, {"https://results.test/0": page}, queries=[])

    summary = orchestrator.run_discovery_agent(
        db_session, _config(fallback_to_other_sector=True, reject_unmatched_category=False, target_valid_events=2)
    )

    assert [e.category for e in db_session.query(DiscoveredEvent).all()] == ["Construction"]
    assert summary.verified_events == 1 and summary.unsupported_category == 2


def test_other_fallback_still_applies_when_no_sector_is_selected(db_session, monkeypatch):
    _wire(monkeypatch, {"https://results.test/0": [_off_sector(1, "Music Performance by ADIGA")]}, queries=[])

    orchestrator.run_discovery_agent(db_session, _config(categories=[], fallback_to_other_sector=True, reject_unmatched_category=False))

    assert [e.category for e in db_session.query(DiscoveredEvent).all()] == ["Other"]


def test_network_stages_run_concurrently(db_session, monkeypatch):
    pages = {f"https://results.test/{p}": [_candidate(p * 10 + k) for k in range(2)] for p in range(6)}
    queries: list[str] = []
    _wire(monkeypatch, pages, page_delay=0.4, org_delay=0.4, search_delay=0.2, queries=queries)

    start = time.perf_counter()
    summary = orchestrator.run_discovery_agent(db_session, _config(search_depth=6))
    elapsed = time.perf_counter() - start

    assert summary.verified_events == 12
    # Sequentially: 6 searches*0.2 + 6 pages*0.4 + 12 lookups*0.4 = 8.4s.
    assert elapsed < 4.0, elapsed
    assert summary.timings["cumulative_worker_ms"]["organizer_ms"] >= 12 * 400 * 0.9
    assert summary.stop_reason == "sources_exhausted"


def test_stops_as_soon_as_target_verified_events_are_stored(db_session, monkeypatch):
    pages = {f"https://results.test/{p}": [_candidate(p * 10 + k) for k in range(5)] for p in range(6)}
    org_calls: list[str] = []
    _wire(monkeypatch, pages, org_delay=0.05, org_calls=org_calls, queries=[])

    summary = orchestrator.run_discovery_agent(db_session, _config(target_valid_events=3, max_parallel_organizer_lookups=2))

    assert summary.verified_events == 3
    assert db_session.query(DiscoveredEvent).filter_by(verification_status="VERIFIED").count() == 3
    assert summary.stop_reason == "target_reached" and summary.target_shortfall == 0
    assert len(org_calls) < 30  # did not verify the whole backlog
    assert summary.timings["target_reached_ms"] >= summary.timings["first_verified_ms"]


def test_needs_review_never_counts_toward_the_target(db_session, monkeypatch):
    pages = {"https://results.test/a": [_candidate(i, best_effort=True) for i in range(4)]}
    _wire(monkeypatch, pages, queries=[])

    summary = orchestrator.run_discovery_agent(db_session, _config(target_valid_events=2, search_depth=1))

    assert summary.verified_events == 0
    assert summary.events_needing_review == 4  # stored, but not counted as valid
    assert summary.stop_reason == "sources_exhausted" and summary.target_shortfall == 2
    run = db_session.query(AgentRun).one()
    assert "Found 0 of 2 requested verified events" in run.error


def test_cheap_rules_reject_before_any_organizer_lookup(db_session, monkeypatch):
    good = _candidate(1)
    past = _candidate(2, when=PAST)
    abroad = _candidate(3, country="Germany", city="Berlin")
    pages = {"https://results.test/a": [good, past, abroad]}
    org_calls: list[str] = []
    _wire(monkeypatch, pages, org_calls=org_calls, queries=[])

    summary = orchestrator.run_discovery_agent(db_session, _config(search_depth=1))

    assert org_calls == [good.url]
    assert summary.verified_events == 1 and summary.out_of_target_country == 1
    stored = {e.name: e for e in db_session.query(DiscoveredEvent).all()}
    assert "REJECTION_REASON: OUT_OF_TARGET_COUNTRY" in stored[abroad.name].verification_notes
    assert "REJECTION_REASON: PAST_OR_EXPIRED" in stored[past.name].verification_notes


def test_unknown_country_is_held_for_review_not_verified(db_session, monkeypatch):
    pages = {"https://results.test/a": [_candidate(1, country="Worldwide", city=None)]}
    _wire(monkeypatch, pages, queries=[])

    summary = orchestrator.run_discovery_agent(db_session, _config(search_depth=1))

    assert summary.verified_events == 0 and summary.events_needing_review == 1


def test_duplicate_candidates_skip_the_organizer_lookup(db_session, monkeypatch):
    same = _candidate(7)
    pages = {"https://results.test/a": [same], "https://results.test/b": [_candidate(7)]}
    org_calls: list[str] = []
    _wire(monkeypatch, pages, org_calls=org_calls, queries=[])

    summary = orchestrator.run_discovery_agent(db_session, _config(search_depth=2, max_parallel_fetches=1, max_parallel_organizer_lookups=1))

    assert summary.verified_events == 1 and summary.duplicate_events == 1
    assert len(org_calls) <= 2  # never more lookups than distinct candidates seen before the first was stored
    assert db_session.query(DiscoveredEvent).count() == 1


def test_time_budget_stops_the_run_and_reports_shortfall(db_session, monkeypatch):
    pages = {f"https://results.test/{p}": [_candidate(p)] for p in range(40)}
    _wire(monkeypatch, pages, org_delay=3.0, queries=[])
    monkeypatch.setattr(orchestrator.query_seeds, "build_search_queries", lambda config: [f"q{i}" for i in range(40)])

    # 40 lookups x 3s over 8 workers would take 15s; the 10s budget cuts it short.
    start = time.perf_counter()
    summary = orchestrator.run_discovery_agent(db_session, _config(target_valid_events=40, search_depth=40, max_run_seconds=10))
    elapsed = time.perf_counter() - start

    assert summary.stop_reason == "time_budget"
    assert elapsed < 14
    assert summary.target_shortfall == 40 - summary.verified_events > 0
    assert "time budget" in db_session.query(AgentRun).one().error


def test_stale_and_repeated_result_urls_are_not_fetched(db_session, monkeypatch):
    fetched: list[str] = []
    results = ["https://expo.test/2019/edition", "https://expo.test/live#top", "https://expo.test/live"]
    monkeypatch.setattr(orchestrator.web_search, "search", lambda query, max_results=5, **kw: results)
    monkeypatch.setattr(orchestrator.page_extractor, "extract_events_from_page", lambda url, m, c: fetched.append(url) or [])
    monkeypatch.setattr(orchestrator.query_seeds, "build_expanded_queries", lambda config: [])

    summary = orchestrator.run_discovery_agent(db_session, _config(search_depth=2))

    assert fetched == ["https://expo.test/live"]
    assert summary.timings["result_urls_skipped"] >= 4


def test_expanded_queries_only_run_when_the_first_wave_falls_short(db_session, monkeypatch):
    pages = {"https://results.test/a": [_candidate(i) for i in range(3)]}
    queries: list[str] = []
    _wire(monkeypatch, pages, queries=queries)
    monkeypatch.setattr(orchestrator.query_seeds, "build_search_queries", lambda config: ["first wave"])
    monkeypatch.setattr(orchestrator.query_seeds, "build_expanded_queries", lambda config: ["expanded"])

    orchestrator.run_discovery_agent(db_session, _config(target_valid_events=2))
    assert queries == ["first wave"]

    queries.clear()
    orchestrator.run_discovery_agent(db_session, _config(target_valid_events=50))
    assert queries == ["first wave", "expanded"]


def test_blocked_search_with_queued_queries_ends_the_run(db_session, monkeypatch):
    calls: list[str] = []

    def blocked(query, max_results=5, **kwargs):
        calls.append(query)
        raise orchestrator.web_search.SearchBlocked("captcha")

    monkeypatch.setattr(orchestrator.web_search, "search", blocked)
    monkeypatch.setattr(orchestrator.query_seeds, "build_search_queries", lambda config: ["q1", "q2", "q3", "q4"])
    monkeypatch.setattr(orchestrator.query_seeds, "build_expanded_queries", lambda config: ["q5"])

    start = time.perf_counter()
    summary = orchestrator.run_discovery_agent(db_session, _config(target_valid_events=5, max_parallel_searches=1))

    assert time.perf_counter() - start < 5
    assert calls == ["q1"]  # nothing else is searched once the engine blocks us
    assert summary.stop_reason == "sources_exhausted"
    assert "captcha" in db_session.query(AgentRun).one().error


# Exactly what DiscoverySourcesManager.tsx sends for each Discovery Strategy toggle.
UI_WEB = ["web", "google_search", "bing_search", "linkedin_search"]
UI_DIRECTORIES = ["global_adapters", "dev_events", "wikicfp", "eventseye", "clocate", "tradeshowradar", "tradefairdates",
                  "conference_alerts", "rx_global", "informa_markets", "terrapinn",
                  "messe_frankfurt_org", "dmg_events", "dwtc_org", "gtr_events", "ieee_events", "acm", "dwtc_events",
                  "excel_london", "javits_center", "mccormick_place", "messe_frankfurt_venue", "india_expo_centre", "us_ita",
                  "indian_trade_portal"]
UI_AGGREGATORS = ["consumer_aggregators", "event_platforms", "eventbrite", "meetup", "allevents", "skillboxes"]
AGGREGATOR_ADAPTERS = {"eventbrite", "meetup", "allevents", "skillboxes"}


def _plan(db_session, monkeypatch, sources):
    from backend.services.discovery_agent.types import RunSummary

    monkeypatch.setattr(orchestrator, "_select_adapter_ids", orchestrator.real_select_adapter_ids)
    run = AgentRun(agent_type="discovery", status="running", config_snapshot={}, summary={})
    db_session.add(run)
    db_session.commit()
    cfg = _config(sources=list(sources), cities=["Mumbai"], listing_urls=list(orchestrator.listing_sources.DEFAULT_LISTING_URLS))
    pipe = orchestrator._DiscoveryPipeline(db_session, run, cfg, RunSummary(), ["Construction"], 0)
    pipe.plan()
    adapters = {origin for kind, origin, _ in pipe.source_jobs if kind == "adapter"}
    listings = [url for kind, _, url in pipe.source_jobs if kind == "listing"]
    return adapters, listings, list(pipe.queries)


def test_web_search_toggle_runs_only_web_search(db_session, monkeypatch):
    adapters, listings, queries = _plan(db_session, monkeypatch, UI_WEB)
    assert adapters == set() and listings == [] and queries
    # search engines are never scheduled as duplicate "adapters"
    assert not {"google_search", "bing_search", "linkedin_search"} & adapters


def test_directories_toggle_runs_only_b2b_adapters(db_session, monkeypatch):
    adapters, listings, queries = _plan(db_session, monkeypatch, UI_DIRECTORIES)  # India-only run
    assert {"dev_events", "eventseye", "tradefairdates", "india_expo_centre"} <= adapters
    assert not {"dwtc_events", "excel_london", "javits_center"} & adapters  # venues in unselected countries
    assert not adapters & AGGREGATOR_ADAPTERS
    assert listings == [] and queries == []


def test_aggregators_toggle_runs_only_aggregators(db_session, monkeypatch):
    adapters, listings, queries = _plan(db_session, monkeypatch, UI_AGGREGATORS)
    # Aggregators run once, as their city listing pages — not again as adapters.
    assert adapters == set()
    assert {h for u in listings for h in ("allevents", "eventbrite", "meetup", "skillboxes") if h in u} == {"allevents", "eventbrite", "meetup", "skillboxes"}
    assert listings and all(any(h in u for h in ("allevents", "eventbrite", "meetup", "skillboxes")) for u in listings)
    assert not any("10times" in u for u in listings)  # 10Times refuses automated requests (403) — removed
    assert queries == []


def test_aggregator_listing_sites_follow_the_toggle_but_custom_sites_always_run(db_session, monkeypatch):
    # .env's DISCOVERY_LISTING_URLS = built-in aggregator templates + dev.events
    from backend.services.discovery_agent.types import RunSummary

    monkeypatch.setattr(orchestrator, "_select_adapter_ids", orchestrator.real_select_adapter_ids)
    listing_urls = ["https://dev.events/", *orchestrator.listing_sources.DEFAULT_LISTING_URLS]
    run = AgentRun(agent_type="discovery", status="running", config_snapshot={}, summary={})
    db_session.add(run)
    db_session.commit()
    for sources, expect_aggregators in ((UI_WEB, False), (UI_DIRECTORIES, False), (UI_AGGREGATORS, True)):
        cfg = _config(sources=list(sources), cities=["Mumbai"], listing_urls=list(listing_urls))
        pipe = orchestrator._DiscoveryPipeline(db_session, run, cfg, RunSummary(), ["Construction"], 0)
        pipe.plan()
        listings = [url for kind, _, url in pipe.source_jobs if kind == "listing"]
        assert "https://dev.events/" in listings  # the admin's own site always runs
        has_aggregators = any(h in u for u in listings for h in ("allevents", "eventbrite", "meetup"))
        assert has_aggregators is expect_aggregators, sources[0]


def test_all_three_toggles_combine(db_session, monkeypatch):
    adapters, listings, queries = _plan(db_session, monkeypatch, UI_WEB + UI_DIRECTORIES + UI_AGGREGATORS)
    assert "eventseye" in adapters and not adapters & AGGREGATOR_ADAPTERS and listings and queries


def test_year_hint_is_current_not_hardcoded(monkeypatch):
    from datetime import datetime as real_datetime

    class FakeDatetime(real_datetime):
        current = real_datetime(2031, 3, 1)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(query_seeds, "datetime", FakeDatetime)
    assert query_seeds._year_hint() == "2031"
    FakeDatetime.current = real_datetime(2031, 11, 5)
    assert query_seeds._year_hint() == "2032"


def test_expanded_queries_stay_in_the_requested_countries():
    queries = query_seeds.build_expanded_queries(_config(countries=["Germany"], country="Germany", cities=["Berlin"]))
    joined = " ".join(queries)
    assert "Munich" in joined or "Frankfurt" in joined
    for indian_city in ("Mumbai", "Bengaluru", "Hyderabad", "Pune"):
        assert indian_city not in joined


def test_run_records_real_metric_without_invented_tokens(db_session, monkeypatch):
    _wire(monkeypatch, {"https://results.test/a": [_candidate(1)]}, queries=[])
    orchestrator.run_discovery_agent(db_session, _config(search_depth=1))
    metric = db_session.query(AgentExecutionMetric).one()
    assert metric.total_tokens == 0 and float(metric.estimated_cost) == 0
    assert metric.model_name == "none (rule-based)"


def test_search_circuit_breaker_stops_hammering_a_failing_provider(monkeypatch):
    from backend.services.discovery_agent.search_providers import search_engine
    from backend.services.discovery_agent.search_providers.web_fallback import WebFallbackProvider

    calls: list[str] = []

    def failing(self, query, **kwargs):
        calls.append(query)
        raise RuntimeError("timed out")

    monkeypatch.setattr(WebFallbackProvider, "search", failing)
    for i in range(12):
        assert search_engine.search(f"query {i}", max_results=3) == []
    assert len(calls) == search_engine._BREAKER_THRESHOLD  # later queries are skipped, not timed out
    assert search_engine.get_recent_logs(1)[0]["status"] == "SKIPPED_CIRCUIT_OPEN"

    # Failed queries were not cached as "no results": once the provider recovers they run again.
    search_engine.reset_breakers()
    monkeypatch.setattr(WebFallbackProvider, "search", lambda self, query, **kw: calls.append(query) or [])
    search_engine.search("query 0", max_results=3)
    assert calls[-1] == "query 0"


def _route(monkeypatch, *, free_results, paid_results=None, free_error=None, strategy="free_first"):
    """Configure SearXNG (free) + Exa (paid) only, with stubbed responses."""
    from backend.services.discovery_agent.search_providers import search_engine
    from backend.services.discovery_agent.search_providers.base import SearchProviderResult

    calls: list[str] = []
    providers = search_engine._providers
    for provider in providers.values():
        monkeypatch.setattr(type(provider), "is_configured", lambda self: self.provider_id in ("searxng", "exa_search"))

    def free(self, query, max_results=5, **kw):
        calls.append("searxng")
        if free_error:
            raise RuntimeError(free_error)
        return [SearchProviderResult(url=f"https://free.test/{i}") for i in range(free_results)][:max_results]

    def paid(self, query, max_results=5, **kw):
        calls.append("exa")
        return [SearchProviderResult(url=f"https://paid.test/{i}") for i in range(paid_results or 0)][:max_results]

    monkeypatch.setattr(type(providers["searxng"]), "search", free)
    monkeypatch.setattr(type(providers["exa_search"]), "search", paid)
    monkeypatch.setattr(search_engine._settings(), "search_strategy", strategy)
    return search_engine, calls


def test_free_first_skips_paid_provider_when_searxng_has_enough(monkeypatch):
    engine, calls = _route(monkeypatch, free_results=8, paid_results=5)
    urls = engine.search("textile expo", max_results=5, requested_sources={"web"})
    assert calls == ["searxng"] and len(urls) == 5 and all("free.test" in u for u in urls)


def test_free_first_tops_up_with_paid_provider_when_short_or_failing(monkeypatch):
    engine, calls = _route(monkeypatch, free_results=2, paid_results=5)
    urls = engine.search("textile expo short", max_results=5, requested_sources={"web"})
    assert calls == ["searxng", "exa"] and len(urls) == 5

    engine, calls = _route(monkeypatch, free_results=0, paid_results=3, free_error="SearXNG HTTP 502")
    urls = engine.search("textile expo failing", max_results=5, requested_sources={"web"})
    assert calls == ["searxng", "exa"] and urls == [f"https://paid.test/{i}" for i in range(3)]


def test_parallel_strategy_queries_every_provider(monkeypatch):
    engine, calls = _route(monkeypatch, free_results=8, paid_results=5, strategy="parallel")
    engine.search("textile expo parallel", max_results=5, requested_sources={"web"})
    assert sorted(calls) == ["exa", "searxng"]


def test_rejected_credentials_trip_the_breaker_immediately(monkeypatch):
    engine, calls = _route(monkeypatch, free_results=0, free_error="Google Custom Search API HTTP 403: PERMISSION_DENIED")
    engine.search("q1", max_results=5, requested_sources={"searxng"})
    engine.search("q2", max_results=5, requested_sources={"searxng"})
    assert calls == ["searxng"]  # second query skipped without a call


def test_searxng_provider_parses_json_and_reports_total_failure(monkeypatch):
    from types import SimpleNamespace

    import pytest

    from backend.services.discovery_agent.search_providers import searxng as searxng_mod

    payload = {"results": [
        {"url": "https://itma.com/", "title": "ITMA", "content": "Textile machinery", "engines": ["google", "brave"]},
        {"url": "https://itma.com/", "title": "dup"},
        {"url": "javascript:alert(1)"},
        {"url": "https://excon.in/", "title": "EXCON"},
    ]}
    seen = {}

    def fake_get(url, params, timeout):
        seen.update(url=url, params=params)
        return SimpleNamespace(status_code=200, json=lambda: payload, text="")

    monkeypatch.setattr(searxng_mod.httpx, "get", fake_get)
    results = searxng_mod.query_searxng("http://searx.test/", "textile machinery expo", max_results=5)
    assert [r.url for r in results] == ["https://itma.com/", "https://excon.in/"]
    assert seen["url"] == "http://searx.test/search" and seen["params"]["format"] == "json"
    assert "google" in results[0].source

    monkeypatch.setattr(searxng_mod.httpx, "get", lambda url, params, timeout: SimpleNamespace(
        status_code=200, json=lambda: {"results": [], "unresponsive_engines": [["google", "CAPTCHA"]]}, text=""))
    with pytest.raises(RuntimeError, match="unresponsive"):
        searxng_mod.query_searxng("http://searx.test", "x")


# ---------------------------------------------------------------------------
# Page cache
# ---------------------------------------------------------------------------


def test_page_cache_reuses_reads_and_never_retries_permanent_failures(monkeypatch):
    calls: list[str] = []
    page = "<html><script type='application/ld+json'>{\"@type\": \"Event\", \"name\": \"X\"}</script></html>"

    def http_get(url):
        calls.append(url)
        if url.endswith("/gone"):
            web_fetch._remember_failure(url)
            return None
        if url.endswith("/flaky"):
            return None  # transient: not remembered
        return page

    monkeypatch.setattr(web_fetch, "_http_get", http_get)
    monkeypatch.setattr(web_fetch, "_wait_for_host", lambda url, crawl_delay=None: 0.0)

    assert web_fetch.fetch("https://a.test/ok", render_js=True) == page
    assert web_fetch.fetch("https://a.test/ok", render_js=True) == page
    assert web_fetch.fetch("https://a.test/ok", render_js=False) == page  # other mode's copy is reused
    assert web_fetch.fetch("https://a.test/gone") is None
    assert web_fetch.fetch("https://a.test/gone") is None
    assert web_fetch.fetch("https://a.test/flaky") is None
    assert web_fetch.fetch("https://a.test/flaky") is None
    assert calls == ["https://a.test/ok", "https://a.test/gone", "https://a.test/flaky", "https://a.test/flaky"]


def test_page_scanning_stays_linear_on_huge_inline_blobs():
    """A 400 KB inline base64 image froze every discovery thread for minutes:
    the old email regex was quadratic and held the GIL the whole time."""
    page = "<html><body><img src='data:image/png;base64," + "A" * 400_000 + "'><a href='mailto:info@expo-org.com'>x</a></body></html>"
    start = time.perf_counter()
    assert [m.group(0) for m in web_fetch.EMAIL_RE.finditer(page)] == ["info@expo-org.com"]
    assert web_fetch.extract_contact(page)[2] == "info@expo-org.com"
    assert web_fetch.is_thin_page(page) is True  # no JSON-LD, little visible text
    assert time.perf_counter() - start < 2.0


def test_thin_page_check_matches_structured_data_and_text_rules():
    ld = '<script type="application/ld+json">{"@type": "Event", "name": "X"}</script>'
    assert web_fetch.is_thin_page("<html><head>" + ld + "</head><body>hi</body></html>") is False
    assert web_fetch.is_thin_page('<html><script type="application/ld+json">{broken</script><p>hi</p></html>') is True
    assert web_fetch.is_thin_page("<html><body>" + "<p>word</p>" * 200 + "</body></html>") is False
    assert web_fetch.is_thin_page("<html><div id=root></div><script>" + "z" * 9000 + "</script></html>") is True


def test_host_pacing_is_per_host_and_thread_safe(monkeypatch):
    web_fetch._last_request_at.clear()
    slept: list[float] = []
    lock = threading.Lock()

    def fake_sleep(seconds):
        with lock:
            slept.append(seconds)

    monkeypatch.setattr(web_fetch.time, "sleep", fake_sleep)
    threads = [threading.Thread(target=web_fetch._wait_for_host, args=("https://same.test/p",)) for _ in range(4)]
    threads += [threading.Thread(target=web_fetch._wait_for_host, args=(f"https://other{i}.test/p",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 4 requests to one host -> 3 waits of increasing length; other hosts never wait.
    assert len(slept) == 3
    assert max(slept) > 2 * web_fetch._MIN_SECONDS_BETWEEN_REQUESTS


# ---------------------------------------------------------------------------
# Dedup index parity
# ---------------------------------------------------------------------------


def test_dedup_index_matches_the_row_by_row_rules(db_session):
    org = DiscoveredOrganizer(name="Messe Group", email="info@messe.test", website="https://www.messe.test/about")
    db_session.add(org)
    db_session.flush()
    db_session.add_all([
        DiscoveredEvent(name="BAU Expo 2027", date="2027-01-10", city="Munich", url="https://bau.test", organizer_id=org.id),
        DiscoveredEvent(name="Textile Week", date="2027-03-01", city="Pune", url="https://tw.test", ticket_url="https://tickets.test/tw"),
    ])
    db_session.flush()
    index = discovery_dedup.DedupIndex(db_session)

    cases = [
        dict(name="x", url="https://bau.test"),
        dict(name="x", url="https://tickets.test/tw"),
        dict(name="BAU  expo 2027!", date="2027-01-10"),
        dict(name="BAU Expo 2027", city=" munich "),
        dict(name="BAU Expo 2027", organizer_name="messe group"),
        dict(name="BAU Expo 2027", city="Berlin", date="2027-02-02"),
        dict(name="Unknown"),
    ]
    for case in cases:
        slow = discovery_dedup.find_duplicate_event(db_session, **case)
        fast = discovery_dedup.find_duplicate_event(db_session, index=index, **case)
        assert (slow.id if slow else None) == (fast.id if fast else None), case

    for case in [dict(name="?", email="info@messe.test"), dict(name="?", website="http://messe.test"), dict(name="MESSE group"), dict(name="nobody")]:
        slow = discovery_dedup.find_duplicate_organizer(db_session, **case)
        fast = discovery_dedup.find_duplicate_organizer(db_session, index=index, **case)
        assert (slow.id if slow else None) == (fast.id if fast else None), case


def test_organizer_email_matching_ignores_case(db_session):
    org = DiscoveredOrganizer(name="Messe Group", email="Info@Messe.test")
    db_session.add(org)
    db_session.flush()
    index = discovery_dedup.DedupIndex(db_session)

    assert discovery_dedup.find_duplicate_organizer(db_session, name="x", email="info@messe.TEST").id == org.id
    assert discovery_dedup.find_duplicate_organizer(db_session, name="x", email="INFO@messe.test", index=index).id == org.id


def test_stage_progress_counters_match_what_the_pipeline_did(db_session, monkeypatch):
    """The run-progress view (Plan → Collect → Read pages → Screen → Find
    organizer → Decide & save) shows these counters — they must be the real
    numbers of what happened, persisted with the run."""
    good = _candidate(1)
    past = _candidate(2, when=PAST)
    abroad = _candidate(3, country="Germany", city="Berlin")
    pages = {"https://results.test/a": [good, past, abroad]}
    org_calls: list[str] = []
    queries: list[str] = []
    _wire(monkeypatch, pages, org_calls=org_calls, queries=queries)

    summary = orchestrator.run_discovery_agent(db_session, _config(search_depth=1))

    t = summary.timings
    assert t["planned_queries"] >= t["searches"] == len(queries) >= 1
    assert t["pages_read"] >= 1
    assert t["screened"] == 3  # every candidate went through screening
    assert t["passed_screening"] == 1 == len(org_calls) == t["organizer_lookups"]  # only the good one reached Find organizer
    assert summary.verified_events == 1 and summary.rejected_events == 2
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "discovery").one()
    assert run.summary["timings"]["screened"] == 3  # persisted for the UI


def test_automatic_discovery_uses_the_saved_configuration_and_the_same_pipeline(db_session, monkeypatch):
    """The scheduler's automatic run builds its config from the saved settings
    (the Discovery configuration page) and goes through run_discovery_agent —
    the same entry point and rules as a manual run."""
    import asyncio

    from backend.services.discovery_agent import auto_toggle
    from backend.services.social_agent import scheduler

    auto_toggle.set_discovery_auto_settings(db_session, {
        "countries": ["Germany"], "locations": [{"country": "Germany", "city": "Munich"}], "cities": ["Munich"],
        "categories": ["Construction"], "sources": ["web"], "require_organizer_email": True, "target_valid_events": 7,
    })
    auto_toggle.set_discovery_auto_enabled(db_session, True)
    db_session.commit()

    seen = []
    monkeypatch.setattr(scheduler, "is_discovery_auto_enabled", lambda db: True)
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    def fake_run(db, config=None, run=None):
        cfg = config or orchestrator.config_from_settings(orchestrator.get_settings(), db=db)
        seen.append(cfg)
        from backend.services.discovery_agent.types import RunSummary

        return RunSummary()

    monkeypatch.setattr(scheduler, "run_discovery_agent", fake_run)
    asyncio.run(scheduler._run_discovery_scan_tick())

    assert len(seen) == 1
    cfg = seen[0]
    assert cfg.countries == ["Germany"] and cfg.categories == ["Construction"]
    assert cfg.require_organizer_email is True and cfg.target_valid_events == 7
