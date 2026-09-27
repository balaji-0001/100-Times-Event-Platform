"""Shared value types for the Event Discovery & Organizer Research Agent —
deliberately plain dataclasses (not DB models), mirroring the pattern
already used by `outreach/types.py` and `connectors/types.py`.
"""

from dataclasses import dataclass, field


@dataclass
class DiscoveryConfig:
    """Everything one discovery run is configured with. Captured verbatim
    into `AgentRun.config_snapshot` so a run is reproducible and auditable."""

    cities: list[str]
    states: list[str]
    categories: list[str]
    search_depth: int = 20  # max search queries this run issues
    sources_per_query: int = 5  # max candidate URLs pulled from each query
    daily_limit: int = 200  # max new DiscoveredEvent rows this run may create
    confidence_threshold: int = 60  # below this, verification_status becomes NEEDS_REVIEW


@dataclass
class CandidateSource:
    """One URL the web-search stage surfaced, not yet fetched/extracted."""

    url: str
    source_type: str
    source_website: str | None = None


@dataclass
class ExtractedEventCandidate:
    """Event facts pulled from one candidate page. Any field the page
    didn't actually contain stays `None` — never guessed. `sources` records
    every page/hop that contributed a fact, for full provenance."""

    name: str | None = None
    event_description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    venue: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    url: str | None = None
    ticket_url: str | None = None
    event_format: str | None = None  # online | offline | hybrid
    organizer_name_hint: str | None = None
    extraction_confidence: int = 0
    primary_source: CandidateSource | None = None
    sources: list[CandidateSource] = field(default_factory=list)
    raw_evidence: dict | None = None


@dataclass
class OrganizerCandidate:
    """Result of `organizer_identifier.identify_organizer`. `found` is True
    only when a usable, publicly-listed contact (email, or at minimum a
    verifiable name+website) was actually located on a fetched page."""

    found: bool
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    linkedin: str | None = None
    organizer_type: str | None = None
    city: str | None = None
    state: str | None = None
    confidence_score: int = 0
    sources: list[CandidateSource] = field(default_factory=list)


@dataclass
class RunSummary:
    """Exact shape requested for Agent 1's structured per-run output."""

    events_discovered: int = 0
    new_events: int = 0
    duplicate_events: int = 0
    organizers_found: int = 0
    new_organizers: int = 0
    contacts_found: int = 0
    events_needing_review: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "events_discovered": self.events_discovered,
            "new_events": self.new_events,
            "duplicate_events": self.duplicate_events,
            "organizers_found": self.organizers_found,
            "new_organizers": self.new_organizers,
            "contacts_found": self.contacts_found,
            "events_needing_review": self.events_needing_review,
        }
