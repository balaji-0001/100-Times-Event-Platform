"""Stage: EVENT_EXTRACTED — turns ONE candidate post (found by the platform-
search stage) into structured, ANY-topic event details.

This is deliberately a separate AI call from `intent_extraction.py`: that
stage understands the ORIGINAL asking discussion ("is someone looking for an
event, and about what"); this one looks at a DIFFERENT post surfaced by
search and decides "does this post actually describe a specific, genuine
event" — the two questions need different judgment and different posts as
input.

Same honesty rules as the rest of the pipeline: no keyword/regex fallback
pretending to be AI, no invented dates/locations/organizers, and this stage
fails openly (`success=False`) rather than silently guessing when AI isn't
configured or output fails schema validation twice in a row.
"""

from pydantic import BaseModel, Field, ValidationError

from backend.services.social_agent.ai_client import AIClientError, get_ai_client, not_configured_message


class ExtractedEventAI(BaseModel):
    is_genuine_event: bool
    event_name: str = ""
    category: str = ""
    event_type: str = ""
    description: str = ""
    date: str = ""
    time: str = ""
    location: str = ""
    organizer: str = ""
    registration_url: str = ""
    is_free: bool | None = None
    price: float | None = None
    confidence_score: int = Field(ge=0, le=100)
    relevance_score: int = Field(ge=0, le=100)
    reason: str


_SYSTEM_PROMPT = (
    "You analyze ONE social media post to decide whether it genuinely describes a specific, "
    "real-world event — the event could be about ANY subject (sports, technology, business, "
    "arts, music, hobbies, or anything else); never assume a domain. Only use information "
    "present or clearly implied in the text — never invent a date, location, price, or "
    "organizer that isn't there; leave a field blank instead of guessing.\n\n"
    "Set `is_genuine_event` to false (and leave the other fields blank/zero) for: questions "
    "asking about events rather than announcing one, general chit-chat, spam, advertisements "
    "with no specific event, recaps of past events, or posts with too little information to "
    "identify a real event.\n\n"
    "`confidence_score` (0-100) is how confident you are this is a real, specific event (not "
    "vague chatter). `relevance_score` (0-100) is how relevant this event is to the search "
    "topic you were given. Call the `extract_event` tool exactly once."
)

_TOOL_NAME = "extract_event"
_TOOL_DESCRIPTION = "Structured event details extracted from a candidate post, for any topic."


class EventExtractionResult:
    __slots__ = ("success", "data", "error", "retry_count")

    def __init__(
        self,
        success: bool,
        data: ExtractedEventAI | None = None,
        error: str | None = None,
        retry_count: int = 0,
    ) -> None:
        self.success = success
        self.data = data
        self.error = error
        self.retry_count = retry_count


def extract_event(topic_summary: str, candidate_title: str, candidate_content: str) -> EventExtractionResult:
    client = get_ai_client()
    if not client.is_configured:
        return EventExtractionResult(success=False, error=not_configured_message(), retry_count=0)

    user_prompt = (
        f"Search topic: {topic_summary}\n\n"
        f"Candidate post title: {candidate_title}\n\n"
        f"Candidate post content: {candidate_content}"
    )
    schema = ExtractedEventAI.model_json_schema()

    last_error = "Unknown extraction failure"
    for attempt in range(2):  # one attempt + one retry on invalid structured output
        try:
            raw = client.generate_structured(
                system=_SYSTEM_PROMPT,
                user=user_prompt,
                tool_name=_TOOL_NAME,
                tool_description=_TOOL_DESCRIPTION,
                input_schema=schema,
            )
        except AIClientError as exc:
            return EventExtractionResult(success=False, error=str(exc), retry_count=attempt)

        try:
            parsed = ExtractedEventAI.model_validate(raw)
            return EventExtractionResult(success=True, data=parsed, retry_count=attempt)
        except ValidationError as exc:
            last_error = f"Model output failed schema validation: {exc}"
            continue

    return EventExtractionResult(success=False, error=last_error, retry_count=1)


def flatten_extracted_event(event: ExtractedEventAI) -> dict:
    """Adapts `ExtractedEventAI` into the same flat hint-dict shape
    `EventMatchingEngine.match_events` already consumes (see
    `pipeline/event_matching.py::flatten_intent`) — keeps that proven
    deterministic matcher unchanged for the discovery flow too."""
    if event.is_free:
        budget = "free"
    elif event.price is not None:
        budget = f"under_{int(event.price) + 1}"
    else:
        budget = "free_or_paid"

    return {
        "intent": "find_event",
        "event_category": event.category,
        "event_type": event.event_type,
        "location": event.location or None,
        "date_range": event.date or "upcoming",
        "budget": budget,
    }
