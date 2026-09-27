"""Stage: MATCHED — two-stage deterministic event matching.

Stage A (candidate filtering) and Stage B (weighted scoring) both live in
`EventMatchingEngine.match_events` (backend/services/acquisition_agent.py) —
that engine was already DB-backed and deterministic; this module just adapts
the AI's structured `ExtractedIntentAI` into the flat hint-dict it expects,
so the proven scoring/filtering logic isn't duplicated.
"""

from typing import Any

from sqlalchemy.orm import Session

from backend.services.social_agent.pipeline.intent_extraction import ExtractedIntentAI

NO_RELEVANT_EVENT_FOUND = "NO_RELEVANT_EVENT_FOUND"
QUALIFIED_MATCH_THRESHOLD = 80


def flatten_intent(intent: ExtractedIntentAI) -> dict[str, Any]:
    """Adapts the rich AI schema into the flat string-hint dict that
    `EventMatchingEngine.match_events` and the platform content generators
    already consume — keeps that proven code path unchanged."""
    category = intent.event_category[0] if intent.event_category else ""
    event_type = intent.event_type[0] if intent.event_type else ""
    location = intent.location.city or intent.location.state or intent.location.country or ""

    if intent.budget.max is not None and intent.budget.max <= 0:
        budget = "free"
    elif intent.budget.max is not None:
        budget = f"under_{int(intent.budget.max)}"
    else:
        budget = "free_or_paid"

    date_range = "upcoming"
    if intent.date_range.start:
        date_range = intent.date_range.start

    return {
        "intent": "find_event",
        "event_category": category,
        "event_type": event_type,
        "location": location or None,
        "date_range": date_range,
        "budget": budget,
    }


def find_and_score_events(db: Session, intent: ExtractedIntentAI) -> tuple[int, list[dict[str, Any]]]:
    """Returns (overall_relevance_score, top_matches). Empty list + score 0
    means NO_RELEVANT_EVENT_FOUND — callers should not generate content."""
    from backend.services.acquisition_agent import EventMatchingEngine

    hint_dict = flatten_intent(intent)
    return EventMatchingEngine.match_events(db, hint_dict)
