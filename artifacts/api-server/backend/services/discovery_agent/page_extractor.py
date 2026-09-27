"""Turns one candidate page into structured event facts.

Two-tier, cheapest/most-trustworthy first:
  1. schema.org JSON-LD `Event` data, if the page publishes it — structured,
     machine-authored, no AI guessing involved.
  2. Otherwise, an LLM extraction pass over the page's visible text (forced
     tool-use, same discipline as `pipeline/event_extraction.py`'s
     `ExtractedEventAI`) — any field the page doesn't actually state comes
     back `None`, never invented.

A page that is unreachable, or contains no genuine event, returns `None`
rather than a half-filled guess.
"""

from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError

from backend.services.discovery_agent.format_normalize import normalize_event_format
from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate
from backend.services.social_agent.ai_client import AIClient, AIClientError, not_configured_message
from backend.services.social_agent.web_fetch import fetch, find_json_ld_nodes

_MAX_PAGE_TEXT_CHARS = 6000


class _ExtractedEventPage(BaseModel):
    is_genuine_event: bool
    event_name: str = ""
    event_description: str = ""
    category: str = ""
    subcategory: str = ""
    date: str = ""
    start_time: str = ""
    end_time: str = ""
    venue: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    ticket_url: str = ""
    event_format: str = ""  # online | offline | hybrid
    organizer_name_hint: str = ""
    confidence_score: int = Field(ge=0, le=100)
    reason: str


_SYSTEM_PROMPT = (
    "You read the visible text of ONE web page and decide whether it genuinely announces or "
    "lists a specific, real event happening in India (any category — technology, healthcare, "
    "finance, startups, academia, career, arts, or anything else). Only use information "
    "actually present on the page — never invent a date, venue, city, or organizer that isn't "
    "there; leave a field blank instead of guessing. Set `is_genuine_event` to false (and leave "
    "other fields blank) for listing/aggregator index pages with no single specific event, past-"
    "event recaps, or pages too vague to identify a real event. `confidence_score` (0-100) "
    "reflects how confident you are this is a real, specific, identifiable event. Call the "
    "`extract_event_page` tool exactly once."
)

_TOOL_NAME = "extract_event_page"
_TOOL_DESCRIPTION = "Structured event details extracted from one web page, for any topic."


def _from_json_ld(source: CandidateSource, soup: BeautifulSoup) -> ExtractedEventCandidate | None:
    for node in find_json_ld_nodes(soup):
        types = node.get("@type")
        type_names = types if isinstance(types, list) else [types]
        if not any(isinstance(t, str) and "event" in t.lower() for t in type_names):
            continue

        name = node.get("name") if isinstance(node.get("name"), str) else None
        if not name:
            continue

        location = node.get("location")
        venue = city = state = None
        if isinstance(location, dict):
            venue = location.get("name") if isinstance(location.get("name"), str) else None
            address = location.get("address")
            if isinstance(address, dict):
                city = address.get("addressLocality")
                state = address.get("addressRegion")
            elif isinstance(address, str):
                venue = venue or address

        offers = node.get("offers")
        ticket_url = None
        if isinstance(offers, dict):
            ticket_url = offers.get("url")
        elif isinstance(offers, list) and offers and isinstance(offers[0], dict):
            ticket_url = offers[0].get("url")

        attendance_mode = node.get("eventAttendanceMode")
        event_format = normalize_event_format(attendance_mode) if isinstance(attendance_mode, str) else None

        return ExtractedEventCandidate(
            name=name,
            event_description=node.get("description") if isinstance(node.get("description"), str) else None,
            date=node.get("startDate") if isinstance(node.get("startDate"), str) else None,
            venue=venue,
            city=city,
            state=state,
            country="India",
            url=source.url,
            ticket_url=ticket_url,
            event_format=event_format,
            organizer_name_hint=None,
            extraction_confidence=90,  # structured data — high trust
            primary_source=source,
            sources=[source],
            raw_evidence=node,
        )
    return None


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:_MAX_PAGE_TEXT_CHARS]


def _from_ai(source: CandidateSource, html: str, ai_client: AIClient) -> ExtractedEventCandidate | None:
    """Raises `AIClientError` on a real API/config failure — deliberately
    NOT swallowed here, so a systemic problem (missing key, API outage)
    surfaces to the orchestrator instead of silently looking like "no event
    on this page". A malformed one-off model response (`ValidationError`)
    IS swallowed to `None` — that's a per-page extraction miss, not a
    systemic failure."""
    if not ai_client.is_configured:
        raise AIClientError(not_configured_message())

    soup = BeautifulSoup(html, "html.parser")
    page_text = _visible_text(soup)
    if not page_text:
        return None

    schema: dict[str, Any] = _ExtractedEventPage.model_json_schema()
    user_prompt = f"Page URL: {source.url}\n\nPage text:\n{page_text}"

    raw = ai_client.generate_structured(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        tool_name=_TOOL_NAME,
        tool_description=_TOOL_DESCRIPTION,
        input_schema=schema,
    )
    try:
        parsed = _ExtractedEventPage.model_validate(raw)
    except ValidationError:
        return None

    if not parsed.is_genuine_event or not parsed.event_name:
        return None

    return ExtractedEventCandidate(
        name=parsed.event_name or None,
        event_description=parsed.event_description or None,
        category=parsed.category or None,
        subcategory=parsed.subcategory or None,
        date=parsed.date or None,
        start_time=parsed.start_time or None,
        end_time=parsed.end_time or None,
        venue=parsed.venue or None,
        city=parsed.city or None,
        state=parsed.state or None,
        country=parsed.country or "India",
        url=source.url,
        ticket_url=parsed.ticket_url or None,
        event_format=normalize_event_format(parsed.event_format),
        organizer_name_hint=parsed.organizer_name_hint or None,
        extraction_confidence=parsed.confidence_score,
        primary_source=source,
        sources=[source],
    )


def extract_event_from_page(source: CandidateSource, ai_client: AIClient) -> ExtractedEventCandidate | None:
    """`AIClientError` from the AI fallback path is NOT caught here — see
    `_from_ai`'s docstring. Callers (the orchestrator) decide whether a
    per-page AI failure should just skip that page or abort the run."""
    html = fetch(source.url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    from_structured = _from_json_ld(source, soup)
    if from_structured is not None:
        return from_structured

    return _from_ai(source, html, ai_client)
