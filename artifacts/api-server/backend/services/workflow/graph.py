"""LangGraph orchestration between Agent 1 (organizer discovery) and Agent 2
(organizer outreach).

The graph only sequences, validates and records — it adds no LLM calls of its
own. Each node invokes one LangChain tool from `tools.py`, which calls the
same route function the console buttons call, so every step still writes its
own `AgentRun` row and every drafted email still stops at PENDING_APPROVAL.

    START -> discover -> draft_outreach -> process_followups -> finalize -> END

Every node runs and records a step (completed / failed / skipped), so a
run's audit trail always lists all three agents' outcomes — "skipped: not
requested" included. State is a typed `WorkflowState`, checkpointed in memory
per run, and the final state is written verbatim into an
`AgentRun(agent_type="workflow")` row so a pipeline run is auditable next to
the agents' own runs.

Error handling, per node:
- transient failures (DB lock, network blip) are retried once by LangGraph's
  `RetryPolicy`;
- anything else — a validation error, or an agent run that ended `failed` —
  is recorded in `steps`/`errors` and the workflow continues to `finalize`,
  which grades the whole run completed / partial / failed;
- if Agent 1 failed because the AI provider is not configured, Agent 2 is
  skipped rather than started, since it would fail on the same precondition.
"""

import logging
import operator
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

import httpx
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.models import AgentRun
from backend.services.workflow.tools import build_tools

logger = logging.getLogger(__name__)

WORKFLOW_AGENT_TYPE = "workflow"
NOT_CONFIGURED_MARKER = "AI provider is not configured"

# Worth a second attempt: a transient DB lock or a network hiccup. Everything
# else is recorded as a failed step and the workflow moves on.
TRANSIENT_ERRORS: tuple[type[Exception], ...] = (OperationalError, httpx.TransportError)
_RETRY = RetryPolicy(max_attempts=2, initial_interval=0.5, retry_on=TRANSIENT_ERRORS)


class StepRecord(TypedDict):
    node: str
    status: str  # completed | failed | skipped
    started_at: str
    finished_at: str
    duration_ms: int
    error: str | None


class WorkflowState(TypedDict, total=False):
    # --- inputs ---
    discovery: dict[str, Any] | None  # DiscoveryToolInput fields; None skips Agent 1
    outreach: dict[str, Any] | None  # OutreachToolInput fields; None skips Agent 2
    run_followups: bool
    # --- outputs ---
    discovery_result: dict[str, Any] | None
    outreach_result: dict[str, Any] | None
    followup_result: dict[str, Any] | None
    steps: Annotated[list[StepRecord], operator.add]
    errors: Annotated[list[str], operator.add]
    status: str  # running | completed | partial | failed


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record(node: str, status: str, started: datetime, error: str | None = None) -> StepRecord:
    finished = _now()
    return StepRecord(
        node=node,
        status=status,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        duration_ms=int((finished - started).total_seconds() * 1000),
        error=error,
    )


def _skipped(node: str, reason: str) -> StepRecord:
    started = _now()
    return _record(node, "skipped", started, reason)


def _run_step(node: str, action: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any] | None, StepRecord]:
    """Runs one agent tool. Transient errors propagate so LangGraph's retry
    policy can re-run the node; any other exception, or an agent run that
    finished `failed`, becomes a failed step record."""
    started = _now()
    try:
        result = action()
    except TRANSIENT_ERRORS:
        raise
    except Exception as exc:  # validation error, programming error — recorded, never hidden
        logger.exception("Workflow step %s raised", node)
        return None, _record(node, "failed", started, f"{type(exc).__name__}: {exc}")

    if result.get("status") == "failed":
        detail = result.get("error") or "agent run failed"
        return result, _record(node, "failed", started, f"agent run #{result.get('runId')} failed: {detail}")
    return result, _record(node, "completed", started)


