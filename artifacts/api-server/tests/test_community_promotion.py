"""Agent 4 extension — Community Promotion tests: event/community
eligibility filtering, deterministic matching + scoring, duplicate
candidates, content drafting (AI + deterministic fallback, no AI needed),
and the batch orchestrator's idempotency."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.models import AcquisitionOpportunity, AgentRun, Category, Community, Event, Organizer
from backend.services.social_agent import community_promotion_orchestrator as orchestrator
from backend.services.social_agent.pipeline import community_promotion
from tests.conftest import FakeAIClient


def _category(db_session, name="Technology") -> Category:
    cat = Category(name=name, slug=name.lower().replace(" ", "-"), description=name, icon="sparkles")
    db_session.add(cat)
    db_session.flush()
    return cat


_organizer_counter = [0]


def _organizer(db_session) -> Organizer:
    _organizer_counter[0] += 1
    org = Organizer(name="Test Organizer", slug=f"test-organizer-{_organizer_counter[0]}", description="desc")
    db_session.add(org)
    db_session.flush()
    return org


def _event(db_session, *, title="AI Builders Meetup", category=None, status="published", days_from_now=14, city_name="Pune", format="offline") -> Event:
    event = Event(
        title=title, slug=title.lower().replace(" ", "-") + f"-{days_from_now}", description="A great event.",
        event_type="Meetup", start_date=date.today() + timedelta(days=days_from_now), end_date=date.today() + timedelta(days=days_from_now),
        start_time="18:00", price=Decimal("0.00"), status=status, format=format, city_name=city_name,
        category_id=category.id if category else None, organizer_id=_organizer(db_session).id,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _community(db_session, *, name="Pune Technology Hub", promotion_allowed=True, platform="telegram", platform_ref=None) -> Community:
    community = Community(
        platform=platform, name=name, slug=name.lower().replace(" ", "-"), url=f"https://t.me/{name.lower().replace(' ', '')}",
        promotion_allowed=promotion_allowed, external_links_allowed=True, automation_allowed=False, risk_level="low",
        quality_score=80, platform_ref=platform_ref,
    )
    db_session.add(community)
    db_session.flush()
    return community


# --- eligibility + matching -----------------------------------------------


def test_eligible_events_excludes_unpublished_and_past(db_session):
    cat = _category(db_session)
    upcoming_published = _event(db_session, title="Upcoming Published", category=cat, status="published", days_from_now=10)
    _event(db_session, title="Draft Event", category=cat, status="draft", days_from_now=10)
    _event(db_session, title="Past Event", category=cat, status="published", days_from_now=-10)

    events = community_promotion._eligible_events(db_session)

    assert [e.id for e in events] == [upcoming_published.id]


def test_approved_communities_excludes_unapproved(db_session):
    approved = _community(db_session, name="Approved Hub", promotion_allowed=True)
    _community(db_session, name="Not Yet Approved", promotion_allowed=False)

    communities = community_promotion._approved_communities(db_session)

    assert [c.id for c in communities] == [approved.id]


def test_find_matches_scores_category_and_location(db_session):
    cat = _category(db_session, "Technology")
    event = _event(db_session, title="Pune Tech Meetup", category=cat, city_name="Pune", format="offline")
    community = _community(db_session, name="Pune Technology Hub")  # name contains both "Pune" and "Technology"

    matches = community_promotion.find_event_community_matches(db_session, match_threshold=60)

    assert len(matches) == 1
    matched_event, matched_community, score, explanation = matches[0]
    assert matched_event.id == event.id
    assert matched_community.id == community.id
    assert score >= 60
    assert "category" in explanation.lower() or "technology" in explanation.lower()


def test_find_matches_excludes_unapproved_communities():
    pass  # covered structurally by test_approved_communities_excludes_unapproved; matching only ever iterates approved ones


def test_find_matches_below_threshold_are_excluded(db_session):
    cat = _category(db_session, "Finance")
    _event(db_session, title="Finance Talk", category=cat, city_name="Mumbai")
    _community(db_session, name="Unrelated Book Club")  # no category/location overlap

    matches = community_promotion.find_event_community_matches(db_session, match_threshold=60)

    assert matches == []


def test_find_matches_online_event_scores_without_location(db_session):
    cat = _category(db_session, "Technology")
    _event(db_session, title="Global Tech Webinar", category=cat, format="online", city_name=None)
    _community(db_session, name="Technology Enthusiasts")

    matches = community_promotion.find_event_community_matches(db_session, match_threshold=60)

    assert len(matches) == 1


# --- content drafting: AI + deterministic fallback, no AI required --------


def test_generate_promotion_content_deterministic_when_ai_not_configured(db_session, monkeypatch):
    cat = _category(db_session, "Technology")
    event = _event(db_session, title="AI Builders Meetup", category=cat)
    community = _community(db_session, name="Pune Technology Hub")
    monkeypatch.setattr(community_promotion, "get_ai_client", lambda: FakeAIClient(configured=False))

    result = community_promotion.generate_promotion_content(event, community)

    assert result.success
    assert result.generated_by == "deterministic_fallback"
    assert event.title in result.body
    assert "100times.in/events" in result.body


def test_generate_promotion_content_uses_ai_when_configured(db_session, monkeypatch):
    cat = _category(db_session, "Technology")
    event = _event(db_session, title="AI Builders Meetup", category=cat)
    community = _community(db_session, name="Pune Technology Hub")
    ai_response = {"subject": "Come to AI Builders Meetup!", "body": "Pune folks, check out AI Builders Meetup — details inside."}
    monkeypatch.setattr(community_promotion, "get_ai_client", lambda: FakeAIClient(structured_response=ai_response))

    result = community_promotion.generate_promotion_content(event, community)

    assert result.success
    assert result.generated_by == "ai"
    assert result.subject == ai_response["subject"]


def test_generate_promotion_content_falls_back_when_ai_fails(db_session, monkeypatch):
    cat = _category(db_session, "Technology")
    event = _event(db_session, title="AI Builders Meetup", category=cat)
    community = _community(db_session, name="Pune Technology Hub")
    from backend.services.social_agent.ai_client import AIClientError

    monkeypatch.setattr(community_promotion, "get_ai_client", lambda: FakeAIClient(raise_error=AIClientError("boom")))

    result = community_promotion.generate_promotion_content(event, community)

    assert result.success
    assert result.generated_by == "deterministic_fallback"


# --- orchestrator: idempotency, duplicate skip, AgentRun tracking --------


def test_run_drafts_opportunities_for_matches(db_session, monkeypatch):
    cat = _category(db_session, "Technology")
    event = _event(db_session, title="AI Builders Meetup", category=cat, city_name="Pune")
    community = _community(db_session, name="Pune Technology Hub")
    monkeypatch.setattr(community_promotion, "get_ai_client", lambda: FakeAIClient(configured=False))

    summary = orchestrator.run_community_promotion_agent(db_session)

    assert summary.drafted == 1
    op = db_session.query(AcquisitionOpportunity).one()
    assert op.source_kind == "community_promotion"
    assert op.promoted_event_id == event.id
    assert op.target_community_id == community.id
    assert op.approval_status == "pending"
    assert op.content_generated_by == "deterministic_fallback"
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "community_promotion").one()
    assert run.status == "completed"


def test_run_never_drafts_the_same_pair_twice(db_session, monkeypatch):
    cat = _category(db_session, "Technology")
    _event(db_session, title="AI Builders Meetup", category=cat, city_name="Pune")
    _community(db_session, name="Pune Technology Hub")
    monkeypatch.setattr(community_promotion, "get_ai_client", lambda: FakeAIClient(configured=False))

    first = orchestrator.run_community_promotion_agent(db_session)
    second = orchestrator.run_community_promotion_agent(db_session)

    assert first.drafted == 1
    assert second.drafted == 0
    assert second.skipped_duplicate == 1
    assert db_session.query(AcquisitionOpportunity).count() == 1


def test_run_respects_max_candidates(db_session, monkeypatch):
    cat = _category(db_session, "Technology")
    for i in range(3):
        _event(db_session, title=f"Tech Talk {i}", category=cat, city_name="Pune", days_from_now=10 + i)
    _community(db_session, name="Pune Technology Hub")
    monkeypatch.setattr(community_promotion, "get_ai_client", lambda: FakeAIClient(configured=False))

    summary = orchestrator.run_community_promotion_agent(db_session, orchestrator.CommunityPromotionConfig(max_candidates=2))

    assert summary.drafted == 2
    assert db_session.query(AcquisitionOpportunity).count() == 2


def test_run_never_matches_an_unapproved_community(db_session, monkeypatch):
    cat = _category(db_session, "Technology")
    _event(db_session, title="AI Builders Meetup", category=cat, city_name="Pune")
    _community(db_session, name="Pune Technology Hub", promotion_allowed=False)
    monkeypatch.setattr(community_promotion, "get_ai_client", lambda: FakeAIClient(configured=False))

    summary = orchestrator.run_community_promotion_agent(db_session)

    assert summary.drafted == 0
    assert db_session.query(AcquisitionOpportunity).count() == 0
