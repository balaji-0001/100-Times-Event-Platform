"""Comprehensive tests for worldwide event discovery, country-level filtering,
query seed generation, and directory APIs.
"""

from datetime import date, timedelta
from decimal import Decimal
import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import get_db
from backend.models import Category, City, Event, Organizer, Venue
from backend.schemas import DiscoveryRunRequest
from backend.services.discovery_agent.country_utils import (
    ALL_WORLD_COUNTRIES,
    infer_country,
    normalize_country,
)
from backend.services.discovery_agent.page_extractor import _event_from_node
from backend.services.discovery_agent.query_seeds import build_search_queries
from backend.services.discovery_agent.text_extractor import extract_best_effort
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig


def test_country_utils_normalization_and_inference():
    """Verifies country code normalization, alias mapping, and city/TLD inference."""
    assert len(ALL_WORLD_COUNTRIES) >= 190
    assert "United States" in ALL_WORLD_COUNTRIES
    assert "United Kingdom" in ALL_WORLD_COUNTRIES
    assert "Germany" in ALL_WORLD_COUNTRIES
    assert "Japan" in ALL_WORLD_COUNTRIES
    assert "India" in ALL_WORLD_COUNTRIES

    # Normalization & aliases
    assert normalize_country("US") == "United States"
    assert normalize_country("usa") == "United States"
    assert normalize_country("UK") == "United Kingdom"
    assert normalize_country("DE") == "Germany"
    assert normalize_country("deutschland") == "Germany"
    assert normalize_country("IN") == "India"
    assert normalize_country("All Countries") is None
    assert normalize_country("all") is None

    # Inference from city
    assert infer_country(city="London") == "United Kingdom"
    assert infer_country(city="Berlin") == "Germany"
    assert infer_country(city="Tokyo") == "Japan"
    assert infer_country(city="San Francisco") == "United States"
    assert infer_country(city="Toronto") == "Canada"
    assert infer_country(city="Singapore") == "Singapore"
    assert infer_country(city="Bengaluru") == "India"

    # Inference from URL TLD
    assert infer_country(url="https://events.co.uk/conference") == "United Kingdom"
    assert infer_country(url="https://symposium.de/2026") == "Germany"
    assert infer_country(url="https://techsummit.jp/agenda") == "Japan"


def test_worldwide_search_query_generation():
    """Verifies search queries cover target country or worldwide scope."""
    # Country-specific discovery
    de_config = DiscoveryConfig(
        cities=["Berlin", "Munich"],
        states=["Bavaria"],
        categories=["Technology", "Finance"],
        country="Germany",
        search_depth=8,
    )
    de_queries = build_search_queries(de_config)
    assert len(de_queries) == 8
    assert any("Germany" in q for q in de_queries)
    assert any("Berlin" in q for q in de_queries)

    # Worldwide discovery across all countries
    global_config = DiscoveryConfig(
        cities=["New York", "London", "Tokyo"],
        states=["California", "England"],
        categories=["Pharmaceuticals", "Energy and Power Generation"],
        countries=["United States", "United Kingdom", "Japan"],
        country="all",
        search_depth=12,
    )
    global_queries = build_search_queries(global_config)
    assert len(global_queries) == 12
    # Verify deterministic output
    assert global_queries == build_search_queries(global_config)
    # Check worldwide or multi-country coverage
    assert any("New York" in q or "London" in q or "worldwide" in q or "international" in q for q in global_queries)


def test_page_extractor_country_extraction():
    """Verifies schema.org JSON-LD country extraction and fallback resolution."""
    source_us = CandidateSource(url="https://example.com/events/ny-summit", source_type="listing")
    node_us = {
        "name": "Global Tech Summit NYC",
        "startDate": "2026-11-20T09:00:00Z",
        "location": {
            "name": "Javits Center",
            "address": {
                "addressLocality": "New York",
                "addressRegion": "NY",
                "addressCountry": "US",
            },
        },
    }
    extracted_us = _event_from_node(source_us, node_us)
    assert extracted_us.country == "United States"
    assert extracted_us.city == "New York"

    source_fr = CandidateSource(url="https://events.fr/paris-expo", source_type="listing")
    node_fr = {
        "name": "Paris Health & Biotech Expo",
        "startDate": "2026-10-15T09:00:00Z",
        "location": {
            "name": "Paris Expo Porte de Versailles",
            "address": {
                "addressLocality": "Paris",
                "addressCountry": {"@type": "Country", "name": "France"},
            },
        },
    }
    extracted_fr = _event_from_node(source_fr, node_fr)
    assert extracted_fr.country == "France"
    assert extracted_fr.city == "Paris"


def test_text_extractor_worldwide_city_and_country():
    """Verifies best-effort text extraction resolves worldwide cities and countries."""
    source = CandidateSource(url="https://conferences.de/annual-ai-symposium", source_type="search")
    html = """
    <html>
      <head><title>Annual European AI Symposium 2026 - Berlin</title></head>
      <body>
        <h1>Annual European AI Symposium 2026</h1>
        <p>Join us on 15th December 2026 for groundbreaking talks.</p>
        <p>Venue: Berlin Congress Center</p>
      </body>
    </html>
    """
    extracted = extract_best_effort(source, html, cities=["Berlin", "Frankfurt", "Munich"], today=date(2026, 1, 1))
    assert extracted is not None
    assert "Annual European AI Symposium" in extracted.name
    assert extracted.city == "Berlin"
    assert extracted.country == "Germany"


