"""Search query generation — turns a `DiscoveryConfig` into a broad,
reproducible list of web-search queries spanning Indian cities, states,
event categories and the source types the spec calls out (event-listing
sites, conference/exhibition sites, college pages, trade associations,
government pages, ...), rather than relying on a single search.

Deterministic (no randomness) so the same config always produces the same
query list — important for `AgentRun.config_snapshot` reproducibility and
for testing.
"""

from backend.services.discovery_agent.types import DiscoveryConfig

# The event "types" the spec explicitly asks to cover, independent of topic category.
_EVENT_TYPE_QUALIFIERS = (
    "conference",
    "exhibition",
    "seminar",
    "workshop",
    "networking event",
    "summit",
    "webinar",
    "festival",
    "trade show",
)

# Broad source-type nudges — not every one applies to every combination, but
# rotating through them steers the search tool toward the variety of source
# types the spec lists, instead of always landing on the same aggregators.
_SOURCE_QUALIFIERS = (
    "site:*.edu.in",
    "college fest",
    "trade association event",
    "government event notice",
    "corporate event",
    "industry summit",
)

_YEAR_HINT = "2026"


def build_search_queries(config: DiscoveryConfig) -> list[str]:
    """Interleaves city-level and state-level queries across categories so
    the first N queries (however small `search_depth` is) already cover
    breadth across geography and topic, rather than exhausting one city
    before moving to the next."""
    cities = config.cities or []
    states = config.states or []
    categories = config.categories or ["events"]

    city_queries: list[str] = []
    for city in cities:
        for category in categories:
            qualifier = _EVENT_TYPE_QUALIFIERS[len(city_queries) % len(_EVENT_TYPE_QUALIFIERS)]
            city_queries.append(f"{category} {qualifier} in {city} India {_YEAR_HINT}")

    state_queries: list[str] = []
    for state in states:
        for category in categories:
            qualifier = _EVENT_TYPE_QUALIFIERS[len(state_queries) % len(_EVENT_TYPE_QUALIFIERS)]
            state_queries.append(f"upcoming {category} {qualifier} {state} India {_YEAR_HINT}")

    source_queries: list[str] = []
    for category in categories:
        for qualifier in _SOURCE_QUALIFIERS:
            source_queries.append(f"{qualifier} {category} event India {_YEAR_HINT}")

    interleaved: list[str] = []
    buckets = [city_queries, state_queries, source_queries]
    index = 0
    while len(interleaved) < config.search_depth and any(buckets):
        bucket = buckets[index % len(buckets)]
        if bucket:
            interleaved.append(bucket.pop(0))
        index += 1
        if not any(buckets):
            break

    return interleaved[: config.search_depth]
