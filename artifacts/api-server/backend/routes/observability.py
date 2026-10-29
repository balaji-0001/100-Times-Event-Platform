"""Admin Observability Endpoints.

Provides server-side authorized telemetry for the dedicated Admin Observability Dashboard:
- Overview (Executions, success rate, latency, token consumption, cost)
- Agent Monitor (Discovery, Trust, Outreach, Attendee, Social)
- Workflow Traces (Searchable with execution step logs)
- Error Center (Failed jobs, retries, guardrail rejections)
- AI Usage & Quality (Tokens, models, cost estimates)
- Guardrails Decision Feed
- System Health & Prometheus Metrics
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.core.telemetry import get_prometheus_metrics_text
from backend.db import get_db
from backend.dependencies import require_roles
from backend.models import (
    AgentExecutionMetric,
    AgentRun,
    AuditLog,
    AutomationRun,
    Event,
    GuardrailLog,
    TrustDecision,
    TrustReview,
    User,
)

router = APIRouter(prefix="/admin/observability", tags=["observability"])
public_metrics_router = APIRouter(tags=["metrics"])


@public_metrics_router.get("/metrics")
def metrics(db: Session = Depends(get_db)) -> Response:
    """Public Prometheus scrape target."""
    return Response(content=get_prometheus_metrics_text(db), media_type="text/plain")


@public_metrics_router.get("/ready")
def readiness_check(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Kubernetes / Docker readiness probe checking MySQL database connectivity."""
    try:
        db.execute(select(1)).scalar()
        return {"status": "ready", "database": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        # Public endpoint: never echo the driver's error (host, user, schema names).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed",
        ) from exc


def _run_duration_ms(run: AgentRun) -> int | None:
    if run.started_at and run.completed_at:
        return max(int((run.completed_at - run.started_at).total_seconds() * 1000), 0)
    return None


