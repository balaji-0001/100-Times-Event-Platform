"""Ticketmaster Discovery API v2 Client for 100 TIMES Discovery Agent.

Pulls official, verified live events, conferences, and exhibitions from
Ticketmaster's global developer discovery API and converts them into
100 TIMES `ExtractedEventCandidate` records.
"""

from __future__ import annotations

import logging
from typing import Any
import requests

from backend.services.discovery_agent.types import CandidateSource, ExtractedEventCandidate

logger = logging.getLogger("discovery_agent.ticketmaster")

TICKETMASTER_DISCOVERY_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

# Common country name to ISO 3166-1 alpha-2 mapping for Ticketmaster query filtering
COUNTRY_CODE_MAP = {
    "united states": "US",
    "usa": "US",
    "us": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "india": "IN",
    "united arab emirates": "AE",
    "uae": "AE",
    "dubai": "AE",
    "canada": "CA",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "singapore": "SG",
    "netherlands": "NL",
    "switzerland": "CH",
    "spain": "ES",
    "italy": "IT",
    "japan": "JP",
    "brazil": "BR",
    "saudi arabia": "SA",
}

# Map Ticketmaster classifications to 100 TIMES primary categories
CATEGORY_MAP = {
    "business": "Finance",
    "conference": "Finance",
    "seminar": "Education",
    "trade show": "Manufacturing",
    "exhibition": "Construction",
    "convention": "Technology",
    "technology": "Telecommunications",
    "tech": "Telecommunications",
    "health": "Healthcare",
    "medical": "Healthcare",
    "pharma": "Pharmaceuticals",
    "energy": "Energy and Power Generation",
    "power": "Energy and Power Generation",
    "logistics": "Transport and Logistics",
    "transport": "Transport and Logistics",
    "mining": "Mining",
    "textiles": "Textiles",
    "packaging": "Packaging",
    "oil": "Oil and Gas",
    "gas": "Oil and Gas",
}


def _resolve_category(classifications: list[dict[str, Any]]) -> str:
    """Infers the closest 100 TIMES category from Ticketmaster's classification hierarchy."""
    if not classifications:
        return "Other"

    for cls in classifications:
        for key in ("segment", "genre", "subGenre"):
            name = (cls.get(key) or {}).get("name", "").strip().lower()
            if not name:
                continue
            for pattern, mapped_category in CATEGORY_MAP.items():
                if pattern in name:
                    return mapped_category

    # If it's a concert, comedy, or show, classify under Other or specific tag
    first_genre = (classifications[0].get("genre") or {}).get("name")
    first_segment = (classifications[0].get("segment") or {}).get("name")
    if first_genre:
        return first_genre
    if first_segment:
        return first_segment
    return "Other"


