"""Search query generation — turns a `CommunityDiscoveryConfig` into a
broad, reproducible list of web-search queries aimed at finding public
Telegram group/channel and Discord server invite links, mirroring
`discovery_agent/query_seeds.py`'s interleaving approach exactly (same
reproducibility rationale: `AgentRun.config_snapshot` + testability).
"""

from backend.services.community_agent.types import CommunityDiscoveryConfig

_TELEGRAM_QUALIFIERS = ("Telegram group", "Telegram channel", "join our Telegram")
_DISCORD_QUALIFIERS = ("Discord server", "join our Discord", "Discord community")

SECTOR_COMMUNITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Pharmaceuticals": ("Pharmaceuticals", "Pharma", "Biotech"),
    "Healthcare": ("Healthcare", "Medical", "Doctors"),
    "Energy and Power Generation": ("Renewable Energy", "Solar Energy", "Power Generation"),
    "Telecommunications": ("Telecommunications", "Telecom", "5G Network"),
    "Construction": ("Construction", "Civil Engineering", "Builders Infrastructure"),
    "Mining": ("Mining", "Minerals Extraction", "Metallurgy"),
    "Finance": ("Finance", "Fintech", "Stock Market Trading"),
    "Packaging": ("Packaging", "Corrugated Packaging", "Packtech"),
    "Transport and Logistics": ("Logistics", "Supply Chain", "Freight Transport"),
    "Oil and Gas": ("Oil and Gas", "Petroleum", "Refinery Hydrocarbon"),
    "Textiles": ("Textiles", "Garments Apparel", "Fabrics Spinning"),
    "Manufacturing": ("Manufacturing", "Industrial Automation", "Robotics Industry"),
}


def build_search_queries(config: CommunityDiscoveryConfig) -> list[str]:
    """Interleaves city-level, category-level and platform-site-scoped
    queries so the first N queries (however small `search_depth` is)
    already cover breadth across all 12 platform sectors, geography and platform."""
    cities = config.cities or []
    categories = config.categories or list(SECTOR_COMMUNITY_KEYWORDS.keys())

    city_queries: list[str] = []
    for i, category in enumerate(categories):
        kw_list = SECTOR_COMMUNITY_KEYWORDS.get(category, (category,))
        kw = kw_list[0]
        city = cities[i % len(cities)] if cities else "India"
        tg = _TELEGRAM_QUALIFIERS[len(city_queries) % len(_TELEGRAM_QUALIFIERS)]
        city_queries.append(f'"{tg}" {kw} {city} India')
        dc = _DISCORD_QUALIFIERS[len(city_queries) % len(_DISCORD_QUALIFIERS)]
        city_queries.append(f'"{dc}" {kw} {city} India')

    category_queries: list[str] = []
    for category in categories:
        kw_list = SECTOR_COMMUNITY_KEYWORDS.get(category, (category,))
        for kw in kw_list:
            category_queries.append(f"site:t.me {kw} India")
            category_queries.append(f"site:discord.gg {kw} India")

    interleaved: list[str] = []
    buckets = [city_queries, category_queries]
    index = 0
    while len(interleaved) < config.search_depth and any(buckets):
        bucket = buckets[index % len(buckets)]
        if bucket:
            interleaved.append(bucket.pop(0))
        index += 1
        if not any(buckets):
            break

    return interleaved[: config.search_depth]
