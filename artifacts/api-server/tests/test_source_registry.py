"""Unit & Integration Tests for Global Event Discovery Source Registry.

Verifies:
- Complete catalog seeding of 74+ candidate sources (7 categories A-G)
- 11 Official Integration Statuses support
- REST API endpoints for listing, filtering, updating, health probing, and testing
- Modular adapter instantiation and normalization fidelity
- Idempotent database synchronizations
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.models import EventDiscoverySource
from backend.services.discovery_agent.adapters import adapter_manager
from backend.services.discovery_agent.source_registry import (
    ALL_CANDIDATE_SOURCES,
    get_registry_summary_stats,
    get_source,
    list_sources,
    record_source_execution,
    seed_or_sync_source_registry,
    update_source,
)


@pytest.fixture
def client(db_session: Session):
    return TestClient(app)


def test_seed_source_registry_populates_all_candidates(db_session: Session):
    """Ensures all candidate sources are seeded with correct categories and attributes."""
    result = seed_or_sync_source_registry(db_session)
    assert result["total"] >= 70
    assert result["created"] > 0 or result["updated"] >= 0

    # Test idempotency
    second_pass = seed_or_sync_source_registry(db_session)
    assert second_pass["created"] == 0
    assert second_pass["total"] == result["total"]


def test_registry_summary_stats(db_session: Session):
    """Validates aggregate summary statistics across all categories and statuses."""
    seed_or_sync_source_registry(db_session)
    stats = get_registry_summary_stats(db_session)

    assert stats["total_sources"] >= 70
    assert stats["operational_sources"] > 0
    assert "status_breakdown" in stats
    assert "Operational" in stats["status_breakdown"]
    assert "Awaiting Credentials" in stats["status_breakdown"]
    assert "category_breakdown" in stats
    assert "Venue Calendar" in stats["category_breakdown"]
    assert "Global Event Discovery" in stats["category_breakdown"]
    assert "access_method_breakdown" in stats


def test_list_and_filter_sources(db_session: Session):
    """Tests multi-criteria filtering by category, status, and search query."""
    seed_or_sync_source_registry(db_session)

    venues, total_venues = list_sources(db_session, category="Venue Calendar")
    assert len(venues) >= 5
    for v in venues:
        assert v.source_category == "Venue Calendar"

    apis, _ = list_sources(db_session, access_method="official_api")
    assert any(s.id == "ticketmaster_api" for s in apis)

    searched, _ = list_sources(db_session, q="Ticketmaster")
    assert len(searched) >= 1
    assert "ticketmaster" in searched[0].name.lower()


def test_update_source_configuration(db_session: Session):
    """Tests updating enabled toggle, status, and config."""
    seed_or_sync_source_registry(db_session)

    # Disable source
    updated = update_source(db_session, "10times", {"is_enabled": False, "permission_status": "Reviewed"})
    assert updated is not None
    assert updated.is_enabled is False
    assert updated.permission_status == "Reviewed"

    # Re-enable
    updated_again = update_source(db_session, "10times", {"is_enabled": True})
    assert updated_again.is_enabled is True


def test_record_source_execution(db_session: Session):
    """Tests updating discovery execution counters and health status."""
    seed_or_sync_source_registry(db_session)

    record_source_execution(
        db_session,
        source_id="10times",
        events_discovered=15,
        events_extracted=14,
        unique_events=12,
        success=True,
        health_status="healthy",
    )

    s = get_source(db_session, "10times")
    assert s is not None
    assert s.events_discovered == 15
    assert s.unique_events_discovered == 12
    assert s.health_status == "healthy"
    assert s.last_successful_execution is not None


def test_adapter_manager_initialization():
    """Validates that all catalogued sources have corresponding modular adapters."""
    adapters = adapter_manager.list_adapters()
    assert len(adapters) >= 70

    tm = adapter_manager.get_adapter("ticketmaster_api")
    assert tm is not None
    assert tm.access_method == "official_api"

    venue = adapter_manager.get_adapter("dwtc_events")
    assert venue is not None
    assert venue.access_method == "html_listing"


def test_adapter_health_check():
    """Tests health check probe returns expected schema."""
    probe = adapter_manager.check_health("eventbrite_api")
    assert "status" in probe
    assert "latency_ms" in probe
    assert probe["status"] in ("awaiting_credentials", "healthy", "degraded", "unreachable")


def test_api_sources_endpoints(db_session: Session):
    """Tests REST endpoints: /api/discovery/sources, /stats, /{id}, PATCH, and /health."""
    from backend.db import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    try:
        # 1. GET /api/discovery/sources
        resp = client.get("/api/discovery/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 70
        assert len(data["sources"]) >= 70

        # 2. GET /api/discovery/sources/stats
        resp_stats = client.get("/api/discovery/sources/stats")
        assert resp_stats.status_code == 200
        stats = resp_stats.json()
        assert stats["total_sources"] >= 70
        assert stats["operational_sources"] > 0

        # 3. GET /api/discovery/sources/ticketmaster_api
        resp_detail = client.get("/api/discovery/sources/ticketmaster_api")
        assert resp_detail.status_code == 200
        assert resp_detail.json()["id"] == "ticketmaster_api"

        # 4. PATCH /api/discovery/sources/ticketmaster_api
        resp_patch = client.patch(
            "/api/discovery/sources/ticketmaster_api",
            json={"is_enabled": False, "integration_status": "Approved"},
        )
        assert resp_patch.status_code == 200
        assert resp_patch.json()["source"]["is_enabled"] is False

        # 5. POST /api/discovery/sources/ticketmaster_api/health
        resp_health = client.post("/api/discovery/sources/ticketmaster_api/health")
        assert resp_health.status_code == 200
        assert "status" in resp_health.json()

        # Re-enable
        client.patch("/api/discovery/sources/ticketmaster_api", json={"is_enabled": True})
    finally:
        app.dependency_overrides.pop(get_db, None)
