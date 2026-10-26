"""Public event-listing pages the Discovery Agent reads directly — the
no-AI path. Each template may contain `{city}`, expanded once per target
city; a template without it is used as-is. Their events come from the
pages' own schema.org data (see `page_extractor.extract_events_from_listing`),
so this works without any AI key.
"""

from urllib.parse import urlparse

DEFAULT_LISTING_URLS = [
    "https://allevents.in/{city}",
    "https://www.eventbrite.com/d/{country}--{city}/events/",
    "https://www.eventbrite.com/d/{city}/events/",
    "https://www.meetup.com/find/?location={city}&source=EVENTS",
    "https://10times.com/{city}",
    "https://www.skillboxes.com/events",
]

# Sites that spell some cities differently in their URLs. allevents.in
# silently redirects an unknown city to its all-India page, so these matter.
_CITY_SLUG_ALIASES = {
    "allevents.in": {"bengaluru": "bangalore", "delhi": "new-delhi", "gurugram": "gurgaon"},
}


def _slug(city: str) -> str:
    return "-".join(city.strip().lower().split())


def build_listing_urls(
    templates: list[str],
    cities: list[str],
    countries: list[str] | None = None,
    country: str | None = None,
) -> list[str]:
    urls: list[str] = []
    target_countries = [country] if (country and country.lower() not in ("all", "all countries", "worldwide")) else (countries or [""])
    for template in templates:
        has_country = "{country}" in template
        has_city = "{city}" in template

        if not has_city and not has_country:
            if template not in urls:
                urls.append(template)
            continue

        c_list = [c for c in target_countries if c] or ["global"]
        for c in c_list:
            c_slug = _slug(c) if c else ""
            t_country = template.replace("{country}", c_slug) if has_country else template
            if not has_city:
                if t_country not in urls:
                    urls.append(t_country)
                continue
            host = (urlparse(t_country).netloc or "").lower().removeprefix("www.")
            aliases = _CITY_SLUG_ALIASES.get(host, {})
            for city in cities:
                if not city.strip():
                    continue
                city_slug = aliases.get(_slug(city), _slug(city))
                url = t_country.replace("{city}", city_slug)
                if url not in urls:
                    urls.append(url)
    return urls
