from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.core.config import get_settings
from backend.db import get_db
from backend.models import (
    AcquisitionOpportunity,
    AcquisitionReferralEvent,
    AgentAction,
    Community,
    Discussion,
    Event,
    PipelineExecution,
    PlatformRateLimit,
)
from backend.schemas import (
    AcquisitionAnalyticsOut,
    AcquisitionOpportunityOut,
    CommunityOut,
    CommunityUpdateInput,
    ConversionSimulationRequest,
    DiscoveryDiscussionRequest,
    DiscussionOut,
    InstagramContentRequest,
    KeywordPerformanceOut,
    MarkPublishedInput,
    MatchingEventSummary,
    OpportunityActionRequest,
    OpportunityEditRequest,
    PipelineExecutionOut,
    PipelineStageLogOut,
    PlatformRateLimitOut,
    PlatformRateLimitUpdateInput,
    ScanTriggerRequest,
    TestDiscussionRequest,
    TrackEventRequest,
)
from backend.services import event_creation
from backend.services.acquisition_agent import AgentOrchestrator
from backend.services.social_agent.connectors import CONNECTOR_REGISTRY
from backend.services.social_agent.orchestrator import SocialAgentOrchestrator
from backend.services.social_agent.pipeline import content_generation, discovery_pipeline, policy_check
from backend.services.social_agent.publishers import PlatformPublisher, get_publisher
from backend.services.social_agent.state_machine import InvalidTransitionError, transition_opportunity

router = APIRouter(prefix="/acquisition", tags=["acquisition"])


def serialize_opportunity(op: AcquisitionOpportunity) -> AcquisitionOpportunityOut:
    disc = op.discussion
    comm_name = disc.community.name if (disc and disc.community) else ""
    comm_risk = disc.community.risk_level if (disc and disc.community) else "low"

    disc_out = DiscussionOut(
        id=disc.id,
        community_id=disc.community_id,
        community_name=comm_name,
        platform=disc.platform,
        external_id=disc.external_id,
        url=disc.url,
        title=disc.title,
        content=disc.content,
        author=disc.author,
        published_at=disc.published_at,
        intent_classification=disc.intent_classification,
        intent_confidence=float(disc.intent_confidence),
        extracted_intent=disc.extracted_intent,
        status=disc.status,
        pipeline_status=disc.pipeline_status,
        qualification_score=disc.qualification_score,
        qualification_breakdown=disc.qualification_breakdown,
        rejection_reason=disc.rejection_reason,
        created_at=disc.created_at,
    )

    events_out = [
        MatchingEventSummary(
            id=ev["id"],
            title=ev["title"],
            slug=ev["slug"],
            location=ev["location"],
            start_date=ev["startDate"],
            price=float(ev["price"]),
            relevance_score=ev["relevanceScore"],
            category=ev.get("category", "Technology"),
            match_reasons=ev.get("matchReasons", []),
            score_breakdown=ev.get("scoreBreakdown", {}),
        )
        for ev in op.matching_events
    ]

    clicks = sum(1 for e in op.referral_events if e.event_type in ("click", "visit")) if op.referral_events else 0
    regs = sum(1 for e in op.referral_events if e.event_type == "registration") if op.referral_events else 0

    referral_url = f"{get_settings().app_base_url}/r/{op.id}"

    return AcquisitionOpportunityOut(
        id=op.id,
        discussion=disc_out,
        matching_events=events_out,
        relevance_score=op.relevance_score,
        generated_response=op.generated_response,
        response_variations=op.response_variations,
        content_payload=op.content_payload,
        content_generated_by=op.content_generated_by,
        policy_notes=op.policy_notes,
        approval_status=op.approval_status,
        community_risk=comm_risk,
        referral_url=referral_url,
        clicks_count=clicks,
        registrations_count=regs,
        scheduled_at=op.scheduled_at,
        published_at=op.published_at,
        published_url=op.published_url,
        reviewed_at=op.reviewed_at,
        created_at=op.created_at,
    )


def _load_opportunity(db: Session, opportunity_id: int) -> AcquisitionOpportunity:
    op = db.scalar(
        select(AcquisitionOpportunity)
        .options(
            selectinload(AcquisitionOpportunity.discussion).selectinload(Discussion.community),
            selectinload(AcquisitionOpportunity.referral_events),
        )
        .where(AcquisitionOpportunity.id == opportunity_id)
    )
    if not op:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return op


