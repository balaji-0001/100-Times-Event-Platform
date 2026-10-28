from __future__ import annotations

import logging

from backend.core.config import get_settings
from backend.services.discovery_agent.search_providers.base import (
    BaseSearchProvider,
    SearchProviderResult,
)

logger = logging.getLogger("discovery_agent.search_providers.google_gemini")

_SYSTEM = (
    "You are a web search tool for an event-discovery system. Use Google Search to find web pages "
    "for the query. Prefer official event websites, organiser pages and event-listing pages for "
    "upcoming events. Answer with one short line per page you found; do not invent pages."
)


class GeminiGoogleSearchProvider(BaseSearchProvider):
    """Google Search through Gemini's "Grounding with Google Search" tool.

    Google's Custom Search JSON API no longer accepts new customers, so this is
    the supported way to get Google results with a Gemini API key. Results are
    ONLY the pages Google Search returned as grounding sources (redirect links
    resolved to the real URL by the shared Gemini client); the model's own text
    is never used as a result, so no URL can be made up. Billed per grounded
    request on the Gemini API key's plan — used as a paid top-up after Exa."""

    provider_id = "google_gemini"
    provider_name = "Google Search (Gemini grounding)"
    display_name = "Google"
    cost_rank = 30
    setup_env = ("GEMINI_API_KEY",)
    docs_url = "https://ai.google.dev/gemini-api/docs/google-search"

    def is_configured(self) -> bool:
        return bool(get_settings().gemini_api_key)

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        from backend.services.social_agent.ai_client import GeminiAIClient

        prompt = f"Search query: {query}" + (f"\nCountry: {country}" if country else "")
        answer = GeminiAIClient().generate_with_web_search(_SYSTEM, prompt, max_tokens=512)
        results: list[SearchProviderResult] = []
        for citation in answer.get("citations") or []:
            url = citation.get("url") or ""
            if url.startswith(("http://", "https://")):
                results.append(SearchProviderResult(url=url, title=citation.get("title") or "", source=self.provider_name))
        return results[:max_results]
