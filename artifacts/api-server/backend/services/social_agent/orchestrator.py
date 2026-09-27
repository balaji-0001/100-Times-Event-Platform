import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AcquisitionOpportunity, AgentAction, City, Community, Discussion
from backend.services.acquisition_agent import AgentOrchestrator, EventMatchingEngine, IntentDetectionAgent
from backend.services.social_agent.connectors import get_connector
from backend.services.social_agent.content.instagram import InstagramContentAgent
from backend.services.social_agent.pipeline import discovery_pipeline
from backend.services.social_agent.unified_processor import UnifiedSignalProcessor

DISCUSSION_PLATFORMS = ["reddit", "discord", "telegram", "x", "linkedin"]


class SocialAgentOrchestrator:
    """Coordinates the multi-platform Demand Capture pipeline: connector layer
    -> unified signal processor (rate limits) -> the real pipeline orchestrator
    (backend/services/social_agent/pipeline/orchestrator.py: AI intent
    extraction, deterministic qualification/matching/policy, AI content
    generation) -> human approval queue."""

    @classmethod
    def run_discussion_cycle(cls, db: Session, platforms: list[str] | None = None) -> dict[str, Any]:
        requested = platforms or DISCUSSION_PLATFORMS
        connectors = [get_connector(p) for p in requested if p in DISCUSSION_PLATFORMS]

        collected = UnifiedSignalProcessor.collect(connectors, db)

        created_ops = 0
        ignored = 0
        communities_seen: set[str] = set()

        for signal in collected.signals:
            communities_seen.add(signal.community_name)
            op = AgentOrchestrator.process_discussion(
                db=db,
                platform=signal.platform,
                community_name=signal.community_name,
                title=signal.title,
                content=signal.content,
                url=signal.url,
                external_id=signal.external_id,
                author=signal.author,
            )
            if op:
                created_ops += 1
            else:
                ignored += 1

        for note in collected.skip_notes:
            db.add(
                AgentAction(
                    opportunity_id=None,
                    action_type="rate_limit_skip",
                    result=note,
                    created_at=datetime.now(timezone.utc),
                )
            )
        if collected.skip_notes:
            db.commit()

        return {
            "status": "success",
            "scannedPlatforms": [c.platform for c in connectors],
            "scannedCommunities": len(communities_seen),
            "newOpportunities": created_ops,
            "ignoredOrLowIntent": ignored,
            "rateLimitSkips": collected.skip_notes,
            "message": f"Scan complete across {len(connectors)} platform(s): {created_ops} high-intent opportunities queued for human approval.",
        }

    @classmethod
    def run_organizer_discovery_cycle(cls, db: Session, platforms: list[str] | None = None) -> dict[str, Any]:
        """The Organizer Agent's automatic entry point — no manually-typed
        discussion required. Reuses the exact same rate-limited signal
        collection as `run_discussion_cycle` (shared discovery/rules
        infrastructure per the architecture spec), then feeds a bounded
        number of those signals as seeds into `discovery_pipeline.run_
        discovery_pipeline`, which does the real work: AI-driven search
        query generation, platform search for candidate event posts, event
        extraction/verification, organizer/contact discovery, duplicate
        check, and drafting an outreach message for human approval.

        Bounded per cycle (`organizer_discovery_max_seeds_per_cycle`, default
        3) because each seed can trigger several AI calls (intent extraction
        + up to 5 event-extraction calls) — this keeps a scheduled tick's
        Claude usage predictable rather than scaling with however many
        signals a connector happens to return."""
        requested = platforms or DISCUSSION_PLATFORMS
        connectors = [get_connector(p) for p in requested if p in DISCUSSION_PLATFORMS]

        collected = UnifiedSignalProcessor.collect(connectors, db)
        max_seeds = get_settings().organizer_discovery_max_seeds_per_cycle
        seeds = collected.signals[:max_seeds]

        opportunities_created = 0
        outreach_drafted = 0
        seed_results: list[dict[str, Any]] = []

        for signal in seeds:
            result = discovery_pipeline.run_discovery_pipeline(
                db,
                platform=signal.platform,
                community_name=signal.community_name,
                title=signal.title,
                content=signal.content,
                url=signal.url,
            )
            opportunities_created += len(result.get("opportunitiesCreated", []))
            for candidate in result.get("candidates", []):
                outreach = candidate.get("organizerOutreach")
                if outreach and outreach.get("outcome") == "DRAFTED_PENDING_APPROVAL":
                    outreach_drafted += 1
            seed_results.append({"platform": signal.platform, "community": signal.community_name, "message": result.get("message")})

        return {
            "status": "success",
            "scannedPlatforms": [c.platform for c in connectors],
            "seedsProcessed": len(seeds),
            "opportunitiesCreated": opportunities_created,
            "outreachDrafted": outreach_drafted,
            "seedResults": seed_results,
            "message": f"Organizer discovery cycle complete: {len(seeds)} seed discussion(s) searched, {outreach_drafted} outreach message(s) drafted for human approval.",
        }

    @classmethod
    def run_instagram_content_cycle(cls, db: Session, theme: str) -> AcquisitionOpportunity:
        cities = db.scalars(select(City.name)).all()
        # Instagram content is operator-initiated (not a discovered discussion), so we
        # always proceed — classification/confidence only inform matching hints here.
        # This is deliberately the regex-based IntentDetectionAgent, not the real-AI
        # pipeline: Instagram is a Content Distribution flow, not Demand Capture.
        _classification, _confidence, extracted = IntentDetectionAgent.classify_and_extract(theme, "", cities)

        relevance_score, matched_events = EventMatchingEngine.match_events(db, extracted)
        pack = InstagramContentAgent.generate_theme_pack(theme, matched_events)

        community = db.scalar(select(Community).where(Community.slug == "instagram-content-calendar"))
        if not community:
            community = Community(
                platform="instagram",
                name="100.com Instagram Content Calendar",
                slug="instagram-content-calendar",
                url="https://instagram.com/100times",
                rules_text="Owned channel. Content is generated from the 100.com catalog and always human-approved before publishing.",
                promotion_allowed=True,
                external_links_allowed=True,
                automation_allowed=False,
                risk_level="low",
                quality_score=90,
                last_checked=datetime.now(timezone.utc),
            )
            db.add(community)
            db.flush()

        raw_hash = hashlib.md5(f"instagram:{theme}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()
        external_id = f"instagram_theme_{raw_hash[:16]}"

        discussion = Discussion(
            community_id=community.id,
            platform="instagram",
            external_id=external_id,
            url=community.url,  # real instagram.com link, not a placeholder domain
            title=theme,
            content="Content distribution theme — generated proactively from the 100.com event catalog, not a discovered discussion.",
            author="content_calendar",
            published_at=datetime.now(timezone.utc),
            intent_classification="CONTENT_OPPORTUNITY",
            intent_confidence=1.0,
            extracted_intent=extracted,
            status="processed",
            pipeline_status="PENDING_APPROVAL",
        )
        db.add(discussion)
        db.flush()

        opportunity = AcquisitionOpportunity(
            discussion_id=discussion.id,
            matching_events=matched_events,
            relevance_score=relevance_score,
            generated_response=pack["caption"],
            response_variations=[pack["caption"]],
            content_payload=pack,
            content_generated_by="deterministic_fallback",
            approval_status="pending",
            created_at=datetime.now(timezone.utc),
        )
        db.add(opportunity)

        db.add(
            AgentAction(
                opportunity=opportunity,
                action_type="instagram_content_generated",
                result=f"Generated Instagram content pack for theme '{theme}' with {len(matched_events)} matched event(s).",
                created_at=datetime.now(timezone.utc),
            )
        )

        db.commit()
        db.refresh(opportunity)
        return opportunity