@router.get("/opportunities", response_model=list[AcquisitionOpportunityOut])
def list_opportunities(
    approval_status: str | None = Query(None),
    platform: str | None = Query(None),
    min_score: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[AcquisitionOpportunityOut]:
    stmt = (
        select(AcquisitionOpportunity)
        .join(AcquisitionOpportunity.discussion)
        .options(
            selectinload(AcquisitionOpportunity.discussion).selectinload(Discussion.community),
            selectinload(AcquisitionOpportunity.referral_events),
        )
        .order_by(AcquisitionOpportunity.created_at.desc())
    )

    if approval_status:
        stmt = stmt.where(AcquisitionOpportunity.approval_status == approval_status)
    if platform:
        stmt = stmt.where(Discussion.platform == platform)
    if min_score is not None:
        stmt = stmt.where(AcquisitionOpportunity.relevance_score >= min_score)

    ops = db.scalars(stmt.limit(limit)).all()
    return [serialize_opportunity(op) for op in ops]


@router.get("/opportunities/{opportunity_id}", response_model=AcquisitionOpportunityOut)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)) -> AcquisitionOpportunityOut:
    return serialize_opportunity(_load_opportunity(db, opportunity_id))


def _maybe_create_event_from_opportunity(db: Session, op: AcquisitionOpportunity, now: datetime) -> None:
    """Case B of the discovery agent: a human just approved a *new* event
    candidate (no existing 100.com match was found at discovery time). This
    is the ONLY place a discovered event actually becomes a real, published
    Event row — it never happens automatically, only on explicit human
    approval — and it reuses the exact same creation logic
    (`backend.services.event_creation`) as an organizer creating their own
    event, per the "don't build a second event-creation path" requirement.
    Idempotent: does nothing if this opportunity already created an event
    (e.g. a second approve-adjacent action on the same row)."""
    payload = op.content_payload or {}
    if payload.get("discoveryKind") != "new_event_candidate" or payload.get("createdEventId"):
        return

    extracted = payload.get("extractedEvent") or {}
    guessed_date = date.fromisoformat(payload["guessedStartDate"]) if payload.get("guessedStartDate") else date.today() + timedelta(days=14)
    price = extracted.get("price")
    price_decimal = Decimal("0.00") if extracted.get("is_free") else (Decimal(str(price)) if price is not None else Decimal("0.00"))

    organizer = event_creation.get_or_create_acquisition_organizer(db)
    event = event_creation.create_event(
        db,
        title=extracted.get("event_name") or (op.discussion.title if op.discussion else "Discovered Event"),
        description=extracted.get("description") or "Event discovered and approved via the acquisition agent.",
        event_type=extracted.get("event_type") or "Event",
        category_name=extracted.get("category") or "General",
        location=extracted.get("location"),
        start_date=guessed_date,
        price=price_decimal,
        organizer=organizer,
        status="published",
    )
    db.flush()

    event_summary = {
        "id": event.id, "title": event.title, "slug": event.slug,
        "location": extracted.get("location") or "Online", "startDate": str(event.start_date),
        "price": float(event.price), "relevanceScore": op.relevance_score,
        "category": extracted.get("category") or "General",
        "matchReasons": ["Created from an approved acquisition opportunity"], "scoreBreakdown": {},
    }
    op.matching_events = [event_summary]
    op.content_payload = {**payload, "createdEventId": event.id, "createdEventSlug": event.slug}

    rules_check = policy_check.check_policy(op.discussion.community if op.discussion else None)
    location_hint = extracted.get("location")
    if op.discussion:
        gen = content_generation.generate_content(
            op.discussion.platform, op.discussion.title, op.discussion.content, [event_summary], rules_check, location_hint,
        )
        if gen.success:
            op.generated_response = gen.data.content
            op.response_variations = [gen.data.content]

    db.add(AgentAction(
        opportunity_id=op.id, action_type="event_created_from_opportunity",
        result=f"Created 100Times event '{event.title}' (#{event.id}, /{event.slug}) from approved acquisition opportunity",
        created_at=now,
    ))


@router.post("/opportunities/{opportunity_id}/action", response_model=AcquisitionOpportunityOut)
def update_opportunity_action(
    opportunity_id: int,
    payload: OpportunityActionRequest,
    db: Session = Depends(get_db),
) -> AcquisitionOpportunityOut:
    op = _load_opportunity(db, opportunity_id)
    now = datetime.now(timezone.utc)

    if payload.response_text:
        op.generated_response = payload.response_text.strip()

    if payload.action == "approve_and_publish":
        # One explicit human click that both approves AND authorizes immediate
        # publish — still 100% human-gated, just combined into a single action
        # instead of two separate ones.
        try:
            op.approval_status = transition_opportunity(op.approval_status, "approved")
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        op.reviewed_at = now
        db.add(AgentAction(
            opportunity_id=op.id, action_type="human_approve_and_publish",
            result=payload.notes or "Human operator approved and requested immediate publish",
            created_at=now,
        ))
        _maybe_create_event_from_opportunity(db, op, now)

        platform = op.discussion.platform if op.discussion else "reddit"
        publisher = get_publisher(platform)
        result = _run_publish_flow(publisher, op.generated_response, op.discussion.external_id)
        action_type = _finalize_publish_result(op, result, now)
        db.add(AgentAction(opportunity_id=op.id, action_type=action_type, result=result.message, created_at=now))
        db.commit()
        db.refresh(op)
        return serialize_opportunity(op)

    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "ignore": "ignored",
        "schedule": "scheduled",
    }
    target_status = status_map[payload.action]

    try:
        op.approval_status = transition_opportunity(op.approval_status, target_status)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    op.reviewed_at = now

    if payload.action == "schedule":
        op.scheduled_at = payload.scheduled_at or now

    action = AgentAction(
        opportunity_id=op.id,
        action_type=f"human_{payload.action}",
        result=payload.notes or f"Human operator transitioned status to {target_status}",
        created_at=now,
    )
    db.add(action)
    if payload.action == "approve":
        _maybe_create_event_from_opportunity(db, op, now)
    db.commit()
    db.refresh(op)
    return serialize_opportunity(op)


