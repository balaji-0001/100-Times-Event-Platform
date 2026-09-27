from typing import Any


class XContentGenerator:
    """Short-form (<=280 char) real-time post/reply suited to X."""

    CHAR_LIMIT = 280

    @classmethod
    def generate_variations(
        cls,
        title: str,
        content: str,
        matched_events: list[dict[str, Any]],
        rules_check: dict[str, Any],
        location: str | None = None,
    ) -> tuple[str, list[str]]:
        if not matched_events:
            return "", []

        ev1 = matched_events[0]
        loc = f" in {location}" if location else ""
        link_allowed = rules_check.get("external_links_allowed", True)
        link = f" 100times.in/events/{ev1['slug']}" if link_allowed else ""

        v1 = cls._truncate(f"{ev1['title']}{loc} — {ev1['startDate']}.{link}")
        v2 = cls._truncate(f"Looking for this? {ev1['title']} is on {ev1['startDate']}{loc}.{link} #Events")
        v3 = cls._truncate(f"{ev1['title']}{loc}, {ev1['startDate']}. Worth a look.{link}")

        return v1, [v1, v2, v3]

    @classmethod
    def _truncate(cls, text: str) -> str:
        if len(text) <= cls.CHAR_LIMIT:
            return text
        return text[: cls.CHAR_LIMIT - 1].rstrip() + "…"
