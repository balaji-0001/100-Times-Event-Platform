"""Search query generation — turns a `DiscoveryConfig` into a reproducible
list of web-search queries built from exactly what the admin selected:
countries, states, cities (each resolved to its own country via
`geo_scope`), sectors, date range and enabled sources. Every selected
sector x country pair is queried first, so a run never leaves part of the
selection unsearched because the budget was spent on the first country.

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

def _year_hint() -> str:
    """Year to put in queries when no date range is set: the current year, or
    next year from October on, when most upcoming editions are already
    listed under next year's dates."""
    today = datetime.now()
    return str(today.year + 1 if today.month >= 10 else today.year)


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
    return _year_hint()


def _place(country: str | None) -> str:
    return f" in {country}" if country else " worldwide"


def _city_label(city: str, country: str | None) -> str:
    return f"{city}, {country}" if country and country.lower() != city.lower() else city


def _plan(config: DiscoveryConfig) -> list[list[str]]:
    """Every query the selection calls for, grouped in priority buckets.

    Bucket 0 is COVERAGE: one query per selected (sector x country), ordered
    diagonally so the first N queries already span N different countries and
    sectors — no selected country or sector is left unsearched because the
    budget ran out on the first one. Then cities (round-robin across their
    countries, sectors rotating), states, source/publication angles, the
    social/platform sources the admin enabled, and finally alternate sector
    terms."""
    from backend.services.discovery_agent import geo_scope

    geo = geo_scope.resolve(config)
    categories = list(config.categories or []) or ["events"]
    places: list[str | None] = list(geo.countries) or [None]
    enabled_sources = set(getattr(config, "sources", None) or [
        "web", "google_search", "bing_search", "linkedin", "facebook", "instagram", "twitter", "telegram", "reddit", "event_platforms"
    ])
    time_hint = _date_hint_for_config(config)
    term = lambda category, i=0: (SECTOR_SYNONYMS.get(category) or (category,))[i % len(SECTOR_SYNONYMS.get(category) or (category,))]  # noqa: E731
    qualifier = lambda i: _EVENT_TYPE_QUALIFIERS[i % len(_EVENT_TYPE_QUALIFIERS)]  # noqa: E731

    buckets: list[list[str]] = []
    has_web_or_engine = bool(enabled_sources & {"web", "google_search", "bing_search", "search_research_tool", "all", "all_sources", "all_operational"})
    if has_web_or_engine:
        coverage = []
        for d in range(len(places)):
            for i, category in enumerate(categories):
                country = places[(i + d) % len(places)]
                coverage.append(f"upcoming {term(category)} {qualifier(len(coverage))}{_place(country)} {time_hint}")
        buckets.append(coverage)

        cities = geo.fair_cities()
        city_queries = []
        for rnd in range(len(categories)):
            for i, (city, country) in enumerate(cities):
                category = categories[(i + rnd) % len(categories)]
                city_queries.append(f"{term(category)} {qualifier(len(city_queries))} in {_city_label(city, country)} {time_hint}")
        buckets.append(city_queries)

        state_queries = []
        for i, (state, country) in enumerate(geo.fair_states()):
            category = categories[i % len(categories)]
            state_queries.append(f"upcoming {term(category)} {qualifier(i)} {_city_label(state, country)} {time_hint}")
        buckets.append(state_queries)

        source_queries = []
        for i, category in enumerate(categories):
            for j, source_q in enumerate(_SOURCE_QUALIFIERS):
                country = places[(i + j) % len(places)]
                source_queries.append(f"{source_q} {term(category)}{_place(country)} {time_hint}")
        buckets.append(source_queries)

        publication_queries = []
        for i, category in enumerate(categories):
            for pub in SECTOR_PUBLICATIONS.get(category, ()):
                country = places[i % len(places)]
                publication_queries.append(f'"{pub}" {category}{_place(country) if country else " international"} {time_hint}')
        buckets.append(publication_queries)

    # Social & platform sources, anchored on the selected places.
    social_targets = [_city_label(c, k) for c, k in geo.fair_cities(4)] or [c for c in places if c] or [""]

    def site_bucket(templates: tuple[str, ...]) -> list[str]:
        out = []
        for loc in social_targets:
            loc_str = f" {loc}" if loc else ""
            for category in categories:
                out.extend(t.format(category=category, loc=loc_str, time=time_hint) for t in templates)
        return out

    if enabled_sources & {"linkedin", "linkedin_search"}:
        buckets.append(site_bucket(("site:linkedin.com/events {category}{loc} {time}", "site:linkedin.com/posts {category} (conference OR expo OR summit){loc} {time}")))
    if "facebook" in enabled_sources:
        buckets.append(site_bucket(("site:facebook.com/events {category}{loc} {time}",)))
    if "twitter" in enabled_sources:
        buckets.append(site_bucket(("site:x.com {category} (conference OR summit OR expo){loc} {time}", "site:twitter.com {category} (conference OR expo OR summit){loc} {time}")))
    if "instagram" in enabled_sources:
        buckets.append(site_bucket(('site:instagram.com {category} (conference OR summit OR expo OR "register now" OR "event in"){loc} {time}',)))
    if "telegram" in enabled_sources:
        buckets.append(site_bucket(('site:t.me {category} (conference OR summit OR expo OR meetup OR "event"){loc} {time}',)))
    if "reddit" in enabled_sources:
        buckets.append(site_bucket(('site:reddit.com {category} (conference OR summit OR expo OR meetup OR "annual event"){loc} {time}',)))
    if enabled_sources & {"event_platforms", "consumer_aggregators"}:
        buckets.append(site_bucket(("site:eventbrite.com/e {category}{loc} {time}", "site:meetup.com {category}{loc} {time}", "site:lu.ma {category}{loc} {time}")))

    if has_web_or_engine:
        # Alternate sector terms last: they broaden recall once every selection is covered.
        synonyms = []
        for i, category in enumerate(categories):
            for k in range(1, min(3, len(SECTOR_SYNONYMS.get(category) or (category,)))):
                for j, country in enumerate(places):
                    synonyms.append(f"{term(category, k)} {qualifier(i + j + k)}{_place(country)} {time_hint} official website")
        buckets.append(synonyms)
    return buckets


