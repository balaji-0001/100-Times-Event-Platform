"""AI & usage page: web search providers (Exa, Brave, …) totalled from the
source reports discovery runs saved — never estimated."""

from datetime import datetime, timezone

from backend.models import AgentRun
from backend.routes.observability import _search_provider_usage


def _run(db, rows):
    db.add(AgentRun(agent_type="discovery", status="completed", started_at=datetime.now(timezone.utc),
                    summary={"sources": {"sources": rows}}))


def _row(pid, calls, ok, failed, results, cost, finished="2026-10-01T10:00:00+00:00"):
    return {"id": pid, "kind": "search_provider", "calls": calls, "jobs_ok": ok, "jobs_failed": failed,
            "rate_limited": 0, "results": results, "cost_usd": cost, "finished_at": finished}


def test_totals_come_from_saved_run_reports(db_session):
    _run(db_session, [_row("exa_search", 2, 2, 0, 9, 0.014), _row("brave_search", 3, 2, 1, 12, None)])
    _run(db_session, [_row("exa_search", 1, 1, 0, 5, 0.007, "2026-10-02T10:00:00+00:00"),
                      {"id": "ticketmaster", "kind": "api", "calls": 4}])
    _run(db_session, [])  # a run without a provider report isn't counted
    db_session.commit()

    usage = _search_provider_usage(db_session)
    by_id = {p["id"]: p for p in usage["providers"]}
    assert usage["runsCounted"] == 2

    exa = by_id["exa_search"]
    assert (exa["name"], exa["runs"], exa["calls"], exa["results"], exa["costUsd"]) == ("Exa", 2, 3, 14, 0.021)
    assert exa["lastUsedAt"] == "2026-10-02T10:00:00+00:00"

    brave = by_id["brave_search"]
    assert (brave["name"], brave["calls"], brave["successes"], brave["failures"]) == ("Brave", 3, 2, 1)
    assert brave["costUsd"] is None  # Brave doesn't report a price: no estimate

    assert "ticketmaster" not in by_id  # only search providers


def test_every_search_provider_is_listed_even_without_usage(db_session):
    by_id = {p["id"]: p for p in _search_provider_usage(db_session)["providers"]}
    for pid in ("exa_search", "brave_search", "searxng"):
        assert by_id[pid]["calls"] == 0 and by_id[pid]["costUsd"] is None
        assert isinstance(by_id[pid]["configured"], bool)
