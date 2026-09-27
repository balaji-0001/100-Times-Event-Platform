"""In-process background scheduler — what makes agents run automatically
with zero manual dashboard input, and without requiring Docker/n8n to be
running. Four independent asyncio loops, each on its own configurable
interval (see `core/config.py`):

  - Attendee Agent scan   (`attendee_scan_interval_minutes`,   default 15m)
  - Organizer Agent scan  (`organizer_scan_interval_minutes`,  default 30m)
  - Outreach follow-up sweep (`outreach_followup_interval_minutes`, default 24h)
  - Event Discovery Agent scan (`discovery_scan_interval_minutes`, default 60m)

The first three are gated by `ENABLE_BACKGROUND_SCHEDULER` (an env var — off
by default, needs a restart to change). The Event Discovery Agent scan loop
is different: it ALWAYS runs, but each tick checks the live, DB-persisted
`discovery_auto_enabled` switch (`services/discovery_agent/auto_toggle.py`,
flipped from the console's Dashboard toggle) and skips the actual work when
it's off — so turning discovery's automatic scan on/off takes effect
immediately, no restart required, independent of the other three loops.

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
from backend.services.discovery_agent.auto_toggle import is_discovery_auto_enabled
from backend.services.discovery_agent.orchestrator import run_discovery_agent
from backend.services.social_agent.orchestrator import SocialAgentOrchestrator
from backend.services.social_agent.outreach.followup import process_followups

logger = logging.getLogger("acquisition.scheduler")


async def _run_attendee_scan_tick() -> None:
    db = SessionLocal()
    try:
        result = SocialAgentOrchestrator.run_discussion_cycle(db=db)
        logger.info("Attendee Agent scheduled scan: %s", result.get("message"))
    except Exception:
        logger.exception("Attendee Agent scheduled scan failed")
    finally:
        db.close()


async def _run_organizer_scan_tick() -> None:
    db = SessionLocal()
    try:
        result = SocialAgentOrchestrator.run_organizer_discovery_cycle(db=db)
        logger.info("Organizer Agent scheduled scan: %s", result.get("message"))
    except Exception:
        logger.exception("Organizer Agent scheduled scan failed")
    finally:
        db.close()


async def _run_followup_tick() -> None:
    db = SessionLocal()
    try:
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


async def _loop(name: str, interval_minutes: int, tick) -> None:
    interval_seconds = max(interval_minutes, 1) * 60
    logger.info("Starting %s loop (every %d minute(s))", name, interval_minutes)
    while True:
        await asyncio.sleep(interval_seconds)
        await tick()


def start_background_scheduler() -> list[asyncio.Task]:
    """Called once from `main.py`'s lifespan startup. Returns the created
    tasks so lifespan can cancel them cleanly on shutdown.

    The event-discovery loop always starts — its tick is a no-op unless the
    live `discovery_auto_enabled` toggle is on, so this alone never spends
    API credits. The other three loops stay behind the
    `ENABLE_BACKGROUND_SCHEDULER` env var, unchanged."""
    settings = get_settings()
    tasks = [asyncio.create_task(_loop("event-discovery", settings.discovery_scan_interval_minutes, _run_discovery_scan_tick))]

    if not settings.enable_background_scheduler:
        logger.info("Legacy background scheduler disabled (ENABLE_BACKGROUND_SCHEDULER=false) — attendee-scan, organizer-scan and outreach-followup stay off")
        return tasks

    tasks += [
        asyncio.create_task(_loop("attendee-scan", settings.attendee_scan_interval_minutes, _run_attendee_scan_tick)),
        asyncio.create_task(_loop("organizer-scan", settings.organizer_scan_interval_minutes, _run_organizer_scan_tick)),
        asyncio.create_task(_loop("outreach-followup", settings.outreach_followup_interval_minutes, _run_followup_tick)),
    ]
    return tasks


async def stop_background_scheduler(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
