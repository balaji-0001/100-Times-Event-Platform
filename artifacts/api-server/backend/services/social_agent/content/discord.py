from typing import Any


class DiscordContentGenerator:
    """Casual, conversational recommendation matching Discord's chat tone."""

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
        price = "free" if ev1.get("price", 0) == 0 else f"₹{int(ev1['price'])}"
        link_line = f"\n🔗 https://100times.in/events/{ev1['slug']}" if link_allowed else ""

        v1 = f"hey! 👋 saw your message — '{ev1['title']}' on {ev1['startDate']}{loc} looks like a solid fit ({price}).{link_line}"
        v2 = (
            f"a couple of options that might work: **{ev1['title']}** ({ev1['startDate']})"
            + (f" and **{ev2['title']}** ({ev2['startDate']})" if ev2 else "")
            + f" — both listed on 100.com{loc}."
        )
        v3 = f"check out **{ev1['title']}**{loc} on {ev1['startDate']}, it's {price} and matches what you're after 🙂"

        return v1, [v1, v2, v3]
