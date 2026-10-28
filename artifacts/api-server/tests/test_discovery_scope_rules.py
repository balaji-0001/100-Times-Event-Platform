"""Whatever the admin selects is what a run keeps — for any country, city or
sector: events in another city of a selected country are rejected, a city
spelled differently still matches, a country with no city ticked means the
whole country, and with "organizer email required" only events whose
organizer published an e-mail are stored."""

from datetime import date, timedelta

import pytest

from backend.models import DiscoveredEvent
from backend.services.discovery_agent import geo_scope, orchestrator, validation
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate, OrganizerCandidate
from tests.test_discovery_pipeline import _wire

SOON = (date.today() + timedelta(days=45)).isoformat()


def _event(name, city, country, i=0):
    source = CandidateSource(url=f"https://fair.test/{i}", source_type="event_directory", source_website="fair.test")
    return ExtractedEventCandidate(name=name, event_description="International trade fair for construction machinery and building materials.",
                                   date=SOON, city=city, country=country, venue="Messe", url=source.url, extraction_confidence=90,
                                   primary_source=source, sources=[source])


def _validate(candidate, config):
    candidate.category = "Construction"  # the run's sector step runs before validation
    geo = geo_scope.resolve(config)
    return validation.validate_event(candidate, 60, organizer=OrganizerCandidate(found=True, name="Org", email="info@org.test"),
                                     target_countries=geo.countries, target_places=geo.place_rules(), supported_categories=["Construction"])


@pytest.mark.parametrize("country, cities, event_city, expected", [
    ("Germany", ["Munich"], "Berlin", "OUT_OF_TARGET_CITY"),
    ("Germany", ["Munich"], "München", "VERIFIED"),            # same city, local spelling
    ("India", ["Bengaluru"], "Bangalore", "VERIFIED"),
    ("India", ["New Delhi"], "Greater Noida", "VERIFIED"),     # Delhi's exhibition centres
    ("United States", ["Las Vegas"], "Chicago", "OUT_OF_TARGET_CITY"),
    ("Brazil", ["São Paulo"], "Sao Paulo", "VERIFIED"),
    ("Germany", ["Munich"], None, "NEEDS_REVIEW"),             # source doesn't say: never counted as verified
    ("Germany", [], "Berlin", "VERIFIED"),                     # no city ticked = the whole country
])
def test_selected_cities_are_enforced_for_any_country(country, cities, event_city, expected):
    config = DiscoveryConfig(countries=[country], locations=[{"country": country, "city": c} for c in cities] or [{"country": country}],
                             cities=list(cities), categories=["Construction"])
    result = _validate(_event("BAU World of Building", event_city, country), config)
    assert (result.rejection_reason or result.status) == expected, result.notes


def test_other_countries_still_rejected_and_ticked_cities_only_bind_their_own_country():
    config = DiscoveryConfig(countries=["Germany", "France"], locations=[{"country": "Germany", "city": "Munich"}, {"country": "France"}], cities=["Munich"])
    assert _validate(_event("Batimat", "Paris", "France"), config).status == "VERIFIED"  # France: no city ticked
    assert _validate(_event("Fair", "Hamburg", "Germany"), config).rejection_reason == "OUT_OF_TARGET_CITY"
    assert _validate(_event("Fair", "Milan", "Italy"), config).rejection_reason == "OUT_OF_TARGET_COUNTRY"


