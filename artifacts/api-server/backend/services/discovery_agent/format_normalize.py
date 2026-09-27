"""Normalizes whatever free-text an extraction source (schema.org JSON-LD's
`eventAttendanceMode`, or the LLM's own words) says about how an event is
held into the fixed vocabulary the rest of the app expects: `"online"`,
`"offline"`, or `"hybrid"` — or `None` when the source didn't say, or said
something too ambiguous to classify.

Deliberately kept separate from the extraction schema itself, which stays
permissive (plain `str`, not a strict enum): a page that phrases its format
unexpectedly ("In-person exhibition and conference", schema.org's
"MixedEventAttendanceMode" URL, ...) still produces a real event record
instead of being rejected outright for one field failing validation. This
function is where that free text gets turned into something storage,
filters, and the dashboard can count on. Never guesses "offline" as a
default — an unrecognized or missing value stays `None`.
"""

_ONLINE_HINTS = ("online", "virtual", "webinar", "livestream", "live stream", "remote")
_OFFLINE_HINTS = ("offline", "in-person", "in person", "physical", "on-site", "onsite", "on site")
_HYBRID_HINTS = ("hybrid", "mixed")


def normalize_event_format(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip().lower()
    if text in ("online", "offline", "hybrid"):
        return text
    if any(hint in text for hint in _HYBRID_HINTS):
        return "hybrid"

    is_online = any(hint in text for hint in _ONLINE_HINTS)
    is_offline = any(hint in text for hint in _OFFLINE_HINTS)
    if is_online and is_offline:
        return "hybrid"
    if is_online:
        return "online"
    if is_offline:
        return "offline"
    return None
