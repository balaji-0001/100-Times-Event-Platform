"""Turns one search query into a list of candidate source URLs, using
the configured AI provider's web-search tool (`AIClient.generate_with_web_search`:
Gemini Google Search grounding, or Claude's server-side web_search) — the only
web-search capability in this codebase. Only URLs the tool
actually returned as citations are used; nothing is invented.
"""

from urllib.parse import urlparse

from backend.services.social_agent.ai_client import AIClient, AIClientError, not_configured_message
from backend.services.discovery_agent.types import CandidateSource

_SYSTEM_PROMPT = (
    "You help find real, currently-listed events happening in India. Search the web for pages "
    "that announce or list a specific event (conferences, exhibitions, seminars, workshops, "
    "networking events, summits, webinars, festivals, trade shows, or other public events) "
    "matching the given query. Prefer official event pages, conference/exhibition sites, "
    "college/university event pages, trade association pages, government/public event notices, "
    "corporate event pages, and organizer websites over generic aggregators when both exist. "
    "Briefly summarize what you found; the actual URLs are read from your search citations."
)

_GOV_DOMAIN_HINTS = (".gov.in", ".nic.in")
_EDU_DOMAIN_HINTS = (".edu.in", ".ac.in", "university", "college", "institute")
_AGGREGATOR_HINTS = ("eventbrite", "meetup.com", "allevents.in", "10times.com", "bookmyshow", "townscript", "eventshigh")
_TRADE_HINTS = ("assocham", "ficci", "cii.in", "federation", "association", "chamber")


def _classify_source_type(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if any(hint in host for hint in _GOV_DOMAIN_HINTS):
        return "government"
    if any(hint in host for hint in _EDU_DOMAIN_HINTS):
        return "college_page"
    if any(hint in host for hint in _TRADE_HINTS):
        return "trade_association"
    if any(hint in host for hint in _AGGREGATOR_HINTS):
        return "aggregator"
    return "event_listing"


def find_candidate_sources(query: str, ai_client: AIClient, max_results: int) -> list[CandidateSource]:
    if not ai_client.is_configured:
        raise AIClientError(not_configured_message())

    result = ai_client.generate_with_web_search(
        system=_SYSTEM_PROMPT,
        user=f"Search query: {query}",
        max_uses=3,
    )

    sources: list[CandidateSource] = []
    seen: set[str] = set()
    for citation in result.get("citations", []):
        url = citation.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        host = urlparse(url).netloc or None
        sources.append(CandidateSource(url=url, source_type=_classify_source_type(url), source_website=host))
        if len(sources) >= max_results:
            break

    return sources
