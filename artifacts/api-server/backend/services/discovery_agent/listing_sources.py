"""Public event-listing pages the Discovery Agent reads directly — the
no-AI path. Each template may contain `{city}`, expanded once per target
city; a template without it is used as-is. Their events come from the
pages' own schema.org data (see `page_extractor.extract_events_from_listing`),
so this works without any AI key.
"""

from urllib.parse import urlparse

# Sites that spell some cities differently in their URLs. allevents.in
# silently redirects an unknown city to its all-India page, so these matter.
_CITY_SLUG_ALIASES = {
    "allevents.in": {"bengaluru": "bangalore", "delhi": "new-delhi", "gurugram": "gurgaon"},
}


def _slug(city: str) -> str:
    return "-".join(city.strip().lower().split())


def build_listing_urls(templates: list[str], cities: list[str]) -> list[str]:
    urls: list[str] = []
    for template in templates:
        if "{city}" not in template:
            expanded = [template]
        else:
            host = (urlparse(template).netloc or "").lower().removeprefix("www.")
            aliases = _CITY_SLUG_ALIASES.get(host, {})
            expanded = [template.replace("{city}", aliases.get(_slug(city), _slug(city))) for city in cities if city.strip()]
        for url in expanded:
            if url not in urls:
                urls.append(url)
    return urls
