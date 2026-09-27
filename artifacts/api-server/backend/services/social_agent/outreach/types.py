"""Shared value types for Organizer Outreach — deliberately plain
dataclasses (not DB models), mirroring the `Signal`/`PublishResult` pattern
already used by connectors/publishers in `services/social_agent/types.py`.
"""

from dataclasses import dataclass


@dataclass
class EventDetails:
    """Event facts extracted from a discussion candidate, OR pulled from a
    `DiscoveredEvent` row the Event Discovery Agent found directly on the
    web. Any field the source data didn't actually contain stays `None` —
    never guessed."""

    name: str | None
    date: str | None
    location: str | None
    category: str | None
    url: str | None
    source_url: str | None
    organizer_name_hint: str | None
    match_score: int
    venue: str | None = None
    city: str | None = None
    event_format: str | None = None
    ticket_url: str | None = None
    subcategory: str | None = None


@dataclass
class OrganizerContactInfo:
    """Result of `organizer_finder.find_organizer` (or the equivalent
    lookup against an already-stored `DiscoveredOrganizer`). `found` is True
    only when a usable, publicly-listed email address was located — a name
    or website alone isn't enough to safely send an outreach email.

    Named `OrganizerContactInfo` (not `OrganizerContact`) to avoid confusion
    with the `backend.models.OrganizerContact` ORM table, which is a
    different, DB-persisted concept (one row per contact channel)."""

    found: bool
    name: str | None = None
    email: str | None = None
    website: str | None = None
    linkedin: str | None = None
    source_url: str | None = None


@dataclass
class SendResult:
    success: bool
    message_id: str | None = None
    message: str = ""
    bounced: bool = False


@dataclass
class OutreachRunConfig:
    """Config for one Agent 2 batch research+draft run — captured verbatim
    into `AgentRun.config_snapshot` for reproducibility, same pattern as
    `discovery_agent.types.DiscoveryConfig`."""

    max_candidates: int = 20
    verification_statuses: tuple[str, ...] = ("VERIFIED", "NEEDS_REVIEW")


@dataclass
class OutreachRunSummary:
    candidates_considered: int = 0
    drafted: int = 0
    skipped_duplicate: int = 0
    skipped_suppressed: int = 0
    skipped_no_organizer: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "candidates_considered": self.candidates_considered,
            "drafted": self.drafted,
            "skipped_duplicate": self.skipped_duplicate,
            "skipped_suppressed": self.skipped_suppressed,
            "skipped_no_organizer": self.skipped_no_organizer,
        }
