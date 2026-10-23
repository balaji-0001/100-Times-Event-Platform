"""Persistence layer for the Community Discovery Agent — the only place
that writes `DiscoveredCommunity`/`community_sources` rows. Always
dedup-checks before inserting, commits after each item so a run that
crashes partway through leaves real, non-duplicated progress behind.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import CommunitySource, DiscoveredCommunity
from backend.services.community_agent import discovery_dedup
from backend.services.community_agent.types import ExtractedCommunityCandidate, RunSummary


def persist_community(
    db: Session,
    *,
    candidate: ExtractedCommunityCandidate,
    approval_status: str,
    verification_notes: list[str],
    confidence_score: int,
    category: str | None,
    subcategory: str | None,
    summary: RunSummary,
) -> DiscoveredCommunity | None:
    """Returns the persisted row, or `None` if this was a duplicate (already
    counted in `summary.duplicate_communities`) and nothing new was written."""
    summary.communities_discovered += 1

    duplicate = discovery_dedup.find_duplicate_community(db, canonical_url=candidate.canonical_url, name=candidate.name, platform=candidate.platform)
    if duplicate is not None:
        summary.duplicate_communities += 1
        duplicate.last_checked_at = datetime.now(timezone.utc)
        db.commit()
        return None

    if approval_status == "NEEDS_REVIEW":
        summary.communities_needing_review += 1

    community = DiscoveredCommunity(
        platform=candidate.platform,
        name=candidate.name or "Unnamed community",
        canonical_url=candidate.canonical_url,
        invite_url=candidate.invite_url,
        description=candidate.description,
        category=category,
        subcategory=subcategory,
        topics=[category] if category else [],
        language=candidate.language,
        city=candidate.city,
        state=candidate.state,
        country=candidate.country,
        member_count=candidate.member_count,
        rules_text=candidate.rules_text,
        promotion_allowed=None,  # never set by the agent — only an admin decides this
        automation_allowed=False,
        risk_level="unknown",
        confidence_score=confidence_score,
        discovery_status="NEW",
        verification_notes=verification_notes,
        approval_status=approval_status,
        connection_status="NOT_CONNECTED",
        discovered_at=datetime.now(timezone.utc),
        last_checked_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(community)
    db.flush()
    summary.new_communities += 1

    seen_urls = set()
    for source in candidate.sources:
        if source.url in seen_urls:
            continue
        seen_urls.add(source.url)
        db.add(
            CommunitySource(
                discovered_community_id=community.id,
                source_url=source.url,
                source_type=source.source_type,
                extracted_fields=candidate.raw_evidence if candidate.primary_source and source.url == candidate.primary_source.url else None,
                fetched_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
        )

    db.commit()
    return community
