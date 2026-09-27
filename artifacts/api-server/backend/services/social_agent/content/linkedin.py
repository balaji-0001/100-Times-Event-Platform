from typing import Any


class LinkedInContentGenerator:
    """Professional, longer-form post suited to LinkedIn's tone."""

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
        ev2 = matched_events[1] if len(matched_events) > 1 else None
        loc = f" in {location}" if location else ""
        link_allowed = rules_check.get("external_links_allowed", True)
        link_line = f"\n\nDetails and registration: https://100times.in/events/{ev1['slug']}" if link_allowed else ""

        v1 = (
            f"For anyone exploring {ev1['category'].lower()} events{loc}, '{ev1['title']}' on {ev1['startDate']} "
            f"looks like a strong fit — it brings together practitioners and operators for focused, substantive conversation."
            f"{link_line}"
        )
        v2 = (
            f"A couple of upcoming professional gatherings{loc} worth your calendar: '{ev1['title']}' on {ev1['startDate']}"
            + (f", and '{ev2['title']}' on {ev2['startDate']}" if ev2 else "")
            + ". Both are listed on 100.com."
        )
        v3 = f"'{ev1['title']}'{loc} on {ev1['startDate']} is a relevant option if you're building your network in this space."

        return v1, [v1, v2, v3]
