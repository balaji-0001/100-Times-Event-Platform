"""Search query generation — turns a `DiscoveryConfig` into a broad,
reproducible list of web-search queries spanning Indian cities, states,
event categories and the source types the spec calls out (event-listing
sites, conference/exhibition sites, college pages, trade associations,
government pages, ...), rather than relying on a single search.

Deterministic (no randomness) so the same config always produces the same
query list — important for `AgentRun.config_snapshot` reproducibility and
for testing.
"""

from datetime import datetime
from backend.services.discovery_agent.types import DiscoveryConfig

# The event "types" covering professional and industrial sectors.
_EVENT_TYPE_QUALIFIERS = (
    "conference",
    "exhibition",
    "summit",
    "expo",
    "conclave",
    "trade show",
    "congress",
    "symposium",
    "seminar",
    "workshop",
)

# Broad source-type nudges directed toward professional trade and industry bodies.
_SOURCE_QUALIFIERS = (
    "trade association",
    "industry expo",
    "annual conference",
    "corporate summit",
    "industry conclave",
    "trade exhibition",
)

SECTOR_PUBLICATIONS: dict[str, tuple[str, ...]] = {
    "Pharmaceuticals": ("World Pharma Today", "Pharma Advancement"),
    "Healthcare": ("HHM Global",),
    "Energy and Power Generation": ("Power Info Today",),
    "Telecommunications": ("Tele Info Today",),
    "Construction": ("World Construction Today",),
    "Mining": ("Mining Frontier",),
    "Finance": ("World Finance Informs",),
    "Packaging": ("Packaging World Insights",),
    "Transport and Logistics": ("Transport Advancement",),
    "Oil and Gas": ("Oil & Gas Advancement",),
    "Textiles": ("Global Textile Times",),
    "Manufacturing": ("Manufacturing Informs",),
}

_YEAR_HINT = "2026"


def _date_hint_for_config(config: DiscoveryConfig) -> str:
    """Computes a search time hint from date_from, date_to, or default year hint."""
    df = getattr(config, "date_from", None)
    dt = getattr(config, "date_to", None)
    if df:
        try:
            d = datetime.strptime(df.strip()[:10], "%Y-%m-%d")
            return d.strftime("%B %Y")
        except Exception:
            pass
    if dt:
        try:
            d = datetime.strptime(dt.strip()[:10], "%Y-%m-%d")
            return d.strftime("%B %Y")
        except Exception:
            pass
    return _YEAR_HINT


