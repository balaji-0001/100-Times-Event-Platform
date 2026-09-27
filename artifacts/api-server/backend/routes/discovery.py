"""Event Discovery & Organizer Research Agent admin API — manual trigger,
run history, and read access to what the agent has found so far.

Every endpoint here requires ADMIN: unlike `acquisition.py`/`outreach.py`
(which currently have no auth dependency at all — a pre-existing gap, not a
pattern worth copying), this router can trigger real, paid LLM calls and
exposes scraped personal contact info (emails/phones), so it gets the same
`require_roles("ADMIN")` gate `routes/dashboard.py` already uses.
"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.db import get_db
from backend.dependencies import require_roles
from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer, User
from backend.schemas import (
    AgentRunOut,
    DiscoveredEventOut,
    DiscoveredOrganizerOut,
    DiscoveryAutoStatusOut,
    DiscoveryAutoToggleRequest,
    DiscoveryRunRequest,
)
from backend.services.discovery_agent.auto_toggle import is_discovery_auto_enabled, set_discovery_auto_enabled
from backend.services.discovery_agent.orchestrator import config_from_settings, run_discovery_agent

router = APIRouter(prefix="/discovery", tags=["event-discovery"])

_admin = Depends(require_roles("ADMIN"))


def _serialize_event(event: DiscoveredEvent) -> DiscoveredEventOut:
    return DiscoveredEventOut.model_validate(event)


def _serialize_organizer(organizer: DiscoveredOrganizer) -> DiscoveredOrganizerOut:
    return DiscoveredOrganizerOut.model_validate(organizer)


@router.post("/run")
def trigger_discovery_run(
    payload: DiscoveryRunRequest | None = None,
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> dict[str, Any]:
    """Manually runs one full discovery cycle now (the same work the
    background scheduler runs on `DISCOVERY_SCAN_INTERVAL_MINUTES`) and
    returns the run id plus the exact structured summary shape the spec
    requires. Blocks until the run finishes, like `/acquisition/organizer-
    scan`'s equivalent manual trigger."""
    config = config_from_settings(get_settings())
    if payload:
        if payload.cities is not None:
            config.cities = payload.cities
        if payload.states is not None:
            config.states = payload.states
        if payload.categories is not None:
            config.categories = payload.categories
        if payload.search_depth is not None:
            config.search_depth = payload.search_depth
        if payload.sources_per_query is not None:
            config.sources_per_query = payload.sources_per_query
        if payload.daily_limit is not None:
            config.daily_limit = payload.daily_limit
        if payload.confidence_threshold is not None:
            config.confidence_threshold = payload.confidence_threshold

    summary = run_discovery_agent(db, config)

    run = db.execute(select(AgentRun).where(AgentRun.agent_type == "discovery").order_by(AgentRun.id.desc())).scalars().first()
    return {
        "runId": run.id if run else None,
        "status": run.status if run else "unknown",
        "config": asdict(config),
        **summary.as_dict(),
    }


@router.get("/auto")
def get_discovery_auto(db: Session = Depends(get_db), _user: User = _admin) -> DiscoveryAutoStatusOut:
    """Live state of the discovery-scan on/off switch. When enabled, the
    background loop that's always running (see `services/social_agent/
    scheduler.py`) actually calls `run_discovery_agent` on its configured
    interval instead of skipping the tick."""
    settings = get_settings()
    return DiscoveryAutoStatusOut(enabled=is_discovery_auto_enabled(db), interval_minutes=settings.discovery_scan_interval_minutes)


@router.patch("/auto")
def set_discovery_auto(payload: DiscoveryAutoToggleRequest, db: Session = Depends(get_db), _user: User = _admin) -> DiscoveryAutoStatusOut:
    """Flip the switch. Takes effect on the next scheduler tick — no restart
    needed — and persists across restarts (`agent_settings` table)."""
    settings = get_settings()
    enabled = set_discovery_auto_enabled(db, payload.enabled)
    return DiscoveryAutoStatusOut(enabled=enabled, interval_minutes=settings.discovery_scan_interval_minutes)


@router.get("/runs")
def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[AgentRunOut]:
    stmt = select(AgentRun).where(AgentRun.agent_type == "discovery").order_by(AgentRun.id.desc()).limit(limit)
    return [AgentRunOut.model_validate(run) for run in db.execute(stmt).scalars().all()]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), _user: User = _admin) -> AgentRunOut:
    run = db.get(AgentRun, run_id)
    if run is None or run.agent_type != "discovery":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discovery run not found")
    return AgentRunOut.model_validate(run)


@router.get("/events")
def list_discovered_events(
    city: str | None = None,
    category: str | None = None,
    verification_status: str | None = Query(default=None, alias="verificationStatus"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[DiscoveredEventOut]:
    stmt = select(DiscoveredEvent).options(selectinload(DiscoveredEvent.sources)).order_by(DiscoveredEvent.id.desc())
    if city:
        stmt = stmt.where(DiscoveredEvent.city.ilike(f"%{city}%"))
    if category:
        stmt = stmt.where(DiscoveredEvent.category.ilike(f"%{category}%"))
    if verification_status:
        stmt = stmt.where(DiscoveredEvent.verification_status == verification_status)
    stmt = stmt.limit(limit)
    return [_serialize_event(event) for event in db.execute(stmt).scalars().all()]


@router.get("/organizers")
def list_discovered_organizers(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[DiscoveredOrganizerOut]:
    stmt = (
        select(DiscoveredOrganizer)
        .options(selectinload(DiscoveredOrganizer.contacts))
        .order_by(DiscoveredOrganizer.id.desc())
        .limit(limit)
    )
    return [_serialize_organizer(organizer) for organizer in db.execute(stmt).scalars().all()]
