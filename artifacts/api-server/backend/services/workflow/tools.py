"""LangChain tools over the existing agent entrypoints.

Each tool wraps the same route function the admin console already calls
(`POST /discovery/run`, `POST /acquisition/outreach/batch-run`,
`POST /acquisition/outreach/process-followups`), so a workflow step does
exactly what a manual button press does — same config handling, same
`AgentRun` audit row, same summary shape, same PENDING_APPROVAL gate on
every drafted email. Nothing here talks to an LLM directly; the agents keep
their own calls through `ai_client.py`.

Input validation reuses the routes' own Pydantic request models (identical
bounds), so a bad workflow config is rejected before any paid work starts.
Invoke tools by field name (`search_depth`), not the API's camelCase alias.
"""

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.models import AgentRun
from backend.routes.discovery import trigger_discovery_run
from backend.routes.outreach import run_process_followups, trigger_batch_run
from backend.schemas import DiscoveryRunRequest, OutreachBatchRunRequest


class DiscoveryToolInput(DiscoveryRunRequest):
    """`DiscoveryRunRequest` (same fields, same bounds) addressable by field
    name as well as by alias, so it can be filled from Python without camelCase."""

    model_config = ConfigDict(populate_by_name=True)


class OutreachToolInput(OutreachBatchRunRequest):
    model_config = ConfigDict(populate_by_name=True)


class NoInput(BaseModel):
    pass


def _with_run_error(db: Session, result: dict[str, Any]) -> dict[str, Any]:
    """The routes return the run id + status but not the stored error text;
    add it so a failed step can explain itself in the workflow state."""
    run = db.get(AgentRun, result["runId"]) if result.get("runId") else None
    return {**result, "error": run.error if run else None}


def build_tools(db: Session) -> dict[str, StructuredTool]:
    """The three agent tools bound to one DB session (the request's), keyed by name."""

    def run_discovery(**kwargs: Any) -> dict[str, Any]:
        payload = DiscoveryToolInput.model_validate(kwargs)
        return _with_run_error(db, trigger_discovery_run(payload=payload, db=db, _user=None))

    def run_outreach(**kwargs: Any) -> dict[str, Any]:
        payload = OutreachToolInput.model_validate(kwargs)
        return _with_run_error(db, trigger_batch_run(payload=payload, db=db, _user=None))

    def run_followups() -> dict[str, Any]:
        return run_process_followups(db=db, _user=None)

    return {
        "run_discovery": StructuredTool.from_function(
            func=run_discovery,
            name="run_discovery",
            description="Run Agent 1 (organizer discovery) once: web-search for events across India, extract organizer details, validate, dedupe and store them. Every field is optional and falls back to the configured defaults.",
            args_schema=DiscoveryToolInput,
        ),
        "run_outreach": StructuredTool.from_function(
            func=run_outreach,
            name="run_outreach",
            description="Run Agent 2 (organizer outreach) once: pick eligible discovered organizers and draft a personalised invitation email for each. Drafts wait for human approval; nothing is sent.",
            args_schema=OutreachToolInput,
        ),
        "run_followups": StructuredTool.from_function(
            func=run_followups,
            name="run_followups",
            description="Process outreach follow-ups: draft the one allowed follow-up for delivered emails past the wait window, and close out those still unanswered after a second window.",
            args_schema=NoInput,
        ),
    }
