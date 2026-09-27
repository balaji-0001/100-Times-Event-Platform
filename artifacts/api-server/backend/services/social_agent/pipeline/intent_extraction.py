"""Stage: INTENT_EXTRACTED — real AI understanding of an ambiguous post.

This is the one stage in the pipeline that genuinely needs an LLM: turning
free-form text into structured, ambiguous-language-aware fields (is this
really an event request? what location/date/budget is implied?). Everything
downstream (qualification, matching, thresholds) is deterministic code.

If the AI provider isn't configured, or the model's output fails schema
validation twice in a row, this stage fails honestly (FAILED_AI_EXTRACTION).
There is no regex/keyword fallback pretending to be AI here.
"""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from backend.services.social_agent.ai_client import AIClientError, get_ai_client, not_configured_message


class AILocation(BaseModel):
    city: str = ""
    state: str = ""
    country: str = ""


class AIDateRange(BaseModel):
    start: str = ""
    end: str = ""


class AIBudget(BaseModel):
    min: float | None = None
    max: float | None = None
    currency: str | None = None


class ExtractedIntentAI(BaseModel):
    is_event_related: bool
    intent_type: Literal[
        "EVENT_SEARCH", "EVENT_RECOMMENDATION", "EVENT_DISCOVERY", "GENERAL_DISCUSSION", "IRRELEVANT"
    ]
    event_category: list[str] = Field(default_factory=list)
    event_type: list[str] = Field(default_factory=list)
    location: AILocation = Field(default_factory=AILocation)
    date_range: AIDateRange = Field(default_factory=AIDateRange)
    budget: AIBudget = Field(default_factory=AIBudget)
    urgency: Literal["HIGH", "MEDIUM", "LOW"]
    explicit_event_request: bool
    reason: str
    # --- Topic-agnostic discovery fields (drive the platform-search stage) ---
    topic: str = ""
    keywords: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)


_SYSTEM_PROMPT = (
    "You extract structured event-seeking intent from a single social media post about ANY "
    "possible subject - the topic could be sports, technology, business, arts, music, hobbies, "
    "or anything else. Never assume a specific domain and never reuse categories or queries from "
    "any other analysis; derive everything fresh from this post's own text. Only use information "
    "present or clearly implied in the text — never invent a location, date, or budget that isn't "
    "there.\n\n"
    "Also produce, purely from this post's own content: a short human-readable `topic` label; a "
    "list of `keywords` (the core nouns/phrases this post is actually about); a list of `synonyms` "
    "(closely related terms someone else might use for the same thing); a list of `entities` (any "
    "named people, organizations, brands, or specific things mentioned); and 3-6 diverse "
    "`search_queries` — short, search-engine-style phrases (mixing broad and narrow wording, and "
    "including the city/locale if one is mentioned) that would help find OTHER public posts or "
    "listings about this exact topic. The queries must be entirely driven by what this specific "
    "post says — never a fixed template reused across posts.\n\n"
    "Call the `extract_intent` tool exactly once with your analysis."
)

_TOOL_NAME = "extract_intent"
_TOOL_DESCRIPTION = "Structured event-seeking intent extracted from the post."


class IntentExtractionResult:
    __slots__ = ("success", "data", "error", "retry_count")

    def __init__(
        self,
        success: bool,
        data: ExtractedIntentAI | None = None,
        error: str | None = None,
        retry_count: int = 0,
    ) -> None:
        self.success = success
        self.data = data
        self.error = error
        self.retry_count = retry_count


def extract_intent(title: str, content: str) -> IntentExtractionResult:
    client = get_ai_client()
    if not client.is_configured:
        return IntentExtractionResult(success=False, error=not_configured_message(), retry_count=0)

    user_prompt = f"Post title: {title}\n\nPost content: {content}"
    schema = ExtractedIntentAI.model_json_schema()

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
            # Config/auth/network failures are not retryable — fail immediately.
            return IntentExtractionResult(success=False, error=str(exc), retry_count=attempt)

        try:
            parsed = ExtractedIntentAI.model_validate(raw)
            return IntentExtractionResult(success=True, data=parsed, retry_count=attempt)
        except ValidationError as exc:
            last_error = f"Model output failed schema validation: {exc}"
            continue

    return IntentExtractionResult(success=False, error=last_error, retry_count=1)
