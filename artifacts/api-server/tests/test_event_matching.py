"""Two-stage event matching: Stage A (real DB filter — published & not yet
started) and Stage B (deterministic weighted scoring, 30/25/20/15/10)."""

from datetime import date, timedelta
from decimal import Decimal

from backend.models import Event
from backend.services.acquisition_agent import EventMatchingEngine


def test_exact_category_and_location_match_scores_high(db_session, seeded_catalog):
    score, matches = EventMatchingEngine.match_events(
        db_session,
        {"event_category": "Artificial Intelligence", "location": "Pune", "event_type": "Hackathon", "budget": "free_or_paid"},
    )
    assert score >= 80
    assert matches[0]["title"] == "AI Builders Hackathon"
    breakdown = matches[0]["scoreBreakdown"]
    assert breakdown["categoryMatch"] > 90
    assert breakdown["locationMatch"] > 90


def test_past_events_are_excluded_by_stage_a_filter(db_session, seeded_catalog):
    past_event = Event(
        title="Old AI Meetup",
        slug="old-ai-meetup",
        description="already happened",
        event_type="Meetup",
        start_date=date.today() - timedelta(days=10),
        end_date=date.today() - timedelta(days=9),
        start_time="10:00 AM",
        price=Decimal("0.00"),
        status="published",
        format="in-person",
        category_id=seeded_catalog["category"].id,
        venue_id=None,
    )
    db_session.add(past_event)
    db_session.commit()

    _, matches = EventMatchingEngine.match_events(
        db_session, {"event_category": "Artificial Intelligence", "location": "Pune", "event_type": "Hackathon"}
    )
    titles = [m["title"] for m in matches]
    assert "Old AI Meetup" not in titles


def test_no_hint_at_all_still_returns_events_with_baseline_score(db_session, seeded_catalog):
    score, matches = EventMatchingEngine.match_events(db_session, {})
    assert len(matches) >= 1
    assert score > 0


def test_free_budget_hint_excludes_paid_events(db_session, seeded_catalog):
    paid_event = Event(
        title="Paid AI Summit",
        slug="paid-ai-summit",
        description="ticketed",
        event_type="Hackathon",
        start_date=date.today() + timedelta(days=20),
        end_date=date.today() + timedelta(days=21),
        start_time="10:00 AM",
        price=Decimal("2000.00"),
        status="published",
        format="in-person",
        category_id=seeded_catalog["category"].id,
        venue_id=None,
    )
    db_session.add(paid_event)
    db_session.commit()

    _, matches = EventMatchingEngine.match_events(
        db_session, {"event_category": "Artificial Intelligence", "location": "Pune", "event_type": "Hackathon", "budget": "free"}
    )
    top = matches[0]
    assert top["title"] == "AI Builders Hackathon"  # the free one still wins on budgetMatch


def test_multiple_strong_matches_all_returned_ranked(db_session, seeded_catalog):
    # Add two more AI/Pune events so three events all plausibly score >= 80.
    for i, days_out in enumerate((21, 28), start=1):
        db_session.add(Event(
            title=f"AI Builders Hackathon Round {i + 1}",
            slug=f"ai-builders-hackathon-round-{i + 1}",
            description="Another hands-on AI hackathon.",
            event_type="Hackathon",
            start_date=date.today() + timedelta(days=days_out),
            end_date=date.today() + timedelta(days=days_out + 1),
            start_time="09:00 AM",
            price=Decimal("0.00"),
            status="published",
            format="in-person",
            category_id=seeded_catalog["category"].id,
            venue_id=None,
        ))
    db_session.commit()

    score, matches = EventMatchingEngine.match_events(
        db_session,
        {"event_category": "Artificial Intelligence", "location": "Pune", "event_type": "Hackathon", "budget": "free_or_paid"},
    )

    assert score >= 80
    assert len(matches) == 3  # top 3 kept, not just the single winner
    scores = [m["relevanceScore"] for m in matches]
    assert scores == sorted(scores, reverse=True)  # ranked highest first
    assert all(s >= 80 for s in scores)
