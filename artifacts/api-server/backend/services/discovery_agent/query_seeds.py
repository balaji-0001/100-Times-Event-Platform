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
    "convention",
)

# Comprehensive industry synonyms covering major trade sectors
SECTOR_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Construction": (
        "Construction",
        "Building",
        "Civil Engineering",
        "Architecture",
        "Infrastructure",
        "HVAC",
        "Concrete",
        "Smart Buildings",
        "Commercial Real Estate",
    ),
    "Energy and Power Generation": (
        "Energy",
        "Power Generation",
        "Renewable Energy",
        "Solar Power",
        "Wind Energy",
        "Clean Energy",
        "Electricity",
        "Grid Infrastructure",
        "Hydrogen Energy",
    ),
    "Finance": (
        "Finance",
        "Banking",
        "Fintech",
        "Investment",
        "Wealth Management",
        "Private Equity",
        "Venture Capital",
        "Insurance",
        "Accounting",
    ),
    "Healthcare": (
        "Healthcare",
        "Medical",
        "Hospital",
        "Digital Health",
        "Medical Devices",
        "Biomedical",
        "Public Health",
        "Clinical",
        "Nursing",
    ),
    "Manufacturing": (
        "Manufacturing",
        "Smart Factory",
        "Industrial Automation",
        "Industry 4.0",
        "Precision Engineering",
        "Robotics",
        "Machinery",
        "Advanced Manufacturing",
    ),
    "Mining": (
        "Mining",
        "Mineral Exploration",
        "Metals & Mining",
        "Quarrying",
        "Extraction",
        "Geology",
        "Heavy Mining Equipment",
    ),
    "Oil and Gas": (
        "Oil and Gas",
        "Petroleum",
        "Hydrocarbons",
        "Offshore Energy",
        "Upstream Downstream",
        "Natural Gas",
        "Drilling",
        "Refining",
    ),
    "Packaging": (
        "Packaging",
        "Flexible Packaging",
        "Sustainable Packaging",
        "Corrugated",
        "Labeling",
        "Printing & Packaging",
        "Food Packaging",
    ),
    "Pharmaceuticals": (
        "Pharmaceuticals",
        "Pharma",
        "Biopharma",
        "Drug Discovery",
        "Clinical Trials",
        "Vaccines",
        "Generics",
        "Active Pharmaceutical Ingredients",
    ),
    "Telecommunications": (
        "Telecommunications",
        "Telecom",
        "5G 6G",
        "Broadband",
        "Wireless Networks",
        "Satellite Communications",
        "Fiber Optics",
        "Network Infrastructure",
    ),
    "Textiles": (
        "Textiles",
        "Apparel",
        "Garments",
        "Technical Textiles",
        "Yarn & Fabric",
        "Fashion Sourcing",
        "Weaving",
        "Nonwoven",
    ),
    "Transport and Logistics": (
        "Transport and Logistics",
        "Supply Chain",
        "Freight",
        "Warehousing",
        "Maritime Shipping",
        "Cargo",
        "Fleet Management",
        "Cold Chain",
    ),
    "Technology": (
        "Technology",
        "Artificial Intelligence",
        "Cloud Computing",
        "Cybersecurity",
        "Software Engineering",
        "Data Science",
        "Enterprise IT",
        "DevOps",
    ),
    "Other": ("Business", "Trade", "Industry Expo", "Commercial Conference"),
}

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
    if df and dt:
        try:
            d1 = datetime.strptime(df.strip()[:10], "%Y-%m-%d")
            d2 = datetime.strptime(dt.strip()[:10], "%Y-%m-%d")
            if d1.year == d2.year and d1.month == d2.month:
                return d1.strftime("%B %Y")
            return f"between {d1.strftime('%B %Y')} and {d2.strftime('%B %Y')}"
        except Exception:
            pass
    elif df:
        try:
            d = datetime.strptime(df.strip()[:10], "%Y-%m-%d")
            return f"from {d.strftime('%B %Y')}"
        except Exception:
            pass
    elif dt:
        try:
            d = datetime.strptime(dt.strip()[:10], "%Y-%m-%d")
            return f"until {d.strftime('%B %Y')}"
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
        "web", "google_search", "bing_search", "linkedin", "facebook", "instagram", "twitter", "telegram", "reddit", "event_platforms"
    ])

    time_hint = _date_hint_for_config(config)

    buckets: list[list[str]] = []

    # 1. General Web & Search Engine queries (City, State, Country, Industry sources, Sector Publications)
    has_web_or_engine = bool(
        enabled_sources.intersection({
            "web",
            "google_search",
            "bing_search",
            "search_research_tool",
            "all",
            "all_sources",
            "all_operational",
        })
    )
    if has_web_or_engine:
        city_queries: list[str] = []
        for city in cities:
            for category in categories:
                synonyms = SECTOR_SYNONYMS.get(category, (category,))
                cat_term = synonyms[len(city_queries) % len(synonyms)]
                qualifier = _EVENT_TYPE_QUALIFIERS[len(city_queries) % len(_EVENT_TYPE_QUALIFIERS)]
                c_label = f" {single_country}" if not is_worldwide and single_country.lower() != city.lower() else ""
                city_queries.append(f"{cat_term} {qualifier} in {city}{c_label} {time_hint}")
        if city_queries:
            buckets.append(city_queries)

        state_queries: list[str] = []
        for state in states:
            for category in categories:
                synonyms = SECTOR_SYNONYMS.get(category, (category,))
                cat_term = synonyms[len(state_queries) % len(synonyms)]
                qualifier = _EVENT_TYPE_QUALIFIERS[len(state_queries) % len(_EVENT_TYPE_QUALIFIERS)]
                s_label = f" {single_country}" if not is_worldwide and single_country.lower() not in state.lower() else ""
                state_queries.append(f"upcoming {cat_term} {qualifier} {state}{s_label} {time_hint}")
        if state_queries:
            buckets.append(state_queries)

        country_queries: list[str] = []
        target_countries = countries if is_worldwide and countries else ([single_country] if single_country and not is_worldwide else ["Worldwide"])
        for c in target_countries[:8]:
            for category in categories:
                synonyms = SECTOR_SYNONYMS.get(category, (category,))
                for cat_term in synonyms[:2]:
                    qualifier = _EVENT_TYPE_QUALIFIERS[len(country_queries) % len(_EVENT_TYPE_QUALIFIERS)]
                    loc_str = f" in {c}" if c != "Worldwide" else ""
                    country_queries.append(f"upcoming {cat_term} {qualifier}{loc_str} {time_hint} official website")
        if country_queries:
            buckets.append(country_queries)

        source_queries: list[str] = []
        for category in categories:
            synonyms = SECTOR_SYNONYMS.get(category, (category,))
            cat_term = synonyms[0]
            for qualifier in _SOURCE_QUALIFIERS:
                region_str = f" {single_country}" if not is_worldwide else " worldwide"
                source_queries.append(f"{qualifier} {cat_term}{region_str} {time_hint}")
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
    if "linkedin" in enabled_sources or "linkedin_search" in enabled_sources:
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
                ig_queries.append(f'site:instagram.com {category} (conference OR summit OR expo OR "register now" OR "event in"){loc_str} {time_hint}')
        if ig_queries:
            buckets.append(ig_queries)

    # 6. Telegram queries
    if "telegram" in enabled_sources:
        tg_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                tg_queries.append(f'site:t.me {category} (conference OR summit OR expo OR meetup OR "event"){loc_str} {time_hint}')
        if tg_queries:
            buckets.append(tg_queries)

    # 7. Reddit queries
    if "reddit" in enabled_sources:
        reddit_queries: list[str] = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else (" in India" if not is_worldwide else "")
            for category in categories:
                reddit_queries.append(f'site:reddit.com {category} (conference OR summit OR expo OR meetup OR "annual event"){loc_str} {time_hint}')
        if reddit_queries:
            buckets.append(reddit_queries)

    # 8. Event Platforms / Aggregators (Eventbrite, Meetup, Luma)
    if "event_platforms" in enabled_sources or "consumer_aggregators" in enabled_sources:
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