@router.patch("/opportunities/{opportunity_id}/edit", response_model=AcquisitionOpportunityOut)
def edit_opportunity_response(
    opportunity_id: int,
    payload: OpportunityEditRequest,
    db: Session = Depends(get_db),
) -> AcquisitionOpportunityOut:
    op = _load_opportunity(db, opportunity_id)

    op.generated_response = payload.response_text.strip()

    action = AgentAction(
        opportunity_id=op.id,
        action_type="human_edited_response",
        result="Human operator customized the generated response",
        created_at=datetime.now(timezone.utc),
    )
    db.add(action)
    db.commit()
    db.refresh(op)
    return serialize_opportunity(op)


@router.get("/communities", response_model=list[CommunityOut])
def list_communities(db: Session = Depends(get_db)) -> list[CommunityOut]:
    comms = db.scalars(select(Community).order_by(Community.quality_score.desc())).all()
    return [
        CommunityOut(
            id=c.id,
            platform=c.platform,
            name=c.name,
            slug=c.slug,
            url=c.url,
            rules_text=c.rules_text,
            promotion_allowed=c.promotion_allowed,
            external_links_allowed=c.external_links_allowed,
            automation_allowed=c.automation_allowed,
            risk_level=c.risk_level,
            quality_score=c.quality_score,
            last_checked=c.last_checked,
            created_at=c.created_at,
        )
        for c in comms
    ]


@router.patch("/communities/{community_id}", response_model=CommunityOut)
def update_community(
    community_id: int,
    payload: CommunityUpdateInput,
    db: Session = Depends(get_db),
) -> CommunityOut:
    c = db.scalar(select(Community).where(Community.id == community_id))
    if not c:
        raise HTTPException(status_code=404, detail="Community not found")

    if payload.promotion_allowed is not None:
        c.promotion_allowed = payload.promotion_allowed
    if payload.external_links_allowed is not None:
        c.external_links_allowed = payload.external_links_allowed
    if payload.automation_allowed is not None:
        c.automation_allowed = payload.automation_allowed
    if payload.risk_level is not None:
        c.risk_level = payload.risk_level
    if payload.rules_text is not None:
        c.rules_text = payload.rules_text

    db.commit()
    db.refresh(c)
    return CommunityOut(
        id=c.id,
        platform=c.platform,
        name=c.name,
        slug=c.slug,
        url=c.url,
        rules_text=c.rules_text,
        promotion_allowed=c.promotion_allowed,
        external_links_allowed=c.external_links_allowed,
        automation_allowed=c.automation_allowed,
        risk_level=c.risk_level,
        quality_score=c.quality_score,
        last_checked=c.last_checked,
        created_at=c.created_at,
    )


