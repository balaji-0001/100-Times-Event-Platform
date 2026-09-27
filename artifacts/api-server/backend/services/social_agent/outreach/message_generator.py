"""Message Generator — drafts a short, professional organizer outreach
email. Uses the same forced tool-use pattern as every other AI stage in
this codebase (`AIClient.generate_structured`) so the model can't ramble
into something spammy; falls back to a deterministic template (matching
the spec's own example) when AI isn't configured or fails, and always
reports which one actually produced the text — the same `generated_by`
honesty convention used by `pipeline/content_generation.py`.

Events reaching this module can come from either producer (a social-media
discussion match, or the Event Discovery Agent's own web search) — the
"why we're reaching out" framing stays honest for both: "we came across
your event" rather than claiming a specific discussion, which wouldn't be
true for a web-discovered event.
"""

from pydantic import BaseModel, ValidationError

from backend.core.config import get_settings
from backend.services.social_agent.ai_client import AIClientError, get_ai_client
from backend.services.social_agent.outreach.types import EventDetails, OrganizerContactInfo


class OutreachEmailAI(BaseModel):
    subject: str
    body: str


_SYSTEM_PROMPT = (
    "You write ONE short, professional, non-spammy outreach email inviting a real event "
    "organizer to list their event on 100Times, an event discovery platform where people find "
    "events happening across India. The event can be about ANY subject — never assume a "
    "category. Only reference facts given to you; never invent event details, attendance "
    "figures, guaranteed reach/results, or misleading claims. "
    "Structure: address the organizer by name if given, a brief line on why you're reaching out "
    "(you came across their event), one sentence on what 100Times does, an offer to showcase "
    "the event to a wider audience, a clear call to action with the given listing URL, and a "
    "closing note that they're welcome to list other upcoming events too. Plain and genuine — "
    "no exclamation-heavy enthusiasm, no fake urgency, no bullet lists, no guaranteed-attendee "
    "or guaranteed-revenue claims. Call the `write_outreach_email` tool exactly once."
)

_FOLLOWUP_SYSTEM_PROMPT = (
    "You write ONE short, low-pressure follow-up email to an event organizer who was emailed "
    "about listing their event on 100Times about a week ago and hasn't replied. Acknowledge "
    "they may be busy or not interested, restate the offer briefly, include the listing URL, "
    "and make clear this is the only follow-up (no further emails implied). Never invent facts "
    "or make guaranteed-results claims. Call the `write_outreach_email` tool exactly once."
)


def _platform_url() -> str:
    return get_settings().platform_listing_url


def _event_context_lines(event: EventDetails) -> str:
    lines = [
        f"Event name: {event.name or 'unknown'}",
        f"Category/topic: {event.category or 'unknown'}" + (f" ({event.subcategory})" if event.subcategory else ""),
        f"Location: {event.venue or event.location or 'unknown'}" + (f", {event.city}" if event.city else ""),
        f"Date: {event.date or 'unknown'}",
        f"Format: {event.event_format or 'unknown'}",
    ]
    if event.ticket_url:
        lines.append(f"Event/ticket URL: {event.ticket_url}")
    return "\n".join(lines)


def _deterministic_initial(event: EventDetails, organizer: OrganizerContactInfo) -> OutreachEmailAI:
    organizer_name = organizer.name or "there"
    event_name = event.name or "your event"
    location = event.city or event.venue or event.location or "your area"
    return OutreachEmailAI(
        subject=f"Help more people discover {event_name} on 100Times",
        body=(
            f"Hi {organizer_name},\n\n"
            f"I came across {event_name} and noticed you're organizing it in {location}.\n\n"
            f"We run 100Times, an event discovery platform where people can discover events "
            f"happening across India.\n\n"
            f"We'd love to help you showcase {event_name} to a wider audience by listing it on "
            f"100Times. You can list your event here:\n{_platform_url()}\n\n"
            f"If you have upcoming events as well, we'd be happy to have them listed on the "
            f"platform too.\n\nBest regards,\n100Times Team\n{_platform_url()}"
        ),
    )


def _deterministic_followup(event: EventDetails, organizer: OrganizerContactInfo) -> OutreachEmailAI:
    event_name = event.name or "your event"
    return OutreachEmailAI(
        subject=f"Following up: {event_name} on 100Times",
        body=(
            f"Hi {organizer.name or 'there'},\n\n"
            f"Just following up on our earlier note about listing {event_name} on 100Times — "
            f"no worries at all if now isn't the right time. If you'd like to explore it, the "
            f"link is still here:\n{_platform_url()}\n\nBest regards,\n100Times Team"
        ),
    )


def _try_ai(system_prompt: str, event: EventDetails, organizer: OrganizerContactInfo) -> OutreachEmailAI | None:
    client = get_ai_client()
    if not client.is_configured:
        return None
    user_prompt = (
        f"Organizer name: {organizer.name or 'unknown'}\n"
        f"{_event_context_lines(event)}\n"
        f"100Times listing URL: {_platform_url()}\n"
    )
    try:
        raw = client.generate_structured(
            system=system_prompt,
            user=user_prompt,
            tool_name="write_outreach_email",
            tool_description="A drafted organizer outreach email (subject + body).",
            input_schema=OutreachEmailAI.model_json_schema(),
        )
        return OutreachEmailAI.model_validate(raw)
    except (AIClientError, ValidationError):
        return None


def generate_outreach_message(event: EventDetails, organizer: OrganizerContactInfo) -> tuple[OutreachEmailAI, str]:
    ai_result = _try_ai(_SYSTEM_PROMPT, event, organizer)
    if ai_result is not None:
        return ai_result, "ai"
    return _deterministic_initial(event, organizer), "deterministic_fallback"


def generate_followup_message(event: EventDetails, organizer: OrganizerContactInfo) -> tuple[OutreachEmailAI, str]:
    ai_result = _try_ai(_FOLLOWUP_SYSTEM_PROMPT, event, organizer)
    if ai_result is not None:
        return ai_result, "ai"
    return _deterministic_followup(event, organizer), "deterministic_fallback"
