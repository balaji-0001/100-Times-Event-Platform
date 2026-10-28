"""Unit tests for the scheduler's Agent 2 automation ticks: each tick is a
no-op while its live toggle is off, runs the real orchestrator call when the
toggle is on, and a failure inside a tick never raises out of it (matching
the discipline already proven for the discovery tick).

No pytest-asyncio in this project's dependencies, so each async tick is
driven with a plain `asyncio.run(...)` from an ordinary sync test function
rather than an `async def test_...` (which pytest would otherwise collect
but never actually await, silently passing without running anything)."""

import asyncio

import pytest

from backend.services.social_agent import scheduler
from backend.services.social_agent.outreach.auto_toggle import set_outreach_auto_enabled


@pytest.fixture(autouse=True)
def _use_test_session(db_session, monkeypatch):
    """Each tick opens its own `SessionLocal()` — point that at the shared
    in-memory test session instead of a real engine connection."""
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)


def test_outreach_draft_tick_is_a_noop_when_toggle_is_off(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "run_outreach_agent", lambda db: calls.append(db))

    asyncio.run(scheduler._run_outreach_draft_tick())

    assert calls == []


def test_outreach_draft_tick_runs_when_toggle_is_on(db_session, monkeypatch):
    set_outreach_auto_enabled(db_session, True)
    db_session.commit()
    calls = []

    class _Summary:
        @staticmethod
        def as_dict():
            return {"drafted": 0}

    monkeypatch.setattr(scheduler, "run_outreach_agent", lambda db: calls.append(db) or _Summary())

    asyncio.run(scheduler._run_outreach_draft_tick())

    assert calls == [db_session]


def test_outreach_draft_tick_logs_and_swallows_errors(db_session, monkeypatch):
    set_outreach_auto_enabled(db_session, True)
    db_session.commit()

    def _boom(db):
        raise RuntimeError("web search exploded")

    monkeypatch.setattr(scheduler, "run_outreach_agent", _boom)

    asyncio.run(scheduler._run_outreach_draft_tick())  # must not raise


def test_followup_tick_is_a_noop_when_toggle_is_off(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "process_followups", lambda db: calls.append(db))

    asyncio.run(scheduler._run_followup_tick())

    assert calls == []


def test_followup_tick_runs_when_toggle_is_on(db_session, monkeypatch):
    set_outreach_auto_enabled(db_session, True)
    db_session.commit()
    calls = []
    monkeypatch.setattr(scheduler, "process_followups", lambda db: calls.append(db) or {"followUpsDrafted": 0})

    asyncio.run(scheduler._run_followup_tick())

    assert calls == [db_session]


def test_followup_tick_logs_and_swallows_errors(db_session, monkeypatch):
    set_outreach_auto_enabled(db_session, True)
    db_session.commit()

    def _boom(db):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(scheduler, "process_followups", _boom)

    asyncio.run(scheduler._run_followup_tick())  # must not raise


def test_start_background_scheduler_always_starts_outreach_loops(monkeypatch):
    """Both Agent 2 loops (draft + follow-up) must start unconditionally,
    same as the event-discovery loop — each tick's own toggle check is what
    keeps them inert, not whether the loop exists at all."""
    created = []
    monkeypatch.setattr(scheduler.asyncio, "create_task", lambda coro: created.append(coro) or coro)
    settings = scheduler.get_settings()
    monkeypatch.setattr(settings, "enable_background_scheduler", False)

    tasks = scheduler.start_background_scheduler()

    # created a coroutine object per loop; close them to avoid "never awaited" warnings
    for coro in created:
        coro.close()

    assert len(tasks) == 6  # event-discovery, outreach-draft, outreach-followup, attendee-notifications, community-discovery, community-promotion — no attendee/organizer scan
