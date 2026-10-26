from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.core.config import get_settings
from backend.services.discovery_agent.search_providers.base import (
    BaseSearchProvider,
    SearchProviderResult,
)

logger = logging.getLogger("discovery_agent.search_providers.google")

_PREFERRED_GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash",
]


class GoogleSearchProvider(BaseSearchProvider):
    """Google Search provider supporting Gemini Google Search Grounding and Google Custom Search JSON API."""

    provider_id = "google_search"
    provider_name = "Google Search (Gemini Grounding / CSE)"

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        """Configured if Gemini API key or Google Custom Search credentials are set."""
        has_gemini = bool(
            self.settings.gemini_api_key
            or os.getenv("GEMINI_API_KEY")
        )
        has_cse = bool(
            (self.settings.google_search_api_key or os.getenv("GOOGLE_SEARCH_API_KEY"))
            and (self.settings.google_cse_id or os.getenv("GOOGLE_CSE_ID"))
        )
        return has_gemini or has_cse

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        """Dispatches Google search via Google Custom Search API or Gemini Search Grounding."""
        # 1. Try Google Custom Search JSON API if keys configured (fastest & direct programmatic Google index)
        cse_key = self.settings.google_search_api_key or os.getenv("GOOGLE_SEARCH_API_KEY")
        cse_cx = self.settings.google_cse_id or os.getenv("GOOGLE_CSE_ID")
        if cse_key and cse_cx:
            try:
                results = self._search_google_cse(query, max_results, cse_key, cse_cx, country)
                if results:
                    return results
            except Exception as e:
                logger.warning("Google Custom Search API error: %s — trying Gemini Grounding", e)

        # 2. Try Gemini API with Google Search Grounding
        gemini_key = self.settings.gemini_api_key or os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise RuntimeError(
                "Neither GEMINI_API_KEY nor GOOGLE_SEARCH_API_KEY + GOOGLE_CSE_ID is configured in environment."
            )

        return self._search_gemini_grounding(query, max_results, gemini_key, country, date_range)

    def _search_google_cse(
        self,
        query: str,
        max_results: int,
        api_key: str,
        cx: str,
        country: str | None = None,
    ) -> list[SearchProviderResult]:
        """Queries Google Custom Search JSON API."""
        url = "https://www.googleapis.com/customsearch/v1"
        params: dict[str, Any] = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": min(max(max_results, 1), 10),
        }
        if country and len(country) == 2:
            params["gl"] = country.lower()

        r = httpx.get(url, params=params, timeout=12.0)
        if r.status_code != 200:
            raise RuntimeError(f"Google CSE HTTP {r.status_code}: {r.text[:200]}")

        data = r.json()
        items = data.get("items", [])
        results: list[SearchProviderResult] = []
        for it in items:
            link = it.get("link")
            if link and link.startswith(("http://", "https://")):
                results.append(
                    SearchProviderResult(
                        url=link,
                        title=it.get("title", ""),
                        snippet=it.get("snippet", ""),
                        source="Google Custom Search API",
                    )
                )
        return results[:max_results]

    def _search_gemini_grounding(
        self,
        query: str,
        max_results: int,
        api_key: str,
        country: str | None = None,
        date_range: tuple[str | None, str | None] | None = None,
    ) -> list[SearchProviderResult]:
        """Calls Gemini API with live Google Search tool to extract grounded web URLs."""
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(f"google.genai SDK is required for Google Search Grounding: {exc}")

        client = genai.Client(api_key=api_key)

        loc_str = f" in {country}" if country and country.lower() not in ("all", "worldwide") else ""
        date_str = ""
        if date_range and (date_range[0] or date_range[1]):
            df, dt = date_range
            if df and dt:
                date_str = f" between {df} and {dt}"
            elif df:
                date_str = f" starting from {df}"
            elif dt:
                date_str = f" happening before {dt}"

        prompt = (
            f"Search Google for official event homepages, organizer portals, and conference listings for: "
            f"'{query}'{loc_str}{date_str}. "
            f"List {max_results} real upcoming events with their exact official website URL, dates, city, and organizer."
        )

        last_error: Exception | None = None
        for model_name in _PREFERRED_GEMINI_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        temperature=0.1,
                    ),
                )
                return self._extract_results_from_gemini(response, max_results)
            except Exception as e:
                err_str = str(e)
                last_error = e
                # If model is deprecated or not found, try next modern model
                if "404" in err_str or "NOT_FOUND" in err_str:
                    continue
                # If rate limit or quota exceeded, re-raise with clear reason
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    raise RuntimeError(f"Google Gemini Search Grounding quota exhausted (429): {err_str[:250]}")
                raise

        raise RuntimeError(f"All Gemini Google Search models failed. Last error: {last_error}")

    def _extract_results_from_gemini(self, response: Any, max_results: int) -> list[SearchProviderResult]:
        """Extracts official search URLs from grounding metadata and markdown links."""
        results: list[SearchProviderResult] = []
        seen_urls: set[str] = set()

        # 1. Primary: Extract directly from Google Search grounding metadata
        if hasattr(response, "candidates") and response.candidates:
            cand = response.candidates[0]
            if hasattr(cand, "grounding_metadata") and cand.grounding_metadata:
                gm = cand.grounding_metadata
                chunks = getattr(gm, "grounding_chunks", []) or []
                for chunk in chunks:
                    web = getattr(chunk, "web", None)
                    if web and getattr(web, "uri", None):
                        uri = web.uri.strip()
                        title = getattr(web, "title", "") or ""
                        if uri.startswith(("http://", "https://")) and uri not in seen_urls:
                            seen_urls.add(uri)
                            results.append(
                                SearchProviderResult(
                                    url=uri,
                                    title=title,
                                    snippet=f"Google Search Grounded Result: {title}",
                                    source="Google Search (Gemini Grounding)",
                                )
                            )

        # 2. Secondary: Parse markdown links in response text (e.g. [Title](https://...))
        text = getattr(response, "text", "") or ""
        md_links = re.findall(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", text)
        for title, link in md_links:
            clean_link = link.strip().rstrip(".,;)")
            if clean_link not in seen_urls and "google.com" not in clean_link:
                seen_urls.add(clean_link)
                results.append(
                    SearchProviderResult(
                        url=clean_link,
                        title=title.strip(),
                        snippet=title.strip(),
                        source="Google Search (Gemini Grounding)",
                    )
                )

        # 3. Tertiary: Plain URL regex extraction
        raw_urls = re.findall(r"https?://[a-zA-Z0-9_\-\.\/]+(?:[a-zA-Z0-9_#?=&%-]*)", text)
        for raw in raw_urls:
            clean_raw = raw.strip().rstrip(".,;)>")
            if clean_raw not in seen_urls and "google.com" not in clean_raw:
                parsed = urlparse(clean_raw)
                if parsed.netloc and "." in parsed.netloc:
                    seen_urls.add(clean_raw)
                    results.append(
                        SearchProviderResult(
                            url=clean_raw,
                            title=parsed.netloc,
                            snippet="",
                            source="Google Search (Gemini Grounding)",
                        )
                    )

        return results[:max_results]
