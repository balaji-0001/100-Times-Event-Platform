"""Event Promotion Admin APIs.

Endpoints for managing cross-platform promotion jobs, approval workflows,
platform toggles, safe retries, and manual trigger dispatches.
"""

from datetime import datetime, timezone
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.dependencies import get_current_user, require_roles
from backend.models import Event, EventPromotionJob, PlatformPromotionSetting, User
from backend.services.social_agent.event_promotion_orchestrator import (
    SUPPORTED_PLATFORMS,
    approve_promotion_job,
    execute_promotion_job,
    get_or_init_platform_settings,
    retry_promotion_job,
    trigger_event_promotions,
)
from backend.services.social_agent.publishers import get_publisher

router = APIRouter(prefix="/promotions", tags=["promotions"])


class JobContentUpdateRequest(BaseModel):
    title: str | None = None
    content: str = Field(min_length=5, max_length=5000)
    destination_ref: str | None = None


class ApproveJobRequest(BaseModel):
    dry_run: bool | None = None


class TriggerEventPromotionRequest(BaseModel):
    platforms: list[str] | None = None
    force: bool = False


class PlatformSettingUpdateRequest(BaseModel):
    enabled: bool | None = None
    auto_publish: bool | None = None
    dry_run: bool | None = None
    default_destination: str | None = None
    rate_limit_per_day: int | None = Field(default=None, ge=1, le=500)


