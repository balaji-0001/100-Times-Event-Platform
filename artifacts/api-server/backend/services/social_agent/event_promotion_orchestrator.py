"""Event Promotion Orchestration Engine.

Handles automated multi-platform promotion triggers, database deduplication,
approval workflows, safe retries, and dry-run execution across Instagram,
Facebook Pages, LinkedIn, Telegram, and Discord.
"""

from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import Event, EventPromotionJob, PlatformPromotionSetting
from backend.services.audit import record_audit_log
from backend.services.social_agent.pipeline.event_promotion_content import (
    build_utm_tracking_url,
    generate_platform_promotion_content,
)
from backend.services.social_agent.publishers import get_publisher

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = ("instagram", "facebook", "linkedin", "telegram", "discord")


def get_or_init_platform_settings(db: Session) -> list[PlatformPromotionSetting]:
    """Retrieves or seeds default platform promotion settings."""
    settings = get_settings()
    existing = {s.platform: s for s in db.scalars(select(PlatformPromotionSetting)).all()}

    default_destinations = {
        "facebook": settings.facebook_page_id,
        "instagram": settings.instagram_business_account_id,
        "linkedin": settings.linkedin_organization_id,
        "telegram": settings.telegram_promotion_channel_id,
        "discord": settings.discord_promotion_webhook_url,
    }

    results: list[PlatformPromotionSetting] = []
    created_any = False

    for platform in SUPPORTED_PLATFORMS:
        if platform in existing:
            results.append(existing[platform])
        else:
            new_setting = PlatformPromotionSetting(
                platform=platform,
                enabled=True,
                auto_publish=False,  # default to requiring approval
                dry_run=True,        # default to dry-run per safety requirements
                default_destination=default_destinations.get(platform),
                rate_limit_per_day=20,
            )
            db.add(new_setting)
            results.append(new_setting)
            created_any = True

    if created_any:
        db.commit()
        for s in results:
            db.refresh(s)

    return results


def trigger_event_promotions(
    db: Session,
    event: Event,
    *,
    actor: str = "system",
    force: bool = False,
    platforms: list[str] | None = None,
) -> list[EventPromotionJob]:
    """Triggers promotions for a published event across enabled social platforms.
    
    Enforces:
    - Event must be published (drafts are never promoted).
    - Database-backed deduplication (prevents duplicate jobs for the same event x platform).
    - Configurable approval vs auto-publish workflow.
    - Default dry-run execution.
    """
    if event.status != "published" and (event.lifecycle_state or "").upper() != "PUBLISHED":
        logger.info(f"Skipping promotion trigger for event #{event.id}: event status is '{event.status}', not published.")
        return []

    platform_settings = get_or_init_platform_settings(db)
    target_platforms = set(p.lower().strip() for p in (platforms or SUPPORTED_PLATFORMS))

    jobs: list[EventPromotionJob] = []

    for setting in platform_settings:
        platform = setting.platform
        if platform not in target_platforms or not setting.enabled:
            continue

        # Check existing job for deduplication
        existing_job = db.scalar(
            select(EventPromotionJob).where(
                EventPromotionJob.event_id == event.id,
                EventPromotionJob.platform == platform,
            )
        )

        if existing_job:
            # If already published or simulated in dry run, skip unless forced
            if existing_job.status in ("PUBLISHED", "DRY_RUN") and not force:
                logger.info(f"Skipping duplicate promotion for event #{event.id} on {platform}: existing job #{existing_job.id} is {existing_job.status}.")
                jobs.append(existing_job)
                continue
            # If failed or pending, we can refresh the content if forced
            job = existing_job
        else:
            job = EventPromotionJob(
                event_id=event.id,
                platform=platform,
                destination_ref=setting.default_destination,
                is_dry_run=setting.dry_run,
                status="PENDING_APPROVAL",
                content="",
            )
            db.add(job)
            db.flush()

        # Build tracking URL and platform-tailored copy
        tracking_url, utm_params = build_utm_tracking_url(event, platform)
        content_data = generate_platform_promotion_content(event, platform, tracking_url)

        job.title = content_data.get("title")
        job.content = content_data.get("content", "")
        job.media_urls = content_data.get("media_urls", [])
        job.utm_params = utm_params
        job.tracking_url = tracking_url
        job.destination_ref = setting.default_destination
        job.is_dry_run = setting.dry_run
        job.approval_required = not setting.auto_publish

        if setting.auto_publish:
            job.status = "QUEUED"
            db.commit()
            db.refresh(job)
            # Execute auto-publish immediately (dry-run or live according to setting.dry_run)
            executed_job = execute_promotion_job(db, job)
            jobs.append(executed_job)
        else:
            job.status = "PENDING_APPROVAL"
            db.commit()
            db.refresh(job)
            jobs.append(job)

        record_audit_log(
            db,
            actor=actor,
            action="EVENT_PROMOTION_DISPATCHED",
            entity="EventPromotionJob",
            entity_id=job.id,
            metadata={
                "event_id": event.id,
                "platform": platform,
                "status": job.status,
                "is_dry_run": job.is_dry_run,
                "auto_publish": setting.auto_publish,
            },
        )

    return jobs


