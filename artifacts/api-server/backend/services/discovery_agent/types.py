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
    # Exact selection from the admin UI's country -> state -> city picker:
    # [{"country": ..., "state": ..., "city": ...}]. Lets every stage know which
    # country each city/state belongs to (see geo_scope.py).
    locations: list[dict] = field(default_factory=list)
    # The location picker's state -> cities lists for countries where a whole
    # state was ticked, so the run can tell which state an event's city is in.
    region_cities: dict[str, dict[str, list[str]]] = field(default_factory=dict)
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
    fallback_to_other_sector: bool = True  # only for runs not limited to particular sectors
    # Set at run start: True when the run covers particular sectors (not all of
    # them), so events outside those sectors are skipped, never filed as 'Other'.
    sector_scoped: bool = False
    # Store rejected candidates (with the reason) so an admin can review and
    # restore them: rule rejections, no organizer e-mail, and events of
    # another real sector. Duplicates and sector-less noise are never stored.
    keep_rejected_events: bool = True
    min_title_length: int = 8
    min_description_length: int = 20
    min_confidence_score: int = 0
    blacklisted_keywords: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)

    # Web-search providers this run may call (ids from the search engine, e.g.
    # "searxng", "exa_search", "google_gemini", "web_fallback"); None = every
    # configured provider. Applies to discovery queries AND organizer lookups,
    # and a provider left out is never called, not even as a fallback.
    search_providers: list[str] | None = None
    # Paid search calls (Exa / Google / Brave …) this run may make; None = settings default.
    paid_search_budget: int | None = None

    # Execution budget & concurrency (network work runs in worker threads;
    # every DB write stays on the run's own thread).
    max_run_seconds: int = 900  # stop launching new work after this; report the shortfall
    max_parallel_searches: int = 4  # concurrent search queries (providers also self rate-limit)
    max_parallel_fetches: int = 8  # concurrent page reads (adapters, listings, result pages)
    max_parallel_organizer_lookups: int = 8  # concurrent organizer/contact verifications


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
    # Which run source produced this candidate (adapter / aggregator / search
    # provider id), for the per-source execution report. Not stored.
    discovery_origin: str | None = None


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
    # Page each other detail was read from ("phone", "website", "name", "linkedin", …).
    field_sources: dict[str, str] = field(default_factory=dict)


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
    # New events stored as VERIFIED — the only ones counted toward `target_valid_events`.
    # (`accepted_events` also includes NEEDS_REVIEW rows.)
    verified_events: int = 0
    out_of_target_country: int = 0
    out_of_target_city: int = 0  # in a selected country, but not in one of its ticked cities
    # target_reached | sources_exhausted | time_budget | candidate_ceiling | cancelled
    stop_reason: str | None = None
    target_shortfall: int | None = None
    # Wall-clock milestones and cumulative per-stage worker time (ms), cache use and request counts.
    timings: dict[str, Any] = field(default_factory=dict)
    # What the run actually covered: countries, city/state counts, sectors, adapters, listing pages, queries.
    scope: dict[str, Any] = field(default_factory=dict)
    event_ids: list[int] = field(default_factory=list)
    # Per-source execution report (see source_report.py): counts + one row per selected source.
    sources: dict[str, Any] = field(default_factory=dict)
    # This run's search calls (provider, query, status, results, latency, cost, purpose) — bounded.
    search_log: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "search_provider_logs": self.search_log,
            "verified_events": self.verified_events,
            "out_of_target_country": self.out_of_target_country,
            "out_of_target_city": self.out_of_target_city,
            "stop_reason": self.stop_reason,
            "target_shortfall": self.target_shortfall,
            "timings": self.timings,
            "scope": self.scope,
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
