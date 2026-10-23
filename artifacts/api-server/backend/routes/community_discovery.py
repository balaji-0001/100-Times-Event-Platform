"""Community Discovery Agent ("Agent 5") admin API — manual trigger, run
history, read access to what the agent has found, and the approve/reject
decision gate. Mirrors `routes/discovery.py`'s shape exactly.

Every endpoint here requires ADMIN, same as `routes/discovery.py`. Approve/
reject/connection actions are audit-logged — one of the few places in this
admin surface that is, deliberately, since the brief explicitly asks for it.
"""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.db import get_db
from backend.dependencies import require_roles
from backend.models import AgentRun, Community, DiscoveredCommunity, User
from backend.schemas import (
    AgentRunOut,
    CommunityActionRequest,
    CommunityDiscoveryAutoStatusOut,
    CommunityDiscoveryAutoToggleRequest,
    CommunityDiscoveryRunRequest,
    CommunityDiscoveryStatsOut,
    DiscoveredCommunityOut,
)
from backend.services.audit import record_audit_log
from backend.services.community_agent.auto_toggle import is_community_discovery_auto_enabled, set_community_discovery_auto_enabled
from backend.services.community_agent.orchestrator import config_from_settings, run_community_discovery_agent

router = APIRouter(prefix="/community-discovery", tags=["community-discovery"])

_admin = Depends(require_roles("ADMIN"))
_VALID_ACTIONS = {
    "approve": "APPROVED",
    "reject": "REJECTED",
    "mark_connection_required": "CONNECTION_REQUIRED",
    "mark_connected": "CONNECTED",
    "mark_permission_missing": "PERMISSION_MISSING",
    "mark_promotion_restricted": "PROMOTION_RESTRICTED",
}


def _serialize(community: DiscoveredCommunity, db: Session) -> DiscoveredCommunityOut:
    """Once a lead is approved and materialized into a real `Community` row
    (`community.community_id` set), that row is the single source of truth
    for whether promotion is actually allowed and whether a real
    destination is connected — both can be changed directly on the
    `Community` row via `PATCH /acquisition/communities/{id}` (e.g. while
    setting up the real connection), so this always reads the live values
    from there instead of trusting this record's own, possibly-stale
    `promotion_allowed`/`connection_status` snapshot."""
    out = DiscoveredCommunityOut.model_validate(community)
    if community.community_id:
        real = db.get(Community, community.community_id)
        if real:
            out.promotion_allowed = real.promotion_allowed
            out.connection_status = "CONNECTED" if real.platform_ref else "CONNECTION_REQUIRED"
    return out


@router.post("/run")
def trigger_community_discovery_run(
    payload: CommunityDiscoveryRunRequest | None = None,
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> dict[str, Any]:
    """Manually runs one full community-discovery cycle now and returns the
    run id plus the structured summary. Blocks until the run finishes,
    same shape as `/discovery/run`."""
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
        if payload.seed_urls is not None:
            config.seed_urls = payload.seed_urls

    summary = run_community_discovery_agent(db, config)

    run = db.execute(select(AgentRun).where(AgentRun.agent_type == "community_discovery").order_by(AgentRun.id.desc())).scalars().first()
    return {
        "runId": run.id if run else None,
        "status": run.status if run else "unknown",
        "config": asdict(config),
        **summary.as_dict(),
    }


@router.get("/auto")
def get_community_discovery_auto(db: Session = Depends(get_db), _user: User = _admin) -> CommunityDiscoveryAutoStatusOut:
    settings = get_settings()
    return CommunityDiscoveryAutoStatusOut(enabled=is_community_discovery_auto_enabled(db), interval_minutes=settings.community_discovery_scan_interval_minutes)


@router.patch("/auto")
def set_community_discovery_auto(payload: CommunityDiscoveryAutoToggleRequest, db: Session = Depends(get_db), _user: User = _admin) -> CommunityDiscoveryAutoStatusOut:
    settings = get_settings()
    enabled = set_community_discovery_auto_enabled(db, payload.enabled)
    db.commit()
    return CommunityDiscoveryAutoStatusOut(enabled=enabled, interval_minutes=settings.community_discovery_scan_interval_minutes)


@router.get("/runs")
def list_runs(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db), _user: User = _admin) -> list[AgentRunOut]:
    stmt = select(AgentRun).where(AgentRun.agent_type == "community_discovery").order_by(AgentRun.id.desc()).limit(limit)
    return [AgentRunOut.model_validate(run) for run in db.execute(stmt).scalars().all()]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), _user: User = _admin) -> AgentRunOut:
    run = db.get(AgentRun, run_id)
    if run is None or run.agent_type != "community_discovery":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community discovery run not found")
    return AgentRunOut.model_validate(run)


