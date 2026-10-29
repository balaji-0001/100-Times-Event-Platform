"""Per-run discovery usage: queries vs provider calls, AI tokens, and honest
costs (reported > configured price > unknown; never "free" by omission)."""

from datetime import datetime, timezone
from types import SimpleNamespace

from backend.models import AgentExecutionMetric, AgentRun
from backend.routes.observability import _discovery_run_usage, observability_ai_usage
from backend.services.discovery_agent import run_usage
from backend.services.discovery_agent.search_providers.base import BaseSearchProvider, SearchProviderResult
from backend.services.discovery_agent.search_providers.engine import MultiProviderSearchEngine, SearchRunStats
from backend.services.social_agent import ai_client


class _Free(BaseSearchProvider):
    provider_id, provider_name, is_free = "free_one", "Free One", True

    def is_configured(self):
        return True

    def search(self, query, max_results=5, country=None, date_range=None):
        return [SearchProviderResult(url=f"https://free.example/{query}")]


class _PaidWithAI(BaseSearchProvider):
    """Like Google-via-Gemini: one AI request per search, tokens reported by the API."""
    provider_id, provider_name, cost_rank = "paid_ai", "Paid AI", 10

    def is_configured(self):
        return True

    def search(self, query, max_results=5, country=None, date_range=None):
        ai_client._note_usage("gemini", "gemini-3.5-flash-lite", ok=True, prompt=1000, completion=200)
        return [SearchProviderResult(url=f"https://paid.example/{query}")]


class _Broken(BaseSearchProvider):
    provider_id, provider_name, cost_rank = "broken", "Broken", 20

    def is_configured(self):
        return True

    def search(self, query, max_results=5, country=None, date_range=None):
        raise RuntimeError("HTTP 500")


def _engine():
    engine = MultiProviderSearchEngine()
    engine._providers = {"free_one": _Free(), "paid_ai": _PaidWithAI(), "broken": _Broken()}
    return engine


def test_queries_calls_and_ai_tokens_are_counted_once():
    engine, stats = _engine(), SearchRunStats()
    ai_client._note_usage("gemini", "stale-model", ok=True, prompt=99)  # earlier, unrelated request on this thread
    engine.search("expo a", max_results=5, stats=stats)
    engine.search("expo a", max_results=5, stats=stats)  # same query again: served from cache, no new calls
    engine.search("expo b", max_results=5, stats=stats)

    usage = stats.usage_snapshot()
    assert usage["queries"] == {"attempted": 3, "with_results": 2, "served_from_cache": 1}
    snap = stats.snapshot()
    assert snap["free_one"]["calls"] == 2 and snap["paid_ai"]["calls"] == 2
    assert snap["broken"]["calls"] == 2 and snap["broken"]["failures"] == 2 and snap["broken"]["successes"] == 0
    model = usage["ai_models"]["gemini-3.5-flash-lite"]
    assert (model["calls"], model["prompt_tokens"], model["completion_tokens"], model["total_tokens"]) == (2, 2000, 400, 2400)
    assert model["used_by"] == {"paid_ai": 2}
    assert "stale-model" not in usage["ai_models"]  # not this run's request


def test_query_no_provider_ran_is_not_sent_and_failed_calls_cost_nothing(monkeypatch):
    engine, stats = _engine(), SearchRunStats()
    engine._providers = {"broken": _Broken()}
    for i in range(engine._BREAKER_THRESHOLD + 2):  # breaker opens after 5 failures: the rest are never sent
        engine.search(f"q{i}", stats=stats)
    queries = stats.usage_snapshot()["queries"]
    assert queries == {"attempted": 7, "no_results": 5, "no_provider": 2}

    _settings(monkeypatch)
    usage = run_usage.build_run_usage(
        {"brave_search": {"calls": 5, "successes": 0, "failures": 5}},
        {"ai_models": {"gemini-flash-lite-latest": {"provider": "gemini", "calls": 2, "failed_calls": 2, "prompt_tokens": 0,
                                                    "completion_tokens": 0, "total_tokens": 0, "used_by": {}}}},
        _providers(), valid_events=0)
    brave = next(p for p in usage["search_providers"] if p["id"] == "brave_search")
    assert (brave["cost_usd"], brave["cost_basis"]) == (0.0, "failed_not_billed")
    assert (usage["ai_models"][0]["cost_usd"], usage["ai_models"][0]["cost_basis"]) == (0.0, "failed_not_billed")
    assert usage["costs"]["total_complete"] is True


def _providers():
    return {pid: SimpleNamespace(display_name=pid.title(), provider_name=pid) for pid in ("searxng", "exa_search", "brave_search", "google_search", "web_fallback")}


def _settings(monkeypatch, search="", models=""):
    monkeypatch.setattr(run_usage, "get_settings", lambda: SimpleNamespace(search_pricing_usd_per_1000=search, ai_model_pricing_usd_per_mtok=models))


