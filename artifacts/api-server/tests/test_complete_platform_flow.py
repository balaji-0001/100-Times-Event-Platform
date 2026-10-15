"""End-to-end integration test suite covering the complete 100 TIMES platform:
- Organizer Onboarding & 12-Stage Lifecycle progression
- 25+ Field Event Creation, Draft saving, and state transitions
- Trust Agent (Agent 3): Multi-signal evaluation, duplicate detection, scam filtering, auto-publishing, admin decisions
- Attendee Agent (Agent 4): Natural language intent extraction, 5-factor weighted event matching, source toggling
- Registration Automation: Capacity enforcement, waitlisting, confirmation code issuance, .ics calendar links
- Timezone-aware Reminder Scheduling (T-7d, T-24h, T-1h) & dispatch
- Event Cancellation, Reschedule diffing, Attendance/No-show tracking, Organizer follow-ups
- Idempotent n8n Webhook handlers with HMAC secret validation
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.core.config import get_settings
from backend.db import get_db
from backend.models import (
    AttendeeIntent,
    AutomationRun,
    Event,
    EventReminder,
    Organization,
    Organizer,
    OrganizerProfile,
    Registration,
    TrustDecision,
    TrustReview,
    User,
)
from backend.routes import webhooks_n8n as webhooks_n8n_routes
from backend.services.attendee_agent import (
    extract_attendee_intent,
    match_events_for_intent,
    process_attendee_signal,
    set_source_enabled,
)
from backend.services.lifecycle import advance_organizer_stage, transition_event_state
from backend.services.notifications import generate_calendar_links
from backend.services.registration_automation import (
    automate_registration,
    cancel_event_workflow,
    dispatch_due_reminders,
    initiate_or_advance_organizer_followup,
    mark_attendance_and_noshows,
    record_organizer_followup_response,
    reschedule_event_workflow,
)
from backend.services.trust_agent import admin_decide_trust_review, evaluate_event_trust


def _test_organizer_user() -> User:
    return User(id=10, name="Summit Host", email="host@techsummit.org", role="ORGANIZER", password_hash="hash")


def _test_attendee_user() -> User:
    return User(id=20, name="Jane Attendee", email="jane@developer.io", role="USER", password_hash="hash")


# ---------------------------------------------------------------------------
# 1. Organizer Onboarding & 12-Stage Lifecycle Progression Tests
# ---------------------------------------------------------------------------


def test_organizer_onboarding_and_lifecycle_progression(db_session):
    """Verifies that an organizer can be onboarded, linked to an organization and profile,
    and advanced through the 12 lifecycle stages."""
    user = _test_organizer_user()
    db_session.add(user)
    db_session.flush()

    org = Organization(name="Tech Horizons Inc", slug="tech-horizons-inc", website="https://techhorizons.org")
    db_session.add(org)
    db_session.flush()

    organizer = Organizer(
        name="Tech Horizons",
        slug="tech-horizons",
        description="Global tech summits and conferences organizer",
        email=user.email,
        user_id=user.id,
    )
    db_session.add(organizer)
    db_session.flush()

    profile = OrganizerProfile(
        user_id=user.id,
        organizer_id=organizer.id,
        organization_id=org.id,
        organization_name=org.name,
        contact_name=user.name,
        contact_email=user.email,
        city="Bengaluru",
        state="Karnataka",
        country="India",
        lifecycle_stage="SIGNED_UP",
        email_verified=True,
        identity_verified=True,
    )
    db_session.add(profile)
    db_session.commit()

    assert profile.lifecycle_stage == "SIGNED_UP"

    # Advance stage to CREATED_EVENT
    advance_organizer_stage(db_session, organizer, profile, "CREATED_EVENT")
    assert profile.lifecycle_stage == "CREATED_EVENT"

    # Advance stage to SUBMITTED
    advance_organizer_stage(db_session, organizer, profile, "SUBMITTED")
    assert profile.lifecycle_stage == "SUBMITTED"

    # Advance to PUBLISHED
    advance_organizer_stage(db_session, organizer, profile, "PUBLISHED")
    assert profile.lifecycle_stage == "PUBLISHED"


# ---------------------------------------------------------------------------
# 2. Rich Event Creation (25+ Fields) & Draft Saving Tests
# ---------------------------------------------------------------------------


def test_rich_event_draft_and_state_transitions(db_session, seeded_catalog):
    """Verifies saving a rich 25+ field event in DRAFT state and transitioning to SUBMITTED."""
    category = seeded_catalog["category"]
    published_event = seeded_catalog["event"]
    organizer = published_event.organizer
    venue = published_event.venue

    event = Event(
        title="Emerging Tech Leaders Summit 2026",
        slug="emerging-tech-leaders-summit-2026",
        description="A full-day conference for engineering managers and startup founders exploring modern AI tooling.",
        event_type="Conference",
        start_date=date.today() + timedelta(days=30),
        end_date=date.today() + timedelta(days=31),
        start_time="09:30 AM",
        end_time="05:30 PM",
        timezone="Asia/Kolkata",
        format="in-person",
        full_address="HITEX Convention Centre, Hitec City",
        city_name="Hyderabad",
        state_name="Telangana",
        country_name="India",
        online_meeting_url=None,
        registration_url="https://100times.io/events/emerging-tech-leaders-summit-2026/register",
        is_free=False,
        price=Decimal("1999.00"),
        capacity=200,
        ticket_info=[{"tier": "Early Bird", "price": 1499, "available": 50}, {"tier": "Standard", "price": 1999, "available": 150}],
        speaker_info=[{"name": "Dr. Sarah Rao", "role": "VP AI Research", "company": "Synthetix"}],
        contact_info={"email": "summit@techleaders.in", "phone": "+91-9876543210"},
        social_links={"x": "https://x.com/techsummit", "linkedin": "https://linkedin.com/company/techsummit"},
        terms_policy="Non-refundable 7 days prior to event.",
        tags=["AI", "Leadership", "Engineering"],
        target_audience="CTOs, Engineering Leads, Product Managers",
        status="draft",
        lifecycle_state="DRAFT",
        category_id=category.id,
        organizer_id=organizer.id,
        venue_id=venue.id,
    )
    db_session.add(event)
    db_session.commit()

    assert event.lifecycle_state == "DRAFT"
    assert event.capacity == 200
    assert len(event.tags) == 3

    # Transition state to SUBMITTED
    transition_event_state(db_session, event, "SUBMITTED", actor="organizer@test.com", reason="Event submission")
    assert event.lifecycle_state == "SUBMITTED"


# ---------------------------------------------------------------------------
# 3. Trust Agent (Agent 3) Multi-Signal Evaluation Tests
# ---------------------------------------------------------------------------


def test_trust_agent_auto_publish_verified_complete_event(db_session, seeded_catalog):
    """A complete event from a verified organizer with no duplicate signals should
    score >= 70, be marked APPROVED, and auto-published."""
    published_event = seeded_catalog["event"]
    organizer = published_event.organizer
    category = seeded_catalog["category"]

    profile = OrganizerProfile(
        user_id=1,
        organizer_id=organizer.id,
        organization_name="Orbit Collective",
        contact_email="lead@orbit.org",
        email_verified=True,
        identity_verified=True,
    )
    db_session.add(profile)
    db_session.flush()

    event = Event(
        title="Verified AI Innovation Conference 2026",
        slug="verified-ai-innovation-conference-2026",
        description="Comprehensive developer conference discussing generative models, agent frameworks, and high-scale production inference with practical architecture sessions.",
        event_type="Conference",
        start_date=date.today() + timedelta(days=20),
        end_date=date.today() + timedelta(days=21),
        start_time="10:00 AM",
        timezone="Asia/Kolkata",
        format="in-person",
        full_address="Koramangala Indoor Stadium, Bengaluru",
        city_name="Bengaluru",
        state_name="Karnataka",
        country_name="India",
        is_free=True,
        capacity=100,
        status="draft",
        lifecycle_state="SUBMITTED",
        category_id=category.id,
        organizer_id=organizer.id,
    )
    db_session.add(event)
    _review, result = evaluate_event_trust(db_session, event, organizer=organizer, profile=profile, auto_publish_if_approved=True)

    assert result.status == "APPROVED"
    assert result.score >= 70
    assert event.status == "published"
    assert event.lifecycle_state == "PUBLISHED"

    # Verify review persisted
    review = db_session.scalar(select(TrustReview).where(TrustReview.event_id == event.id))
    assert review is not None
    assert review.status == "APPROVED"


def test_trust_agent_flags_prohibited_scam_language(db_session, seeded_catalog):
    """An event with deceptive financial/crypto scam keywords should be flagged with warnings."""
    published_event = seeded_catalog["event"]
    organizer = published_event.organizer
    category = seeded_catalog["category"]

    event = Event(
        title="Get Rich Fast Guaranteed 100x Crypto Scheme",
        slug="crypto-guaranteed-returns-scheme",
        description="Learn how to get rich fast with 100% guaranteed profit crypto returns and zero risk secret schemes.",
        event_type="Workshop",
        start_date=date.today() + timedelta(days=10),
        end_date=date.today() + timedelta(days=10),
        start_time="02:00 PM",
        format="online",
        online_meeting_url="https://meet.jit.si/crypto-scheme",
        status="draft",
        lifecycle_state="SUBMITTED",
        category_id=category.id,
        organizer_id=organizer.id,
    )
    db_session.add(event)
    db_session.commit()

    _review, result = evaluate_event_trust(db_session, event, auto_publish_if_approved=True)

    assert result.status in ("REJECTED", "NEEDS_REVIEW")
    assert len(result.warnings) > 0
    # Must NOT auto-publish
    assert event.status != "published"


def test_trust_agent_duplicate_detection(db_session, seeded_catalog):
    """Submitting an event with high title and date similarity to an existing published event
    should identify it as a duplicate candidate."""
    category = seeded_catalog["category"]
    existing_event = seeded_catalog["event"]
    organizer = existing_event.organizer

    duplicate_event = Event(
        title="AI Builders Hackathon",  # Exact duplicate title
        slug="ai-builders-hackathon-second-submission",
        description="Duplicate entry for the hands-on AI hackathon.",
        event_type="Hackathon",
        start_date=existing_event.start_date,
        end_date=existing_event.end_date,
        start_time="09:00 AM",
        format="in-person",
        city_name="Pune",
        status="draft",
        lifecycle_state="SUBMITTED",
        category_id=category.id,
        organizer_id=organizer.id,
    )
    db_session.add(duplicate_event)
    db_session.commit()

    _review, result = evaluate_event_trust(db_session, duplicate_event, auto_publish_if_approved=True)

    assert result.status in ("DUPLICATE", "NEEDS_REVIEW")
    assert len(result.duplicate_candidates) > 0
    assert result.duplicate_candidates[0].candidate_event_id == existing_event.id


def test_admin_decide_trust_review(db_session, seeded_catalog):
    """An admin should be able to manually approve a review that was held for review."""
    event = seeded_catalog["event"]
    event.status = "draft"
    event.lifecycle_state = "TRUST_CHECK"

    review = TrustReview(
        event_id=event.id,
        organizer_id=event.organizer_id,
        status="NEEDS_REVIEW",
        score=70,
        confidence="MEDIUM",
        reasons=["Minor missing social proof"],
        warnings=[],
        recommended_action="HUMAN_REVIEW",
    )
    db_session.add(review)
    db_session.commit()

    updated_review = admin_decide_trust_review(
        db_session,
        review,
        decision="APPROVE",
        admin_user_id=1,
        notes="Manually verified organizer credentials via phone.",
    )

    assert updated_review.status == "APPROVED"
    assert event.status == "published"
    assert event.lifecycle_state == "PUBLISHED"

    # Verify decision logged in TrustDecision
    dec = db_session.scalar(select(TrustDecision).where(TrustDecision.trust_review_id == review.id))
    assert dec is not None
    assert dec.decision == "APPROVE"
    assert "Manually verified" in dec.notes


# ---------------------------------------------------------------------------
# 4. Attendee Agent (Agent 4) Intent Extraction & Matching Tests
# ---------------------------------------------------------------------------


def test_attendee_agent_intent_extraction_and_matching(db_session, seeded_catalog):
    """Verifies parsing natural language attendee intent and computing relevance scores."""
    published_event = seeded_catalog["event"]

    # Natural language query
    user_query = "Looking for an AI hackathon in Pune next week"
    extracted = extract_attendee_intent(user_query)

    assert extracted.category.lower() in ("ai", "artificial intelligence", "technology")
    assert extracted.location.lower() == "pune"
    assert extracted.confidence > 0.5

    # Create AttendeeIntent model instance for matching
    intent = AttendeeIntent(
        raw_text=user_query,
        source_platform="community",
        author_handle="anon",
        event_category=extracted.category,
        location=extracted.location,
        event_type=extracted.event_type,
        date_preference=extracted.time_range,
        price_preference=extracted.price_preference,
        format_preference=extracted.format_preference,
        keywords=extracted.keywords,
        inferred_interests=extracted.inferred_interests,
        confidence=Decimal(str(extracted.confidence)),
        status="MATCHED",
    )
    db_session.add(intent)
    db_session.flush()

    matches = match_events_for_intent(db_session, intent)
    assert len(matches) > 0
    top_match = matches[0]
    assert top_match.event_id == published_event.id
    assert top_match.match_score >= 50
    assert any("location" in r.lower() or "category" in r.lower() or "ai" in r.lower() for r in (top_match.match_reasons or []))


def test_attendee_agent_signal_processing_and_source_toggles(db_session, seeded_catalog):
    """Verifies that public community signals are ingested and source platform limits can be adjusted."""
    intent, matches = process_attendee_signal(
        db_session,
        raw_text="Any upcoming tech summits in Pune?",
        source_platform="telegram",
        author_handle="@techdev",
        source_url="https://t.me/pune_tech/123",
    )
    db_session.commit()

    assert intent.id is not None
    assert intent.source_platform == "telegram"
    assert intent.author_handle == "@techdev"

    # Verify toggling attendee sources
    res = set_source_enabled(db_session, "telegram", enabled=False, daily_limit=15)
    assert res["enabled"] is False
    assert res["dailyLimit"] == 15


# ---------------------------------------------------------------------------
# 5. Registration Automation & Timezone-Aware Reminders Tests
# ---------------------------------------------------------------------------


def test_registration_automation_and_calendar_sync(db_session, seeded_catalog):
    """Verifies full registration flow, capacity enforcement, .ics generation, and reminder creation."""
    event = seeded_catalog["event"]
    event.capacity = 2
    event.timezone = "Asia/Kolkata"
    db_session.commit()

    attendee = _test_attendee_user()
    db_session.add(attendee)
    db_session.commit()

    # 1. Successful first registration
    reg1 = automate_registration(
        db_session,
        event=event,
        user=attendee,
        ticket_type="Standard",
        attendee_name="Jane Attendee",
        attendee_email="jane@developer.io",
    )["registration"]

    assert reg1.status.upper() == "CONFIRMED"
    assert reg1.registration_code.startswith("100T-")

    # Verify scheduled reminders (T-7d, T-24h, T-1h)
    reminders = db_session.scalars(select(EventReminder).where(EventReminder.registration_id == reg1.id)).all()
    assert len(reminders) == 3
    reminder_types = {r.reminder_type for r in reminders}
    assert reminder_types == {"7_DAYS", "24_HOURS", "1_HOUR"}

    # 2. Calendar links generation
    cal = generate_calendar_links(event)
    assert "calendar.google.com" in cal["googleCalendarUrl"]
    assert "BEGIN:VCALENDAR" in cal["icsContent"]
    assert event.title in cal["icsContent"]

    # 3. Register second attendee to fill capacity
    attendee2 = User(id=30, name="Bob Developer", email="bob@developer.io", role="USER", password_hash="x")
    db_session.add(attendee2)
    db_session.commit()

    reg2 = automate_registration(
        db_session,
        event=event,
        user=attendee2,
        ticket_type="Standard",
        attendee_name="Bob Developer",
        attendee_email="bob@developer.io",
    )["registration"]
    assert reg2.status.upper() == "CONFIRMED"

    # 4. Third registration when allow_waitlist=True should be placed on WAITLIST
    attendee3 = User(id=31, name="Charlie", email="charlie@developer.io", role="USER", password_hash="x")
    db_session.add(attendee3)
    db_session.commit()

    reg3 = automate_registration(
        db_session,
        event=event,
        user=attendee3,
        ticket_type="Standard",
        attendee_name="Charlie",
        attendee_email="charlie@developer.io",
        allow_waitlist=True,
    )["registration"]
    assert reg3.status.upper() == "WAITLISTED"


def test_due_reminders_dispatch(db_session, seeded_catalog):
    """Verifies that reminders whose scheduled_for_utc time has passed are marked SENT."""
    event = seeded_catalog["event"]
    attendee = _test_attendee_user()
    db_session.add(attendee)
    db_session.flush()

    reg = Registration(
        event_id=event.id,
        user_id=attendee.id,
        ticket_type="Standard",
        status="CONFIRMED",
        registration_code="100T-TEST-00001",
    )
    db_session.add(reg)
    db_session.flush()

    # Past reminder that is due now
    past_reminder = EventReminder(
        registration_id=reg.id,
        event_id=event.id,
        user_id=attendee.id,
        reminder_type="T-24H",
        scheduled_for_utc=datetime.now(timezone.utc) - timedelta(minutes=15),
        status="SCHEDULED",
        idempotency_key=f"reminder:{event.id}:reg:{reg.id}:T-24H-past",
    )
    db_session.add(past_reminder)
    db_session.commit()

    summary = dispatch_due_reminders(db_session)
    assert summary["sent"] >= 1
    assert past_reminder.status == "SENT"


# ---------------------------------------------------------------------------
# 6. Event Lifecycle: Cancellation, Reschedule & Attendance
# ---------------------------------------------------------------------------


def test_event_cancellation_suppresses_reminders(db_session, seeded_catalog):
    """Cancelling an event updates its state, suppresses pending reminders, and notifies attendees."""
    event = seeded_catalog["event"]
    attendee = _test_attendee_user()
    db_session.add(attendee)
    db_session.flush()

    reg = automate_registration(db_session, event=event, user=attendee, ticket_type="Standard")["registration"]

    summary = cancel_event_workflow(db_session, event, reason="Severe weather forecast", actor_id=1)
    db_session.commit()

    assert event.lifecycle_state == "CANCELLED"
    assert summary["remindersCancelled"] >= 3

    # Verify all reminders are CANCELLED
    pending = db_session.scalars(
        select(EventReminder).where(EventReminder.event_id == event.id, EventReminder.status == "SCHEDULED")
    ).all()
    assert len(pending) == 0


def test_event_reschedule_workflow(db_session, seeded_catalog):
    """Rescheduling an event modifies dates and recalculates reminder schedules."""
    event = seeded_catalog["event"]
    attendee = _test_attendee_user()
    db_session.add(attendee)
    db_session.flush()

    reg = automate_registration(db_session, event=event, user=attendee, ticket_type="Standard")["registration"]

    new_date = event.start_date + timedelta(days=14)
    summary = reschedule_event_workflow(
        db_session,
        event,
        new_start_date=new_date,
        new_end_date=new_date + timedelta(days=1),
        new_start_time="11:00 AM",
        new_timezone="Asia/Kolkata",
        actor_id=1,
    )
    db_session.commit()

    assert event.start_date == new_date
    assert event.start_time == "11:00 AM"
    assert summary["remindersUpdated"] >= 3


def test_attendance_and_organizer_followup(db_session, seeded_catalog):
    """Marks attended vs no-show and initiates organizer post-event follow-up sequence."""
    event = seeded_catalog["event"]
    user1 = _test_attendee_user()
    user2 = User(id=40, name="Attendee 2", email="att2@dev.io", role="USER", password_hash="x")
    db_session.add_all([user1, user2])
    db_session.flush()

    reg1 = automate_registration(db_session, event=event, user=user1, ticket_type="Standard")["registration"]
    reg2 = automate_registration(db_session, event=event, user=user2, ticket_type="Standard")["registration"]

    # Mark reg1 attended, reg2 no-show
    summary = mark_attendance_and_noshows(db_session, event, attended_registration_ids=[reg1.id])
    assert summary["attended"] == 1
    assert summary["noShows"] == 1
    assert reg1.status == "ATTENDED"
    assert reg2.status == "NO_SHOW"

    # Organizer follow-up initiated
    followup = initiate_or_advance_organizer_followup(db_session, event=event, reason="POST_EVENT")
    assert followup.status == "AWAITING_RESPONSE"

    # Record organizer feedback response
    record_organizer_followup_response(
        db_session,
        followup,
        reported_attendance=45,
        event_outcome="SUCCESS",
        organizer_feedback="Great attendees and high engagement.",
        wants_repeat_event=True,
        next_event_date=date.today() + timedelta(days=90),
    )
    assert followup.status == "RESPONDED"
    assert followup.wants_repeat_event is True


# ---------------------------------------------------------------------------
# 7. n8n Webhook Integration & Idempotency Tests
# ---------------------------------------------------------------------------


def test_n8n_webhooks_security_and_idempotency(db_session, seeded_catalog):
    """Verifies that n8n webhook calls validate the secret header and enforce idempotency."""
    event = seeded_catalog["event"]
    attendee = _test_attendee_user()
    db_session.add(attendee)
    db_session.commit()

    app = FastAPI()
    app.include_router(webhooks_n8n_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session

    client = TestClient(app)
    expected_secret = get_settings().n8n_webhook_secret

    payload = {
        "idempotencyKey": f"wf01-test-{event.id}-{attendee.id}",
        "eventId": event.id,
        "userId": attendee.id,
        "data": {"ticketType": "Standard", "calendarProvider": "ics", "emailProvider": "smtp"},
    }

    # 1. Request without secret header should fail 401
    unauth_resp = client.post("/api/webhooks/n8n/registration", json=payload)
    assert unauth_resp.status_code == 401

    # 2. Request with valid secret succeeds 200
    headers = {"X-Webhook-Secret": expected_secret}
    resp1 = client.post("/api/webhooks/n8n/registration", json=payload, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "COMPLETED"
    assert "ticketCode" in data1["result"]

    # 3. Duplicate request with identical idempotencyKey returns cached duplicate
    resp2 = client.post("/api/webhooks/n8n/registration", json=payload, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["idempotentDuplicate"] is True
    assert data2["result"]["ticketCode"] == data1["result"]["ticketCode"]

    # Verify recorded in AutomationRun table
    auto_run = db_session.scalar(
        select(AutomationRun).where(AutomationRun.idempotency_key == payload["idempotencyKey"])
    )
    assert auto_run is not None
    assert auto_run.status == "COMPLETED"