@router.get("/overview")
def observability_overview(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Aggregate overview of all agent workflows, latency, errors, and AI costs."""
    total_metrics = int(db.scalar(select(func.count(AgentExecutionMetric.id))) or 0)
    total_agent_runs = int(db.scalar(select(func.count(AgentRun.id))) or 0)
    total_auto_runs = int(db.scalar(select(func.count(AutomationRun.id))) or 0)
    total_executions = total_metrics + total_agent_runs + total_auto_runs

    metrics_success = int(db.scalar(select(func.count(AgentExecutionMetric.id)).where(AgentExecutionMetric.status == "SUCCESS")) or 0)
    # Only finished runs count; a run still in progress hasn't succeeded yet.
    runs_success = int(db.scalar(select(func.count(AgentRun.id)).where(AgentRun.status.in_(["completed", "stopped"]))) or 0)
    auto_success = int(db.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status.in_(["SUCCESS", "completed"]))) or 0)
    total_success = metrics_success + runs_success + auto_success

    metrics_failed = int(db.scalar(select(func.count(AgentExecutionMetric.id)).where(AgentExecutionMetric.status == "FAILED")) or 0)
    runs_failed = int(db.scalar(select(func.count(AgentRun.id)).where(AgentRun.status == "failed")) or 0)
    auto_failed = int(db.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status == "FAILED")) or 0)
    total_failed = metrics_failed + runs_failed + auto_failed

    # Success rate over finished executions; None when nothing has finished yet.
    finished = total_success + total_failed
    success_rate = round((total_success / finished) * 100, 1) if finished else None

    # Average latency in ms (None when no execution recorded a duration)
    avg_duration = db.scalar(select(func.avg(AgentExecutionMetric.duration_ms)))
    avg_latency_ms = round(float(avg_duration), 1) if avg_duration is not None else None

    # Token and cost tally
    total_prompt_tokens = int(db.scalar(select(func.sum(AgentExecutionMetric.prompt_tokens))) or 0)
    total_completion_tokens = int(db.scalar(select(func.sum(AgentExecutionMetric.completion_tokens))) or 0)
    # Only tokens and cost the executions actually recorded — nothing estimated per run.
    total_tokens = total_prompt_tokens + total_completion_tokens
    total_cost = round(float(db.scalar(select(func.sum(AgentExecutionMetric.estimated_cost))) or 0.0), 4)

    # Guardrail decisions
    guardrail_blocks = int(db.scalar(select(func.count(GuardrailLog.id)).where(GuardrailLog.decision.in_(["BLOCKED", "FLAGGED"]))) or 0)

    system_health = "UNKNOWN" if not finished else ("HEALTHY" if total_failed / finished < 0.05 else "DEGRADED")

    return {
        "totalExecutions": total_executions,
        "successCount": total_success,
        "failureCount": total_failed,
        "successRate": success_rate,
        "avgLatencyMs": avg_latency_ms,
        "totalTokens": total_tokens,
        "estimatedCostUsd": total_cost,
        "guardrailBlocks": guardrail_blocks,
        "systemHealth": system_health,
    }


@router.get("/agents")
def observability_agents(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    """Monitors live status, duration, and error counts for all platform agents."""
    agents_def = [
        {"id": "discovery", "name": "Event Discovery Agent", "category": "Ingestion"},
        {"id": "trust", "name": "Trust & Safety Agent", "category": "Verification"},
        {"id": "outreach", "name": "Organizer Outreach Agent", "category": "Acquisition"},
        # Social promotion and attendee reminders are automations, not agents:
        # they're listed on the Automations page.
    ]

    out = []
    for ag in agents_def:
        agent_key = ag["id"]
        # 1. Query AgentExecutionMetric
        query_m = select(AgentExecutionMetric).where(AgentExecutionMetric.agent_name.ilike(f"%{agent_key}%"))
        metrics = db.scalars(query_m.order_by(desc(AgentExecutionMetric.created_at)).limit(50)).all()

        # 2. Query AgentRun
        query_r = select(AgentRun).where(AgentRun.agent_type.ilike(f"%{agent_key}%"))
        runs = db.scalars(query_r.order_by(desc(AgentRun.id)).limit(50)).all()

        total_runs = len(metrics) + len(runs)
        metric_fails = sum(1 for m in metrics if m.status == "FAILED")
        run_fails = sum(1 for r in runs if r.status == "failed")
        fails = metric_fails + run_fails

        # Calculate average duration
        durations = [m.duration_ms for m in metrics if m.duration_ms and m.duration_ms > 0]
        durations += [_run_duration_ms(r) for r in runs if _run_duration_ms(r) is not None]
        avg_dur = int(sum(durations) / len(durations)) if durations else None

        # Most recent execution timestamp
        last_metric_time = metrics[0].created_at if metrics else None
        last_run_time = runs[0].started_at if runs else None
        last_ts = max(filter(None, [last_metric_time, last_run_time]), default=None)
        last_run_iso = last_ts.isoformat() if last_ts else None

        # Determine agent operational status
        is_running_now = any(r.status == "running" for r in runs)
        if fails > 3:
            status_str = "DEGRADED"
        elif is_running_now or total_runs > 0:
            status_str = "ACTIVE"
        else:
            status_str = "STANDBY"

        recent_error = None
        if runs and runs[0].status == "failed" and runs[0].error:
            recent_error = runs[0].error
        elif metrics and metrics[0].status == "FAILED" and metrics[0].error_message:
            recent_error = metrics[0].error_message

        out.append({
            "id": ag["id"],
            "name": ag["name"],
            "category": ag["category"],
            "status": status_str,
            "totalRuns": total_runs,
            "successCount": sum(1 for m in metrics if m.status == "SUCCESS") + sum(1 for r in runs if r.status in ("completed", "stopped")),
            "failureCount": fails,
            "avgDurationMs": avg_dur,
            "lastExecution": last_run_iso,
            "recentError": recent_error,
        })
    return out


@router.get("/traces")
def observability_traces(
    q: str | None = None,
    agent: str | None = None,
    status_filter: str | None = None,
    limit: int = Query(default=50, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    """Searchable workflow execution traces from AgentExecutionMetric and AgentRun."""
    combined_traces = []

    # 1. Traces from AgentExecutionMetric
    query_m = select(AgentExecutionMetric).order_by(desc(AgentExecutionMetric.created_at))
    if q:
        query_m = query_m.where(AgentExecutionMetric.workflow_id.ilike(f"%{q.strip()}%"))
    if agent and agent != "ALL":
        query_m = query_m.where(AgentExecutionMetric.agent_name.ilike(f"%{agent.strip()}%"))
    if status_filter and status_filter != "ALL":
        query_m = query_m.where(AgentExecutionMetric.status == status_filter.upper())

    for r in db.scalars(query_m.limit(limit)).all():
        combined_traces.append({
            "id": r.id,
            "workflowId": r.workflow_id,
            "agentName": r.agent_name,
            "status": r.status,
            "durationMs": r.duration_ms,
            "promptTokens": r.prompt_tokens,
            "completionTokens": r.completion_tokens,
            "totalTokens": r.total_tokens,
            "estimatedCost": float(r.estimated_cost),
            "modelName": r.model_name,
            "errorMessage": r.error_message,
            "createdAt": r.created_at.isoformat() if r.created_at else "",
        })

    # 2. Traces from AgentRun
    query_r = select(AgentRun).order_by(desc(AgentRun.id))
    if agent and agent != "ALL":
        query_r = query_r.where(AgentRun.agent_type.ilike(f"%{agent.strip()}%"))
    if status_filter and status_filter != "ALL":
        if status_filter.upper() == "SUCCESS":
            query_r = query_r.where(AgentRun.status.in_(["completed", "stopped"]))
        elif status_filter.upper() == "RUNNING":
            query_r = query_r.where(AgentRun.status == "running")
        elif status_filter.upper() == "FAILED":
            query_r = query_r.where(AgentRun.status == "failed")

    for ar in db.scalars(query_r.limit(limit)).all():
        wf_id = f"wf-{ar.agent_type[:4]}-{ar.id:04d}"
        if q and q.strip().lower() not in wf_id.lower():
            continue

        status_str = {"completed": "SUCCESS", "stopped": "SUCCESS", "running": "RUNNING"}.get(ar.status, "FAILED")
        # Agent runs record no LLM usage of their own (discovery/outreach are
        # rule-based); tokens/cost/model come only from AgentExecutionMetric.
        combined_traces.append({
            "id": 10000 + ar.id,
            "workflowId": wf_id,
            "agentName": f"{ar.agent_type.capitalize()} Agent",
            "status": status_str,
            "durationMs": _run_duration_ms(ar),
            "promptTokens": None,
            "completionTokens": None,
            "totalTokens": None,
            "estimatedCost": None,
            "modelName": None,
            "errorMessage": ar.error,
            "createdAt": ar.started_at.isoformat() if ar.started_at else "",
        })

    # Sort descending by createdAt
    combined_traces.sort(key=lambda x: x["createdAt"], reverse=True)
    return combined_traces[:limit]


@router.get("/errors")
def observability_errors(
    limit: int = Query(default=50, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    """Error Center listing failed workflows, guardrail blocks, and recovery diagnostics."""
    items = []

    # 1. Failed AgentRuns
    failed_runs = db.scalars(
        select(AgentRun)
        .where(AgentRun.status == "failed")
        .order_by(desc(AgentRun.id))
        .limit(limit)
    ).all()
    for fr in failed_runs:
        items.append({
            "type": "AGENT_FAILURE",
            "source": f"{fr.agent_type.capitalize()} Agent",
            "workflowId": f"wf-{fr.agent_type[:4]}-{fr.id:04d}",
            "message": fr.error or "Workflow terminated with failure state",
            "severity": "HIGH",
            "timestamp": fr.started_at.isoformat() if fr.started_at else "",
        })

    # 2. Failed AgentExecutionMetrics
    failed_metrics = db.scalars(
        select(AgentExecutionMetric)
        .where(AgentExecutionMetric.status == "FAILED")
        .order_by(desc(AgentExecutionMetric.created_at))
        .limit(limit)
    ).all()
    for m in failed_metrics:
        items.append({
            "type": "AGENT_FAILURE",
            "source": m.agent_name,
            "workflowId": m.workflow_id,
            "message": m.error_message or "Execution exception occurred",
            "severity": "HIGH",
            "timestamp": m.created_at.isoformat() if m.created_at else "",
        })

    # 3. Guardrail blocks
    guardrail_blocks = db.scalars(
        select(GuardrailLog)
        .where(GuardrailLog.decision.in_(["BLOCKED", "FLAGGED"]))
        .order_by(desc(GuardrailLog.created_at))
        .limit(limit)
    ).all()
    for g in guardrail_blocks:
        items.append({
            "type": "GUARDRAIL_BLOCKED",
            "source": g.agent_name,
            "workflowId": g.workflow_id or "N/A",
            "message": f"Rule [{g.rule_name}]: {g.reason}",
            "severity": "MEDIUM",
            "timestamp": g.created_at.isoformat() if g.created_at else "",
        })

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]


def _search_provider_usage(db: Session) -> dict[str, Any]:
    """Web search providers (Exa, Brave, SearXNG, …) as used by discovery runs.

    Totals come only from what each run recorded in its source report
    (`agent_runs.summary.sources`): calls, successes, failures, results and the
    cost the provider itself reported. A provider that doesn't report a price
    (e.g. Brave) has `costUsd: null` — no estimate is made."""
    from backend.services.discovery_agent.search_providers.engine import search_engine

    totals: dict[str, dict[str, Any]] = {}
    runs_counted = 0
    for run in db.scalars(select(AgentRun).where(AgentRun.agent_type == "discovery").order_by(AgentRun.id)).all():
        rows = ((run.summary or {}).get("sources") or {}).get("sources") or []
        if not rows:
            continue
        runs_counted += 1
        for row in rows:
            if row.get("kind") != "search_provider" or not row.get("calls"):
                continue
            t = totals.setdefault(row["id"], {
                "runs": 0, "calls": 0, "successes": 0, "failures": 0, "rateLimited": 0, "results": 0,
                "costUsd": None, "lastUsedAt": None,
            })
            t["runs"] += 1
            t["calls"] += row.get("calls") or 0
            t["successes"] += row.get("jobs_ok") or 0
            t["failures"] += row.get("jobs_failed") or 0
            t["rateLimited"] += row.get("rate_limited") or 0
            t["results"] += row.get("results") or 0
            if row.get("cost_usd") is not None:
                t["costUsd"] = round((t["costUsd"] or 0) + float(row["cost_usd"]), 4)
            used_at = row.get("finished_at")
            if not isinstance(used_at, str):
                used_at = (run.completed_at or run.started_at).isoformat()
            if not t["lastUsedAt"] or used_at > t["lastUsedAt"]:
                t["lastUsedAt"] = used_at

    providers = []
    for pid, provider in search_engine.providers.items():
        usage = totals.pop(pid, None)
        providers.append({
            "id": pid,
            "name": provider.display_name or provider.provider_name,
            "isFree": bool(provider.is_free),
            "configured": bool(provider.is_configured()),
            "unavailableReason": provider.unavailable_reason(),
            **(usage or {"runs": 0, "calls": 0, "successes": 0, "failures": 0, "rateLimited": 0, "results": 0, "costUsd": None, "lastUsedAt": None}),
        })
    # Usage recorded for a provider no longer registered is still real usage.
    for pid, usage in totals.items():
        providers.append({"id": pid, "name": pid, "isFree": False, "configured": False, "unavailableReason": "No longer available", **usage})
    return {"runsCounted": runs_counted, "providers": providers}


def _legacy_run_usage(summary: dict[str, Any]) -> dict[str, Any]:
    """A run saved before per-run usage tracking: only its search-provider
    rows exist (in the usage block's shape here; `reprice` prices them).
    Queries and AI tokens weren't recorded, so they stay unknown."""
    rows = [r for r in ((summary.get("sources") or {}).get("sources") or []) if r.get("kind") == "search_provider"]
    return {
        "queries": None,
        "ai_models": None,
        "valid_events": summary.get("verified_events") or 0,
        "search_providers": [{
            "id": r["id"], "name": r.get("name") or r["id"], "calls": r.get("calls") or 0, "successes": r.get("jobs_ok") or 0,
            "failures": r.get("jobs_failed") or 0, "rate_limited": r.get("rate_limited") or 0, "results": r.get("results") or 0,
            "cost_usd": r.get("cost_usd"), "cost_basis": "reported_by_provider" if r.get("cost_usd") is not None else "unknown",
        } for r in rows],
    }


def _discovery_run_usage(db: Session, limit: int = 50) -> dict[str, Any]:
    """Each discovery run's own usage and estimated cost, newest first, from
    what the run stored in `agent_runs.summary["usage"]`. Runs saved before
    this tracking existed show their search-provider calls only (`tracked: false`)."""
    from backend.services.discovery_agent import run_usage
    from backend.services.discovery_agent.search_providers.engine import search_engine

    runs = db.scalars(
        select(AgentRun).where(AgentRun.agent_type == "discovery").order_by(desc(AgentRun.id)).limit(limit)
    ).all()
    history = []
    for run in runs:
        summary = run.summary or {}
        usage = summary.get("usage") or None
        tracked = bool(usage)
        if not tracked:
            if not ((summary.get("sources") or {}).get("sources")):
                continue  # nothing was recorded for this run (e.g. it failed before searching)
            usage = _legacy_run_usage(summary)
        usage = run_usage.reprice(usage, search_engine.providers)  # stored counts, today's prices
        history.append({
            "runId": run.id,
            "status": run.status,
            "startedAt": run.started_at.isoformat() if run.started_at else None,
            "completedAt": run.completed_at.isoformat() if run.completed_at else None,
            "tracked": tracked,
            "validEvents": summary.get("verified_events") or 0,
            **usage,
        })
    return {"latest": history[0] if history else None, "history": history}


@router.get("/ai-usage")
def observability_ai_usage(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Breakdown of LLM usage by model, daily token consumption, and cost attribution."""
    # Only what executions actually recorded: no per-run estimates, no assumed models.
    model_breakdown: dict[str, dict[str, Any]] = {}
    for m in db.scalars(select(AgentExecutionMetric).limit(5000)).all():
        if (m.model_name or "").startswith("none ("):
            continue  # a run that called no AI model (its search cost is under web search providers)
        meta = m.meta_json or {}
        b = model_breakdown.setdefault(m.model_name or "unknown model", {"calls": 0, "promptTokens": 0, "completionTokens": 0, "totalTokens": 0, "costUsd": 0.0, "costComplete": True})
        b["calls"] += int(meta.get("calls") or 1)  # a discovery run stores one row per model with its call count
        b["promptTokens"] += m.prompt_tokens or 0
        b["completionTokens"] += m.completion_tokens or 0
        b["totalTokens"] += m.total_tokens or 0
        b["costUsd"] = round(b["costUsd"] + float(m.estimated_cost or 0), 5)
        if meta.get("cost_known") is False:
            b["costComplete"] = False

    filtered_models = {k: v for k, v in model_breakdown.items() if v["calls"] > 0}

    return {
        "models": filtered_models,
        "searchProviders": _search_provider_usage(db),
        "discoveryRuns": _discovery_run_usage(db),
        "currency": "USD",
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/guardrails")
def observability_guardrails(
    limit: int = Query(default=50, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    """List of recent guardrail inspection events and safety decisions."""
    logs = db.scalars(select(GuardrailLog).order_by(desc(GuardrailLog.id)).limit(limit)).all()
    return [
        {
            "id": l.id,
            "workflowId": l.workflow_id,
            "agentName": l.agent_name,
            "decision": l.decision,
            "reason": l.reason,
            "ruleName": l.rule_name,
            "inputSnippet": l.input_snippet,
            "createdAt": l.created_at.isoformat() if l.created_at else "",
        }
        for l in logs
    ]