def build_workflow(db: Session, *, checkpointer: BaseCheckpointSaver | None = None):
    """Compiles the graph with its tools bound to `db` (one session per run)."""
    tools = build_tools(db)

    def discover(state: WorkflowState) -> dict[str, Any]:
        if state.get("discovery") is None:
            return {"discovery_result": None, "steps": [_skipped("discover", "not requested")]}
        result, step = _run_step("discover", lambda: tools["run_discovery"].invoke(state["discovery"]))
        return {"discovery_result": result, "steps": [step], "errors": [step["error"]] if step["error"] else []}

    def draft_outreach(state: WorkflowState) -> dict[str, Any]:
        if state.get("outreach") is None:
            return {"outreach_result": None, "steps": [_skipped("draft_outreach", "not requested")]}
        discovery_error = (state.get("discovery_result") or {}).get("error") or ""
        if NOT_CONFIGURED_MARKER in discovery_error:
            reason = "skipped: Agent 1 failed because the AI provider is not configured, so Agent 2 would fail the same way"
            return {"outreach_result": None, "steps": [_skipped("draft_outreach", reason)], "errors": [f"draft_outreach {reason}"]}
        result, step = _run_step("draft_outreach", lambda: tools["run_outreach"].invoke(state["outreach"]))
        return {"outreach_result": result, "steps": [step], "errors": [step["error"]] if step["error"] else []}

    def process_followups(state: WorkflowState) -> dict[str, Any]:
        if not state.get("run_followups"):
            return {"followup_result": None, "steps": [_skipped("process_followups", "not requested")]}
        result, step = _run_step("process_followups", lambda: tools["run_followups"].invoke({}))
        return {"followup_result": result, "steps": [step], "errors": [step["error"]] if step["error"] else []}

    def finalize(state: WorkflowState) -> dict[str, Any]:
        attempted = [step for step in state.get("steps", []) if step["status"] != "skipped"]
        failed = [step for step in attempted if step["status"] == "failed"]
        if attempted and len(failed) == len(attempted):
            status = "failed"
        elif failed:
            status = "partial"
        else:
            status = "completed"
        return {"status": status}

    graph = StateGraph(WorkflowState)
    graph.add_node("discover", discover, retry_policy=_RETRY)
    graph.add_node("draft_outreach", draft_outreach, retry_policy=_RETRY)
    graph.add_node("process_followups", process_followups, retry_policy=_RETRY)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "discover")
    graph.add_edge("discover", "draft_outreach")
    graph.add_edge("draft_outreach", "process_followups")
    graph.add_edge("process_followups", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver(), name="organizer-pipeline")


def run_pipeline(
    db: Session,
    *,
    discovery: dict[str, Any] | None,
    outreach: dict[str, Any] | None,
    run_followups: bool = False,
) -> dict[str, Any]:
    """Runs Agent 1 -> Agent 2 -> follow-ups as one workflow and records it as
    an `AgentRun(agent_type="workflow")`. Blocks until done, like the agents'
    own manual triggers. Pass `None` for `discovery`/`outreach` to skip that
    agent; `{}` runs it with the configured defaults."""
    inputs: dict[str, Any] = {"discovery": discovery, "outreach": outreach, "run_followups": run_followups}
    run = AgentRun(
        agent_type=WORKFLOW_AGENT_TYPE,
        status="running",
        started_at=_now(),
        config_snapshot=inputs,
        summary={},
        created_at=_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    workflow = build_workflow(db)
    config = {"configurable": {"thread_id": f"workflow-{run.id}"}}
    try:
        final: WorkflowState = workflow.invoke({**inputs, "steps": [], "errors": [], "status": "running"}, config=config)
    except Exception as exc:  # retries exhausted or an unexpected crash — record it honestly, never lose the run
        logger.exception("Workflow run #%s crashed", run.id)
        db.rollback()
        final = WorkflowState(steps=[], errors=[f"workflow crashed: {type(exc).__name__}: {exc}"], status="failed")

    errors = list(final.get("errors", []))
    run.status = final.get("status", "failed")
    run.completed_at = _now()
    run.error = "; ".join(errors) or None
    run.summary = {
        "steps": final.get("steps", []),
        "discovery": final.get("discovery_result"),
        "outreach": final.get("outreach_result"),
        "followups": final.get("followup_result"),
        "errors": errors,
    }
    db.add(run)
    db.commit()

    return {"runId": run.id, "status": run.status, **run.summary}
