import pytest

from backend.services.social_agent.state_machine import (
    InvalidTransitionError,
    transition_discussion,
    transition_opportunity,
)


def test_discussion_happy_path_transitions_are_all_valid():
    path = [
        "DISCOVERED", "NORMALIZED", "INTENT_EXTRACTED", "QUALIFIED",
        "MATCHED", "RULES_CHECKED", "DRAFT_GENERATED", "PENDING_APPROVAL",
    ]
    current = path[0]
    for target in path[1:]:
        current = transition_discussion(current, target)
    assert current == "PENDING_APPROVAL"


def test_discussion_cannot_skip_stages():
    with pytest.raises(InvalidTransitionError):
        transition_discussion("DISCOVERED", "MATCHED")


def test_discussion_terminal_states_accept_no_further_transitions():
    with pytest.raises(InvalidTransitionError):
        transition_discussion("REJECTED_LOW_INTENT", "QUALIFIED")


def test_opportunity_approve_then_manual_publish_then_published():
    status = "pending"
    status = transition_opportunity(status, "approved")
    status = transition_opportunity(status, "ready_for_manual_publishing")
    status = transition_opportunity(status, "published")
    assert status == "published"


def test_opportunity_cannot_go_from_published_back_to_approved():
    with pytest.raises(InvalidTransitionError):
        transition_opportunity("published", "approved")


def test_opportunity_scheduled_can_still_be_approved_or_rejected():
    assert transition_opportunity("scheduled", "approved") == "approved"
    assert transition_opportunity("scheduled", "rejected") == "rejected"


def test_opportunity_rejected_is_terminal():
    with pytest.raises(InvalidTransitionError):
        transition_opportunity("rejected", "approved")
