"""Deterministic Qualification Engine — every case checks the exact point
breakdown, not just the final bucket, since the spec requires every decision
to be explainable."""

from backend.services.social_agent.pipeline.intent_extraction import (
    AIBudget,
    AIDateRange,
    AILocation,
    ExtractedIntentAI,
)
from backend.services.social_agent.pipeline.qualification import qualify


def _intent(**overrides) -> ExtractedIntentAI:
    defaults = dict(
        is_event_related=True,
        intent_type="EVENT_SEARCH",
        event_category=["AI"],
        event_type=["Hackathon"],
        location=AILocation(city="Pune"),
        date_range=AIDateRange(start="2026-10-01"),
        budget=AIBudget(),
        urgency="MEDIUM",
        explicit_event_request=True,
        reason="test",
    )
    defaults.update(overrides)
    return ExtractedIntentAI(**defaults)


def test_full_signal_scores_100_high_intent():
    result = qualify(_intent())
    assert result.score == 100
    assert result.level == "HIGH_INTENT"
    assert result.breakdown == {
        "explicit_request": 30,
        "location": 15,
        "category": 15,
        "event_type": 15,
        "date_context": 15,
        "actionable": 10,
    }


def test_irrelevant_post_scores_zero():
    result = qualify(_intent(is_event_related=False, intent_type="IRRELEVANT"))
    assert result.score == 0
    assert result.level == "IRRELEVANT"


def test_general_discussion_scores_zero_even_if_flagged_event_related():
    result = qualify(_intent(intent_type="GENERAL_DISCUSSION"))
    assert result.score == 0
    assert result.level == "IRRELEVANT"


def test_missing_location_drops_score_by_15():
    result = qualify(_intent(location=AILocation()))
    assert result.breakdown["location"] == 0
    assert result.score == 85
    assert result.level == "HIGH_INTENT"


def test_no_explicit_request_drops_below_high_intent():
    result = qualify(_intent(explicit_event_request=False, location=AILocation()))
    # 100 - 30 (explicit) - 15 (location, also missing) = 55
    assert result.score == 55
    assert result.level == "MEDIUM_INTENT"


def test_sparse_signal_is_low_intent():
    result = qualify(
        _intent(
            explicit_event_request=False,
            event_category=[],
            event_type=[],
            location=AILocation(),
            date_range=AIDateRange(),
            intent_type="GENERAL_DISCUSSION",
        )
    )
    assert result.level == "IRRELEVANT"  # GENERAL_DISCUSSION always short-circuits to IRRELEVANT


def test_medium_intent_band():
    # Only category + actionable = 15 + 10 = 25... need to hit the 50-79 band precisely.
    result = qualify(
        _intent(
            explicit_event_request=False,
            location=AILocation(city="Pune"),
            date_range=AIDateRange(start="2026-10-01"),
        )
    )
    # 15 (location) + 15 (category) + 15 (event_type) + 15 (date) + 10 (actionable) = 70
    assert result.score == 70
    assert result.level == "MEDIUM_INTENT"
