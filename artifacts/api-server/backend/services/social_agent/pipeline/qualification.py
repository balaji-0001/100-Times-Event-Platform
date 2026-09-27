"""Stage: QUALIFIED — deterministic qualification engine.

No LLM confidence is used anywhere here. Every point is computed from the
already-extracted structured fields, so the decision is fully explainable
and reproducible — the "Golden Rule": AI understands, backend decides.
"""

from dataclasses import dataclass, field

from backend.services.social_agent.pipeline.intent_extraction import ExtractedIntentAI

HIGH_INTENT_THRESHOLD = 80
MEDIUM_INTENT_THRESHOLD = 50

_ACTIONABLE_INTENT_TYPES = {"EVENT_SEARCH", "EVENT_RECOMMENDATION", "EVENT_DISCOVERY"}


@dataclass
class QualificationResult:
    score: int
    level: str  # HIGH_INTENT | MEDIUM_INTENT | LOW_INTENT | IRRELEVANT
    breakdown: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def qualify(intent: ExtractedIntentAI) -> QualificationResult:
    if not intent.is_event_related or intent.intent_type in ("IRRELEVANT", "GENERAL_DISCUSSION"):
        return QualificationResult(
            score=0,
            level="IRRELEVANT",
            breakdown={},
            reasons=["Not event-related (AI classified as IRRELEVANT or GENERAL_DISCUSSION)"],
        )

    breakdown: dict[str, int] = {}
    reasons: list[str] = []

    if intent.explicit_event_request:
        breakdown["explicit_request"] = 30
        reasons.append("+30 Explicit event request")
    else:
        breakdown["explicit_request"] = 0

    has_location = bool(intent.location.city or intent.location.state or intent.location.country)
    breakdown["location"] = 15 if has_location else 0
    if has_location:
        reasons.append("+15 Location identified")

    breakdown["category"] = 15 if intent.event_category else 0
    if intent.event_category:
        reasons.append("+15 Category identified")

    breakdown["event_type"] = 15 if intent.event_type else 0
    if intent.event_type:
        reasons.append("+15 Event type identified")

    has_date = bool(intent.date_range.start or intent.date_range.end)
    breakdown["date_context"] = 15 if has_date else 0
    if has_date:
        reasons.append("+15 Date/time context identified")

    is_actionable = intent.intent_type in _ACTIONABLE_INTENT_TYPES
    breakdown["actionable"] = 10 if is_actionable else 0
    if is_actionable:
        reasons.append("+10 Clear actionable request")

    score = sum(breakdown.values())

    if score >= HIGH_INTENT_THRESHOLD:
        level = "HIGH_INTENT"
    elif score >= MEDIUM_INTENT_THRESHOLD:
        level = "MEDIUM_INTENT"
    else:
        level = "LOW_INTENT"

    return QualificationResult(score=score, level=level, breakdown=breakdown, reasons=reasons)
