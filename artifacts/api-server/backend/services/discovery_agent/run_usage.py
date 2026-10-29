"""Per-run usage and estimated cost of a discovery run: search queries,
search-provider calls and AI model tokens, priced honestly.

Cost of a search provider, in order of preference:
1. what the provider itself reported (Exa returns the billed amount),
2. a configured price per 1,000 successful searches (SEARCH_PRICING_USD_PER_1000),
3. otherwise "unknown" — a provider that doesn't report a cost is never assumed free.
Only providers with no per-search fee by design (self-hosted SearXNG, the
DuckDuckGo HTML fallback) default to $0.

AI model cost = reported tokens x price per 1M tokens (official list prices
below, overridable with AI_MODEL_PRICING_USD_PER_MTOK); a model without a
known price is "unknown".
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from backend.core.config import get_settings

logger = logging.getLogger("discovery_agent.run_usage")

# Providers with no per-search fee: SearXNG runs on our own server; the
# DuckDuckGo fallback reads its free HTML results page.
_NO_FEE_PROVIDERS = {"searxng": "Self-hosted: no per-search fee", "web_fallback": "Free HTML results page: no per-search fee"}

# Official list prices, USD per 1M tokens (input, output). Checked 2026-10-28
# against ai.google.dev/gemini-api/docs/pricing and platform.claude.com pricing.
_DEFAULT_MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "claude-fable-5-1": (10.00, 50.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
}
PRICES_CHECKED_ON = "2026-10-28"


def _json_setting(raw: str, name: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except ValueError:
        logger.warning("%s is not valid JSON; ignoring it.", name)
        return {}


def search_price_per_1000(provider_id: str) -> tuple[float | None, str]:
    """(USD per 1,000 successful searches or None, where the price came from)."""
    configured = _json_setting(get_settings().search_pricing_usd_per_1000, "SEARCH_PRICING_USD_PER_1000")
    if provider_id in configured:
        try:
            return float(configured[provider_id]), "configured_price"
        except (TypeError, ValueError):
            pass
    if provider_id in _NO_FEE_PROVIDERS:
        return 0.0, "no_fee"
    return None, "unknown"


def model_price_per_mtok(model: str) -> tuple[tuple[float, float] | None, str]:
    """((input, output) USD per 1M tokens or None, where the price came from).
    Matches the model id exactly or as a prefix of a dated/versioned id."""
    configured = _json_setting(get_settings().ai_model_pricing_usd_per_mtok, "AI_MODEL_PRICING_USD_PER_MTOK")
    name = (model or "").lower().removeprefix("models/")
    for table, basis in ((configured, "configured_price"), (_DEFAULT_MODEL_PRICES, "list_price")):
        matches = [k for k in table if name == k.lower() or name.startswith(f"{k.lower()}-")]
        if matches:
            value = table[max(matches, key=len)]
            try:
                return (float(value[0]), float(value[1])), basis
            except (TypeError, ValueError, IndexError):
                continue
    return None, "unknown"


def _sum_known(items: list[dict[str, Any]]) -> tuple[float, bool]:
    """(sum of known costs, True if no used item had an unknown cost)."""
    used = [i for i in items if i["used"]]
    return round(sum(i["cost_usd"] or 0.0 for i in used), 6), all(i["cost_usd"] is not None for i in used)


def reprice(usage: dict[str, Any], providers: dict[str, Any]) -> dict[str, Any]:
    """A stored usage block re-priced with today's prices. The recorded counts
    and any cost a provider reported are kept as they were; only prices that
    come from configuration or the list-price table are applied again."""
    snapshot = {
        p["id"]: {"calls": p["calls"], "successes": p["successes"], "failures": p["failures"], "rate_limited": p["rate_limited"],
                  "results": p["results"], "skipped": p.get("skipped") or {},
                  "cost_usd": p["cost_usd"] if p.get("cost_basis") == "reported_by_provider" else None}
        for p in usage.get("search_providers") or []
    }
    known = {**providers, **{pid: SimpleNamespace(display_name=next(p["name"] for p in usage["search_providers"] if p["id"] == pid))
                             for pid in snapshot if pid not in providers}}
    models = usage.get("ai_models")
    rebuilt = build_run_usage(
        snapshot,
        {"queries": usage.get("queries") or {}, "ai_models": {m["model"]: m for m in models or []}},
        known,
        usage.get("valid_events") or 0,
    )
    if usage.get("queries") is None:  # saved before query tracking
        rebuilt["queries"] = None
    if models is None:  # saved before AI usage tracking: unknown, not zero
        rebuilt.update(ai_models=None, ai_totals=None)
        rebuilt["costs"].update(ai_usd=None, ai_complete=False, total_complete=False)
    return rebuilt


def build_run_usage(search_snapshot: dict[str, dict[str, Any]], usage_snapshot: dict[str, Any],
                    providers: dict[str, Any], valid_events: int) -> dict[str, Any]:
    """The run's usage block stored in `agent_runs.summary["usage"]`."""
    provider_rows: list[dict[str, Any]] = []
    for pid, provider in providers.items():
        row = search_snapshot.get(pid) or {}
        calls = int(row.get("calls") or 0)
        successes = int(row.get("successes") or 0)
        price, basis = search_price_per_1000(pid)
        if not calls:
            cost, basis = None, "not_used"
        elif row.get("cost_usd") is not None:
            cost, basis = float(row["cost_usd"]), "reported_by_provider"
        elif not successes:
            cost, basis = 0.0, "failed_not_billed"  # every request failed (quota, timeout, error): nothing to bill
        elif price is not None:
            cost = round(successes * price / 1000, 6)  # failed / rate-limited requests aren't billed
        else:
            cost = None
        provider_rows.append({
            "id": pid,
            "name": getattr(provider, "display_name", "") or getattr(provider, "provider_name", pid),
            "used": calls > 0,
            "calls": calls,
            "successes": successes,
            "failures": int(row.get("failures") or 0),
            "rate_limited": int(row.get("rate_limited") or 0),
            "results": int(row.get("results") or 0),
            "skipped": row.get("skipped") or {},
            "cost_usd": cost,
            "cost_basis": basis,
            "price_per_1000": price,
        })

    model_rows: list[dict[str, Any]] = []
    for model, row in (usage_snapshot.get("ai_models") or {}).items():
        price, basis = model_price_per_mtok(model)
        cost = None
        if not row["prompt_tokens"] and not row["completion_tokens"]:
            cost, basis = 0.0, "failed_not_billed" if row["failed_calls"] == row["calls"] else "no_tokens"
        elif price is not None:
            cost = round(row["prompt_tokens"] * price[0] / 1e6 + row["completion_tokens"] * price[1] / 1e6, 6)
        model_rows.append({
            "model": model,
            "provider": row.get("provider"),
            "used": True,
            "calls": row["calls"],
            "failed_calls": row["failed_calls"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "total_tokens": row["total_tokens"],
            "used_by": row.get("used_by") or {},
            "cost_usd": cost,
            "cost_basis": basis,
            "price_per_mtok": list(price) if price else None,
        })

    search_cost, search_complete = _sum_known(provider_rows)
    ai_cost, ai_complete = _sum_known(model_rows)
    queries = usage_snapshot.get("queries") or {}
    return {
        "queries": {k: int(queries.get(k, 0)) for k in ("attempted", "with_results", "no_results", "served_from_cache", "no_provider")},
        "provider_calls": {
            "attempted": sum(p["calls"] for p in provider_rows),
            "succeeded": sum(p["successes"] for p in provider_rows),
            "failed": sum(p["failures"] for p in provider_rows),
            "rate_limited": sum(p["rate_limited"] for p in provider_rows),
        },
        "search_providers": provider_rows,
        "ai_models": model_rows,
        "ai_totals": {
            "calls": sum(m["calls"] for m in model_rows),
            "failed_calls": sum(m["failed_calls"] for m in model_rows),
            "prompt_tokens": sum(m["prompt_tokens"] for m in model_rows),
            "completion_tokens": sum(m["completion_tokens"] for m in model_rows),
            "total_tokens": sum(m["total_tokens"] for m in model_rows),
        },
        "costs": {
            "search_usd": search_cost,
            "search_complete": search_complete,
            "ai_usd": ai_cost,
            "ai_complete": ai_complete,
            "total_usd": round(search_cost + ai_cost, 6),
            "total_complete": search_complete and ai_complete,
        },
        "valid_events": valid_events,
        "prices_checked_on": PRICES_CHECKED_ON,
    }
