from typing import Any


class InstagramContentAgent:
    """Instagram works as a Content Distribution Agent: it turns a theme

    ("Top 5 events this weekend", "Best AI events in Hyderabad", ...) plus
    the matched 100.com catalog into a ready-to-review content pack, instead
    of replying to individual discussions like the other connectors.
    """

    @classmethod
    def generate_theme_pack(cls, theme: str, matched_events: list[dict[str, Any]]) -> dict[str, Any]:
        top = matched_events[:5]

        if not top:
            return {
                "caption": f"{theme} — fresh listings drop on 100.com regularly, check back soon! 👀",
                "carouselSlides": [],
                "reelScript": "",
                "hashtags": ["#100times", "#EventsNearYou"],
                "cta": "Explore more on 100.com",
                "eventLinks": [],
            }

        lines = [f"{i + 1}. {ev['title']} — {ev['location']}, {ev['startDate']}" for i, ev in enumerate(top)]
        caption = (
            f"{theme} 🎉\n\n"
            + "\n".join(lines)
            + "\n\nSwipe through for the full lineup and tap the link in bio to grab your spot on 100.com."
        )

        carousel_slides: list[dict[str, Any]] = [
            {
                "slideNumber": 1,
                "headline": theme,
                "subtext": f"{len(top)} handpicked events you don't want to miss",
            }
        ]
        for i, ev in enumerate(top):
            price_label = "Free" if ev.get("price", 0) == 0 else f"₹{int(ev['price'])}"
            carousel_slides.append(
                {
                    "slideNumber": i + 2,
                    "headline": ev["title"],
                    "subtext": f"{ev['location']} · {ev['startDate']} · {price_label}",
                }
            )

        reel_script = (
            f"HOOK (0-3s): \"{theme}? Here's your shortlist.\"\n"
            f"BODY (3-15s): Quick cuts through {min(3, len(top))} events — venue, date, one-line hook for each.\n"
            f"CTA (15-20s): \"Full list + tickets on 100.com — link in bio.\""
        )

        hashtags = ["#100times", "#EventsNearYou"]
        for ev in top:
            cat = (ev.get("category") or "").strip()
            if not cat:
                continue
            tag = "#" + "".join(word.capitalize() for word in cat.split())
            if tag not in hashtags:
                hashtags.append(tag)
        for extra in ("#ThingsToDo", "#WeekendPlans"):
            if extra not in hashtags:
                hashtags.append(extra)

        event_links = [f"https://100times.in/events/{ev['slug']}" for ev in top]

        return {
            "caption": caption,
            "carouselSlides": carousel_slides,
            "reelScript": reel_script,
            "hashtags": hashtags[:10],
            "cta": "Tap the link in bio to explore & register on 100.com",
            "eventLinks": event_links,
        }
