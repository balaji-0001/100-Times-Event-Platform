from datetime import date
import pytest
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate, OrganizerCandidate
from backend.services.discovery_agent.query_seeds import build_search_queries
from backend.services.discovery_agent.validation import validate_event
from backend.services.discovery_agent.auto_toggle import (
    get_discovery_auto_settings,
    set_discovery_auto_settings,
    is_discovery_auto_enabled,
    set_discovery_auto_enabled,
)
from backend.services.discovery_agent.email_verifier import is_valid_organizer_email
from backend.services.discovery_agent.platforms import is_platform_url


def test_social_search_queries_generated():
    """Verify LinkedIn, Twitter/X, and Facebook public event queries are generated."""
    config = DiscoveryConfig(
        cities=["Mumbai"],
        states=["Maharashtra"],
        categories=["Healthcare"],
        country="India",
        search_depth=30,
    )
    queries = build_search_queries(config)
    
    assert any("linkedin.com/events" in q for q in queries)
    assert any("facebook.com/events" in q for q in queries)
    assert any("x.com" in q for q in queries)


def test_date_range_queries_and_validation():
    """Verify that specifying date_from and date_to influences queries and filters out-of-range dates.
    (Far-future dates: a fixed 2026 date became "past" and hit the past-event rule first.)"""
    config = DiscoveryConfig(
        cities=["Pune"],
        states=["Maharashtra"],
        categories=["Finance"],
        country="India",
        date_from="2099-11-01",
        date_to="2099-11-30",
        search_depth=10,
    )
    queries = build_search_queries(config)
    assert any("November 2099" in q for q in queries)

    # Event within date range -> VERIFIED
    ev_in_range = ExtractedEventCandidate(
        name="FinTech Conclave 2099",
        category="Finance",
        date="2099-11-15",
        extraction_confidence=80,
    )
    org = OrganizerCandidate(found=True, name="Finance Org", email="team@finconclave.org")
    res_in = validate_event(
        ev_in_range,
        60,
        organizer=org,
        supported_categories=["Finance"],
        date_from="2099-11-01",
        date_to="2099-11-30",
    )
    assert res_in.status == "VERIFIED"

    # Event before date_from -> REJECTED with OUT_OF_DATE_RANGE
    ev_early = ExtractedEventCandidate(
        name="FinTech Conclave 2099",
        category="Finance",
        date="2099-10-25",
        extraction_confidence=80,
    )
    res_early = validate_event(
        ev_early,
        60,
        organizer=org,
        supported_categories=["Finance"],
        date_from="2099-11-01",
        date_to="2099-11-30",
    )
    assert res_early.status == "REJECTED"
    assert res_early.rejection_reason == "OUT_OF_DATE_RANGE"

    # Event after date_to -> REJECTED with OUT_OF_DATE_RANGE
    ev_late = ExtractedEventCandidate(
        name="FinTech Conclave 2099",
        category="Finance",
        date="2099-12-15",
        extraction_confidence=80,
    )
    res_late = validate_event(
        ev_late,
        60,
        organizer=org,
        supported_categories=["Finance"],
        date_from="2099-11-01",
        date_to="2099-11-30",
    )
    assert res_late.status == "REJECTED"
    assert res_late.rejection_reason == "OUT_OF_DATE_RANGE"


def test_platform_url_and_email_rejection():
    """Verify social domains are identified as platforms and platform domain emails are rejected."""
    assert is_platform_url("https://www.linkedin.com/events/12345")
    assert is_platform_url("https://facebook.com/events/67890")
    assert is_platform_url("https://x.com/someuser")

    # Platform emails rejected as organizer email
    val, _, reason = is_valid_organizer_email("support@linkedin.com")
    assert not val
    val, _, reason = is_valid_organizer_email("help@facebook.com")
    assert not val
    val, _, reason = is_valid_organizer_email("press@twitter.com")
    assert not val


def test_discovery_auto_settings_persistence(db_session):
    """Verify automated discovery settings save and load from agent_settings."""
    set_discovery_auto_settings(db_session, {
        "country": "United States",
        "countries": ["United States", "India", "Dubai"],
        "cities": ["San Francisco", "Austin", "Mumbai"],
        "states": ["California", "Texas", "Maharashtra"],
        "categories": ["Healthcare", "Finance"],
        "search_depth": 15,
        "daily_limit": 50,
    })
    db_session.commit()

    saved = get_discovery_auto_settings(db_session)
    assert saved["country"] == "United States"
    assert saved["countries"] == ["United States", "India", "Dubai"]
    assert saved["cities"] == ["San Francisco", "Austin", "Mumbai"]
    assert saved["states"] == ["California", "Texas", "Maharashtra"]
    assert saved["categories"] == ["Healthcare", "Finance"]
    assert saved["search_depth"] == 15
    assert saved["daily_limit"] == 50


def test_multi_country_query_seeds_generated():
    """Verify query generation runs across all specified countries."""
    config = DiscoveryConfig(
        countries=["India", "Dubai", "United States"],
        cities=["Mumbai", "Dubai", "San Francisco"],
        categories=["Healthcare"],
        search_depth=30,
    )
    queries = build_search_queries(config)
    queries_str = " ".join(queries).lower()
    assert "india" in queries_str or "mumbai" in queries_str
    assert "dubai" in queries_str
    assert "united states" in queries_str or "san francisco" in queries_str

