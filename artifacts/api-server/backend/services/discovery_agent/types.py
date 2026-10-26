"""Shared value types for the Event Discovery & Organizer Research Agent —
deliberately plain dataclasses (not DB models), mirroring the pattern
already used by `outreach/types.py` and `connectors/types.py`.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiscoveryConfig:
    """Everything one discovery run is configured with. Captured verbatim
    into `AgentRun.config_snapshot` so a run is reproducible and auditable."""

    cities: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=lambda: ["web", "linkedin", "facebook", "instagram", "twitter", "telegram", "reddit", "event_platforms"])
    countries: list[str] = field(default_factory=list)
    country: str | None = None
    search_depth: int = 20  # max search queries this run issues
    sources_per_query: int = 5  # max candidate URLs pulled from each query
    daily_limit: int = 200  # max new DiscoveredEvent rows this run may create
    events_per_run: int = 50  # max events/candidates to discover in a single run
    target_valid_events: int | None = None  # stop run once this many valid/accepted events are found
    confidence_threshold: int = 60  # below this, verification_status becomes NEEDS_REVIEW
    listing_urls: list[str] = field(default_factory=list)  # listing-page templates read without AI; may contain {city}
    events_per_listing: int = 25  # max events taken from one listing page
    require_organizer_email: bool = False  # mandatory organizer email check (production rule)
    date_from: str | None = None  # optional start date filter (YYYY-MM-DD)
    date_to: str | None = None  # optional end date filter (YYYY-MM-DD)
    ticketmaster_api_key: str | None = None
    ticketmaster_enabled: bool = False
    is_manual: bool = False  # True when manually triggered by an admin from Ops / Manual Research

    # Configurable rejection & quality filter rules
    reject_no_organizer: bool = False
    require_organizer_phone: bool = False
    require_organizer_website: bool = False
    reject_past_events: bool = True
    reject_unparseable_dates: bool = True
    reject_missing_location: bool = False
    reject_missing_ticket_url: bool = False
    reject_unmatched_category: bool = False
    fallback_to_other_sector: bool = True
    min_title_length: int = 8
    min_description_length: int = 20
    min_confidence_score: int = 0
    blacklisted_keywords: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)


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
    # Read from page text by fixed rules (no structured data on the page) —
    # always held for human review, whatever its confidence.
    best_effort: bool = False


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
    twitter: str | None = None
    instagram: str | None = None
    facebook: str | None = None
    organizer_type: str | None = None
    city: str | None = None
    state: str | None = None
    confidence_score: int = 0
    sources: list[CandidateSource] = field(default_factory=list)
    email_source_url: str | None = None  # Exact public source URL where organizer email was verified


@dataclass
class RunSummary:
    """Exact shape requested for Agent 1's structured per-run output,
    tracking discovered, accepted, rejected, duplicate, and missing-organiser-email counts."""

    events_discovered: int = 0
    accepted_events: int = 0
    new_events: int = 0  # alias/backwards-compat for accepted_events
    rejected_events: int = 0
    duplicate_events: int = 0
    missing_organizer_email: int = 0
    unsupported_category: int = 0
    past_or_expired: int = 0
    organizers_found: int = 0
    new_organizers: int = 0
    contacts_found: int = 0
    events_needing_review: int = 0
    event_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "events_discovered": self.events_discovered,
            "accepted_events": self.accepted_events or self.new_events,
            "new_events": self.new_events,
            "rejected_events": self.rejected_events,
            "duplicate_events": self.duplicate_events,
            "missing_organizer_email": self.missing_organizer_email,
            "unsupported_category": self.unsupported_category,
            "past_or_expired": self.past_or_expired,
            "organizers_found": self.organizers_found,
            "new_organizers": self.new_organizers,
            "contacts_found": self.contacts_found,
            "events_needing_review": self.events_needing_review,
            "event_ids": self.event_ids,
        }
