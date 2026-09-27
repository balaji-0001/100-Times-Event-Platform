from typing import Any


class TelegramContentGenerator:
    """Formatted community-update style, suited to Telegram channel posts."""

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

        loc = f" in {location}" if location else ""
        link_allowed = rules_check.get("external_links_allowed", True)

        lines = []
        for ev in matched_events[:3]:
            price = "Free" if ev.get("price", 0) == 0 else f"₹{int(ev['price'])}"
            link = f" — https://100times.in/events/{ev['slug']}" if link_allowed else ""
            lines.append(f"• {ev['title']} ({ev['startDate']}, {price}){link}")

        v1 = f"📅 Upcoming events{loc} that match what you're looking for:\n" + "\n".join(lines)
        v2 = f"A few community picks{loc} this week:\n" + "\n".join(lines[:2])
        v3 = f"Quick update — {matched_events[0]['title']} is happening on {matched_events[0]['startDate']}{loc}."

        return v1, [v1, v2, v3]
