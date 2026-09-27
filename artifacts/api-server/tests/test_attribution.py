from backend.models import AcquisitionOpportunity, ClickEvent, Discussion, Registration, User
from backend.services.social_agent.attribution import attribute_registration


def _make_discussion_and_opportunity(db_session, community_id):
    discussion = Discussion(
        community_id=community_id,
        platform="reddit",
        external_id="ext-attr-1",
        url="https://reddit.com",
        title="t",
        content="c",
        intent_classification="HIGH_INTENT",
        intent_confidence=0.9,
        status="processed",
        pipeline_status="PENDING_APPROVAL",
    )
    db_session.add(discussion)
    db_session.flush()

    opportunity = AcquisitionOpportunity(
        discussion_id=discussion.id,
        matching_events=[],
        relevance_score=90,
        generated_response="resp",
        response_variations=["resp"],
        approval_status="published",
    )
    db_session.add(opportunity)
    db_session.flush()
    return opportunity


def test_registration_within_window_is_attributed(db_session, seeded_catalog):
    opportunity = _make_discussion_and_opportunity(db_session, seeded_catalog["community"].id)
    click = ClickEvent(opportunity_id=opportunity.id, anonymous_session_id="sess-1", destination_url="https://x")
    db_session.add(click)

    user = User(name="Test", email="t@example.com", password_hash="x", role="USER")
    db_session.add(user)
    db_session.flush()

    registration = Registration(event_id=seeded_catalog["event"].id, user_id=user.id, ticket_type="general", status="confirmed")
    db_session.add(registration)
    db_session.flush()

    attribution = attribute_registration(db_session, registration, "sess-1", event_id=seeded_catalog["event"].id)

    assert attribution is not None
    assert attribution.click_id == click.id
    assert attribution.opportunity_id == opportunity.id


def test_no_click_means_no_attribution(db_session, seeded_catalog):
    user = User(name="Test2", email="t2@example.com", password_hash="x", role="USER")
    db_session.add(user)
    db_session.flush()
    registration = Registration(event_id=seeded_catalog["event"].id, user_id=user.id, ticket_type="general", status="confirmed")
    db_session.add(registration)
    db_session.flush()

    attribution = attribute_registration(db_session, registration, "no-such-session", event_id=seeded_catalog["event"].id)
    assert attribution is None


def test_no_session_cookie_means_no_attribution(db_session, seeded_catalog):
    user = User(name="Test3", email="t3@example.com", password_hash="x", role="USER")
    db_session.add(user)
    db_session.flush()
    registration = Registration(event_id=seeded_catalog["event"].id, user_id=user.id, ticket_type="general", status="confirmed")
    db_session.add(registration)
    db_session.flush()

    attribution = attribute_registration(db_session, registration, None, event_id=seeded_catalog["event"].id)
    assert attribution is None
