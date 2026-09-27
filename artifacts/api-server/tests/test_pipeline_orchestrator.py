"""Integration tests for the full pipeline orchestrator, against a real
in-memory DB and a FakeAIClient — never a real network call."""

from backend.models import AcquisitionOpportunity, Discussion, PipelineExecution
from backend.services.social_agent.pipeline import content_generation, intent_extraction
from tests.conftest import FakeAIClient

HIGH_INTENT_RESPONSE = {
    "is_event_related": True,
    "intent_type": "EVENT_SEARCH",
    "event_category": ["Artificial Intelligence"],
    "event_type": ["Hackathon"],
    "location": {"city": "Pune", "state": "", "country": ""},
    "date_range": {"start": "2026-10-01", "end": ""},
    "budget": {"min": None, "max": None, "currency": None},
    "urgency": "HIGH",
    "explicit_event_request": True,
    "reason": "Explicit request for an AI hackathon in Pune",
}

LOW_INTENT_RESPONSE = {
    "is_event_related": True,
    "intent_type": "GENERAL_DISCUSSION",
    "event_category": [],
    "event_type": [],
    "location": {"city": "", "state": "", "country": ""},
    "date_range": {"start": "", "end": ""},
    "budget": {"min": None, "max": None, "currency": None},
    "urgency": "LOW",
    "explicit_event_request": False,
    "reason": "Just reminiscing about a past event",
}

NO_MATCH_RESPONSE = {
    "is_event_related": True,
    "intent_type": "EVENT_SEARCH",
    "event_category": ["Underwater Basket Weaving"],
    "event_type": ["Retreat"],
    "location": {"city": "Nowhereville", "state": "", "country": ""},
    "date_range": {"start": "2026-10-01", "end": ""},
    "budget": {"min": None, "max": None, "currency": None},
    "urgency": "MEDIUM",
    "explicit_event_request": True,
    "reason": "Explicit but nothing in the catalog matches",
}

CONTENT_RESPONSE = {
    "content": "There's an AI Builders Hackathon in Pune next week that matches what you're after!",
    "mentioned_events": ["AI Builders Hackathon"],
    "contains_link": True,
    "policy_notes": [],
}


def _patch_ai(monkeypatch, *, intent_response=None, intent_configured=True, content_response=None, content_configured=True):
    monkeypatch.setattr(
        intent_extraction, "get_ai_client",
        lambda: FakeAIClient(structured_response=intent_response, configured=intent_configured),
    )
    monkeypatch.setattr(
        content_generation, "get_ai_client",
        lambda: FakeAIClient(structured_response=content_response, configured=content_configured),
    )


def _run(db_session, **overrides):
    from backend.services.social_agent.pipeline.orchestrator import run_pipeline

    params = dict(
        db=db_session, platform="reddit", community_name="r/pune",
        title="Any AI hackathons in Pune?", content="Looking for an AI hackathon in Pune next month.",
    )
    params.update(overrides)
    return run_pipeline(**params)


def test_high_intent_creates_opportunity(db_session, seeded_catalog, monkeypatch):
    _patch_ai(monkeypatch, intent_response=HIGH_INTENT_RESPONSE, content_response=CONTENT_RESPONSE)

    op = _run(db_session)

    assert op is not None
    assert isinstance(op, AcquisitionOpportunity)
    assert op.approval_status == "pending"
    assert op.content_generated_by == "ai"
    assert op.relevance_score >= 80
    assert len(op.matching_events) >= 1

    discussion = db_session.get(Discussion, op.discussion_id)
    assert discussion.pipeline_status == "PENDING_APPROVAL"
    assert discussion.qualification_score == 100
    assert discussion.intent_classification == "HIGH_INTENT"

    execution = db_session.query(PipelineExecution).filter_by(discussion_id=discussion.id).one()
    stages = [s.stage for s in execution.stage_logs]
    assert stages == ["NORMALIZE", "INTENT_EXTRACTION", "QUALIFICATION", "EVENT_MATCHING", "POLICY_CHECK", "CONTENT_GENERATION", "APPROVAL_QUEUE"]
    assert execution.final_status == "PENDING_APPROVAL"


def test_ai_not_configured_fails_honestly(db_session, seeded_catalog, monkeypatch):
    _patch_ai(monkeypatch, intent_configured=False)

    op = _run(db_session)

    assert op is None
    discussion = db_session.query(Discussion).one()
    assert discussion.pipeline_status == "FAILED_AI_EXTRACTION"
    assert discussion.rejection_reason.startswith("AI provider is not configured")


def test_low_intent_rejected_without_opportunity(db_session, seeded_catalog, monkeypatch):
    _patch_ai(monkeypatch, intent_response=LOW_INTENT_RESPONSE)

    op = _run(db_session)

    assert op is None
    discussion = db_session.query(Discussion).one()
    assert discussion.pipeline_status == "REJECTED_LOW_INTENT"
    assert discussion.status == "ignored"
    assert db_session.query(AcquisitionOpportunity).count() == 0


def test_no_matching_event_rejected(db_session, seeded_catalog, monkeypatch):
    _patch_ai(monkeypatch, intent_response=NO_MATCH_RESPONSE)

    op = _run(db_session)

    assert op is None
    discussion = db_session.query(Discussion).one()
    assert discussion.pipeline_status == "REJECTED_NO_MATCH"
    assert "No event scored" in discussion.rejection_reason


def test_duplicate_signal_never_reprocesses(db_session, seeded_catalog, monkeypatch):
    _patch_ai(monkeypatch, intent_response=HIGH_INTENT_RESPONSE, content_response=CONTENT_RESPONSE)

    first = _run(db_session)
    assert first is not None
    execution_count_after_first = db_session.query(PipelineExecution).count()

    second = _run(db_session)  # identical platform/community/title/content -> same external_id
    assert second is not None
    assert second.id == first.id
    assert db_session.query(PipelineExecution).count() == execution_count_after_first, (
        "a duplicate signal must not trigger a second pipeline execution"
    )


def test_community_links_prohibited_omits_link_in_fallback_content(db_session, seeded_catalog, monkeypatch):
    # Only links are prohibited (promotion allowed) so the community stays
    # low-risk and reaches content generation — CommunityRulesChecker
    # escalates to "high risk" (blocked entirely) only when BOTH are False,
    # which is exercised separately by the policy engine's own behavior.
    seeded_catalog["community"].external_links_allowed = False
    seeded_catalog["community"].promotion_allowed = True
    db_session.commit()

    # AI configured for intent extraction, NOT for content generation -> exercises
    # the deterministic fallback template, which must respect the community's
    # link policy exactly like the AI path is instructed to.
    _patch_ai(monkeypatch, intent_response=HIGH_INTENT_RESPONSE, content_configured=False)

    op = _run(db_session, community_name="r/pune")

    assert op is not None
    assert op.content_generated_by == "deterministic_fallback"
    assert "http" not in op.generated_response
    assert "Links omitted per community policy" in op.policy_notes


def test_high_risk_community_blocks_opportunity_entirely(db_session, seeded_catalog, monkeypatch):
    seeded_catalog["community"].external_links_allowed = False
    seeded_catalog["community"].promotion_allowed = False
    db_session.commit()

    _patch_ai(monkeypatch, intent_response=HIGH_INTENT_RESPONSE, content_response=CONTENT_RESPONSE)

    op = _run(db_session)

    assert op is None
    discussion = db_session.query(Discussion).one()
    assert discussion.pipeline_status == "REJECTED_POLICY"
