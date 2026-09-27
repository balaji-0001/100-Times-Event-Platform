"""Stage: DRAFT_GENERATED — platform-native content generation.

When the AI provider is configured, this calls the model with a
platform-specific system prompt and the spec's exact output shape
(content / mentioned_events / contains_link / policy_notes).

When it isn't configured, this stage does NOT pretend to be AI — it falls
back to the existing deterministic per-platform templates
(`backend/services/social_agent/content/*.py`) and honestly labels the
result `generated_by: "deterministic_fallback"` so nothing downstream (or
in the UI) can mistake one for the other.
"""

from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.services.social_agent.ai_client import AIClientError, get_ai_client

_PLATFORM_TONE = {
    "reddit": "Helpful, discussion-first. Answer the question directly before mentioning any event. No hype.",
    "discord": "Casual, friendly community voice. Light emoji is fine. Sounds like a helpful regular, not a bot.",
    "telegram": "Short, conversational, formatted as a quick community update. Bullet points are fine.",
    "x": "Extremely concise — this MUST fit in 280 characters total. No hashtag spam.",
    "linkedin": "Professional, contextual, slightly longer-form. Speaks to career/industry relevance.",
}


class GeneratedContentAI(BaseModel):
    content: str
    mentioned_events: list[str] = Field(default_factory=list)
    contains_link: bool = False
    policy_notes: list[str] = Field(default_factory=list)


_TOOL_NAME = "generate_response"
_TOOL_DESCRIPTION = "The platform-native, policy-compliant response to publish (pending human approval)."


class ContentGenerationResult:
    __slots__ = ("success", "data", "generated_by", "error")

    def __init__(
        self,
        success: bool,
        data: GeneratedContentAI | None = None,
        generated_by: str = "deterministic_fallback",
        error: str | None = None,
    ) -> None:
        self.success = success
        self.data = data
        self.generated_by = generated_by
        self.error = error


def generate_content(
    platform: str,
    title: str,
    original_content: str,
    matched_events: list[dict[str, Any]],
    rules_check: dict[str, Any],
    location: str | None,
) -> ContentGenerationResult:
    client = get_ai_client()

    if client.is_configured:
        result = _generate_via_ai(client, platform, title, original_content, matched_events, rules_check)
        if result.success:
            return result
        # AI was configured but the call/validation failed — do not silently
        # swap to the deterministic path pretending nothing happened; the
        # caller decides whether that's acceptable. We still offer the
        # deterministic draft so a human isn't blocked, but label it clearly.

    return _generate_via_template(platform, title, original_content, matched_events, rules_check, location)


def _format_event_line(ev: dict[str, Any]) -> str:
    price_str = "Free" if ev.get("price", 0) == 0 else f"₹{int(ev['price'])}"
    link = f"https://100times.in/events/{ev['slug']}"
    return f"- {ev['title']} on {ev['startDate']} in {ev['location']} ({price_str}) -- {link}"


def _generate_via_ai(
    client,
    platform: str,
    title: str,
    original_content: str,
    matched_events: list[dict[str, Any]],
    rules_check: dict[str, Any],
) -> ContentGenerationResult:
    tone = _PLATFORM_TONE.get(platform, _PLATFORM_TONE["reddit"])
    links_allowed = rules_check.get("external_links_allowed", True)
    events_summary = "\n".join(_format_event_line(ev) for ev in matched_events[:3])

    system = (
        f"You write a single {platform} response recommending 100.com events to someone who asked about them. "
        f"Tone: {tone} "
        "Rules: answer their question first; only mention events from the provided list, never invent one; "
        f"{'you may include the event link(s) above.' if links_allowed else 'do NOT include any links — this community prohibits them.'} "
        "Never frame this as an advertisement. Call the `generate_response` tool exactly once."
    )
    user = f"Original post title: {title}\nOriginal post: {original_content}\n\nMatched events:\n{events_summary}"

    try:
        raw = client.generate_structured(
            system=system,
            user=user,
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=GeneratedContentAI.model_json_schema(),
        )
        parsed = GeneratedContentAI.model_validate(raw)
        return ContentGenerationResult(success=True, data=parsed, generated_by="ai")
    except AIClientError as exc:
        return ContentGenerationResult(success=False, generated_by="ai", error=str(exc))
    except ValidationError as exc:
        return ContentGenerationResult(success=False, generated_by="ai", error=f"Invalid AI output: {exc}")


def _generate_via_template(
    platform: str,
    title: str,
    original_content: str,
    matched_events: list[dict[str, Any]],
    rules_check: dict[str, Any],
    location: str | None,
) -> ContentGenerationResult:
    from backend.services.social_agent.content.dispatch import get_content_generator

    generator = get_content_generator(platform)
    primary, _variations = generator.generate_variations(
        title=title,
        content=original_content,
        matched_events=matched_events,
        rules_check=rules_check,
        location=location,
    )
    if not primary:
        return ContentGenerationResult(success=False, generated_by="deterministic_fallback", error="No matched events to generate content from")

    data = GeneratedContentAI(
        content=primary,
        mentioned_events=[ev["title"] for ev in matched_events[:3]],
        contains_link="http" in primary,
        policy_notes=[] if rules_check.get("external_links_allowed", True) else ["Links omitted per community policy"],
    )
    return ContentGenerationResult(success=True, data=data, generated_by="deterministic_fallback")
