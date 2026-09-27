"""Tests for the LangChain/LangGraph layer (`backend/services/workflow/`).

The agents themselves are replaced by fakes at the route-function boundary
that the tools wrap, so these tests exercise the real tool validation, the
real graph routing/retry/state handling, and the real workflow route — with
no LLM call, no network, and no credits spent."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError

from backend.db import get_db
from backend.dependencies import get_current_user
from backend.models import AgentRun, User
from backend.routes import workflow as workflow_routes
from backend.services.social_agent.ai_client import AIClientError
from backend.services.workflow import graph as graph_module
from backend.services.workflow import llm as llm_module
from backend.services.workflow import tools as tools_module
from backend.services.workflow.graph import run_pipeline
from tests.conftest import FakeAIClient

NOT_CONFIGURED = "AI provider is not configured (AI_PROVIDER=gemini requires GEMINI_API_KEY)"


class _FakeAgents:
    """Stand-ins for the three route functions the tools call. Records every
    call; each response can be a dict or an exception to raise."""

    def __init__(self, discovery=None, outreach=None, followups=None):
        self.calls: list[tuple[str, Any]] = []
        self._responses = {
            "discovery": list(discovery or [{"runId": 101, "status": "completed", "new_events": 3}]),
            "outreach": list(outreach or [{"runId": 202, "status": "completed", "drafted": 2}]),
            "followups": list(followups or [{"stage1_drafted": 0, "stage2_closed": 1}]),
        }

    def _next(self, kind: str, payload: Any):
        self.calls.append((kind, payload))
        item = self._responses[kind].pop(0)
        if isinstance(item, Exception):
            raise item
        return dict(item)

    def discovery(self, payload, db, _user):
        return self._next("discovery", payload)

    def outreach(self, payload, db, _user):
        return self._next("outreach", payload)

    def followups(self, db, _user):
        return self._next("followups", None)


@pytest.fixture()
def agents(monkeypatch):
    def install(**responses):
        fake = _FakeAgents(**responses)
        monkeypatch.setattr(tools_module, "trigger_discovery_run", fake.discovery)
        monkeypatch.setattr(tools_module, "trigger_batch_run", fake.outreach)
        monkeypatch.setattr(tools_module, "run_process_followups", fake.followups)
        return fake

    return install


def _steps(result):
    return {step["node"]: step["status"] for step in result["steps"]}


# --- tools -------------------------------------------------------------------


def test_tools_validate_input_with_the_routes_own_bounds(db_session, agents):
    fake = agents()
    tools = tools_module.build_tools(db_session)

    result = tools["run_discovery"].invoke({"cities": ["Pune"], "search_depth": 2})
    assert result["status"] == "completed" and result["error"] is None
    kind, payload = fake.calls[0]
    assert kind == "discovery" and payload.cities == ["Pune"] and payload.search_depth == 2

    with pytest.raises(Exception, match="search_depth"):
        tools["run_discovery"].invoke({"search_depth": 0})  # below the route's ge=1 bound
    with pytest.raises(Exception, match="max_candidates"):
        tools["run_outreach"].invoke({"max_candidates": 999})  # above the route's le=200 bound
    assert len(fake.calls) == 1  # invalid input never reached an agent


def test_tools_attach_the_stored_run_error(db_session, agents):
    db_session.add(AgentRun(id=101, agent_type="discovery", status="failed", error=NOT_CONFIGURED, summary={}))
    db_session.commit()
    agents(discovery=[{"runId": 101, "status": "failed", "new_events": 0}])

    result = tools_module.build_tools(db_session)["run_discovery"].invoke({})

    assert result["status"] == "failed" and result["error"] == NOT_CONFIGURED


# --- graph -------------------------------------------------------------------


def test_full_pipeline_runs_agents_in_order_and_records_a_workflow_run(db_session, agents):
    fake = agents()

    result = run_pipeline(db_session, discovery={"search_depth": 1}, outreach={"max_candidates": 5}, run_followups=True)

    assert result["status"] == "completed"
    assert [kind for kind, _ in fake.calls] == ["discovery", "outreach", "followups"]
    assert _steps(result) == {"discover": "completed", "draft_outreach": "completed", "process_followups": "completed"}
    assert result["discovery"]["new_events"] == 3 and result["outreach"]["drafted"] == 2 and result["followups"]["stage2_closed"] == 1
    assert result["errors"] == []

    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "workflow").one()
    assert run.id == result["runId"] and run.status == "completed" and run.completed_at is not None
    assert run.config_snapshot == {"discovery": {"search_depth": 1}, "outreach": {"max_candidates": 5}, "run_followups": True}
    assert [step["node"] for step in run.summary["steps"]] == ["discover", "draft_outreach", "process_followups"]
    assert all(step["duration_ms"] >= 0 for step in run.summary["steps"])


def test_skipped_agents_are_recorded_not_run(db_session, agents):
    fake = agents()

    result = run_pipeline(db_session, discovery=None, outreach=None, run_followups=True)

    assert [kind for kind, _ in fake.calls] == ["followups"]
    assert _steps(result) == {"discover": "skipped", "draft_outreach": "skipped", "process_followups": "completed"}
    assert result["status"] == "completed"

    nothing = run_pipeline(db_session, discovery=None, outreach=None)
    assert nothing["status"] == "completed" and len(fake.calls) == 1


def test_unconfigured_provider_fails_discovery_and_skips_outreach(db_session, agents):
    db_session.add(AgentRun(id=101, agent_type="discovery", status="failed", error=NOT_CONFIGURED, summary={}))
    db_session.commit()
    fake = agents(discovery=[{"runId": 101, "status": "failed", "new_events": 0}])

    result = run_pipeline(db_session, discovery={}, outreach={})

    assert result["status"] == "failed"
    assert [kind for kind, _ in fake.calls] == ["discovery"]  # Agent 2 never started
    assert _steps(result) == {"discover": "failed", "draft_outreach": "skipped", "process_followups": "skipped"}
    assert any(NOT_CONFIGURED in error for error in result["errors"])
    assert any("Agent 2 would fail the same way" in error for error in result["errors"])
    workflow_run = db_session.query(AgentRun).filter(AgentRun.agent_type == "workflow").one()
    assert workflow_run.status == "failed" and NOT_CONFIGURED in workflow_run.error


def test_outreach_failure_after_successful_discovery_is_partial(db_session, agents):
    db_session.add(AgentRun(id=202, agent_type="outreach", status="failed", error="SMTP relay refused", summary={}))
    db_session.commit()
    agents(outreach=[{"runId": 202, "status": "failed", "drafted": 0}])

    result = run_pipeline(db_session, discovery={}, outreach={})

    assert result["status"] == "partial"
    assert _steps(result) == {"discover": "completed", "draft_outreach": "failed", "process_followups": "skipped"}
    assert result["errors"] == ["agent run #202 failed: SMTP relay refused"]


def test_invalid_config_is_a_failed_step_and_never_reaches_an_agent(db_session, agents):
    fake = agents()

    result = run_pipeline(db_session, discovery={"search_depth": 0}, outreach=None)

    assert result["status"] == "failed"
    assert fake.calls == []
    assert _steps(result) == {"discover": "failed", "draft_outreach": "skipped", "process_followups": "skipped"}
    assert "ValidationError" in result["errors"][0] and "search_depth" in result["errors"][0]


def test_transient_error_is_retried_once(db_session, agents):
    transient = OperationalError("SELECT 1", {}, Exception("database is locked"))
    fake = agents(discovery=[transient, {"runId": 101, "status": "completed", "new_events": 1}])

    result = run_pipeline(db_session, discovery={}, outreach=None)

    assert result["status"] == "completed"
    assert [kind for kind, _ in fake.calls] == ["discovery", "discovery"]
    assert _steps(result)["discover"] == "completed"


def test_exhausted_retries_are_recorded_as_a_failed_workflow_run(db_session, agents):
    transient = OperationalError("SELECT 1", {}, Exception("database is locked"))
    fake = agents(discovery=[transient, transient])

    result = run_pipeline(db_session, discovery={}, outreach={})

    assert result["status"] == "failed"
    assert len(fake.calls) == 2  # two attempts, then the workflow stops instead of running Agent 2
    assert result["errors"] and "OperationalError" in result["errors"][0]
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "workflow").one()
    assert run.status == "failed" and "OperationalError" in run.error


def test_graph_state_is_checkpointed_per_run(db_session, agents):
    agents()
    workflow = graph_module.build_workflow(db_session)
    config = {"configurable": {"thread_id": "test-thread"}}

    workflow.invoke({"discovery": {}, "outreach": None, "run_followups": False, "steps": [], "errors": [], "status": "running"}, config=config)

    snapshot = workflow.get_state(config)
    assert snapshot.values["status"] == "completed"
    assert [step["node"] for step in snapshot.values["steps"]] == ["discover", "draft_outreach", "process_followups"]
    assert snapshot.values["steps"][-1]["status"] == "skipped"
    assert snapshot.next == ()


# --- structured LLM runnable -------------------------------------------------


class _Verdict(BaseModel):
    is_event: bool
    confidence: int = Field(ge=0, le=100)


def test_structured_llm_validates_and_retries_once_on_bad_output(monkeypatch):
    calls = []

    def respond(kwargs):
        calls.append(kwargs)
        return {"is_event": True, "confidence": 500} if len(calls) == 1 else {"is_event": True, "confidence": 88}

    monkeypatch.setattr(llm_module, "get_ai_client", lambda: FakeAIClient(structured_response=respond))
    chain = llm_module.structured_llm(_Verdict, system="judge", tool_name="judge_event", tool_description="Is this an event?")

    verdict = chain.invoke("Pune Tech Expo, 12 March 2027")

    assert verdict == _Verdict(is_event=True, confidence=88)
    assert len(calls) == 2
    assert calls[0]["tool_name"] == "judge_event" and calls[0]["input_schema"]["required"] == ["is_event", "confidence"]


def test_structured_llm_does_not_retry_provider_errors(monkeypatch):
    monkeypatch.setattr(llm_module, "get_ai_client", lambda: FakeAIClient(configured=False))
    chain = llm_module.structured_llm(_Verdict, system="s", tool_name="t", tool_description="d")
    with pytest.raises(AIClientError, match="AI provider is not configured"):
        chain.invoke("anything")

    calls = []

    def boom(kwargs):
        calls.append(kwargs)
        raise AIClientError("Gemini API call failed: 429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm_module, "get_ai_client", lambda: FakeAIClient(structured_response=boom))
    with pytest.raises(AIClientError, match="429"):
        llm_module.structured_llm(_Verdict, system="s", tool_name="t", tool_description="d").invoke("anything")
    assert len(calls) == 1


# --- route -------------------------------------------------------------------


def _admin_user() -> User:
    return User(id=1, name="Admin", email="admin@100times.test", password_hash="x", role="ADMIN")


def _regular_user() -> User:
    return User(id=2, name="Attendee", email="attendee@100times.test", password_hash="x", role="USER")


def _app(db_session, user=None) -> FastAPI:
    app = FastAPI()
    app.include_router(workflow_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    if user is not None:
        app.dependency_overrides[get_current_user] = user
    return app


def test_workflow_routes_require_admin(db_session):
    with TestClient(_app(db_session)) as anonymous:
        assert anonymous.post("/api/workflow/run").status_code == 401
        assert anonymous.get("/api/workflow/runs").status_code == 401
    with TestClient(_app(db_session, _regular_user)) as non_admin:
        assert non_admin.post("/api/workflow/run").status_code == 403


def test_workflow_run_route_maps_body_to_tool_inputs_and_lists_runs(db_session, agents):
    fake = agents()
    client = TestClient(_app(db_session, _admin_user))

    response = client.post("/api/workflow/run", json={"discovery": {"cities": ["Pune"], "searchDepth": 2}, "outreach": {"maxCandidates": 3}, "runFollowups": True})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed" and body["runId"]
    assert [kind for kind, _ in fake.calls] == ["discovery", "outreach", "followups"]
    assert fake.calls[0][1].cities == ["Pune"] and fake.calls[0][1].search_depth == 2
    assert fake.calls[1][1].max_candidates == 3

    runs = client.get("/api/workflow/runs").json()
    assert [run["id"] for run in runs] == [body["runId"]]
    assert runs[0]["agentType"] == "workflow" and runs[0]["status"] == "completed"
    assert client.get(f"/api/workflow/runs/{body['runId']}").json()["summary"]["steps"][0]["node"] == "discover"
    assert client.get("/api/workflow/runs/999").status_code == 404

    skipped = client.post("/api/workflow/run", json={"skipDiscovery": True, "skipOutreach": True}).json()
    assert skipped["status"] == "completed" and len(fake.calls) == 3
    assert client.post("/api/workflow/run", json={"discovery": {"searchDepth": 0}}).status_code == 422
