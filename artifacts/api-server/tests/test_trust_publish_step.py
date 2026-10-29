"""Trust review: an admin first approves an event, then publishes it as a
separate step; publishing needs an approved review and happens only once."""

import pytest

from backend.models import TrustReview
from backend.services.trust_agent import admin_decide_trust_review


@pytest.fixture()
def held_event(db_session, seeded_catalog):
    event = seeded_catalog["event"]
    event.status, event.lifecycle_state = "draft", "NEEDS_REVIEW"
    review = TrustReview(event_id=event.id, status="NEEDS_REVIEW", score=40, confidence="LOW", recommended_action="MANUAL_REVIEW")
    db_session.add(review)
    db_session.commit()
    return event, review


def test_approve_does_not_publish_then_publish_does(db_session, held_event):
    event, review = held_event

    admin_decide_trust_review(db_session, review, decision="APPROVE", admin_user_id=1)
    assert review.status == "APPROVED" and event.lifecycle_state == "APPROVED"
    assert event.status != "published"

    admin_decide_trust_review(db_session, review, decision="PUBLISH", admin_user_id=1)
    assert review.status == "APPROVED" and event.lifecycle_state == "PUBLISHED"

    with pytest.raises(ValueError, match="already published"):
        admin_decide_trust_review(db_session, review, decision="PUBLISH", admin_user_id=1)


def test_an_event_still_under_review_cannot_be_published(db_session, held_event):
    event, review = held_event
    with pytest.raises(ValueError, match="Approve it first"):
        admin_decide_trust_review(db_session, review, decision="PUBLISH", admin_user_id=1)
    assert event.lifecycle_state == "NEEDS_REVIEW"