def _serialize_job(job: EventPromotionJob) -> dict[str, Any]:
    event_dict = None
    if job.event:
        event_dict = {
            "id": job.event.id,
            "title": job.event.title,
            "slug": job.event.slug,
            "startDate": str(job.event.start_date) if job.event.start_date else None,
            "format": job.event.format,
            "city": job.event.city_name,
            "category": job.event.category.name if job.event.category else None,
            "status": job.event.status,
            "image": job.event.image,
        }
    return {
        "id": job.id,
        "eventId": job.event_id,
        "event": event_dict,
        "platform": job.platform,
        "destinationRef": job.destination_ref,
        "status": job.status,
        "isDryRun": job.is_dry_run,
        "title": job.title,
        "content": job.content,
        "mediaUrls": job.media_urls or [],
        "utmParams": job.utm_params or {},
        "trackingUrl": job.tracking_url,
        "externalPostId": job.external_post_id,
        "publishedUrl": job.published_url,
        "retryCount": job.retry_count,
        "maxRetries": job.max_retries,
        "lastError": job.last_error,
        "approvalRequired": job.approval_required,
        "approvedBy": job.approved_by,
        "approvedAt": job.approved_at.isoformat() if job.approved_at else None,
        "publishedAt": job.published_at.isoformat() if job.published_at else None,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.get("/jobs")
def list_promotion_jobs(
    event_id: int | None = Query(None),
    platform: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Lists promotion jobs across all platforms with event summary details."""
    stmt = (
        select(EventPromotionJob)
        .options(
            selectinload(EventPromotionJob.event).selectinload(Event.category),
        )
        .order_by(desc(EventPromotionJob.created_at))
    )

    if event_id is not None:
        stmt = stmt.where(EventPromotionJob.event_id == event_id)
    if platform:
        stmt = stmt.where(EventPromotionJob.platform == platform.lower().strip())
    if status:
        stmt = stmt.where(EventPromotionJob.status == status.upper().strip())

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    jobs = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()

    return {
        "items": [_serialize_job(j) for j in jobs],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/jobs/{job_id}")
def get_promotion_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Retrieves full details for a single promotion job."""
    job = db.scalar(
        select(EventPromotionJob)
        .options(selectinload(EventPromotionJob.event).selectinload(Event.category))
        .where(EventPromotionJob.id == job_id)
    )
    if not job:
        raise HTTPException(status_code=404, detail="Promotion job not found.")
    return _serialize_job(job)


@router.post("/jobs/{job_id}/approve")
def approve_job(
    job_id: int,
    payload: ApproveJobRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Approves and dispatches a pending promotion job (live or dry-run)."""
    try:
        dry_run = payload.dry_run if payload else None
        job = approve_promotion_job(db, job_id, admin_email=user.email, dry_run=dry_run)
        return _serialize_job(job)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Promotion dispatch failed: {str(exc)}") from exc


@router.post("/jobs/{job_id}/reject")
def reject_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Rejects or cancels a pending promotion job."""
    job = db.get(EventPromotionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Promotion job not found.")
    job.status = "CANCELLED"
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Retries a failed promotion job."""
    try:
        job = retry_promotion_job(db, job_id)
        return _serialize_job(job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Retry failed: {str(exc)}") from exc


@router.patch("/jobs/{job_id}/content")
def update_job_content(
    job_id: int,
    payload: JobContentUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Edits generated promotional copy before approval or retry."""
    job = db.get(EventPromotionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Promotion job not found.")

    if payload.title is not None:
        job.title = payload.title.strip()
    job.content = payload.content.strip()
    if payload.destination_ref is not None:
        job.destination_ref = payload.destination_ref.strip()

    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


@router.get("/settings")
def get_promotion_settings(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    """Retrieves configuration and connection status for each platform."""
    settings_rows = get_or_init_platform_settings(db)
    result = []
    for s in settings_rows:
        publisher = get_publisher(s.platform)
        conn = publisher.validate_connection()
        result.append({
            "id": s.id,
            "platform": s.platform,
            "enabled": s.enabled,
            "autoPublish": s.auto_publish,
            "dryRun": s.dry_run,
            "defaultDestination": s.default_destination,
            "rateLimitPerDay": s.rate_limit_per_day,
            "customPromptTemplate": s.custom_prompt_template,
            "isConnected": conn.get("connected", False),
            "connectionMessage": conn.get("message", ""),
            "updatedAt": s.updated_at.isoformat() if s.updated_at else None,
        })
    return result


@router.patch("/settings/{platform}")
def update_platform_setting(
    platform: str,
    payload: PlatformSettingUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Updates per-platform settings (toggle enabled, auto-publish, dry-run)."""
    norm_platform = platform.lower().strip()
    setting = db.scalar(
        select(PlatformPromotionSetting).where(PlatformPromotionSetting.platform == norm_platform)
    )
    if not setting:
        get_or_init_platform_settings(db)
        setting = db.scalar(
            select(PlatformPromotionSetting).where(PlatformPromotionSetting.platform == norm_platform)
        )
    if not setting:
        raise HTTPException(status_code=404, detail=f"Platform '{platform}' not supported.")

    if payload.enabled is not None:
        setting.enabled = payload.enabled
    if payload.auto_publish is not None:
        setting.auto_publish = payload.auto_publish
    if payload.dry_run is not None:
        setting.dry_run = payload.dry_run
    if payload.default_destination is not None:
        setting.default_destination = payload.default_destination.strip() or None
    if payload.rate_limit_per_day is not None:
        setting.rate_limit_per_day = payload.rate_limit_per_day

    setting.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(setting)

    publisher = get_publisher(setting.platform)
    conn = publisher.validate_connection()

    return {
        "id": setting.id,
        "platform": setting.platform,
        "enabled": setting.enabled,
        "autoPublish": setting.auto_publish,
        "dryRun": setting.dry_run,
        "defaultDestination": setting.default_destination,
        "rateLimitPerDay": setting.rate_limit_per_day,
        "customPromptTemplate": setting.custom_prompt_template,
        "isConnected": conn.get("connected", False),
        "connectionMessage": conn.get("message", ""),
        "updatedAt": setting.updated_at.isoformat() if setting.updated_at else None,
    }


@router.post("/events/{event_id}/trigger")
def trigger_event_promotion_manually(
    event_id: int,
    payload: TriggerEventPromotionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, Any]]:
    """Manually triggers or re-dispatches promotion for a published event."""
    event = db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event #{event_id} not found.")

    if event.status != "published" and (event.lifecycle_state or "").upper() != "PUBLISHED":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot promote event with status '{event.status}'. Only published events can be promoted.",
        )

    force = payload.force if payload else False
    target_platforms = payload.platforms if payload else None

    jobs = trigger_event_promotions(
        db,
        event,
        actor=user.email,
        force=force,
        platforms=target_platforms,
    )
    return [_serialize_job(j) for j in jobs]


@router.get("/stats")
def get_promotion_stats(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict[str, Any]:
    """Provides high-level metrics for the promotion dashboard."""
    total_jobs = db.scalar(select(func.count(EventPromotionJob.id))) or 0
    published = db.scalar(select(func.count(EventPromotionJob.id)).where(EventPromotionJob.status == "PUBLISHED")) or 0
    dry_run = db.scalar(select(func.count(EventPromotionJob.id)).where(EventPromotionJob.status == "DRY_RUN")) or 0
    pending = db.scalar(select(func.count(EventPromotionJob.id)).where(EventPromotionJob.status == "PENDING_APPROVAL")) or 0
    failed = db.scalar(select(func.count(EventPromotionJob.id)).where(EventPromotionJob.status == "FAILED")) or 0

    platform_counts: dict[str, int] = {}
    for p in SUPPORTED_PLATFORMS:
        cnt = db.scalar(select(func.count(EventPromotionJob.id)).where(EventPromotionJob.platform == p)) or 0
        platform_counts[p] = cnt

    return {
        "totalJobs": total_jobs,
        "published": published,
        "dryRun": dry_run,
        "pendingApproval": pending,
        "failed": failed,
        "byPlatform": platform_counts,
    }