def test_manual_run_does_not_silently_add_major_cities(db_session, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.db import get_db
    from backend.dependencies import get_current_user
    from backend.models import User
    from backend.routes import discovery as discovery_routes

    seen = {}
    monkeypatch.setattr(discovery_routes, "run_discovery_agent", lambda db, config, run=None: seen.setdefault("config", config) and orchestrator.RunSummary() or orchestrator.RunSummary())
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: User(id=1, name="A", email="a@x.test", password_hash="x", role="ADMIN")
    TestClient(app).post("/api/discovery/run", json={"countries": ["Germany"], "locations": [{"country": "Germany"}], "categories": ["Construction"], "background": False})
    config = seen["config"]
    assert config.cities == [] and geo_scope.resolve(config).target_cities() == {}  # all of Germany, not 10 big cities
    # Search and listing pages still anchor on major German cities by themselves.
    assert any(country == "Germany" for _, country in geo_scope.resolve(config).anchor_places(5))


@pytest.mark.parametrize("require_email, expected_names", [
    (True, {"With Contact Expo 1"}),
    (False, {"With Contact Expo 1", "No Contact Expo 2"}),
])
def test_organizer_email_required_means_only_events_with_a_contact_are_stored(db_session, monkeypatch, require_email, expected_names):
    with_contact = _event("With Contact Expo 1", "Munich", "Germany", 1)
    without = _event("No Contact Expo 2", "Munich", "Germany", 2)
    _wire(monkeypatch, {"https://results.test/0": [with_contact, without]}, queries=[])
    monkeypatch.setattr(orchestrator.organizer_identifier, "identify_organizer", lambda c: OrganizerCandidate(
        found="With" in c.name, name="Fair Org GmbH", email="info@fair-org.test" if "With" in c.name else None,
        website="https://fair-org.test", confidence_score=70, sources=[c.primary_source],
        email_source_url="https://fair-org.test/contact" if "With" in c.name else None,
    ))
    config = DiscoveryConfig(countries=["Germany"], locations=[{"country": "Germany", "city": "Munich"}], cities=["Munich"], categories=["Construction"],
                             sources=["web"], search_depth=1, sources_per_query=2, require_organizer_email=require_email,
                             reject_no_organizer=require_email, reject_unmatched_category=True, fallback_to_other_sector=False, min_confidence_score=0)
    summary = orchestrator.run_discovery_agent(db_session, config)

    stored = db_session.query(DiscoveredEvent).filter(DiscoveredEvent.verification_status != "REJECTED").all()
    assert {e.name for e in stored} == expected_names
    if require_email:
        assert summary.missing_organizer_email == 1 and all(e.organizer and e.organizer.email for e in stored)
    else:
        no_contact = next(e for e in stored if e.name.startswith("No Contact"))
        assert no_contact.verification_status == "NEEDS_REVIEW"  # never counted as verified without a contact


# --- Whole states (a state ticked without any of its cities) -------------------

GERMANY = {"Bavaria": ["Munich", "Nuremberg", "Augsburg"], "Berlin": ["Berlin"], "Hesse": ["Frankfurt", "Wiesbaden"]}
US = {"California": ["Los Angeles", "San Francisco", "San Jose", "San Diego"], "Texas": ["Houston", "Dallas", "Austin"]}
UK = {"England": ["London", "Manchester", "Birmingham"], "Scotland": ["Edinburgh", "Glasgow"]}
INDIA = {"Maharashtra": ["Mumbai", "Pune", "Nagpur"], "Karnataka": ["Bengaluru", "Mysuru"], "Tamil Nadu": ["Chennai", "Coimbatore"]}


def _state_config(country, states, region, cities=()):
    locations = [{"country": country, "state": s} for s in states] + [{"country": country, "state": st, "city": c}
                                                                       for st, cs in region.items() for c in cs if c in cities]
    return DiscoveryConfig(countries=[country], locations=locations, states=list(states), cities=list(cities),
                           region_cities={country: region}, categories=["Construction"])


@pytest.mark.parametrize("country, states, region, city, state, expected", [
    ("Germany", ["Bavaria"], GERMANY, "Munich", None, "VERIFIED"),
    ("Germany", ["Bavaria"], GERMANY, "Nürnberg", None, "VERIFIED"),          # city spelled the local way
    ("Germany", ["Bavaria"], GERMANY, "Berlin", None, "OUT_OF_TARGET_CITY"),   # another state
    ("Germany", ["Bavaria"], GERMANY, "Landshut", "Bayern", "VERIFIED"),       # unlisted town, state given natively
    ("Germany", ["Bavaria"], GERMANY, "Leipzig", None, "NEEDS_REVIEW"),        # unlisted city, no state: can't confirm
    ("United States", ["California"], US, "San Jose, CA", None, "VERIFIED"),
    ("United States", ["California"], US, "Las Vegas, NV", None, "OUT_OF_TARGET_CITY"),
    ("United States", ["California"], US, "Houston", "Texas", "OUT_OF_TARGET_CITY"),
    ("United Kingdom", ["England"], UK, "London", "Greater London", "VERIFIED"),  # a sub-region is not "another state"
    ("United Kingdom", ["England"], UK, "Glasgow", None, "OUT_OF_TARGET_CITY"),
])
def test_whole_state_selection_is_enforced(country, states, region, city, state, expected):
    candidate = _event("Construction Expo", city, country)
    candidate.state = state
    result = _validate(candidate, _state_config(country, states, region))
    assert (result.rejection_reason or result.status) == expected, result.notes


def test_whole_state_and_ticked_cities_combine_within_one_country():
    # Maharashtra (whole state) + Bengaluru (one city of Karnataka).
    config = _state_config("India", ["Maharashtra"], INDIA, cities=["Bengaluru"])
    assert geo_scope.resolve(config).place_rules()["India"]["states"] == ["Maharashtra"]
    assert _validate(_event("Expo", "Pune", "India"), config).status == "VERIFIED"
    assert _validate(_event("Expo", "Bangalore", "India"), config).status == "VERIFIED"
    assert _validate(_event("Expo", "Mysuru", "India"), config).rejection_reason == "OUT_OF_TARGET_CITY"  # Karnataka, but only Bengaluru ticked
    assert _validate(_event("Expo", "Chennai", "India"), config).rejection_reason == "OUT_OF_TARGET_CITY"


@pytest.mark.parametrize("title, is_listing", [
    ("Browse through our Trade Fairs for ➡️ Building & Construction industry", True),
    ("Oil & Gas Trade Shows in India", True),
    ("Upcoming Construction Exhibitions", True),
    ("All Things Open 2026", False),          # a real conference
    ("Conferences in Construction Management 2027", False),
    ("BAU 2027", False),
])
def test_listing_page_titles_are_not_events(title, is_listing):
    candidate = _event(title, "Munich", "Germany")
    candidate.best_effort = True  # read from page text, no structured event data
    result = _validate(candidate, DiscoveryConfig(countries=["Germany"], locations=[{"country": "Germany"}], categories=["Construction"]))
    assert (result.rejection_reason == "LISTING_PAGE") is is_listing, result.notes
