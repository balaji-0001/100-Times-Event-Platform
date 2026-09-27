"""Central state-machine guard for pipeline and approval statuses.

Every status write in the acquisition pipeline should go through
`transition()` so an invalid jump (e.g. `published -> matched`) raises
instead of silently corrupting state.
"""

# Discussion.pipeline_status lifecycle
DISCUSSION_TRANSITIONS: dict[str, set[str]] = {
    "DISCOVERED": {"NORMALIZED", "FAILED_PROCESSING"},
    "NORMALIZED": {"INTENT_EXTRACTED", "FAILED_AI_EXTRACTION", "FAILED_PROCESSING"},
    "INTENT_EXTRACTED": {"QUALIFIED", "REJECTED_LOW_INTENT", "FAILED_PROCESSING"},
    "QUALIFIED": {"MATCHED", "REJECTED_NO_MATCH", "FAILED_PROCESSING"},
    "MATCHED": {"RULES_CHECKED", "REJECTED_POLICY", "FAILED_PROCESSING"},
    "RULES_CHECKED": {"DRAFT_GENERATED", "REJECTED_POLICY", "FAILED_AI_EXTRACTION", "FAILED_PROCESSING"},
    "DRAFT_GENERATED": {"PENDING_APPROVAL", "FAILED_PROCESSING"},
    "PENDING_APPROVAL": set(),  # terminal for the Discussion; AcquisitionOpportunity takes over
    # Terminal / failure states — no further transitions.
    "REJECTED_LOW_INTENT": set(),
    "REJECTED_NO_MATCH": set(),
    "REJECTED_POLICY": set(),
    "FAILED_AI_EXTRACTION": set(),
    "FAILED_PROCESSING": set(),
}

# AcquisitionOpportunity.approval_status lifecycle
OPPORTUNITY_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved", "rejected", "scheduled", "ignored"},
    "scheduled": {"approved", "rejected", "ready_for_manual_publishing", "published"},
    "approved": {"ready_for_manual_publishing", "published", "rejected"},
    "ready_for_manual_publishing": {"published", "rejected"},
    "published": set(),
    "rejected": set(),
    "ignored": set(),
}

# OutreachMessage.status lifecycle (Organizer Outreach "Agent 2").
# SENT exists for schema/future-ESP compatibility but is not reachable with
# plain SMTP alone — a successful send goes straight to DELIVERED since
# there's no separate async delivery confirmation to wait for.
OUTREACH_MESSAGE_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"RESEARCHED", "REJECTED", "OPTED_OUT"},
    "RESEARCHED": {"EMAIL_GENERATED", "REJECTED", "OPTED_OUT"},
    "EMAIL_GENERATED": {"PENDING_APPROVAL", "REJECTED", "OPTED_OUT"},
    "PENDING_APPROVAL": {"APPROVED", "REJECTED", "OPTED_OUT"},
    "APPROVED": {"SENT", "DELIVERED", "BOUNCED", "REJECTED", "OPTED_OUT"},
    "SENT": {"DELIVERED", "BOUNCED"},
    "DELIVERED": {"REPLIED", "OPTED_OUT", "FOLLOW_UP_DUE", "COMPLETED"},
    "BOUNCED": {"COMPLETED"},
    "FOLLOW_UP_DUE": {"APPROVED", "REJECTED", "OPTED_OUT"},
    "REPLIED": {"COMPLETED"},
    "OPTED_OUT": {"COMPLETED"},
    "COMPLETED": set(),
    "REJECTED": set(),
}


class InvalidTransitionError(ValueError):
    def __init__(self, entity: str, current: str, target: str):
        super().__init__(f"Invalid {entity} transition: '{current}' -> '{target}'")
        self.entity = entity
        self.current = current
        self.target = target


def transition_discussion(current: str, target: str) -> str:
    allowed = DISCUSSION_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError("Discussion.pipeline_status", current, target)
    return target


def transition_opportunity(current: str, target: str) -> str:
    allowed = OPPORTUNITY_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError("AcquisitionOpportunity.approval_status", current, target)
    return target


def transition_outreach_message(current: str, target: str) -> str:
    allowed = OUTREACH_MESSAGE_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError("OutreachMessage.status", current, target)
    return target