def test_ticketmaster_connection(api_key: str) -> dict[str, Any]:
    """Tests the Ticketmaster API key against the Discovery v2 endpoint."""
    if not api_key or not api_key.strip():
        return {
            "success": False,
            "message": "Ticketmaster API Key is missing. Please provide a valid key.",
            "totalEvents": 0,
        }

    key = api_key.strip()
    try:
        resp = requests.get(
            TICKETMASTER_DISCOVERY_URL,
            params={"apikey": key, "size": 1},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            total = data.get("page", {}).get("totalElements", 0)
            return {
                "success": True,
                "message": f"Successfully authenticated with Ticketmaster! Access to {total:,} live global events verified.",
                "totalEvents": total,
            }
        elif resp.status_code == 401:
            return {
                "success": False,
                "message": "Invalid Ticketmaster API Key (OAuth 401 Unauthorized). Check your consumer key at developer.ticketmaster.com.",
                "totalEvents": 0,
            }
        elif resp.status_code == 429:
            return {
                "success": False,
                "message": "Ticketmaster API rate limit exceeded (HTTP 429). Please wait a moment before trying again.",
                "totalEvents": 0,
            }
        else:
            return {
                "success": False,
                "message": f"Ticketmaster API error (HTTP {resp.status_code}): {resp.text[:200]}",
                "totalEvents": 0,
            }
    except requests.exceptions.RequestException as exc:
        logger.warning("Ticketmaster connection test failed: %s", exc)
        return {
            "success": False,
            "message": f"Network error connecting to Ticketmaster: {str(exc)}",
            "totalEvents": 0,
        }


def parse_ticketmaster_event(event: dict[str, Any]) -> ExtractedEventCandidate | None:
    """Converts a single Ticketmaster Discovery v2 event dict into an ExtractedEventCandidate."""
    name = event.get("name")
    if not name or not name.strip():
        return None

    url = event.get("url") or ""
    dates_info = event.get("dates", {})
    start_info = dates_info.get("start", {})
    event_date = start_info.get("localDate")
    start_time = start_info.get("localTime")

    # Venue & location details
    venues = event.get("_embedded", {}).get("venues", [])
    venue_name = None
    city = None
    state = None
    country = None
    if venues and isinstance(venues[0], dict):
        v = venues[0]
        venue_name = v.get("name")
        city = (v.get("city") or {}).get("name")
        state = (v.get("state") or {}).get("name")
        country = (v.get("country") or {}).get("name")

    # Description & info
    description = event.get("info") or event.get("pleaseNote") or ""
    if not description and venue_name:
        description = f"{name} scheduled at {venue_name}{f', {city}' if city else ''}."

    # Classifications
    classifications = event.get("classifications", [])
    category = _resolve_category(classifications)

    # Organizer / Promoter hint
    promoter_name = (event.get("promoter") or {}).get("name")
    if not promoter_name:
        promoters = event.get("promoters", [])
        if promoters and isinstance(promoters[0], dict):
            promoter_name = promoters[0].get("name")
    if not promoter_name:
        promoter_name = "Ticketmaster Official Event"

    # Images
    images = event.get("images", [])
    best_img = None
    if images:
        # Prefer 16:9 ratio with highest width
        sorted_imgs = sorted(images, key=lambda img: img.get("width", 0), reverse=True)
        best_img = sorted_imgs[0].get("url")

    source_entry = CandidateSource(
        url=url,
        source_type="ticketmaster_api",
        source_website="ticketmaster.com",
    )

    return ExtractedEventCandidate(
        name=name.strip(),
        event_description=description.strip() if description else None,
        category=category,
        date=event_date,
        start_time=start_time,
        venue=venue_name,
        city=city,
        state=state,
        country=country,
        url=url,
        ticket_url=url,
        event_format="offline",
        organizer_name_hint=promoter_name,
        extraction_confidence=92,
        primary_source=source_entry,
        sources=[source_entry],
        raw_evidence={"ticketmaster_id": event.get("id"), "image_url": best_img},
        best_effort=False,
    )


def fetch_ticketmaster_events(
    api_key: str,
    cities: list[str] | None = None,
    countries: list[str] | None = None,
    country: str | None = None,
    categories: list[str] | None = None,
    max_events_per_city: int = 25,
) -> list[ExtractedEventCandidate]:
    """Fetches upcoming events from Ticketmaster for specified cities or countries."""
    if not api_key or not api_key.strip():
        logger.info("Ticketmaster API key not provided — skipping Ticketmaster discovery.")
        return []

    target_cities = cities or ["London", "New York", "Mumbai", "San Francisco", "Dubai", "Singapore"]
    key = api_key.strip()
    candidates: list[ExtractedEventCandidate] = []
    seen_urls: set[str] = set()

    # Determine country code filter if supplied
    country_code = None
    if country and country.strip().lower() in COUNTRY_CODE_MAP:
        country_code = COUNTRY_CODE_MAP[country.strip().lower()]
    elif countries:
        for c in countries:
            if c and c.strip().lower() in COUNTRY_CODE_MAP:
                country_code = COUNTRY_CODE_MAP[c.strip().lower()]
                break

    for city in target_cities[:10]:  # Limit to 10 cities per batch to avoid rate limits
        params: dict[str, Any] = {
            "apikey": key,
            "city": city,
            "size": min(max_events_per_city, 100),
            "sort": "date,asc",
        }
        if country_code:
            params["countryCode"] = country_code

        try:
            resp = requests.get(TICKETMASTER_DISCOVERY_URL, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                events_list = data.get("_embedded", {}).get("events", [])
                logger.info("Ticketmaster returned %d events for city %r.", len(events_list), city)
                for ev in events_list:
                    cand = parse_ticketmaster_event(ev)
                    if cand and cand.url and cand.url not in seen_urls:
                        seen_urls.add(cand.url)
                        candidates.append(cand)
            elif resp.status_code == 401:
                logger.warning("Ticketmaster API Key is invalid or expired.")
                break
            elif resp.status_code == 429:
                logger.warning("Ticketmaster rate limit reached — pausing Ticketmaster queries.")
                break
            else:
                logger.debug("Ticketmaster API returned status %d for city %r: %s", resp.status_code, city, resp.text[:120])
        except Exception:
            logger.exception("Failed to fetch Ticketmaster events for city %r", city)
            continue

    return candidates
