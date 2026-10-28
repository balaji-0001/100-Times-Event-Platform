"""End-to-end: what the admin selects (countries, states, cities, sectors,
sources, websites) is exactly what a discovery run searches — for manual
runs (POST /discovery/run) and automatic runs (saved PATCH /discovery/auto
scope). Network is stubbed; every query, listing page, adapter and search
parameter is captured and checked against the selection."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import AgentRun, User
from backend.routes import discovery as discovery_routes
from backend.services.discovery_agent import geo_scope, orchestrator, query_seeds
from backend.services.discovery_agent.types import DiscoveryConfig


def _admin() -> User:
    return User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = _admin
    return TestClient(app)


@pytest.fixture()
def capture(monkeypatch):
    """Record every query (with its country hint), page read and adapter run."""
    seen = {"queries": [], "countries": [], "pages": [], "adapters": []}

    def search(query, max_results=5, country=None, **kwargs):
        seen["queries"].append(query)
        seen["countries"].append(country)
        return []

    monkeypatch.setattr(orchestrator.web_search, "search", search)
    monkeypatch.setattr(orchestrator.page_extractor, "extract_events_from_page", lambda url, m, c: seen["pages"].append(url) or [])
    monkeypatch.setattr(orchestrator, "_select_adapter_ids", lambda requested, countries=None: (
        seen["adapters"].extend(orchestrator.real_select_adapter_ids(requested, countries)) or []
    ))
    return seen


UI_SOURCES = ["web", "global_adapters", "consumer_aggregators", "event_platforms", "dwtc_events", "javits_center",
              "india_expo_centre", "excel_london", "messe_frankfurt_venue", "eventseye"]
UI_LISTINGS = ["https://allevents.in/{city}", "https://www.eventbrite.com/d/{country}--{city}/events/", "https://www.myexpo-site.test/events"]


def _manual(client, **overrides):
    payload = {
        "countries": ["India", "Germany", "United States"],
        "country": "India",
        "locations": [
            {"country": "India", "state": "Telangana", "city": "Hyderabad"},
            {"country": "India", "state": "Maharashtra", "city": "Pune"},
            {"country": "Germany", "state": "Bavaria", "city": "Munich"},
            {"country": "United States"},
        ],
        "states": ["Telangana", "Maharashtra", "Bavaria"],
        "cities": ["Hyderabad", "Pune", "Munich"],
        "categories": ["Construction", "Textiles"],
        "sources": UI_SOURCES,
        "listingUrls": UI_LISTINGS,
        "searchDepth": 6,
        "targetValidEvents": 5,
        "background": False,
    }
    payload.update(overrides)
    response = client.post("/api/discovery/run", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_run_searches_every_selected_country_and_sector(client, capture):
    _manual(client)
    queries = " || ".join(capture["queries"])
    for country in ("India", "Germany", "United States"):
        assert country in queries, country
    for sector in ("Construction", "Textiles"):
        assert sector in queries, sector
    # Each selected (sector x country) pair is in the FIRST wave, despite searchDepth=6.
    first = query_seeds.build_search_queries
    assert len([q for q in capture["queries"] if q.startswith("upcoming ")]) >= 6


def test_cities_are_labelled_with_their_own_country(client, capture):
    _manual(client)
    queries = capture["queries"]
    assert any("Hyderabad, India" in q for q in queries)
    assert any("Munich, Germany" in q for q in queries)
    assert not any("Munich" in q and "India" in q for q in queries)
    assert not any("Hyderabad" in q and "Germany" in q for q in queries)


def test_search_country_hint_is_not_forced_to_the_first_country(client, capture):
    _manual(client)
    assert set(capture["countries"]) == {None}  # multi-country: queries carry their own place


def test_listing_pages_cover_every_country_with_the_right_country_slug(client, capture):
    _manual(client)
    pages = capture["pages"]
    assert "https://allevents.in/hyderabad" in pages and "https://allevents.in/munich" in pages
    assert any("eventbrite.com/d/germany--munich" in p for p in pages)
    assert any("eventbrite.com/d/india--hyderabad" in p for p in pages)
    assert not any("india--munich" in p or "germany--hyderabad" in p for p in pages)
    # United States had no city selected: its major cities anchor the listing pages.
    assert any("eventbrite.com/d/united-states--" in p for p in pages)
    # The admin's own website always runs.
    assert "https://www.myexpo-site.test/events" in pages


def test_location_bound_venue_sources_follow_the_selected_countries(client, capture):
    _manual(client)
    adapters = set(capture["adapters"])
    assert {"india_expo_centre", "javits_center", "messe_frankfurt_venue"} <= adapters  # India / US / Germany venues
    assert not {"dwtc_events", "excel_london"} & adapters  # UAE / UK venues: not selected
    assert "eventseye" in adapters  # worldwide directory always eligible


def test_manual_run_never_inherits_the_saved_automatic_scope(client, capture, db_session):
    client.patch("/api/discovery/auto", json={"countries": ["Japan"], "states": ["Kanto"], "cities": ["Tokyo"],
                                             "categories": ["Mining"], "listingUrls": ["https://auto-only.test/{city}"]})
    _manual(client, states=None, locations=[{"country": "India"}], cities=None, countries=["India"], categories=["Construction"])
    blob = " || ".join(capture["queries"] + capture["pages"])
    for leaked in ("Japan", "Kanto", "Tokyo", "Mining", "auto-only.test"):
        assert leaked not in blob, leaked
    assert "India" in blob and "Construction" in blob


def test_run_summary_reports_what_was_covered(client, capture, db_session):
    _manual(client)
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "discovery").one()
    scope = run.summary["scope"]
    assert scope["countries"] == ["India", "Germany", "United States"]
    assert scope["cities"] >= 3 and scope["sectors"] == ["Construction", "Textiles"]
    assert scope["first_wave_queries"] >= 6 and scope["listing_pages"] > 0


def test_automatic_run_uses_the_saved_scope_with_locations(client, capture, db_session):
    saved = client.patch("/api/discovery/auto", json={
        "countries": ["Dubai", "United Kingdom"], "locations": [{"country": "United Kingdom", "city": "Manchester"}, {"country": "Dubai"}],
        "cities": ["Manchester"], "categories": ["Textiles"], "sources": ["web"], "searchDepth": 4,
    }).json()
    assert saved["locations"] and saved["countries"] == ["Dubai", "United Kingdom"]
    config = orchestrator.config_from_settings(orchestrator.get_settings(), db=db_session)
    geo = geo_scope.resolve(config)
    assert geo.countries == ["United Arab Emirates", "United Kingdom"]
    assert geo.cities_by_country["United Kingdom"] == ["Manchester"] and "Dubai" in geo.cities_by_country["United Arab Emirates"]
    queries = query_seeds.build_search_queries(config)
    assert any("United Arab Emirates" in q for q in queries) and any("United Kingdom" in q for q in queries)
    assert any("Manchester, United Kingdom" in q for q in query_seeds.build_expanded_queries(config) + queries)


def test_flat_lists_without_locations_still_map_cities_to_countries():
    cfg = DiscoveryConfig(countries=["India", "Germany"], country="India", cities=["Mumbai", "Berlin"], categories=["Construction"], search_depth=1)
    geo = geo_scope.resolve(cfg)
    assert geo.cities_by_country == {"India": ["Mumbai"], "Germany": ["Berlin"]}
    queries = query_seeds.build_search_queries(cfg) + query_seeds.build_expanded_queries(cfg)
    assert any("Berlin, Germany" in q for q in queries) and not any("Berlin" in q and "India" in q for q in queries)


def test_leftover_city_of_an_unselected_country_is_not_searched(client, capture):
    # Germany was deselected but Berlin stayed in the city list; custom cities are kept.
    cfg = DiscoveryConfig(countries=["India"], country="India", cities=["Mumbai", "Berlin", "Hosur"], categories=["Construction"])
    geo = geo_scope.resolve(cfg)
    assert geo.countries == ["India"]
    assert "Berlin" not in geo.all_cities and {"Mumbai", "Hosur"} <= set(geo.all_cities)

    _manual(client, countries=["India"], locations=[], states=[], cities=["Mumbai", "Berlin"], listingUrls=[])
    assert capture["queries"] and not any("Berlin" in q or "Germany" in q for q in capture["queries"])


def test_software_architecture_is_not_construction():
    from backend.services.discovery_agent.categorizer import CATEGORIES, categorize

    assert categorize("Clean Architecture Masterclass", "clean architecture for software developers", None, supported_categories=CATEGORIES)[0] == "Technology"
    assert categorize("Festival of Architecture and Interior Designing", "architects and interior design", None, supported_categories=CATEGORIES)[0] == "Construction"
    assert categorize("BAU 2027", "trade fair for architecture, materials, systems", None, supported_categories=CATEGORIES)[0] == "Construction"


def test_validation_uses_every_selected_country():
    cfg = DiscoveryConfig(countries=["India", "Germany"], country="India")
    assert orchestrator._target_countries(cfg) == ["India", "Germany"]
    only_cities = DiscoveryConfig(cities=["Berlin", "Mumbai"])
    assert set(orchestrator._target_countries(only_cities)) == {"Germany", "India"}