def _interleave(buckets: list[list[str]]) -> list[str]:
    """Coverage bucket first in full, then the rest round-robin; no repeats."""
    seen: set[str] = set()
    out: list[str] = []
    for q in buckets[0] if buckets else []:
        if q not in seen:
            seen.add(q)
            out.append(q)
    queues = [list(b) for b in buckets[1:] if b]
    while queues:
        for q in queues:
            item = q.pop(0)
            if item not in seen:
                seen.add(item)
                out.append(item)
        queues = [q for q in queues if q]
    return out


_COVERAGE_CAP = 60


def _first_wave_size(config: DiscoveryConfig, coverage: int) -> int:
    """`search_depth`, raised just enough that every selected (sector x
    country) pair is searched at least once (up to _COVERAGE_CAP)."""
    return max(int(config.search_depth or 0), min(coverage, _COVERAGE_CAP))


def build_search_queries(config: DiscoveryConfig) -> list[str]:
    """First wave of queries for a run: every selected sector x country first,
    then cities, states, sources and social/platform angles (see `_plan`)."""
    buckets = _plan(config)
    ordered = _interleave(buckets)
    return ordered[: _first_wave_size(config, len(buckets[0]) if buckets else 0)]


def build_expanded_queries(config: DiscoveryConfig) -> list[str]:
    """Second wave, used only when the first falls short: the rest of the
    selection's plan, then listing-site queries for more cities in the
    requested countries (never cities outside them)."""
    from backend.services.discovery_agent import geo_scope
    from backend.services.discovery_agent.country_utils import cities_for_country

    buckets = _plan(config)
    first = set(build_search_queries(config))
    rest = [q for q in _interleave(buckets) if q not in first]

    geo = geo_scope.resolve(config)
    categories = config.categories or ["conference", "summit", "expo", "exhibition"]
    time_hint = _date_hint_for_config(config)
    india_cities = [
        "Mumbai", "Bengaluru", "Delhi", "Hyderabad", "Pune", "Chennai",
        "Kolkata", "Ahmedabad", "Gurgaon", "Noida", "Jaipur", "Goa",
        "Chandigarh", "Kochi", "Indore", "Lucknow", "Bhopal", "Coimbatore",
    ]
    selected = set(geo.all_cities)
    extra: dict[str, list[str]] = {}
    for country in geo.countries:
        pool = india_cities if country == "India" else cities_for_country(country)
        extra[country] = [c for c in dict.fromkeys(pool) if c not in selected]
    if not geo.countries:
        extra[""] = [c for c in ["London", "New York", "Singapore", "Dubai", "Berlin", "Mumbai", "Bengaluru", "Tokyo", "Paris", "Sydney"] if c not in selected]
    more_cities = geo_scope._round_robin(extra, None)  # fair across the requested countries

    site_queries: list[str] = []
    for city, country in more_cities:
        label = _city_label(city, country)
        for cat in categories[:6]:
            site_queries.append(f"site:allevents.in/{city.lower()} {cat}")
            site_queries.append(f"site:eventbrite.com {cat} {label} {time_hint}")
            site_queries.append(f"site:meetup.com {cat} {label}")
            site_queries.append(f"upcoming {cat} in {label} {time_hint} registration")
            site_queries.append(f"{cat} conference expo {label} {time_hint}")
    return rest + [q for q in site_queries if q not in first]
