"""Organizer pipeline workflow API — runs Agent 1 (discovery) then Agent 2
(outreach drafting) then follow-up processing as one LangGraph workflow, and
exposes the workflow's own run history. ADMIN-only, like `/discovery`: one
call can trigger real, paid LLM work.

The agents' existing endpoints are untouched; this router only adds a way to
run them in sequence with shared state and a single audit record.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.dependencies import require_roles
from backend.models import AgentRun, User
from backend.schemas import AgentRunOut, DiscoveryRunRequest, OutreachBatchRunRequest
from backend.services.workflow.graph import WORKFLOW_AGENT_TYPE, run_pipeline

router = APIRouter(prefix="/workflow", tags=["workflow"])

_admin = Depends(require_roles("ADMIN"))


class WorkflowRunRequest(BaseModel):
    """Which agents to run, with the same per-run overrides their own
    endpoints accept. Everything is optional: an empty body runs discovery
    then outreach with the configured defaults and no follow-up sweep."""

    discovery: DiscoveryRunRequest | None = None
    skip_discovery: bool = Field(default=False, alias="skipDiscovery")
    outreach: OutreachBatchRunRequest | None = None
    skip_outreach: bool = Field(default=False, alias="skipOutreach")
    run_followups: bool = Field(default=False, alias="runFollowups")


@router.post("/run")
def trigger_workflow_run(
    payload: WorkflowRunRequest | None = None,
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> dict[str, Any]:
    payload = payload or WorkflowRunRequest()
    discovery = None if payload.skip_discovery else (payload.discovery or DiscoveryRunRequest()).model_dump(exclude_none=True)
    outreach = None if payload.skip_outreach else (payload.outreach or OutreachBatchRunRequest()).model_dump(exclude_none=True)
    return run_pipeline(db, discovery=discovery, outreach=outreach, run_followups=payload.run_followups)


@router.get("/runs", response_model=list[AgentRunOut])
def list_workflow_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[AgentRunOut]:
    stmt = select(AgentRun).where(AgentRun.agent_type == WORKFLOW_AGENT_TYPE).order_by(AgentRun.id.desc()).limit(limit)
    return [AgentRunOut.model_validate(run) for run in db.execute(stmt).scalars().all()]


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_workflow_run(run_id: int, db: Session = Depends(get_db), _user: User = _admin) -> AgentRunOut:
    run = db.get(AgentRun, run_id)
    if run is None or run.agent_type != WORKFLOW_AGENT_TYPE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow run not found")
    return AgentRunOut.model_validate(run)
