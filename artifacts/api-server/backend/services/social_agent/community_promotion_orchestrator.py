"""Agent 4 extension — Community Promotion batch orchestrator. Mirrors
`outreach/orchestrator.py::run_outreach_agent`'s discipline exactly: one
`AgentRun` per batch, drafts land at `pending` (never sent/published on
their own), every drafted `AcquisitionOpportunity` records which path
produced its text (`generated_by`). No AI required — see
`pipeline/community_promotion.py`'s deterministic-fallback drafting.

Reuses the EXISTING `AcquisitionOpportunity` table, state machine, publish
flow, and click/registration-attribution chain as-is — this orchestrator's
only job is finding matches and drafting content; approval, publishing,
and conversion tracking are all handled by code that already exists for
the discussion-reply flow.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AcquisitionOpportunity, AgentRun
from backend.services.social_agent.pipeline.community_promotion import find_event_community_matches, generate_promotion_content


@dataclass
class CommunityPromotionConfig:
    max_candidates: int = 20
    match_threshold: int = 60


@dataclass
class CommunityPromotionRunSummary:
    candidates_considered: int = 0
    drafted: int = 0
    skipped_duplicate: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"candidates_considered": self.candidates_considered, "drafted": self.drafted, "skipped_duplicate": self.skipped_duplicate}


def _already_drafted(db: Session, event_id: int, community_id: int) -> bool:
    """A standalone promotion post is never drafted twice for the same
    event x community pair — mirrors `outreach/duplicate_check.py`'s role,
    scoped to this narrower (event, community) key instead of (event,
    organizer)."""
    stmt = select(AcquisitionOpportunity.id).where(
        AcquisitionOpportunity.source_kind == "community_promotion",
        AcquisitionOpportunity.promoted_event_id == event_id,
        AcquisitionOpportunity.target_community_id == community_id,
    )
    return db.execute(stmt).scalars().first() is not None


def run_community_promotion_agent(db: Session, config: CommunityPromotionConfig | None = None) -> CommunityPromotionRunSummary:
    config = config or CommunityPromotionConfig()

    run = AgentRun(
        agent_type="community_promotion", status="running", started_at=datetime.now(timezone.utc),
        config_snapshot=asdict(config), summary=CommunityPromotionRunSummary().as_dict(), created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    summary = CommunityPromotionRunSummary()
    try:
        matches = find_event_community_matches(db, match_threshold=config.match_threshold)
        summary.candidates_considered = len(matches)

        for event, community, score, explanation in matches:
            if summary.drafted >= config.max_candidates:
                break
            if _already_drafted(db, event.id, community.id):
                summary.skipped_duplicate += 1
                continue

            content = generate_promotion_content(event, community)
            opportunity = AcquisitionOpportunity(
                discussion_id=None,
                source_kind="community_promotion",
                promoted_event_id=event.id,
                target_community_id=community.id,
                match_explanation=explanation,
                # Same shape `EventMatchingEngine` already produces (services/acquisition_agent.py)
                # — the admin UI's event-summary card and the `/r/{id}` redirect's destination
                # lookup both expect this full shape, not just id/title/slug.
                matching_events=[{
                    "id": event.id,
                    "title": event.title,
                    "slug": event.slug,
                    "location": event.city_name or ("Online" if event.format == "online" else "Not specified"),
                    "startDate": str(event.start_date),
                    "price": float(event.price),
                    "relevanceScore": score,
                    "category": event.category.name if event.category else "Technology",
                    "matchReasons": [explanation],
                    "scoreBreakdown": {},
                }],
                relevance_score=score,
                generated_response=content.body,
                content_payload={"subject": content.subject},
                content_generated_by=content.generated_by,
                approval_status="pending",
                created_at=datetime.now(timezone.utc),
            )
            db.add(opportunity)
            db.commit()
            summary.drafted += 1

            run.summary = summary.as_dict()
            db.add(run)
            db.commit()

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.summary = summary.as_dict()
        db.add(run)
        db.commit()

    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error = str(exc)
        run.summary = summary.as_dict()
        db.add(run)
        db.commit()

    return summary
