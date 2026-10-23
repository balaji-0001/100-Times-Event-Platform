"""Validation gate — scores a discovered community candidate and decides
whether it lands at `DISCOVERED` (ready for an admin to review) or
`NEEDS_REVIEW` (something about it is thin enough to flag more visibly).

Unlike `discovery_agent/validation.py`, there is no auto-`VERIFIED`/auto-pass
outcome here at all: the brief requires an admin to explicitly approve or
reject every community before it can ever be used for promotion, regardless
of confidence — discovery only ever produces a lead, never a decision.
"""

from backend.services.community_agent.types import ExtractedCommunityCandidate


def validate_community(candidate: ExtractedCommunityCandidate, confidence_threshold: int) -> tuple[str, list[str], int]:
    """Returns (approval_status, notes, confidence_score)."""
    notes: list[str] = []
    confidence = candidate.extraction_confidence

    if candidate.description:
        confidence += 10
    else:
        notes.append("No description was found on the source page — relevance/topic could not be assessed confidently.")

    if candidate.member_count is not None:
        confidence += 10
    else:
        notes.append("Member/subscriber count is not shown publicly for this community — left unknown, never estimated.")

    if not candidate.rules_text:
        notes.append("No posting/promotion rules were found — promotion permission must be checked by a human before this community can be used.")

    confidence = max(0, min(confidence, 100))

    status = "NEEDS_REVIEW" if (confidence < confidence_threshold or not candidate.description or candidate.member_count is None) else "DISCOVERED"
    return status, notes, confidence
