"""Pipeline Orchestrator.

Chains: normalize -> intent extraction (AI) -> qualification (deterministic)
-> event matching (deterministic) -> policy check (deterministic) -> content
generation (AI, with an honestly-labeled deterministic fallback) -> human
approval queue.

Every stage writes a `PipelineStageLog` row under one `PipelineExecution`,
so `GET /acquisition/discussions/{id}/pipeline` can render the exact ✓/✗
timeline the Debug Pipeline View needs. Every status write goes through the
state-machine validator so an invalid jump raises instead of corrupting data.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    AcquisitionOpportunity,
    AgentAction,
    Discussion,
    PipelineExecution,
    PipelineStageLog,
)
from backend.services.social_agent.pipeline import (
    content_generation,
    event_matching,
    intent_extraction,
    normalize,
    policy_check,
    qualification,
)
from backend.services.social_agent.state_machine import transition_discussion

NO_MATCH_THRESHOLD = 80


def _set_status(discussion: Discussion, target: str) -> None:
    discussion.pipeline_status = transition_discussion(discussion.pipeline_status, target)


def _log(db: Session, execution: PipelineExecution, stage: str, status: str, detail: dict[str, Any] | None = None) -> None:
    db.add(
        PipelineStageLog(
            pipeline_execution_id=execution.id,
            stage=stage,
            status=status,
            detail=detail or {},
            created_at=datetime.now(timezone.utc),
        )
    )


def _reject(
    db: Session,
    execution: PipelineExecution,
    discussion: Discussion,
    target_status: str,
    reason: str,
    stage: str,
    detail: dict[str, Any] | None = None,
) -> None:
    _log(db, execution, stage, "failed", {**(detail or {}), "reason": reason})
    _set_status(discussion, target_status)
    discussion.rejection_reason = reason
    discussion.status = "ignored"
    execution.completed_at = datetime.now(timezone.utc)
    execution.final_status = target_status
    db.commit()


def run_pipeline(
    db: Session,
    platform: str,
    community_name: str,
    title: str,
    content: str,
    url: str = "",
    external_id: str | None = None,
    author: str | None = None,
) -> AcquisitionOpportunity | None:
    # --- Stage: NORMALIZED (+ dedup) ---
    norm = normalize.normalize_signal(
        db, platform=platform, community_name=community_name, title=title, content=content,
        url=url, external_id=external_id, author=author,
    )
    if norm.is_duplicate:
        return db.scalar(
            select(AcquisitionOpportunity).where(AcquisitionOpportunity.discussion_id == norm.discussion.id)
        )

    discussion = norm.discussion
    community = norm.community

    execution = PipelineExecution(discussion_id=discussion.id, started_at=datetime.now(timezone.utc))
    db.add(execution)
    db.flush()

    _set_status(discussion, "NORMALIZED")
    _log(db, execution, "NORMALIZE", "success", {"communityId": community.id, "platform": platform})

    # --- Stage: INTENT_EXTRACTED (AI) ---
    extraction = intent_extraction.extract_intent(title, content)
    if not extraction.success:
        _reject(
            db, execution, discussion, "FAILED_AI_EXTRACTION", extraction.error or "AI extraction failed",
            "INTENT_EXTRACTION", {"retryCount": extraction.retry_count},
        )
        return None

    ai_intent = extraction.data
    discussion.ai_intent = ai_intent.model_dump()
    discussion.ai_extraction_retry_count = extraction.retry_count
    _set_status(discussion, "INTENT_EXTRACTED")
    _log(db, execution, "INTENT_EXTRACTION", "success", {"intentType": ai_intent.intent_type, "retryCount": extraction.retry_count})

    # --- Stage: QUALIFIED (deterministic) ---
    qual = qualification.qualify(ai_intent)
    discussion.qualification_score = qual.score
    discussion.qualification_breakdown = qual.breakdown
    discussion.intent_classification = qual.level
    discussion.intent_confidence = Decimal(str(round(qual.score / 100, 2)))
    discussion.extracted_intent = {
        **event_matching.flatten_intent(ai_intent),
        "confidence": round(qual.score / 100, 2),
    }

    if qual.level in ("LOW_INTENT", "IRRELEVANT"):
        _reject(
            db, execution, discussion, "REJECTED_LOW_INTENT",
            f"Qualification score {qual.score}/100 ({qual.level}) below the HIGH/MEDIUM threshold",
            "QUALIFICATION", {"score": qual.score, "level": qual.level, "breakdown": qual.breakdown},
        )
        return None

    _set_status(discussion, "QUALIFIED")
    _log(db, execution, "QUALIFICATION", "success", {"score": qual.score, "level": qual.level, "breakdown": qual.breakdown, "reasons": qual.reasons})

    # --- Stage: MATCHED (deterministic, two-stage) ---
    relevance_score, matched_events = event_matching.find_and_score_events(db, ai_intent)
    if relevance_score < NO_MATCH_THRESHOLD or not matched_events:
        top_candidate = matched_events[0] if matched_events else None
        _reject(
            db, execution, discussion, "REJECTED_NO_MATCH",
            f"No event scored >= {NO_MATCH_THRESHOLD} (best: {relevance_score})",
            "EVENT_MATCHING", {"bestScore": relevance_score, "topCandidate": top_candidate},
        )
        return None

    _set_status(discussion, "MATCHED")
    _log(db, execution, "EVENT_MATCHING", "success", {"relevanceScore": relevance_score, "matchCount": len(matched_events)})

    # --- Stage: RULES_CHECKED (deterministic) ---
    rules_check = policy_check.check_policy(community)
    if not rules_check.get("can_generate_opportunity", True):
        _reject(
            db, execution, discussion, "REJECTED_POLICY",
            f"Community policy blocks outreach (risk={rules_check.get('risk_level')})",
            "POLICY_CHECK", {"rulesCheck": rules_check},
        )
        return None

    _set_status(discussion, "RULES_CHECKED")
    _log(db, execution, "POLICY_CHECK", "success", {"rulesCheck": rules_check})

    # --- Stage: DRAFT_GENERATED (AI, honest fallback) ---
    location = discussion.extracted_intent.get("location")
    gen = content_generation.generate_content(platform, title, content, matched_events, rules_check, location)
    if not gen.success:
        _reject(
            db, execution, discussion, "FAILED_PROCESSING",
            gen.error or "Content generation failed", "CONTENT_GENERATION", {"generatedBy": gen.generated_by},
        )
        return None

    _set_status(discussion, "DRAFT_GENERATED")
    _log(db, execution, "CONTENT_GENERATION", "success", {"generatedBy": gen.generated_by})

    # --- Stage: PENDING_APPROVAL ---
    _set_status(discussion, "PENDING_APPROVAL")
    discussion.status = "processed"

    opportunity = AcquisitionOpportunity(
        discussion_id=discussion.id,
        matching_events=matched_events,
        relevance_score=relevance_score,
        generated_response=gen.data.content,
        response_variations=[gen.data.content],
        content_generated_by=gen.generated_by,
        policy_notes=gen.data.policy_notes,
        approval_status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(opportunity)

    db.add(
        AgentAction(
            opportunity=opportunity,
            action_type="opportunity_created",
            result=(
                f"Matched {len(matched_events)} events with relevance {relevance_score}/100 in {community.name} "
                f"(qualification {qual.score}/100 {qual.level}, content by {gen.generated_by})"
            ),
            created_at=datetime.now(timezone.utc),
        )
    )

    _log(db, execution, "APPROVAL_QUEUE", "success", {"opportunityId": None})
    execution.completed_at = datetime.now(timezone.utc)
    execution.final_status = "PENDING_APPROVAL"

    db.commit()
    db.refresh(opportunity)
    return opportunity
