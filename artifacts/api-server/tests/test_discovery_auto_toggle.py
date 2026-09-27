"""Unit tests for the live discovery auto-scan toggle
(`services/discovery_agent/auto_toggle.py`) and the scheduler tick that
reads it (`services/social_agent/scheduler.py`)."""

import asyncio

import pytest

from backend.core.config import get_settings
from backend.models import AgentSetting
from backend.services.discovery_agent import auto_toggle
from backend.services.social_agent import scheduler


def test_defaults_to_disabled_when_no_row_exists(db_session):
    assert auto_toggle.is_discovery_auto_enabled(db_session) is False


def test_set_then_get_round_trips(db_session):
    assert auto_toggle.set_discovery_auto_enabled(db_session, True) is True
    assert auto_toggle.is_discovery_auto_enabled(db_session) is True

    assert auto_toggle.set_discovery_auto_enabled(db_session, False) is False
    assert auto_toggle.is_discovery_auto_enabled(db_session) is False


def test_toggling_reuses_the_same_row_rather_than_duplicating(db_session):
    auto_toggle.set_discovery_auto_enabled(db_session, True)
    auto_toggle.set_discovery_auto_enabled(db_session, False)
    auto_toggle.set_discovery_auto_enabled(db_session, True)

    assert db_session.query(AgentSetting).count() == 1


def test_scheduler_tick_skips_the_agent_run_when_toggle_is_off(db_session, monkeypatch):
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)  # the tick closes its session; keep it open for assertions
    calls = []
    monkeypatch.setattr(scheduler, "run_discovery_agent", lambda db: calls.append(db) or pytest.fail("should not run while the toggle is off"))

    asyncio.run(scheduler._run_discovery_scan_tick())

    assert calls == []


def test_scheduler_tick_runs_the_agent_when_toggle_is_on(db_session, monkeypatch):
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    auto_toggle.set_discovery_auto_enabled(db_session, True)
    calls = []
    monkeypatch.setattr(scheduler, "run_discovery_agent", lambda db: calls.append(db))

    asyncio.run(scheduler._run_discovery_scan_tick())

    assert calls == [db_session]


def test_scheduler_tick_survives_a_failed_run(db_session, monkeypatch):
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    auto_toggle.set_discovery_auto_enabled(db_session, True)

    def boom(db):
        raise RuntimeError("transient failure")

    monkeypatch.setattr(scheduler, "run_discovery_agent", boom)

    asyncio.run(scheduler._run_discovery_scan_tick())  # must not raise


def test_start_background_scheduler_always_creates_the_discovery_loop(monkeypatch):
    """The discovery loop must run regardless of ENABLE_BACKGROUND_SCHEDULER
    — its own tick is the thing gated by the live toggle, not this env var."""
    settings = get_settings()
    created = []
    monkeypatch.setattr(scheduler.asyncio, "create_task", lambda coro: created.append(coro) or coro.close())

    monkeypatch.setattr(settings, "enable_background_scheduler", False)
    scheduler.start_background_scheduler()
    assert len(created) == 1  # only the always-on event-discovery loop

    created.clear()
    monkeypatch.setattr(settings, "enable_background_scheduler", True)
    scheduler.start_background_scheduler()
    assert len(created) == 4  # discovery + the three legacy loops
