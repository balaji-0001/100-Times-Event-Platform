"""Shared value types for the Community Discovery Agent — plain dataclasses
(not DB models), mirroring `discovery_agent/types.py`'s pattern exactly.
"""

from dataclasses import dataclass, field


@dataclass
class CommunityDiscoveryConfig:
    """Everything one discovery run is configured with. Captured verbatim
    into `AgentRun.config_snapshot` so a run is reproducible and auditable."""

    cities: list[str]
    states: list[str]
    categories: list[str]
    search_depth: int = 30  # max search queries this run issues
    sources_per_query: int = 5  # max candidate URLs pulled from each query
    daily_limit: int = 100  # max new DiscoveredCommunity rows this run may create
    confidence_threshold: int = 60  # below this, approval_status becomes NEEDS_REVIEW
    seed_urls: list[str] = field(default_factory=list)


@dataclass
class CandidateSource:
    """One URL the search stage surfaced, not yet fetched/extracted."""

    url: str
    source_type: str  # search_result | invite_page | platform_api


@dataclass
class ExtractedCommunityCandidate:
    """Community facts read from one candidate's invite page/public API.
    Any field the source didn't actually contain stays `None` — never
    guessed. `member_count` in particular is only ever a number the
    platform itself reported."""

    platform: str | None = None  # telegram | discord
    name: str | None = None
    canonical_url: str | None = None
    invite_url: str | None = None
    description: str | None = None
    topics: list[str] = field(default_factory=list)
    language: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    member_count: int | None = None
    rules_text: str | None = None
    extraction_confidence: int = 0
    primary_source: CandidateSource | None = None
    sources: list[CandidateSource] = field(default_factory=list)
    raw_evidence: dict | None = None


@dataclass
class RunSummary:
    """Structured per-run output, same shape discipline as discovery_agent's."""

    communities_discovered: int = 0
    new_communities: int = 0
    duplicate_communities: int = 0
    communities_needing_review: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "communities_discovered": self.communities_discovered,
            "new_communities": self.new_communities,
            "duplicate_communities": self.duplicate_communities,
            "communities_needing_review": self.communities_needing_review,
        }