def execute_promotion_job(
    db: Session,
    job: EventPromotionJob,
    *,
    force_dry_run: bool | None = None,
) -> EventPromotionJob:
    """Executes a promotion job via the official platform publisher.
    
    If dry-run is requested or configured, simulates publication with 100% honesty.
    If live, invokes the official publisher and persists the resulting post ID or error.
    """
    if force_dry_run is not None:
        job.is_dry_run = force_dry_run
    is_dry_run = job.is_dry_run
    publisher = get_publisher(job.platform)

    now = datetime.now(timezone.utc)
    target_ref = job.destination_ref or ""

    if is_dry_run:
        res = publisher.publish_post(
            job.content,
            target_ref=target_ref,
            link=job.tracking_url,
            title=job.title,
            is_dry_run=True,
            media_urls=job.media_urls,
            image_url=(job.media_urls[0] if job.media_urls else None),
        )
        job.status = "DRY_RUN"
        job.is_dry_run = True
        job.external_post_id = res.post_id or f"dry_run_{job.platform}_{job.event_id}"
        job.published_url = res.published_url
        job.published_at = now
        job.last_error = None
        job.updated_at = now
        db.commit()
        db.refresh(job)
        return job

    # Live execution: check connection & permissions first
    conn_check = publisher.validate_connection()
    if not conn_check.get("connected"):
        job.status = "FAILED"
        job.last_error = conn_check.get("message", "Connection validation failed.")
        job.retry_count += 1
        job.updated_at = now
        db.commit()
        db.refresh(job)
        return job

    perm_check = publisher.validate_publish_permission(target_ref)
    if not perm_check.get("allowed"):
        job.status = "FAILED"
        job.last_error = perm_check.get("message", "Publish permission validation failed.")
        job.retry_count += 1
        job.updated_at = now
        db.commit()
        db.refresh(job)
        return job

    # Execute live post
    res = publisher.publish_post(
        job.content,
        target_ref=target_ref,
        link=job.tracking_url,
        title=job.title,
        is_dry_run=False,
        media_urls=job.media_urls,
        image_url=(job.media_urls[0] if job.media_urls else None),
    )

    if res.success:
        job.status = "PUBLISHED"
        job.is_dry_run = False
        job.external_post_id = res.post_id or res.published_url
        job.published_url = res.published_url
        job.published_at = now
        job.last_error = None
    else:
        job.status = "FAILED"
        job.last_error = res.message
        job.retry_count += 1

    job.updated_at = now
    db.commit()
    db.refresh(job)

    record_audit_log(
        db,
        actor=job.approved_by or "system",
        action="EVENT_PROMOTION_PUBLISHED" if job.status == "PUBLISHED" else "EVENT_PROMOTION_FAILED",
        entity="EventPromotionJob",
        entity_id=job.id,
        result="SUCCESS" if job.status == "PUBLISHED" else "FAILURE",
        metadata={
            "platform": job.platform,
            "external_post_id": job.external_post_id,
            "published_url": job.published_url,
            "error": job.last_error,
        },
    )

    return job


def approve_promotion_job(
    db: Session,
    job_id: int,
    *,
    admin_email: str,
    dry_run: bool | None = None,
) -> EventPromotionJob:
    """Human approval action transitioning a PENDING_APPROVAL job to execution."""
    job = db.get(EventPromotionJob, job_id)
    if not job:
        raise ValueError(f"EventPromotionJob #{job_id} not found.")

    job.approved_by = admin_email
    job.approved_at = datetime.now(timezone.utc)
    if dry_run is not None:
        job.is_dry_run = dry_run

    db.commit()
    return execute_promotion_job(db, job, force_dry_run=dry_run)


def retry_promotion_job(db: Session, job_id: int) -> EventPromotionJob:
    """Safely retries a failed promotion job if retry limit has not been reached."""
    job = db.get(EventPromotionJob, job_id)
    if not job:
        raise ValueError(f"EventPromotionJob #{job_id} not found.")

    if job.retry_count >= job.max_retries:
        raise ValueError(f"Job #{job_id} has reached maximum retry attempts ({job.max_retries}).")

    return execute_promotion_job(db, job)

