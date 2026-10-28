"""The run wizard's recommended settings come from real availability: only
usable providers and working default sources are pre-selected, anything
unavailable is reported in plain language, and a blocker appears only when
nothing at all can run."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import User
from backend.routes import discovery as discovery_routes
from backend.services.discovery_agent.catalog import recommended_config


@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(discovery_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")
    return TestClient(app)


def _provider(pid, *, configured=True, tier="free", cooling=0):
    return {"id": pid, "name": pid.title(), "tier": tier, "configured": configured, "cooling_down_seconds": cooling, "cooldown_reason": "quota exceeded" if cooling else None}


def _source(sid, channel, *, status="ok", configured=True, enabled=True, default=True):
    return {"id": sid, "name": sid.title(), "channel": channel, "configured": configured, "enabled_by_admin": enabled, "default_selected": default,
            "health": {"status": status}}


def _catalog(providers, sources):
    return {"providers": providers, "sources": sources, "paid_search_budget_per_run": 60}


def test_usable_providers_and_working_sources_are_recommended():
    rec = recommended_config(_catalog(
        [_provider("searxng"), _provider("exa_search", tier="paid"), _provider("google_search", configured=False)],
        [_source("eventseye", "directories"), _source("tradeshowradar", "directories", status="failed"), _source("allevents", "aggregators")],
    ))
    assert rec["sources"] == ["web", "global_adapters", "consumer_aggregators", "eventseye", "allevents"]
    assert [p["id"] for p in rec["usableProviders"]] == ["searxng", "exa_search"]  # the unconfigured one is not offered
    assert rec["searchProviders"] is None  # automatic order: free first, paid only as top-up
    assert rec["blocker"] is None
    assert any("Tradeshowradar" in n["message"] for n in rec["notices"])  # failing source skipped and said so
    assert rec["targetValidEvents"] == 25 and rec["requireOrganizerEmail"] and rec["dateFrom"] < rec["dateTo"]


def test_paused_provider_is_not_used_and_is_reported():
    rec = recommended_config(_catalog([_provider("google_gemini", tier="paid", cooling=600), _provider("searxng")], []))
    assert [p["id"] for p in rec["usableProviders"]] == ["searxng"]
    assert any("paused" in n["message"] for n in rec["notices"])


def test_no_search_provider_falls_back_to_directories_with_one_clear_message():
    rec = recommended_config(_catalog([_provider("searxng", configured=False)], [_source("eventseye", "directories")]))
    assert rec["sources"] == ["global_adapters", "eventseye"]
    assert rec["channels"]["web"]["available"] is False
    warnings = [n for n in rec["notices"] if n["level"] == "warning"]
    assert len(warnings) == 1 and "SEARXNG_URL" in warnings[0]["action"]
    assert rec["blocker"] is None


def test_blocker_only_when_nothing_can_run():
    rec = recommended_config(_catalog([_provider("searxng", configured=False)], [_source("eventseye", "directories", status="failed")]))
    assert rec["sources"] == []
    assert rec["blocker"] and "No discovery source is available" in rec["blocker"]


def test_recommended_config_endpoint(client):
    response = client.get("/api/discovery/recommended-config")
    assert response.status_code == 200
    body = response.json()
    assert {"sources", "usableProviders", "channels", "notices", "blocker", "dateFrom", "dateTo"} <= set(body)