def test_costs_reported_configured_unknown_and_not_used(monkeypatch):
    _settings(monkeypatch, search='{"google_search": 5.0}')
    snapshot = {
        "searxng": {"calls": 10, "successes": 9, "failures": 1},
        "exa_search": {"calls": 2, "successes": 2, "cost_usd": 0.014},
        "brave_search": {"calls": 3, "successes": 3},           # used, reports no cost, no price
        "google_search": {"calls": 4, "successes": 2, "failures": 2},
    }
    ai = {"queries": {"attempted": 12, "with_results": 10, "no_results": 2},
          "ai_models": {"gemini-3.5-flash-lite": {"provider": "gemini", "calls": 2, "failed_calls": 0, "prompt_tokens": 2000,
                                                  "completion_tokens": 400, "total_tokens": 2400, "used_by": {"google_gemini": 2}}}}
    usage = run_usage.build_run_usage(snapshot, ai, _providers(), valid_events=7)
    by_id = {p["id"]: p for p in usage["search_providers"]}

    assert (by_id["searxng"]["cost_usd"], by_id["searxng"]["cost_basis"]) == (0.0, "no_fee")
    assert (by_id["exa_search"]["cost_usd"], by_id["exa_search"]["cost_basis"]) == (0.014, "reported_by_provider")
    assert (by_id["brave_search"]["cost_usd"], by_id["brave_search"]["cost_basis"]) == (None, "unknown")
    assert (by_id["google_search"]["cost_usd"], by_id["google_search"]["cost_basis"]) == (0.01, "configured_price")  # 2 successes
    assert (by_id["web_fallback"]["used"], by_id["web_fallback"]["cost_basis"]) == (False, "not_used")

    model = usage["ai_models"][0]
    assert model["cost_usd"] == round(2000 * 0.30 / 1e6 + 400 * 2.50 / 1e6, 6) and model["cost_basis"] == "list_price"
    costs = usage["costs"]
    assert costs["search_usd"] == 0.024 and costs["search_complete"] is False  # Brave's cost is unknown
    assert costs["ai_complete"] is True and costs["total_complete"] is False
    assert usage["queries"]["attempted"] == 12 and usage["valid_events"] == 7
    assert usage["provider_calls"] == {"attempted": 19, "succeeded": 16, "failed": 3, "rate_limited": 0}


def test_unpriced_model_is_unknown_not_free(monkeypatch):
    _settings(monkeypatch)
    ai = {"ai_models": {"gemini-flash-lite-latest": {"provider": "gemini", "calls": 1, "failed_calls": 0, "prompt_tokens": 10,
                                                     "completion_tokens": 5, "total_tokens": 15, "used_by": {}}}}
    usage = run_usage.build_run_usage({}, ai, {}, valid_events=0)
    assert usage["ai_models"][0]["cost_usd"] is None and usage["costs"]["ai_complete"] is False
    _settings(monkeypatch, models='{"gemini-flash-lite-latest": [1, 2]}')
    usage = run_usage.build_run_usage({}, ai, {}, valid_events=0)
    assert usage["ai_models"][0]["cost_usd"] == 0.00002 and usage["ai_models"][0]["cost_basis"] == "configured_price"


def test_dashboard_lists_each_run_and_marks_untracked_ones(db_session, monkeypatch):
    _settings(monkeypatch)
    now = datetime.now(timezone.utc)
    legacy = AgentRun(agent_type="discovery", status="completed", started_at=now, summary={
        "verified_events": 3,
        "sources": {"sources": [{"id": "exa_search", "kind": "search_provider", "calls": 1, "jobs_ok": 1, "cost_usd": 0.007},
                                {"id": "searxng", "kind": "search_provider", "calls": 3, "jobs_ok": 3}]},
    })
    tracked_usage = run_usage.build_run_usage({"searxng": {"calls": 4, "successes": 4}}, {"queries": {"attempted": 4, "with_results": 4}},
                                              _providers(), valid_events=5)
    tracked = AgentRun(agent_type="discovery", status="completed", started_at=now, summary={"verified_events": 5, "usage": tracked_usage})
    db_session.add_all([legacy, tracked])
    db_session.flush()
    db_session.add_all([
        AgentExecutionMetric(workflow_id="wf-disc-x", agent_name="DiscoveryAgent", model_name="none (rule-based)", created_at=now),
        AgentExecutionMetric(workflow_id="wf-disc-x", agent_name="DiscoveryAgent", model_name="gemini-3.5-flash-lite", prompt_tokens=100,
                             completion_tokens=20, total_tokens=120, meta_json={"calls": 3, "cost_known": True}, created_at=now),
    ])
    db_session.commit()

    runs = _discovery_run_usage(db_session)
    assert runs["latest"]["runId"] == tracked.id and runs["latest"]["tracked"] is True
    assert runs["latest"]["queries"]["attempted"] == 4 and runs["latest"]["validEvents"] == 5
    old = next(r for r in runs["history"] if r["runId"] == legacy.id)
    assert old["tracked"] is False and old["queries"] is None and old["ai_models"] is None
    assert old["costs"]["search_usd"] == 0.007 and old["costs"]["search_complete"] is True
    assert old["costs"]["ai_usd"] is None and old["costs"]["total_complete"] is False  # AI wasn't recorded back then
    searx = next(p for p in old["search_providers"] if p["id"] == "searxng")
    assert (searx["cost_usd"], searx["cost_basis"]) == (0.0, "no_fee")

    models = observability_ai_usage(db=db_session, _=None)["models"]
    assert "none (rule-based)" not in models
    assert models["gemini-3.5-flash-lite"]["calls"] == 3
