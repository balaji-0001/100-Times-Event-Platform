"""In-process background scheduler — what makes agents run automatically
with zero manual dashboard input, and without requiring Docker/n8n to be
running. Four independent asyncio loops, each on its own configurable
interval (see `core/config.py`):

  - Event Discovery Agent scan (`discovery_scan_interval_minutes`, default 60m)
  - Agent 2 outreach draft (`outreach_scan_interval_minutes`,  default 60m)
  - Agent 2 outreach follow-up sweep (`outreach_followup_interval_minutes`, default 24h)
  - Attendee reminders sweep (`attendee_notifications_interval_minutes`)

Every loop always runs, but each tick checks its own live, DB-persisted
switch and skips the actual work when it's off — so turning automatic
scanning on/off for Agent 1 (`services/discovery_agent/auto_toggle.py`),
Agent 2 (`services/social_agent/outreach/auto_toggle.py`, one switch covers
both of Agent 2's ticks) or attendee reminders takes effect immediately, no
restart required. Agent 2's ticks only ever draft messages to
PENDING_APPROVAL/FOLLOW_UP_DUE — nothing here ever sends an email; a human
still approves and sends every message by hand. (The community listening,
community discovery and community posting loops of the previous plan were
removed.)

Each tick opens its own short-lived DB session (never shares one across
ticks/loops) and never lets an exception kill the loop — a failed tick is
logged and the loop keeps running on schedule. n8n's equivalent Schedule
Trigger workflows (`infra/n8n/workflows/discovery.json`, `outreach_followup.
json`) remain available as an alternative/parity option.
"""

import asyncio
import logging

from backend.core.config import get_settings
from backend.db import SessionLocal
from backend.services.attendee_agent.auto_toggle import is_attendee_notifications_auto_enabled
from backend.services.attendee_agent.notifier import run_attendee_notifications
from backend.services.discovery_agent.auto_toggle import is_discovery_auto_enabled
from backend.services.discovery_agent.orchestrator import run_discovery_agent
from backend.services.social_agent.outreach.auto_toggle import is_outreach_auto_enabled
from backend.services.social_agent.outreach.followup import process_followups
from backend.services.social_agent.outreach.orchestrator import run_outreach_agent

logger = logging.getLogger("acquisition.scheduler")


async def _run_outreach_draft_tick() -> None:
    db = SessionLocal()
    try:
        if not is_outreach_auto_enabled(db):
            logger.debug("Agent 2 scheduled draft skipped — automatic outreach is off")
            return
        summary = run_outreach_agent(db)
        logger.info("Agent 2 scheduled draft: %s", summary.as_dict())
    except Exception:
        logger.exception("Agent 2 scheduled draft failed")
    finally:
        db.close()


async def _run_followup_tick() -> None:
    db = SessionLocal()
    try:
        if not is_outreach_auto_enabled(db):
            logger.debug("Agent 2 scheduled follow-up sweep skipped — automatic outreach is off")
            return
        summary = process_followups(db)
        logger.info("Outreach follow-up sweep: %s", summary)
    except Exception:
        logger.exception("Outreach follow-up sweep failed")
    finally:
        db.close()


async def _run_discovery_scan_tick() -> None:
    db = SessionLocal()
    try:
        if not is_discovery_auto_enabled(db):
            logger.debug("Event Discovery Agent scheduled scan skipped — automatic discovery is off")
            return
        summary = run_discovery_agent(db)
        logger.info("Event Discovery Agent scheduled scan: %s", summary.as_dict())
    except Exception:
        logger.exception("Event Discovery Agent scheduled scan failed")
    finally:
        db.close()


async def _run_attendee_notifications_tick() -> None:
    db = SessionLocal()
    try:
        if not is_attendee_notifications_auto_enabled(db):
            logger.debug("Attendee notification sweep skipped — automatic notifications are off")
            return
        summary = run_attendee_notifications(db)
        db.commit()
        logger.info("Attendee notification sweep: %s", summary)
    except Exception:
        db.rollback()
        logger.exception("Attendee notification sweep failed")
    finally:
        db.close()


def _saved_discovery_interval(default: int):
    """Automatic discovery's interval from the saved Discovery configuration,
    read at every cycle (falls back to DISCOVERY_SCAN_INTERVAL_MINUTES)."""
    def interval() -> int:
        from backend.services.discovery_agent.auto_toggle import get_discovery_auto_settings

        try:
            with SessionLocal() as db:
                value = get_discovery_auto_settings(db).get("interval_minutes")
            return int(value) if isinstance(value, (int, float)) and value > 0 else default
        except Exception:
            return default

    return interval


def _saved_outreach_interval(key: str, default: int):
    """An interval read from the saved Outreach settings at every cycle, so a
    change in the UI applies without a restart (falls back to `default`)."""
    def interval() -> int:
        from backend.services.social_agent.outreach.auto_toggle import get_outreach_auto_settings

        try:
            with SessionLocal() as db:
                value = get_outreach_auto_settings(db).get(key)
            return int(value) if isinstance(value, (int, float)) and value > 0 else default
        except Exception:
            return default

    return interval


async def _loop(name: str, interval_minutes, tick) -> None:
    """`interval_minutes` is a number or a function returning the current one."""
    current = interval_minutes() if callable(interval_minutes) else interval_minutes
    logger.info("Starting %s loop (every %d minute(s))", name, current)
    while True:
        minutes = interval_minutes() if callable(interval_minutes) else interval_minutes
        await asyncio.sleep(max(int(minutes), 1) * 60)
        # The ticks call long, synchronous agent runs (web reads, DB writes);
        # run them on a worker thread so the API's event loop keeps serving
        # requests meanwhile.
        await asyncio.to_thread(lambda: asyncio.run(tick()))


def start_background_scheduler() -> list[asyncio.Task]:
    """Called once from `main.py`'s lifespan startup. Returns the created
    tasks so lifespan can cancel them cleanly on shutdown.

    Every loop always starts — each tick is a no-op unless its own live
    toggle is on, so starting them alone never spends API credits."""
    settings = get_settings()
    return [
        asyncio.create_task(_loop("event-discovery", _saved_discovery_interval(settings.discovery_scan_interval_minutes), _run_discovery_scan_tick)),
        asyncio.create_task(_loop(
            "outreach-draft", _saved_outreach_interval("draft_interval_minutes", settings.outreach_scan_interval_minutes), _run_outreach_draft_tick
        )),
        asyncio.create_task(_loop(
            "outreach-followup", _saved_outreach_interval("followup_interval_minutes", settings.outreach_followup_interval_minutes), _run_followup_tick
        )),
        asyncio.create_task(
            _loop("attendee-notifications", settings.attendee_notifications_interval_minutes, _run_attendee_notifications_tick)
        ),
    ]


async def stop_background_scheduler(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
