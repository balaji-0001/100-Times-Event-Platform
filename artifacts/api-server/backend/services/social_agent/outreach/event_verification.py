"""Event Verification — the "is this worth contacting an organizer about"
gate, run after the AI's event extraction and before the organizer finder.
Per the architecture spec: never contact an organizer based on a weak or
unverified result.

Checks performed here, deliberately narrow and honest:
  - is it real?        -> `ExtractedEventAI.is_genuine_event` (already the
                           AI extraction's own judgment; re-checked here as
                           defense-in-depth for direct/manual callers)
  - is it upcoming?     -> best-effort date parse; only REJECTS when a date
                           was confidently parsed AND it's clearly in the
                           past. An unparseable/relative date ("next month")
                           is not rejected — it's flagged as a note for the
                           human reviewer instead of guessed at.
  - is the source trustworthy? -> reuses the existing `Community.risk_level`
                           (the same field the Attendee Agent's own
                           `CommunityRulesChecker` already relies on) as a
                           note for the reviewer, not a hard reject — the
                           human approval gate is the real safety net.

"Is date/location valid" and "is organizer identifiable" are handled by
their own dedicated stages (this module only owns the two checks above);
duplicating them here would just be re-deriving what those stages already do.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

from backend.models import Community
from backend.services.social_agent.pipeline.event_extraction import ExtractedEventAI

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")


@dataclass
class VerificationResult:
    is_upcoming: bool
    reason: str | None
    notes: list[str] = field(default_factory=list)


def _try_parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def verify_event(event: ExtractedEventAI, community: Community | None) -> VerificationResult:
    notes: list[str] = []

    if not event.is_genuine_event:
        return VerificationResult(is_upcoming=False, reason="Not flagged as a genuine, specific event.", notes=notes)

    parsed_date = _try_parse_date(event.date)
    if parsed_date is not None and parsed_date < date.today():
        return VerificationResult(
            is_upcoming=False,
            reason=f"Extracted event date ({event.date}) is in the past.",
            notes=notes,
        )
    if parsed_date is None and event.date:
        notes.append(f"Could not confidently parse the event date ({event.date!r}) — verify manually before approving.")

    if community is not None and community.risk_level == "high":
        notes.append(f"Source community ({community.name}) is flagged high-risk — verify carefully before approving.")

    return VerificationResult(is_upcoming=True, reason=None, notes=notes)
