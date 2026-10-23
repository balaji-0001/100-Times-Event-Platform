"""Agent 4 extension — Community Promotion admin API: trigger a batch
match+draft run, the live auto-toggle, and run history. Deliberately thin —
the actual approve/edit/publish actions on a drafted post reuse the
already-generic `/api/acquisition/opportunities/*` endpoints as-is (the
whole point of extending the existing pipeline instead of duplicating it).
"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.dependencies import require_roles
from backend.models import AgentRun, User
from backend.schemas import (
    AgentRunOut,
    CommunityPromotionAutoStatusOut,
    CommunityPromotionAutoToggleRequest,
    CommunityPromotionRunRequest,
)
from backend.services.social_agent.community_promotion_auto_toggle import is_community_promotion_auto_enabled, set_community_promotion_auto_enabled
from backend.services.social_agent.community_promotion_orchestrator import CommunityPromotionConfig, run_community_promotion_agent

router = APIRouter(prefix="/community-promotion", tags=["community-promotion"])

_admin = Depends(require_roles("ADMIN"))


@router.post("/run")
def trigger_community_promotion_run(
    payload: CommunityPromotionRunRequest | None = None,
    db: Session = Depends(get_db),
    _user: User = _admin,
) -> dict[str, Any]:
    """Matches eligible events to approved communities and drafts a
    standalone post for each good match. Every draft lands at `pending` —
    review and send it from the Organizer Outreach-style opportunities
    queue (`/api/acquisition/opportunities`), same approve/publish gate as
    the original discussion-reply flow."""
    config = CommunityPromotionConfig()
    if payload and payload.max_candidates is not None:
        config.max_candidates = payload.max_candidates

    summary = run_community_promotion_agent(db, config)
    run = db.execute(select(AgentRun).where(AgentRun.agent_type == "community_promotion").order_by(AgentRun.id.desc())).scalars().first()
    return {
        "runId": run.id if run else None,
        "status": run.status if run else "unknown",
        "config": asdict(config),
        **summary.as_dict(),
    }


@router.get("/auto")
def get_community_promotion_auto(db: Session = Depends(get_db), _user: User = _admin) -> CommunityPromotionAutoStatusOut:
    from backend.core.config import get_settings

    settings = get_settings()
    return CommunityPromotionAutoStatusOut(enabled=is_community_promotion_auto_enabled(db), interval_minutes=settings.community_promotion_scan_interval_minutes)


@router.patch("/auto")
def set_community_promotion_auto(payload: CommunityPromotionAutoToggleRequest, db: Session = Depends(get_db), _user: User = _admin) -> CommunityPromotionAutoStatusOut:
    from backend.core.config import get_settings

    settings = get_settings()
    enabled = set_community_promotion_auto_enabled(db, payload.enabled)
    db.commit()
    return CommunityPromotionAutoStatusOut(enabled=enabled, interval_minutes=settings.community_promotion_scan_interval_minutes)


@router.get("/runs")
def list_runs(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db), _user: User = _admin) -> list[AgentRunOut]:
    stmt = select(AgentRun).where(AgentRun.agent_type == "community_promotion").order_by(AgentRun.id.desc()).limit(limit)
    return [AgentRunOut.model_validate(run) for run in db.execute(stmt).scalars().all()]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), _user: User = _admin) -> AgentRunOut:
    run = db.get(AgentRun, run_id)
    if run is None or run.agent_type != "community_promotion":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community promotion run not found")
    return AgentRunOut.model_validate(run)