def build_search_queries(config: DiscoveryConfig) -> list[str]:
    """Interleaves city-level, state-level, country-level, social-level, source-level and
    publication-level queries across categories so the queries cover breadth
    worldwide across geography, user-selected sources and target sectors."""
    cities = config.cities or []
    states = config.states or []
    categories = config.categories or ["events"]
    countries = getattr(config, "countries", None) or []
    single_country = getattr(config, "country", None)
    is_worldwide = not single_country or single_country.lower() in ("all", "all countries", "worldwide")

    enabled_sources = set(getattr(config, "sources", None) or [
        "web", "linkedin", "facebook", "instagram", "twitter", "telegram", "reddit", "event_platforms"
    ])

    time_hint = _date_hint_for_config(config)

    buckets: list[list[str]] = []

    # 1. General Web queries (City, State, Country, Industry sources, Sector Publications)
    if "web" in enabled_sources:
        city_queries: list[str] = []
        for city in cities:
            for category in categories:
                qualifier = _EVENT_TYPE_QUALIFIERS[len(city_queries) % len(_EVENT_TYPE_QUALIFIERS)]
                c_label = f" {single_country}" if not is_worldwide and single_country.lower() != city.lower() else ""
                city_queries.append(f"{category} {qualifier} in {city}{c_label} {time_hint}")
        if city_queries:
            buckets.append(city_queries)

        state_queries: list[str] = []
        for state in states:
            for category in categories:
                qualifier = _EVENT_TYPE_QUALIFIERS[len(state_queries) % len(_EVENT_TYPE_QUALIFIERS)]
                s_label = f" {single_country}" if not is_worldwide and single_country.lower() not in state.lower() else ""
                state_queries.append(f"upcoming {category} {qualifier} {state}{s_label} {time_hint}")
        if state_queries:
            buckets.append(state_queries)

        country_queries: list[str] = []
        if is_worldwide and countries:
            for c in countries:
                for category in categories:
                    qualifier = _EVENT_TYPE_QUALIFIERS[len(country_queries) % len(_EVENT_TYPE_QUALIFIERS)]
                    country_queries.append(f"upcoming {category} {qualifier} in {c} {time_hint}")
            if country_queries:
                buckets.append(country_queries)

        source_queries: list[str] = []
        for category in categories:
            for qualifier in _SOURCE_QUALIFIERS:
                region_str = f" {single_country}" if not is_worldwide else " worldwide"
                source_queries.append(f"{qualifier} {category}{region_str} {time_hint}")
        if source_queries:
            buckets.append(source_queries)

        publication_queries: list[str] = []
        for category in categories:
            for pub in SECTOR_PUBLICATIONS.get(category, ()):
                target_str = f" {single_country}" if not is_worldwide else " international"
                publication_queries.append(f'"{pub}" {category}{target_str} {time_hint}')
        if publication_queries:
            buckets.append(publication_queries)

    social_targets = cities[:4] if cities else ([single_country] if not is_worldwide and single_country else [""])

    # 2. LinkedIn queries
    if "linkedin" in enabled_sources:
        linkedin_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                linkedin_queries.append(f"site:linkedin.com/events {category}{loc_str} {time_hint}")
                linkedin_queries.append(f"site:linkedin.com/posts {category} (conference OR expo OR summit){loc_str} {time_hint}")
        if linkedin_queries:
            buckets.append(linkedin_queries)

    # 3. Facebook queries
    if "facebook" in enabled_sources:
        fb_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                fb_queries.append(f"site:facebook.com/events {category}{loc_str} {time_hint}")
        if fb_queries:
            buckets.append(fb_queries)

    # 4. Twitter / X queries
    if "twitter" in enabled_sources:
        tw_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                tw_queries.append(f"site:x.com {category} (conference OR summit OR expo){loc_str} {time_hint}")
                tw_queries.append(f"site:twitter.com {category} (conference OR expo OR summit){loc_str} {time_hint}")
        if tw_queries:
            buckets.append(tw_queries)

    # 5. Instagram queries
    if "instagram" in enabled_sources:
        ig_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                ig_queries.append(f"site:instagram.com {category} (conference OR summit OR expo OR \"register now\" OR \"event in\"){loc_str} {time_hint}")
        if ig_queries:
            buckets.append(ig_queries)

    # 6. Telegram queries
    if "telegram" in enabled_sources:
        tg_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                tg_queries.append(f"site:t.me {category} (conference OR summit OR expo OR meetup OR \"event\"){loc_str} {time_hint}")
        if tg_queries:
            buckets.append(tg_queries)

    # 7. Reddit queries
    if "reddit" in enabled_sources:
        reddit_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                reddit_queries.append(f"site:reddit.com {category} (conference OR summit OR expo OR meetup OR \"annual event\"){loc_str} {time_hint}")
        if reddit_queries:
            buckets.append(reddit_queries)

    # 8. Event Platforms / Aggregators (Eventbrite, Meetup, Luma)
    if "event_platforms" in enabled_sources:
        platform_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                platform_queries.append(f"site:eventbrite.com/e {category}{loc_str} {time_hint}")
                platform_queries.append(f"site:meetup.com {category}{loc_str} {time_hint}")
                platform_queries.append(f"site:lu.ma {category}{loc_str} {time_hint}")
        if platform_queries:
            buckets.append(platform_queries)

    interleaved: list[str] = []
    index = 0
    while len(interleaved) < config.search_depth and any(buckets):
        bucket = buckets[index % len(buckets)]
        if bucket:
            interleaved.append(bucket.pop(0))
        index += 1
        if not any(buckets):
            break

    return interleaved[: config.search_depth]