def build_expanded_queries(config: DiscoveryConfig) -> list[str]:
    """Supplemental multi-source search queries across major city hubs and event portals,
    ensuring continuous discovery until the target valid event count is fulfilled."""
    categories = config.categories or ["conference", "summit", "expo", "exhibition"]
    time_hint = _date_hint_for_config(config)
    supplemental_cities = [
        "Mumbai", "Bengaluru", "Delhi", "Hyderabad", "Pune", "Chennai",
        "Kolkata", "Ahmedabad", "Gurgaon", "Noida", "Jaipur", "Goa",
        "Chandigarh", "Kochi", "Indore", "Lucknow", "Bhopal", "Coimbatore"
    ]
    selected_cities = config.cities or []
    additional_cities = [c for c in supplemental_cities if c not in selected_cities] or supplemental_cities[:8]

    queries: list[str] = []
    for city in additional_cities:
        for cat in categories[:6]:
            queries.append(f"site:allevents.in/{city.lower()} {cat}")
            queries.append(f"site:eventbrite.com {cat} {city} {time_hint}")
            queries.append(f"site:10times.com/{city.lower()} {cat}")
            queries.append(f"site:meetup.com {cat} {city}")
            queries.append(f"upcoming {cat} in {city} {time_hint} registration")
            queries.append(f"{cat} conference expo {city} {time_hint}")

    return queries
