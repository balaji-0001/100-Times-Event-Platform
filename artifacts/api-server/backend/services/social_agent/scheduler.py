"""In-process background scheduler — what makes agents run automatically
with zero manual dashboard input, and without requiring Docker/n8n to be
running. Eight independent asyncio loops, each on its own configurable
interval (see `core/config.py`):

  - Attendee Agent scan   (`attendee_scan_interval_minutes`,   default 15m)
  - Organizer Agent scan  (`organizer_scan_interval_minutes`,  default 30m)
  - Event Discovery Agent scan (`discovery_scan_interval_minutes`, default 60m)
  - Agent 2 outreach draft (`outreach_scan_interval_minutes`,  default 60m)
  - Agent 2 outreach follow-up sweep (`outreach_followup_interval_minutes`, default 24h)
  - Agent 5 community-discovery scan (`community_discovery_scan_interval_minutes`, default 60m)
  - Agent 4 community-promotion draft (`community_promotion_scan_interval_minutes`, default 60m)

The first two are gated by `ENABLE_BACKGROUND_SCHEDULER` (an env var — off
by default, needs a restart to change). The other five ALWAYS run as
loops, but each tick checks its own live, DB-persisted switch and skips the
actual work when it's off — so turning automatic scanning on/off for
Agent 1 (`services/discovery_agent/auto_toggle.py`, flipped from the
console's Dashboard toggle), Agent 2 (`services/social_agent/outreach/
auto_toggle.py`, same pattern, one switch covers both of Agent 2's ticks),
or Agent 5 (`services/community_agent/auto_toggle.py`, same pattern again)
takes effect immediately, no restart required, independent of the two
legacy-flag-gated loops. Agent 2's ticks only ever draft messages to
PENDING_APPROVAL/FOLLOW_UP_DUE — nothing here ever sends an email; a human
still approves and sends every message by hand. Agent 5 only ever discovers
leads — nothing here ever joins a community or connects a bot.

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
from backend.services.community_agent.auto_toggle import is_community_discovery_auto_enabled
from backend.services.community_agent.orchestrator import run_community_discovery_agent
from backend.services.discovery_agent.auto_toggle import is_discovery_auto_enabled
from backend.services.discovery_agent.orchestrator import run_discovery_agent
from backend.services.social_agent.community_promotion_auto_toggle import is_community_promotion_auto_enabled
from backend.services.social_agent.community_promotion_orchestrator import run_community_promotion_agent
from backend.services.social_agent.orchestrator import SocialAgentOrchestrator
from backend.services.social_agent.outreach.auto_toggle import is_outreach_auto_enabled
from backend.services.social_agent.outreach.followup import process_followups
from backend.services.social_agent.outreach.orchestrator import run_outreach_agent

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


async def _run_community_discovery_scan_tick() -> None:
    db = SessionLocal()
    try:
        if not is_community_discovery_auto_enabled(db):
            logger.debug("Community Discovery Agent scheduled scan skipped — automatic discovery is off")
            return
        summary = run_community_discovery_agent(db)
        logger.info("Community Discovery Agent scheduled scan: %s", summary.as_dict())
    except Exception:
        logger.exception("Community Discovery Agent scheduled scan failed")
    finally:
        db.close()


async def _run_community_promotion_tick() -> None:
    db = SessionLocal()
    try:
        if not is_community_promotion_auto_enabled(db):
            logger.debug("Agent 4 community-promotion scheduled draft skipped — automatic drafting is off")
            return
        summary = run_community_promotion_agent(db)
        logger.info("Agent 4 community-promotion scheduled draft: %s", summary.as_dict())
    except Exception:
        logger.exception("Agent 4 community-promotion scheduled draft failed")
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


async def _loop(name: str, interval_minutes: int, tick) -> None:
    interval_seconds = max(interval_minutes, 1) * 60
    logger.info("Starting %s loop (every %d minute(s))", name, interval_minutes)
    while True:
        await asyncio.sleep(interval_seconds)
        await tick()


def start_background_scheduler() -> list[asyncio.Task]:
    """Called once from `main.py`'s lifespan startup. Returns the created
    tasks so lifespan can cancel them cleanly on shutdown.

    The event-discovery and both outreach loops always start — each tick is
    a no-op unless its own live toggle is on, so starting them alone never
    spends API credits. The remaining two loops (attendee-scan,
    organizer-scan — unrelated to Agent 1/2) stay behind the legacy
    `ENABLE_BACKGROUND_SCHEDULER` env var, unchanged."""
    settings = get_settings()
    tasks = [
        asyncio.create_task(_loop("event-discovery", settings.discovery_scan_interval_minutes, _run_discovery_scan_tick)),
        asyncio.create_task(_loop("outreach-draft", settings.outreach_scan_interval_minutes, _run_outreach_draft_tick)),
        asyncio.create_task(_loop("outreach-followup", settings.outreach_followup_interval_minutes, _run_followup_tick)),
        asyncio.create_task(
            _loop("attendee-notifications", settings.attendee_notifications_interval_minutes, _run_attendee_notifications_tick)
        ),
    ]

    if not settings.enable_background_scheduler:
        logger.info("Legacy background scheduler disabled (ENABLE_BACKGROUND_SCHEDULER=false) — attendee-scan and organizer-scan stay off")
        return tasks

    tasks += [
        asyncio.create_task(_loop("attendee-scan", settings.attendee_scan_interval_minutes, _run_attendee_scan_tick)),
        asyncio.create_task(_loop("organizer-scan", settings.organizer_scan_interval_minutes, _run_organizer_scan_tick)),
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
