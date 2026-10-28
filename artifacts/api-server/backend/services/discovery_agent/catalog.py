"""The discovery provider registry as the UI and the run planner see it.

One place that answers, for every search provider and source adapter:
which channel it belongs to (General Web Search / Global Directories &
Adapters / Consumer Aggregators / Event Platform APIs), whether it is
implemented and configured, whether an admin disabled it, its real health
from past runs and probes, and — for a run — which sources the admin's
selection actually schedules and why each other selected source is skipped.

Built on the existing pieces (no second registry): `source_registry`'s
catalogue + `event_discovery_sources` table, `adapters.adapter_manager`, and
the search engine's providers. No credential value ever leaves the backend:
only whether one is set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import EventDiscoverySource
from backend.services.discovery_agent import geo_scope, listing_sources
from backend.services.discovery_agent.source_registry import ALL_CANDIDATE_SOURCES

# Channel tokens stored in a run's `sources` (the three strategy toggles).
WEB_TOKEN, DIRECTORIES_TOKEN, AGGREGATORS_TOKEN = "web", "global_adapters", "consumer_aggregators"
_ALL_TOKENS = {"all", "all_sources", "all_operational"}
# Older saved settings meant "web search on" with these ids.
_LEGACY_WEB_TOKENS = {"google_search", "bing_search", "search_research_tool"}

# Public listing sites read through their own city pages.
AGGREGATOR_IDS = ("eventbrite", "meetup", "allevents", "skillboxes")
_AGGREGATOR_HOSTS = (("allevents.in", "allevents"), ("eventbrite.", "eventbrite"), ("meetup.com", "meetup"), ("skillboxes.com", "skillboxes"))

CHANNELS = (
    {"id": "web", "token": WEB_TOKEN, "name": "General Web Search",
     "description": "Search providers find official event sites, organiser pages and listings worldwide; every result page is then read and verified."},
    {"id": "directories", "token": DIRECTORIES_TOKEN, "name": "Global Directories & Adapters",
     "description": "Trade-show directories, CFP feeds, exhibition organisers, venue calendars, associations and trade portals, read from their own events pages."},
    {"id": "aggregators", "token": AGGREGATORS_TOKEN, "name": "Consumer Aggregators",
     "description": "Eventbrite, Meetup, AllEvents and Skillboxes city listing pages. They often hide organiser emails."},
    {"id": "apis", "token": None, "name": "Event Platform APIs",
     "description": "Official platform APIs. Only Ticketmaster has a working client; the others are listed with what they would need."},
)

_REGION_WILDCARDS = {"worldwide", "global", "europe", "asia", "middle east", "africa", "americas", "north america",
                     "south america", "latin america", "oceania", "apac", "emea", "gcc"}


def channel_of(src: dict[str, Any]) -> str:
    if src["id"] in AGGREGATOR_IDS:
        return "aggregators"
    category = src.get("source_category")
    if category == "Search & Research Tool":
        return "web"
    if category == "Event Platform & API":
        return "apis"
    return "directories"


def aggregator_for_url(url: str) -> str | None:
    host = (urlparse(url).netloc or "").lower()
    return next((sid for marker, sid in _AGGREGATOR_HOSTS if marker in host), None)


def covers_countries(src: dict[str, Any], countries: list[str]) -> bool:
    """False only for a source tied to specific countries none of which were
    selected (e.g. a New York venue calendar on an India-only run)."""
    if not countries:
        return True
    listed = [str(c).strip() for c in (src.get("supported_countries") or []) if str(c).strip()]
    # A venue calendar lists where the venue IS ("United Arab Emirates", "Middle
    # East"): its region tag isn't coverage, so only its country counts.
    is_venue = src.get("source_category") == "Venue Calendar"
    if not listed or (not is_venue and any(c.lower() in _REGION_WILDCARDS for c in listed)):
        return True
    wanted = {c.lower() for c in countries}
    return any((geo_scope.canonical_country(c) or c).lower() in wanted for c in listed)


def _by_id() -> dict[str, dict[str, Any]]:
    return {src["id"]: src for src in ALL_CANDIDATE_SOURCES}


def _adapter(source_id: str):
    from backend.services.discovery_agent.adapters import adapter_manager

    return adapter_manager.get_adapter(source_id)


def is_implemented(source_id: str) -> bool:
    adapter = _adapter(source_id)
    return bool(adapter is not None and getattr(adapter, "implemented", True))


def default_selected(src: dict[str, Any]) -> bool:
    """The curated default selection (what "Reset to defaults" ticks)."""
    return src.get("integration_status") == "Operational" and src.get("is_enabled", True) and is_implemented(src["id"])


def admin_disabled_ids(db: Session | None) -> set[str]:
    """Sources an admin switched off on the Source Registry page."""
    if db is None:
        return set()
    try:
        return set(db.scalars(select(EventDiscoverySource.id).where(EventDiscoverySource.is_enabled.is_(False))).all())
    except Exception:
        return set()


def channel_states(requested: set[str]) -> dict[str, bool]:
    everything = not requested or bool(requested & _ALL_TOKENS)
    return {
        "web": everything or bool(requested & ({WEB_TOKEN} | _LEGACY_WEB_TOKENS)),
        "directories": everything or DIRECTORIES_TOKEN in requested,
        "aggregators": everything or bool(requested & {AGGREGATORS_TOKEN, "event_platforms", "listing_sources"}),
    }


@dataclass
class SourcePlan:
    """Which selected sources a run schedules, and why the rest are skipped."""

    channels: dict[str, bool]
    adapters: list[str] = field(default_factory=list)
    aggregators: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (source id, reason)


def plan_sources(requested: set[str], countries: list[str] | None, disabled: set[str] | None = None) -> SourcePlan:
    """Inside an enabled channel, the individually ticked sources run; a
    channel token with nothing ticked inside it (older saved settings) means
    the channel's default sources. A source of a disabled channel never runs,
    even if ticked."""
    countries = countries or []
    disabled = disabled or set()
    sources = _by_id()
    plan = SourcePlan(channels=channel_states(requested))

    def eligible(sid: str, check_geo: bool) -> str | None:
        src = sources[sid]
        if not is_implemented(sid):
            adapter = _adapter(sid)
            return getattr(adapter, "not_implemented_reason", lambda: "no discovery client implemented")()
        if sid in disabled:
            return "disabled on the Source Registry page"
        if check_geo and not covers_countries(src, countries):
            return "covers none of the selected countries"
        return None

    if plan.channels["directories"]:
        directory_ids = [sid for sid, src in sources.items() if channel_of(src) == "directories"]
        ticked = [sid for sid in directory_ids if sid in requested]
        chosen = ticked or [sid for sid in directory_ids if default_selected(sources[sid])]
        for sid in chosen:
            reason = eligible(sid, check_geo=True)
            if reason:
                plan.skipped.append((sid, reason))
            else:
                plan.adapters.append(sid)

    if plan.channels["aggregators"]:
        ticked = [sid for sid in AGGREGATOR_IDS if sid in requested]
        for sid in ticked or list(AGGREGATOR_IDS):
            reason = eligible(sid, check_geo=False)
            if reason:
                plan.skipped.append((sid, reason))
            else:
                plan.aggregators.append(sid)

    priority = ["dev_events", "wikicfp", "dwtc_events", "excel_london", "javits_center", "mccormick_place", "messe_frankfurt_venue", "india_expo_centre", "gtr_events", "ieee_events", "acm", "rx_global", "informa_markets", "terrapinn", "messe_frankfurt_org", "dmg_events", "dwtc_org", "us_ita", "indian_trade_portal"]
    plan.adapters = [s for s in priority if s in plan.adapters] + sorted(s for s in plan.adapters if s not in priority)
    return plan


# ---------------------------------------------------------------------------
# Health (from real executions and probes recorded in event_discovery_sources)
# ---------------------------------------------------------------------------


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def health_of(row: EventDiscoverySource | None) -> dict[str, Any]:
    """Seeded `health_status` values are curated labels, not checks, so a
    source counts as checked only once a run or probe recorded an outcome."""
    if row is None or (row.last_successful_execution is None and not row.last_error):
        return {"status": "untested", "detail": None, "checked_at": None, "last_success_at": None}
    failed_last = bool(row.last_error) and (row.last_successful_execution is None or (row.updated_at and row.updated_at > row.last_successful_execution))
    if failed_last:
        return {"status": "failed", "detail": row.last_error, "checked_at": _iso(row.updated_at), "last_success_at": _iso(row.last_successful_execution)}
    status = "no_events" if row.health_status == "no_events" else "ok"
    return {"status": status, "detail": None, "checked_at": _iso(row.last_successful_execution), "last_success_at": _iso(row.last_successful_execution)}


def record_outcome(db: Session, source_id: str, *, ok: bool, events: int, error: str | None) -> None:
    """Persist one real execution/probe outcome of a source (registry table)."""
    from backend.services.discovery_agent.source_registry import record_source_execution

    record_source_execution(
        db,
        source_id=source_id,
        events_discovered=events,
        events_extracted=events,
        unique_events=0,
        success=ok,
        error=None if ok else (error or "failed"),
        health_status=("healthy" if events else "no_events") if ok else "failing",
    )


# ---------------------------------------------------------------------------
# Catalog for the UI
# ---------------------------------------------------------------------------


def build_catalog(db: Session | None, ticketmaster_key_set: bool) -> dict[str, Any]:
    from backend.core.config import get_settings
    from backend.services.discovery_agent.search_providers import search_engine
    from backend.services.discovery_agent.source_registry import seed_or_sync_source_registry

    rows: dict[str, EventDiscoverySource] = {}
    if db is not None:
        seed_or_sync_source_registry(db)
        rows = {row.id: row for row in db.scalars(select(EventDiscoverySource)).all()}

    providers = []
    for pid, status in search_engine.get_providers_status().items():
        providers.append({
            "id": pid,
            "name": status["display_name"],
            "full_name": status["name"],
            "tier": status["tier"],
            "cost_rank": status["cost_rank"],
            "configured": status["configured"],
            "unavailable_reason": status["unavailable_reason"],
            "setup_env": status["setup_env"],
            "docs_url": status["docs_url"],
            "cooling_down_seconds": status["cooling_down_seconds"],
            "cooldown_reason": status["cooldown_reason"],
            "last_call": {"status": status["last_status"], "error": status["last_error"], "results": status["last_result_count"], "at": status["last_at"]},
        })
    providers.sort(key=lambda p: (p["tier"] == "last_resort", p["tier"] != "free", p["cost_rank"]))

    sources = []
    for src in ALL_CANDIDATE_SOURCES:
        channel = channel_of(src)
        if channel == "web":
            continue  # search engines are the providers above, not adapters
        sid = src["id"]
        adapter = _adapter(sid)
        implemented = is_implemented(sid)
        configured = implemented and (sid != "ticketmaster_api" or ticketmaster_key_set)
        row = rows.get(sid)
        if not implemented:
            health = {"status": "not_implemented", "detail": adapter.not_implemented_reason() if adapter else None, "checked_at": None, "last_success_at": None}
        elif not configured:
            health = {"status": "not_configured", "detail": "Ticketmaster API key not set (enter it below or set TICKETMASTER_API_KEY)", "checked_at": None, "last_success_at": None}
        else:
            health = health_of(row)
        sources.append({
            "id": sid,
            "name": src["name"],
            "url": src["website_url"],
            "events_page": adapter.listing_template() if adapter is not None and hasattr(adapter, "listing_template") else None,
            "category": src["source_category"],
            "channel": channel,
            "access_method": src["access_method"],
            "countries": src.get("supported_countries") or [],
            "implemented": implemented,
            "configured": configured,
            "enabled_by_admin": bool(row.is_enabled) if row is not None else bool(src.get("is_enabled", True)),
            "default_selected": default_selected(src),
            "health": health,
        })

    settings = get_settings()
    default_sources = [WEB_TOKEN, DIRECTORIES_TOKEN, AGGREGATORS_TOKEN, "linkedin_search"] + [
        s["id"] for s in sources if s["default_selected"] and s["channel"] in ("directories", "aggregators")
    ]
    return {
        "channels": [dict(c) for c in CHANNELS],
        "providers": providers,
        "web_options": [{"id": "linkedin_search", "name": "LinkedIn event pages", "description": "Adds site:linkedin.com searches for event pages and posts (run through the providers above)."}],
        "sources": sources,
        "default_sources": default_sources,
        "default_listing_urls": list(listing_sources.DEFAULT_LISTING_URLS),
        "strategy": (settings.search_strategy or "free_first").lower(),
        "paid_search_budget_per_run": settings.paid_search_calls_per_run,
    }


# ---------------------------------------------------------------- recommendations

RECOMMENDED_TARGET_VALID_EVENTS = 25


def recommended_config(catalog: dict[str, Any]) -> dict[str, Any]:
    """Run settings the system can choose itself, from what is really
    available right now: usable search providers (configured, not paused),
    and the default directory/aggregator sources that are set up and not
    failing their last check. Returns plain-language notices about anything
    that changes the run, and one `blocker` only when nothing can run at all.
    Never reports an unavailable provider as usable."""
    from datetime import date, timedelta

    from backend.core.config import get_settings

    settings = get_settings()
    providers = catalog["providers"]
    usable = [p for p in providers if p["configured"] and not p["cooling_down_seconds"]]
    paused = [p for p in providers if p["configured"] and p["cooling_down_seconds"]]
    primary = [p for p in usable if p["tier"] != "last_resort"]

    def usable_source(src: dict) -> bool:
        return src["configured"] and src["enabled_by_admin"] and src["health"]["status"] != "failed"

    defaults = [s for s in catalog["sources"] if s["default_selected"] and s["channel"] in ("directories", "aggregators")]
    picked = [s for s in defaults if usable_source(s)]
    failing = [s for s in defaults if s["configured"] and s["health"]["status"] == "failed"]
    channel_sources = {ch: [s for s in picked if s["channel"] == ch] for ch in ("directories", "aggregators")}

    sources: list[str] = []
    if usable:
        sources += [WEB_TOKEN]
    for channel, token in (("directories", DIRECTORIES_TOKEN), ("aggregators", AGGREGATORS_TOKEN)):
        if channel_sources[channel]:
            sources.append(token)
    sources += [s["id"] for s in picked]

    notices: list[dict[str, str]] = []
    if not usable:
        notices.append({
            "level": "warning",
            "message": "Web search is unavailable: no search provider is configured or reachable. This run uses directories and aggregators only.",
            "action": "Set SEARXNG_URL (free, self-hosted) or a search API key such as EXA_API_KEY, then restart the backend.",
        })
    elif not primary:
        notices.append({"level": "info", "message": f"Only the last-resort search ({', '.join(p['name'] for p in usable)}) is available, so web results may be thin.", "action": ""})
    for p in paused:
        minutes = max(1, round(p["cooling_down_seconds"] / 60))
        notices.append({"level": "info", "message": f"{p['name']} is paused for about {minutes} min ({p['cooldown_reason'] or 'recent errors'}); the other providers are used instead.", "action": ""})
    if failing:
        names = ", ".join(s["name"] for s in failing[:5]) + (f" and {len(failing) - 5} more" if len(failing) > 5 else "")
        notices.append({"level": "info", "message": f"Skipped because they failed their last check: {names}.", "action": "Re-check them under Discovery configuration → Sources."})

    blocker = None
    if not sources:
        blocker = "No discovery source is available: no search provider is configured and no directory or aggregator source is working. Set SEARXNG_URL or a search API key, or re-check the sources under Discovery configuration → Sources."

    today = date.today()
    window_days = settings.discovery_default_window_days
    return {
        "sources": sources,
        "searchProviders": None,  # None = every usable provider, cheapest/free first (the engine's own order)
        "usableProviders": [{"id": p["id"], "name": p["name"], "tier": p["tier"]} for p in usable],
        "channels": {
            "web": {"available": bool(usable), "providers": [p["name"] for p in usable]},
            "directories": {"available": bool(channel_sources["directories"]), "sources": len(channel_sources["directories"])},
            "aggregators": {"available": bool(channel_sources["aggregators"]), "sources": len(channel_sources["aggregators"])},
        },
        "targetValidEvents": RECOMMENDED_TARGET_VALID_EVENTS,
        "dateFrom": today.isoformat(),
        "dateTo": (today + timedelta(days=window_days)).isoformat(),
        "upcomingWindowDays": window_days,
        "requireOrganizerEmail": True,
        "rejectPastEvents": True,
        "keepRejectedEvents": True,
        "maxRunMinutes": 15,
        "paidSearchBudget": catalog.get("paid_search_budget_per_run"),
        # Also read by a recommended run (server defaults), listed so the card can say so.
        "listingUrls": list(catalog.get("default_listing_urls") or []),
        "ticketmaster": {"available": any(s["id"] == "ticketmaster_api" and s["configured"] for s in catalog["sources"])},
        "notices": notices,
        "blocker": blocker,
    }