@router.get("/stats")
def get_community_discovery_stats(db: Session = Depends(get_db), _user: User = _admin) -> CommunityDiscoveryStatsOut:
    """Real database counts, same discipline as `/discovery/stats` — never
    `.length` on a capped list."""

    def count(*where: Any) -> int:
        stmt = select(func.count()).select_from(DiscoveredCommunity)
        if where:
            stmt = stmt.where(*where)
        return db.scalar(stmt) or 0

    return CommunityDiscoveryStatsOut(
        communities_total=count(),
        needs_review_total=count(DiscoveredCommunity.approval_status == "NEEDS_REVIEW"),
        approved_total=count(DiscoveredCommunity.approval_status == "APPROVED"),
        connected_total=count(DiscoveredCommunity.connection_status == "CONNECTED"),
        telegram_total=count(DiscoveredCommunity.platform == "telegram"),
        discord_total=count(DiscoveredCommunity.platform == "discord"),
    )


@router.get("/communities")
def list_discovered_communities(
    platform: str | None = None,
    category: str | None = None,
    city: str | None = None,
    approval_status: str | None = Query(default=None, alias="approvalStatus"),
    limit: int = Query(default=50, ge=1, le=5000),
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> list[DiscoveredCommunityOut]:
    stmt = select(DiscoveredCommunity).options(selectinload(DiscoveredCommunity.sources)).order_by(DiscoveredCommunity.id.desc())
    if platform:
        stmt = stmt.where(DiscoveredCommunity.platform == platform)
    if category:
        stmt = stmt.where(DiscoveredCommunity.category.ilike(f"%{category}%"))
    if city:
        stmt = stmt.where(DiscoveredCommunity.city.ilike(f"%{city}%"))
    if approval_status:
        stmt = stmt.where(DiscoveredCommunity.approval_status == approval_status)
    stmt = stmt.limit(limit)
    return [_serialize(c, db) for c in db.execute(stmt).scalars().all()]


@router.get("/communities/{community_id}")
def get_discovered_community(community_id: int, db: Session = Depends(get_db), _user: User = _admin) -> DiscoveredCommunityOut:
    community = db.get(DiscoveredCommunity, community_id)
    if not community:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Discovered community not found")
    return _serialize(community, db)


@router.post("/communities/{community_id}/action")
def act_on_discovered_community(
    community_id: int, payload: CommunityActionRequest, db: Session = Depends(get_db), user: User = _admin,
) -> DiscoveredCommunityOut:
    community = db.get(DiscoveredCommunity, community_id)
    if not community:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Discovered community not found")

    new_status = _VALID_ACTIONS[payload.action]
    community.approval_status = new_status
    if payload.action == "reject":
        community.rejection_reason = payload.reason

    if payload.action == "approve":
        community.promotion_allowed = None  # still unknown — approving the LEAD isn't the same as confirming promotion policy
        if community.community_id is None:
            # Materialize into the real, postable-to Community row Agent 4's
            # existing pipeline already keys off — same relationship
            # `DiscoveredOrganizer` has to `Organizer` once a human acts on it.
            real_community = Community(
                platform=community.platform,
                name=community.name,
                slug=f"{community.platform}-{community.id}-{community.name}"[:200],
                url=community.canonical_url,
                rules_text=community.rules_text,
                promotion_allowed=False,  # still requires a separate, explicit policy confirmation before Agent 4 can use it
                automation_allowed=False,
                risk_level=community.risk_level if community.risk_level != "unknown" else "low",
                quality_score=max(0, min(community.confidence_score, 100)),
                discovered_community_id=community.id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(real_community)
            db.flush()
            community.community_id = real_community.id
            community.connection_status = "CONNECTION_REQUIRED"

    record_audit_log(
        db, actor=user.email, actor_id=user.id, action=f"COMMUNITY_{payload.action.upper()}",
        entity="DiscoveredCommunity", entity_id=community.id, result="SUCCESS",
        metadata={"reason": payload.reason} if payload.reason else None,
    )
    db.commit()
    db.refresh(community)
    return _serialize(community, db)