def test_list_events_filtered_by_country(db_session):
    """Verifies GET /api/events filters by country and supports worldwide pagination."""
    category = Category(name="Technology", slug="tech", description="Tech", icon="laptop")
    organizer = Organizer(name="Global Summit Org", slug="global-summit-org", description="Global events")
    db_session.add_all([category, organizer])
    db_session.flush()

    # Seed 3 events in different countries
    us_event = Event(
        title="Silicon Valley AI Summit",
        slug="silicon-valley-ai-summit",
        description="US AI event",
        event_type="Summit",
        start_date=date.today() + timedelta(days=20),
        end_date=date.today() + timedelta(days=22),
        start_time="09:00 AM",
        country_name="United States",
        city_name="San Francisco",
        status="published",
        format="in-person",
        category_id=category.id,
        organizer_id=organizer.id,
    )
    uk_event = Event(
        title="London FinTech Week",
        slug="london-fintech-week",
        description="UK FinTech event",
        event_type="Conference",
        start_date=date.today() + timedelta(days=30),
        end_date=date.today() + timedelta(days=32),
        start_time="10:00 AM",
        country_name="United Kingdom",
        city_name="London",
        status="published",
        format="in-person",
        category_id=category.id,
        organizer_id=organizer.id,
    )
    in_event = Event(
        title="Bengaluru Tech Summit",
        slug="bengaluru-tech-summit",
        description="India Tech event",
        event_type="Exhibition",
        start_date=date.today() + timedelta(days=40),
        end_date=date.today() + timedelta(days=42),
        start_time="09:30 AM",
        country_name="India",
        city_name="Bengaluru",
        status="published",
        format="in-person",
        category_id=category.id,
        organizer_id=organizer.id,
    )
    dubai_event = Event(
        title="Dubai Web3 & AI Conclave",
        slug="dubai-web3-ai-conclave",
        description="Dubai Web3 event",
        event_type="Summit",
        start_date=date.today() + timedelta(days=50),
        end_date=date.today() + timedelta(days=52),
        start_time="09:00 AM",
        country_name="United Arab Emirates",
        city_name="Dubai",
        status="published",
        format="in-person",
        category_id=category.id,
        organizer_id=organizer.id,
    )
    db_session.add_all([us_event, uk_event, in_event, dubai_event])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    try:
        # Filter for United States
        res_us = client.get("/api/events?country=United States")
        assert res_us.status_code == 200
        data_us = res_us.json()
        assert data_us["total"] == 1
        assert data_us["items"][0]["title"] == "Silicon Valley AI Summit"

        # Filter for United Kingdom (also test alias 'UK')
        res_uk = client.get("/api/events?country=UK")
        assert res_uk.status_code == 200
        data_uk = res_uk.json()
        assert data_uk["total"] == 1
        assert data_uk["items"][0]["title"] == "London FinTech Week"

        # Filter for India
        res_in = client.get("/api/events?country=India")
        assert res_in.status_code == 200
        data_in = res_in.json()
        assert data_in["total"] == 1
        assert data_in["items"][0]["title"] == "Bengaluru Tech Summit"

        # Filter for Dubai
        res_dxb = client.get("/api/events?country=Dubai")
        assert res_dxb.status_code == 200
        data_dxb = res_dxb.json()
        assert data_dxb["total"] == 1
        assert data_dxb["items"][0]["title"] == "Dubai Web3 & AI Conclave"

        # Filter for United Arab Emirates (cross-matches Dubai)
        res_uae = client.get("/api/events?country=United Arab Emirates")
        assert res_uae.status_code == 200
        data_uae = res_uae.json()
        assert data_uae["total"] == 1
        assert data_uae["items"][0]["title"] == "Dubai Web3 & AI Conclave"

        # All Countries / Worldwide (no country filter)
        res_all = client.get("/api/events?country=all")
        assert res_all.status_code == 200
        data_all = res_all.json()
        assert data_all["total"] == 4

        # Test pagination
        res_page = client.get("/api/events?pageSize=2&page=1")
        assert res_page.status_code == 200
        data_page = res_page.json()
        assert len(data_page["items"]) == 2
        assert data_page["total"] == 4
        assert data_page["totalPages"] == 2
        assert data_page["page"] == 1

    finally:
        app.dependency_overrides.pop(get_db, None)


def test_directories_countries_endpoint(db_session):
    """Verifies GET /api/countries returns comprehensive country list with counts."""
    category = Category(name="General", slug="general", description="Gen", icon="globe")
    organizer = Organizer(name="Host Org", slug="host-org", description="Desc")
    db_session.add_all([category, organizer])
    db_session.flush()

    event = Event(
        title="German Automotive Expo",
        slug="german-automotive-expo",
        description="Automotive in Germany",
        event_type="Expo",
        start_date=date.today() + timedelta(days=15),
        end_date=date.today() + timedelta(days=17),
        start_time="09:00 AM",
        country_name="Germany",
        status="published",
        format="in-person",
        category_id=category.id,
        organizer_id=organizer.id,
    )
    db_session.add(event)
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    try:
        res = client.get("/api/countries")
        assert res.status_code == 200
        countries = res.json()
        assert len(countries) >= 190
        # Check Germany has eventCount >= 1
        germany = next((c for c in countries if c["name"] == "Germany"), None)
        assert germany is not None
        assert germany["eventCount"] == 1
        # Check an empty country has eventCount 0
        japan = next((c for c in countries if c["name"] == "Japan"), None)
        assert japan is not None
        assert japan["eventCount"] == 0

        # Check Dubai is present in world countries list
        dubai = next((c for c in countries if c["name"] == "Dubai"), None)
        assert dubai is not None
    finally:
        app.dependency_overrides.pop(get_db, None)

