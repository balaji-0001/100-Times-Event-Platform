"""Technology is no longer a 100 TIMES sector: discovery rejects technology
events in every run, never searches for them, and the site never offers it."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.models import Category
from backend.routes import directories
from backend.services.discovery_agent import query_seeds, validation
from backend.services.discovery_agent.source_registry import ALL_CANDIDATE_SOURCES
from backend.services.discovery_agent.types import DiscoveryConfig, ExtractedEventCandidate


def test_discovery_rejects_technology_events_whatever_the_selection():
    tech = ExtractedEventCandidate(name="Cloud Summit 2027", date="2027-03-10", city="Mumbai", country="India",
                                   url="https://example.com/cloud", category="Technology", extraction_confidence=90)
    for selected in (None, ["Construction"], ["Technology"]):
        result = validation.validate_event(tech, 60, supported_categories=selected, require_organizer_email=False)
        assert result.status == "REJECTED" and result.rejection_reason == "UNSUPPORTED_CATEGORY"
        assert "Technology events aren't listed" in result.notes[0]


def test_saved_technology_selection_is_never_searched():
    config = DiscoveryConfig(categories=["Technology", "Healthcare"], countries=["India"], search_depth=30)
    queries = " ".join(query_seeds.build_search_queries(config)).lower()
    assert "healthcare" in queries
    assert "technology" not in queries and "artificial intelligence" not in queries


def test_site_never_offers_the_technology_sector(db_session):
    db_session.add_all([
        Category(name="Technology", slug="technology", description="Tech", icon="cpu"),
        Category(name="Healthcare", slug="healthcare", description="Health", icon="heart"),
    ])
    db_session.commit()
    app = FastAPI()
    app.include_router(directories.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    assert [c["name"] for c in client.get("/api/categories").json()] == ["Healthcare"]
    assert client.get("/api/categories/technology").status_code == 404
    assert client.get("/api/categories/healthcare").status_code == 200


def test_removed_websites_are_gone_from_the_source_list():
    ids = {s["id"] for s in ALL_CANDIDATE_SOURCES}
    removed = {"dev_events", "sessionize", "pretalx", "acm", "getonsite", "hackevents",  # technology-only
               "koelnmesse", "spie_conferences", "intracen", "european_commission", "skillboxes"}  # no 100 TIMES sector
    assert not ids & removed