@router.post("/run-scan")
def trigger_community_scan(
    payload: ScanTriggerRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Runs the connector-layer discovery scan across approved discussion platforms
    (Reddit, Discord, Telegram, X, LinkedIn) — Instagram is content-distribution only
    and is triggered separately via `/acquisition/instagram/generate`."""
    platforms = None
    if payload and payload.platforms:
        platforms = payload.platforms
    elif payload and payload.platform:
        platforms = [payload.platform]

    return SocialAgentOrchestrator.run_discussion_cycle(db=db, platforms=platforms)


@router.post("/organizer-scan")
def trigger_organizer_scan(
    payload: ScanTriggerRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Manual trigger for the Organizer Agent's automatic discovery cycle —
    the same cycle the background scheduler already runs on its own
    interval (`ORGANIZER_SCAN_INTERVAL_MINUTES`, default 30m). Useful to
    see results immediately instead of waiting for the next tick; not
    required for normal operation."""
    platforms = None
    if payload and payload.platforms:
        platforms = payload.platforms
    elif payload and payload.platform:
        platforms = [payload.platform]

    return SocialAgentOrchestrator.run_organizer_discovery_cycle(db=db, platforms=platforms)


@router.post("/instagram/generate", response_model=dict[str, Any])
def generate_instagram_content(
    payload: InstagramContentRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Instagram Content Distribution Agent: turns a theme (e.g. 'Best AI events in
    Hyderabad') into a ready-to-review caption/carousel/reel/hashtag pack, generated
    from the 100.com catalog rather than from a discovered discussion."""
    op = SocialAgentOrchestrator.run_instagram_content_cycle(db=db, theme=payload.theme)
    return {
        "result": "CONTENT_GENERATED",
        "opportunity": serialize_opportunity(op),
        "message": f"Instagram content pack generated for '{payload.theme}' and queued for human approval.",
    }


@router.get("/ai-status")
def get_ai_status() -> dict[str, Any]:
    """Safe AI connectivity diagnostic: confirms the configured AI provider's key is loaded
    and reachable with a minimal real request. Never returns the key itself
    or any raw SDK error body — only configured/reachable booleans, latency,
    model name, and a short sanitized message."""
    from backend.services.social_agent.ai_client import get_ai_client

    return get_ai_client().ping()


@router.get("/connectors/status")
def get_connector_status() -> list[dict[str, Any]]:
    """Reports each platform's real status — REAL / MOCK / NOT_CONFIGURED /
    APPROVAL_REQUIRED / ERROR — plus its actual capabilities, so the
    dashboard never claims a capability the underlying platform API doesn't
    really support (e.g. Reddit shows APPROVAL_REQUIRED, not just "not
    configured", since a credential alone wouldn't be enough there)."""
    statuses = []
    for connector_cls in CONNECTOR_REGISTRY.values():
        connector = connector_cls()
        statuses.append({
            "platform": connector.platform,
            "status": connector.status,
            "credentialsConfigured": connector.is_live,
            "requiresApproval": connector.requires_approval,
            "description": connector.description,
            "capabilities": connector.get_capabilities(),
        })
    return statuses


def _finalize_publish_result(op: AcquisitionOpportunity, result, now: datetime) -> str:
    """Applies a PublishResult to the opportunity's state, returning the
    audit-log action_type. Shared by /publish and the approve_and_publish
    action so both go through identical, honest state transitions."""
    if result.success:
        op.approval_status = transition_opportunity(op.approval_status, "published")
        op.published_at = now
        op.published_url = result.published_url
        return "real_publish_succeeded"

    if op.approval_status != "ready_for_manual_publishing":
        try:
            op.approval_status = transition_opportunity(op.approval_status, "ready_for_manual_publishing")
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return "manual_publish_requested"


def _run_publish_flow(publisher: "PlatformPublisher", text: str, target_ref: str):
    """The real four-step flow from the spec: validate_connection ->
    validate_publish_permission -> publish_reply -> verify_publication.
    Stub publishers (no real integration) skip straight to publish_reply,
    whose own honest failure message is more specific than a generic
    "not connected" would be."""
    from backend.services.social_agent.types import PublishResult

    if publisher.is_real:
        conn_check = publisher.validate_connection()
        if not conn_check.get("connected"):
            return PublishResult(success=False, platform=publisher.platform, published_url=None, message=conn_check.get("message", "Connection validation failed"))

        perm_check = publisher.validate_publish_permission(target_ref)
        if not perm_check.get("allowed"):
            return PublishResult(success=False, platform=publisher.platform, published_url=None, message=perm_check.get("message", "Publish permission check failed"))

    raw_result = publisher.publish_reply(text, target_ref)
    return publisher.verify_publication(raw_result)


@router.post("/opportunities/{opportunity_id}/publish", response_model=AcquisitionOpportunityOut)
def prepare_manual_publish(
    opportunity_id: int,
    db: Session = Depends(get_db),
) -> AcquisitionOpportunityOut:
    """Human-triggered step after approval. Runs the full four-step publish
    flow (validate_connection -> validate_publish_permission -> publish_reply
    -> verify_publication) against the platform's real publisher when one
    exists (currently: Telegram). Otherwise it moves the opportunity into
    Manual Publishing Mode: the human copies the approved content, posts it
    themselves, then confirms via `/mark-published`. Never fakes success —
    a real publish attempt that fails is reported as a failure, not
    silently downgraded to manual mode."""
    op = _load_opportunity(db, opportunity_id)

    if op.published_at:
        raise HTTPException(status_code=409, detail="Opportunity has already been published")

    now = datetime.now(timezone.utc)
    if op.approval_status == "scheduled":
        scheduled_at = op.scheduled_at
        if scheduled_at and scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        if not scheduled_at or scheduled_at > now:
            raise HTTPException(status_code=400, detail="Scheduled publish time has not arrived yet")
    elif op.approval_status not in ("approved", "ready_for_manual_publishing"):
        raise HTTPException(status_code=400, detail="Opportunity must be approved or scheduled-and-due before publishing")

    platform = op.discussion.platform if op.discussion else "reddit"
    publisher = get_publisher(platform)
    result = _run_publish_flow(publisher, op.generated_response, op.discussion.external_id)
    action_type = _finalize_publish_result(op, result, now)

    db.add(
        AgentAction(
            opportunity_id=op.id,
            action_type=action_type,
            result=result.message,
            created_at=now,
        )
    )
    db.commit()
    db.refresh(op)
    return serialize_opportunity(op)


@router.post("/opportunities/{opportunity_id}/mark-published", response_model=AcquisitionOpportunityOut)
def mark_published(
    opportunity_id: int,
    payload: MarkPublishedInput,
    db: Session = Depends(get_db),
) -> AcquisitionOpportunityOut:
    """The only way `published_url`/`published_at` are ever set — a human
    confirms they actually posted the content and pastes the real URL.
    Nothing in this system fabricates a published link."""
    op = _load_opportunity(db, opportunity_id)

    if op.approval_status != "ready_for_manual_publishing":
        raise HTTPException(status_code=400, detail="Call /publish first to enter manual-publishing mode")

    now = datetime.now(timezone.utc)
    try:
        op.approval_status = transition_opportunity(op.approval_status, "published")
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    op.published_at = now
    op.published_url = payload.published_url.strip()

    db.add(
        AgentAction(
            opportunity_id=op.id,
            action_type="human_confirmed_published",
            result=f"Human confirmed manual publish at {payload.published_url.strip()}"
            + (f" (platform post id: {payload.platform_post_id})" if payload.platform_post_id else ""),
            created_at=now,
        )
    )
    db.commit()
    db.refresh(op)
    return serialize_opportunity(op)


@router.get("/discussions/{discussion_id}/pipeline", response_model=list[PipelineExecutionOut])
def get_discussion_pipeline(discussion_id: int, db: Session = Depends(get_db)) -> list[PipelineExecutionOut]:
    """Debug Pipeline View: the full ✓/✗ timeline for every orchestrator run
    over this discussion, so it's immediately obvious where (and why) a
    signal stopped."""
    discussion = db.scalar(select(Discussion).where(Discussion.id == discussion_id))
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")

    executions = db.scalars(
        select(PipelineExecution)
        .options(selectinload(PipelineExecution.stage_logs))
        .where(PipelineExecution.discussion_id == discussion_id)
        .order_by(PipelineExecution.started_at.desc())
    ).all()

    return [
        PipelineExecutionOut(
            id=ex.id,
            discussion_id=ex.discussion_id,
            started_at=ex.started_at,
            completed_at=ex.completed_at,
            final_status=ex.final_status,
            stages=[
                PipelineStageLogOut(id=s.id, stage=s.stage, status=s.status, detail=s.detail, created_at=s.created_at)
                for s in sorted(ex.stage_logs, key=lambda s: s.created_at)
            ],
        )
        for ex in executions
    ]


@router.get("/rate-limits", response_model=list[PlatformRateLimitOut])
def list_rate_limits(db: Session = Depends(get_db)) -> list[PlatformRateLimitOut]:
    rows = db.scalars(select(PlatformRateLimit).order_by(PlatformRateLimit.platform)).all()
    return [
        PlatformRateLimitOut(id=r.id, platform=r.platform, daily_limit=r.daily_limit, updated_at=r.updated_at)
        for r in rows
    ]


@router.patch("/rate-limits/{platform}", response_model=PlatformRateLimitOut)
def update_rate_limit(
    platform: str,
    payload: PlatformRateLimitUpdateInput,
    db: Session = Depends(get_db),
) -> PlatformRateLimitOut:
    row = db.scalar(select(PlatformRateLimit).where(PlatformRateLimit.platform == platform))
    if not row:
        raise HTTPException(status_code=404, detail=f"No rate limit configured for platform '{platform}'")
    row.daily_limit = payload.daily_limit
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return PlatformRateLimitOut(id=row.id, platform=row.platform, daily_limit=row.daily_limit, updated_at=row.updated_at)


@router.post("/test-discussion", response_model=dict[str, Any])
def test_custom_discussion(
    payload: TestDiscussionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Allows an operator to paste any public post to run it through the agent pipeline."""
    op = AgentOrchestrator.process_discussion(
        db=db,
        platform=payload.platform,
        community_name=payload.community_name,
        title=payload.title,
        content=payload.content,
        url=payload.url,
    )
    if op:
        return {
            "result": "OPPORTUNITY_CREATED",
            "opportunity": serialize_opportunity(op),
            "relevanceScore": op.relevance_score,
            "message": "High-intent match found! Opportunity sent to approval queue.",
        }

    # If ignored/failed, fetch the discussion to see exactly why.
    disc = db.scalar(
        select(Discussion)
        .where(Discussion.title == payload.title)
        .order_by(Discussion.created_at.desc())
    )
    return {
        "result": "IGNORED",
        "classification": disc.intent_classification if disc else "IRRELEVANT",
        "confidence": float(disc.intent_confidence) if disc else 0.0,
        "pipelineStatus": disc.pipeline_status if disc else None,
        "rejectionReason": disc.rejection_reason if disc else None,
        "message": (disc.rejection_reason if (disc and disc.rejection_reason) else "Discussion did not qualify or match a relevant event."),
    }


@router.post("/discussions/discover", response_model=dict[str, Any])
def discover_from_discussion(
    payload: DiscoveryDiscussionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The generic, topic-agnostic acquisition agent entry point: receives
    ONE discussion (any platform, any topic — "biking" is just an example),
    has Claude understand it and generate dynamic search queries, searches
    the selected platform for candidate posts, extracts structured event
    details from each one, checks them against the 100.com catalog, and
    either queues a reply pointing at an existing match (Case A) or stages a
    new-event candidate for human approval (Case B). See
    `backend/services/social_agent/pipeline/discovery_pipeline.py`."""
    result = discovery_pipeline.run_discovery_pipeline(
        db=db,
        platform=payload.platform,
        community_name=payload.community_name,
        title=payload.title,
        content=payload.content,
        url=payload.url,
    )

    opportunities = []
    for entry in result["opportunitiesCreated"]:
        op = _load_opportunity(db, entry["opportunityId"])
        opportunities.append({"kind": entry["kind"], "opportunity": serialize_opportunity(op)})
    result["opportunities"] = opportunities
    return result


@router.post("/track")
def track_referral_interaction(
    payload: TrackEventRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Records click/visit/registration events driven by community acquisition links."""
    op = db.scalar(
        select(AcquisitionOpportunity)
        .options(selectinload(AcquisitionOpportunity.discussion).selectinload(Discussion.community))
        .where(AcquisitionOpportunity.id == payload.opportunity_id)
    )
    if not op:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    ref_event = AcquisitionReferralEvent(
        opportunity_id=op.id,
        event_id=payload.event_id,
        event_type=payload.event_type,
        visitor_id=payload.visitor_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(ref_event)

    if payload.event_type == "registration":
        act = AgentAction(
            opportunity_id=op.id,
            action_type="attendee_converted",
            result=f"Attendee converted: Registration completed via community recommendation (Event #{payload.event_id or 'direct'})",
            created_at=datetime.now(timezone.utc),
        )
        db.add(act)
        if op.discussion and op.discussion.community:
            comm = op.discussion.community
            comm.quality_score = min(99, comm.quality_score + 2)

    db.commit()
    return {
        "status": "success",
        "opportunityId": op.id,
        "eventType": payload.event_type,
        "message": f"Referral {payload.event_type} tracked successfully.",
    }


@router.post("/simulate-conversion")
def simulate_conversion(
    payload: ConversionSimulationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Dev/testing tool only — logs synthetic click/registration rows to verify
    the analytics feedback loop without waiting on real traffic. The
    production attribution path is the `/r/{opportunity_id}` redirect route
    (backend/routes/redirect.py), which records real ClickEvent rows."""
    op = db.scalar(
        select(AcquisitionOpportunity)
        .options(
            selectinload(AcquisitionOpportunity.discussion).selectinload(Discussion.community),
            selectinload(AcquisitionOpportunity.referral_events),
        )
        .where(AcquisitionOpportunity.id == payload.opportunity_id)
    )
    if not op:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    primary_event_id = op.matching_events[0].get("id") if (op.matching_events and len(op.matching_events) > 0) else None
    now = datetime.now(timezone.utc)

    for i in range(payload.clicks):
        db.add(
            AcquisitionReferralEvent(
                opportunity_id=op.id,
                event_id=primary_event_id,
                event_type="click",
                visitor_id=f"sim_visitor_{op.id}_{i+1}",
                created_at=now,
            )
        )

    for j in range(payload.registrations):
        db.add(
            AcquisitionReferralEvent(
                opportunity_id=op.id,
                event_id=primary_event_id,
                event_type="registration",
                visitor_id=f"sim_attendee_{op.id}_{j+1}",
                created_at=now,
            )
        )

    db.add(
        AgentAction(
            opportunity_id=op.id,
            action_type="conversion_loop_tested",
            result=f"Feedback loop test: Logged {payload.clicks} click(s) and {payload.registrations} verified attendee registration(s).",
            created_at=now,
        )
    )

    if op.discussion and op.discussion.community:
        comm = op.discussion.community
        bonus = (payload.registrations * 3) + 1
        comm.quality_score = min(99, comm.quality_score + bonus)

    db.commit()
    db.refresh(op)

    return {
        "status": "success",
        "clicksRecorded": payload.clicks,
        "registrationsRecorded": payload.registrations,
        "opportunity": serialize_opportunity(op),
        "message": f"Successfully simulated {payload.clicks} clicks and {payload.registrations} attendee registrations for Opportunity #{op.id}.",
    }


@router.get("/analytics", response_model=AcquisitionAnalyticsOut)
def get_acquisition_analytics(db: Session = Depends(get_db)) -> AcquisitionAnalyticsOut:
    total_ops = db.scalar(select(func.count(AcquisitionOpportunity.id))) or 0
    pending_ops = db.scalar(select(func.count(AcquisitionOpportunity.id)).where(AcquisitionOpportunity.approval_status == "pending")) or 0
    approved_ops = db.scalar(
        select(func.count(AcquisitionOpportunity.id)).where(
            AcquisitionOpportunity.approval_status.in_(["approved", "ready_for_manual_publishing", "published"])
        )
    ) or 0
    rejected_ops = db.scalar(select(func.count(AcquisitionOpportunity.id)).where(AcquisitionOpportunity.approval_status.in_(["rejected", "ignored"]))) or 0

    total_discs = db.scalar(select(func.count(Discussion.id))) or 0
    high_intent_discs = db.scalar(select(func.count(Discussion.id)).where(Discussion.intent_classification == "HIGH_INTENT")) or 0
    intent_rate = round((high_intent_discs / total_discs * 100), 1) if total_discs > 0 else 0.0

    avg_score = db.scalar(select(func.avg(AcquisitionOpportunity.relevance_score))) or 0.0

    # Total clicks & registrations
    total_clicks = db.scalar(
        select(func.count(AcquisitionReferralEvent.id)).where(AcquisitionReferralEvent.event_type.in_(["click", "visit"]))
    ) or 0
    total_registrations = db.scalar(
        select(func.count(AcquisitionReferralEvent.id)).where(AcquisitionReferralEvent.event_type == "registration")
    ) or 0
    overall_conversion_rate = round((total_registrations / total_clicks * 100), 1) if total_clicks > 0 else 0.0

    funnel_steps = {
        "discussions_scanned": total_discs,
        "high_intent_identified": high_intent_discs,
        "opportunities_matched": total_ops,
        "human_approved": approved_ops,
        "clicks_generated": total_clicks,
        "attendee_registrations": total_registrations,
    }

    # Source quality rankings with referral metrics
    communities = db.scalars(select(Community).order_by(Community.quality_score.desc())).all()
    source_rankings = []
    for c in communities:
        disc_count = db.scalar(select(func.count(Discussion.id)).where(Discussion.community_id == c.id)) or 0
        opp_ids = db.scalars(
            select(AcquisitionOpportunity.id)
            .join(AcquisitionOpportunity.discussion)
            .where(Discussion.community_id == c.id)
        ).all()
        opp_count = len(opp_ids)

        comm_clicks = 0
        comm_regs = 0
        if opp_ids:
            comm_clicks = db.scalar(
                select(func.count(AcquisitionReferralEvent.id)).where(
                    AcquisitionReferralEvent.opportunity_id.in_(opp_ids),
                    AcquisitionReferralEvent.event_type.in_(["click", "visit"]),
                )
            ) or 0
            comm_regs = db.scalar(
                select(func.count(AcquisitionReferralEvent.id)).where(
                    AcquisitionReferralEvent.opportunity_id.in_(opp_ids),
                    AcquisitionReferralEvent.event_type == "registration",
                )
            ) or 0

        conv_rate = round((comm_regs / comm_clicks * 100), 1) if comm_clicks > 0 else 0.0

        source_rankings.append({
            "id": c.id,
            "name": c.name,
            "platform": c.platform,
            "qualityScore": c.quality_score,
            "riskLevel": c.risk_level,
            "discussionsFound": disc_count,
            "opportunitiesGenerated": opp_count,
            "clicks": comm_clicks,
            "registrations": comm_regs,
            "conversionRate": conv_rate,
        })

    # Platform performance — which social platforms bring the best attendees
    platform_names = db.scalars(select(Discussion.platform).distinct()).all()
    platform_performance = []
    for plat in platform_names:
        plat_discs = db.scalar(select(func.count(Discussion.id)).where(Discussion.platform == plat)) or 0
        plat_opp_ids = db.scalars(
            select(AcquisitionOpportunity.id)
            .join(AcquisitionOpportunity.discussion)
            .where(Discussion.platform == plat)
        ).all()
        plat_opp_count = len(plat_opp_ids)
        plat_approved = db.scalar(
            select(func.count(AcquisitionOpportunity.id))
            .join(AcquisitionOpportunity.discussion)
            .where(Discussion.platform == plat, AcquisitionOpportunity.approval_status.in_(["approved", "scheduled", "ready_for_manual_publishing", "published"]))
        ) or 0

        plat_clicks = 0
        plat_regs = 0
        if plat_opp_ids:
            plat_clicks = db.scalar(
                select(func.count(AcquisitionReferralEvent.id)).where(
                    AcquisitionReferralEvent.opportunity_id.in_(plat_opp_ids),
                    AcquisitionReferralEvent.event_type.in_(["click", "visit"]),
                )
            ) or 0
            plat_regs = db.scalar(
                select(func.count(AcquisitionReferralEvent.id)).where(
                    AcquisitionReferralEvent.opportunity_id.in_(plat_opp_ids),
                    AcquisitionReferralEvent.event_type == "registration",
                )
            ) or 0

        plat_conv_rate = round((plat_regs / plat_clicks * 100), 1) if plat_clicks > 0 else 0.0

        platform_performance.append({
            "platform": plat,
            "discussionsFound": plat_discs,
            "opportunitiesGenerated": plat_opp_count,
            "approvedCount": plat_approved,
            "clicks": plat_clicks,
            "registrations": plat_regs,
            "conversionRate": plat_conv_rate,
        })
    platform_performance.sort(key=lambda p: p["registrations"], reverse=True)

    # High-intent category intelligence — computed from real qualified discussions,
    # not a hardcoded list. "Keyword" here is the AI-extracted event category.
    category_rows = db.execute(
        select(Discussion.id, Discussion.extracted_intent, Discussion.intent_classification).where(
            Discussion.extracted_intent.is_not(None)
        )
    ).all()

    category_stats: dict[str, dict[str, Any]] = {}
    for disc_id, extracted, classification in category_rows:
        category = (extracted or {}).get("event_category") or "General"
        stats = category_stats.setdefault(category, {"frequency": 0, "high_intent": 0, "discussion_ids": []})
        stats["frequency"] += 1
        if classification == "HIGH_INTENT":
            stats["high_intent"] += 1
        stats["discussion_ids"].append(disc_id)

    top_keywords: list[KeywordPerformanceOut] = []
    for category, stats in sorted(category_stats.items(), key=lambda kv: kv[1]["frequency"], reverse=True)[:6]:
        conv_count = db.scalar(
            select(func.count(AcquisitionReferralEvent.id))
            .join(AcquisitionOpportunity, AcquisitionReferralEvent.opportunity_id == AcquisitionOpportunity.id)
            .where(
                AcquisitionOpportunity.discussion_id.in_(stats["discussion_ids"]),
                AcquisitionReferralEvent.event_type == "registration",
            )
        ) or 0
        high_intent_rate = round((stats["high_intent"] / stats["frequency"] * 100), 1) if stats["frequency"] else 0.0
        top_keywords.append(
            KeywordPerformanceOut(
                keyword=category,
                frequency=stats["frequency"],
                high_intent_rate=high_intent_rate,
                conversions=conv_count,
            )
        )

    # Recent actions
    actions = db.scalars(select(AgentAction).order_by(AgentAction.created_at.desc()).limit(15)).all()
    recent_actions = [
        {
            "id": a.id,
            "opportunityId": a.opportunity_id,
            "actionType": a.action_type,
            "result": a.result,
            "createdAt": a.created_at.isoformat(),
        }
        for a in actions
    ]

    return AcquisitionAnalyticsOut(
        total_opportunities=total_ops,
        pending_approval=pending_ops,
        approved_count=approved_ops,
        rejected_count=rejected_ops,
        high_intent_rate=intent_rate,
        avg_relevance_score=float(avg_score),
        total_clicks=total_clicks,
        total_registrations=total_registrations,
        overall_conversion_rate=overall_conversion_rate,
        funnel_steps=funnel_steps,
        source_quality_rankings=source_rankings,
        platform_performance=platform_performance,
        top_keywords=top_keywords,
        recent_actions=recent_actions,
    )



@router.post("/analytics/insights")
def generate_analytics_insights(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Optional qualitative layer on top of the deterministic analytics
    numbers (Claude may provide qualitative insights; it never computes the
    numbers themselves — those are always calculated by
    `get_acquisition_analytics`, real DB aggregation, no LLM involved).
    Intended to be called by the n8n Analytics workflow on a schedule."""
    from backend.services.social_agent.ai_client import AIClientError, get_ai_client, not_configured_message

    analytics = get_acquisition_analytics(db=db)

    client = get_ai_client()
    if not client.is_configured:
        return {"available": False, "message": not_configured_message(), "insight": None}

    summary_lines = [
        f"Total opportunities: {analytics.total_opportunities}",
        f"Pending approval: {analytics.pending_approval}",
        f"Approved: {analytics.approved_count}",
        f"Rejected: {analytics.rejected_count}",
        f"High intent rate: {analytics.high_intent_rate}%",
        f"Avg relevance score: {analytics.avg_relevance_score}",
        f"Total clicks: {analytics.total_clicks}",
        f"Total registrations: {analytics.total_registrations}",
        f"Overall conversion rate: {analytics.overall_conversion_rate}%",
    ]
    for p in analytics.platform_performance[:6]:
        summary_lines.append(
            f"Platform {p['platform']}: {p['discussionsFound']} found, {p['clicks']} clicks, "
            f"{p['registrations']} registrations, {p['conversionRate']}% conversion"
        )

    try:
        insight = client.generate_text(
            system=(
                "You are a growth analyst for an event-discovery platform's attendee acquisition agent. "
                "Given real funnel numbers, write a short (3-5 sentence), concrete, non-generic qualitative "
                "summary: what's working, what isn't, and one specific next action. Never invent a number "
                "that wasn't given to you."
            ),
            user=chr(10).join(summary_lines),
            max_tokens=300,
        )
    except AIClientError as exc:
        return {"available": False, "message": str(exc), "insight": None}

    return {"available": True, "message": "Generated from current analytics", "insight": insight}
