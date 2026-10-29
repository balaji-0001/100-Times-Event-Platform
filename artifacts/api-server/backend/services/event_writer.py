"""Description assistant for organisers creating an event.

Writes (or rewrites) an event description from what the organiser has typed
into the create-event form plus, optionally, their own instructions. The only
facts it may use are those two sources: the model is told never to add
speakers, sponsors, numbers, prices, dates or venues that weren't given, and
the organiser always reviews the draft before using it.

Without a configured AI provider, a request with no instructions still gets a
plain description assembled from the form fields (`source="template"`); a
request with instructions fails honestly instead of pretending to follow them.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.services.social_agent import ai_client as ai_client_module
from backend.services.social_agent.ai_client import AIClientError

SYSTEM = """You write event descriptions for 100 TIMES, an event listing platform.

Rules:
- Use ONLY facts from the event details and the organiser's messages. Never invent speakers, sponsors, partners, attendee numbers, prices, dates, venues, agenda items, awards or statistics.
- Don't promise activities or benefits that weren't mentioned (workshops, networking, demos, exhibitors, "cutting-edge insights"). Describe what the event is, for whom, when and where.
- If a detail isn't given, leave it out. Don't write placeholders like "[speaker name]".
- Follow the organiser's instructions for tone, length and focus. If they mention a fact (e.g. "there are hands-on labs"), you may use it.
- Plain text only: no markdown, headings, bullet symbols or emojis unless the organiser asks for them. Paragraphs separated by a blank line are fine.
- Default length 90-160 words unless the organiser asks otherwise. Never exceed 300 words.
- Write in the same language as the organiser's message (English if there is none).
- Reply with the description text only, no preamble or commentary."""

_FIELD_LABELS = (
    ("title", "Title"),
    ("event_type", "Event type"),
    ("sector", "Sector"),
    ("format", "Format"),
    ("start_date", "Start date"),
    ("end_date", "End date"),
    ("start_time", "Start time"),
    ("city", "City"),
    ("country", "Country"),
    ("venue", "Venue / address"),
    ("organizer_name", "Organiser"),
    ("organization_name", "Organisation"),
    ("price", "Ticket price"),
    ("target_audience", "Target audience"),
)


class DescriptionUnavailable(Exception):
    """AI is needed (the organiser gave instructions) but isn't available."""


def _known_fields(fields: dict[str, Any]) -> list[tuple[str, str]]:
    out = []
    for key, label in _FIELD_LABELS:
        value = fields.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out.append((label, text))
    return out


def _fmt_day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    return f"{d.day} {d.strftime('%B %Y')}"


def template_description(fields: dict[str, Any]) -> str:
    """A plain, factual description built only from the form fields."""
    title = (fields.get("title") or "").strip() or "This event"
    kind = (fields.get("event_type") or "").strip().lower() or "event"
    sector = (fields.get("sector") or "").strip()
    fmt = (fields.get("format") or "").strip().lower()
    city = (fields.get("city") or "").strip()
    country = (fields.get("country") or "").strip()
    start = _fmt_day(fields.get("start_date"))
    end = _fmt_day(fields.get("end_date"))
    org = (fields.get("organization_name") or fields.get("organizer_name") or "").strip()
    audience = (fields.get("target_audience") or "").strip()

    article = "an" if kind[:1] in "aeiou" else "a"
    first = f"{title} is {article} {kind}"
    if sector:
        first += f" for the {sector} sector"
    if fmt == "online":
        first += ", held online"
    elif fmt == "hybrid":
        first += ", held both in person and online"
    place = ", ".join(p for p in (city, country) if p)
    if place and fmt != "online":
        first += f" in {place}"
    if start and end and end != start:
        first += f" from {start} to {end}"
    elif start:
        first += f" on {start}"
    sentences = [first + "."]
    if org:
        sentences.append(f"It is organised by {org}.")
    if audience:
        sentences.append(f"It is aimed at {audience}.")
    sentences.append("Register on 100 TIMES to reserve your place.")
    return " ".join(sentences)


def _user_message(fields: dict[str, Any], current: str | None, history: list[dict[str, str]], prompt: str | None) -> str:
    known = _known_fields(fields)
    parts = ["Event details (the only facts you may use besides the organiser's messages):"]
    parts += [f"- {label}: {value}" for label, value in known] or ["- (none filled in yet)"]
    if current and current.strip():
        parts += ["", "Current description in the form:", current.strip()]
    if history:
        parts += ["", "Earlier in this conversation:"]
        for turn in history:
            who = "Organiser" if turn.get("role") == "user" else "You (draft)"
            parts.append(f"{who}: {turn.get('text', '').strip()}")
    parts += ["", "Organiser's request:", (prompt or "").strip() or "Write a description for this event from the details above."]
    return "\n".join(parts)


def write_description(
    fields: dict[str, Any],
    *,
    prompt: str | None = None,
    current: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    client = ai_client_module.get_ai_client()
    if not client.is_configured:
        if prompt and prompt.strip():
            raise DescriptionUnavailable(
                "AI writing isn't set up on this server, so it can't follow instructions. "
                "Use 'Write it for me' for a basic description from your details, or write your own."
            )
        return {"description": template_description(fields), "source": "template"}
    try:
        text = client.generate_text(SYSTEM, _user_message(fields, current, history or [], prompt), max_tokens=700)
    except AIClientError as exc:
        if prompt and prompt.strip():
            raise DescriptionUnavailable(f"The AI writer couldn't answer right now: {exc}") from exc
        return {"description": template_description(fields), "source": "template"}
    text = (text or "").strip()
    if len(text) < 25:
        raise DescriptionUnavailable("The AI writer returned an empty draft. Please try again.")
    return {"description": text[:4000], "source": "ai", "provider": client.provider, "model": client.model}
