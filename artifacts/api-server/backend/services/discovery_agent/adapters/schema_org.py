"""Schema.org / JSON-LD Source Adapter for 100 TIMES Global Event Discovery.

Sites like Clocate, dev.events, AllEvents and Skillboxes publish
machine-readable schema.org Event metadata on their listing pages. Reading
works exactly like `HtmlListingAdapter` (the shared page extractor tries
JSON-LD first); this class only labels the access method.
"""

from backend.services.discovery_agent.adapters.html_listing import HtmlListingAdapter


class SchemaOrgAdapter(HtmlListingAdapter):
    """Adapter for websites exposing schema.org / JSON-LD Event metadata."""

    access_method = "schema_org"

    def __init__(self, source_id: str, name: str, website_url: str, category: str = "Global Event Discovery", config: dict | None = None) -> None:
        super().__init__(source_id=source_id, name=name, website_url=website_url, category=category, config=config)
