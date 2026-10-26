"""Event Discovery Agent orchestrator — end-to-end idempotency test. Search
and extraction are monkeypatched to always return the SAME candidate event,
which exercises dedup both within one run (several queries surface the same
event) and across two separate runs (a re-run must not duplicate what the
first run already stored) — the restartable/idempotent requirement."""

from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer
from backend.services.discovery_agent import orchestrator
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate, OrganizerCandidate


def _fixed_candidate() -> ExtractedEventCandidate:
    source = CandidateSource(url="https://example.test/pune-tech-summit", source_type="event_listing", source_website="example.test")
    return ExtractedEventCandidate(
        name="Pune Tech Summit",
        date="2099-01-01",
        venue="Convention Centre",
        city="Pune",
        state="Maharashtra",
        country="India",
        url=source.url,
        extraction_confidence=85,
        primary_source=source,
        sources=[source],
    )


def _fixed_organizer() -> OrganizerCandidate:
    source = CandidateSource(url="https://example.test/pune-tech-summit", source_type="event_listing")
    return OrganizerCandidate(found=True, name="Pune Events Collective", email="hello@puneevents.test", confidence_score=70, sources=[source])


def _config() -> DiscoveryConfig:
    return DiscoveryConfig(cities=["Pune"], states=[], categories=["Technology"], search_depth=2, sources_per_query=1, daily_limit=200, confidence_threshold=60)


def _patch_pipeline(monkeypatch):
    # Each query surfaces a different page, but every page lists the same event.
    monkeypatch.setattr(orchestrator.web_search, "search", lambda query, max_results: [f"https://example.test/results/{abs(hash(query))}"])
    monkeypatch.setattr(orchestrator.page_extractor, "extract_events_from_page", lambda url, max_events, cities: [_fixed_candidate()])
    monkeypatch.setattr(orchestrator.organizer_identifier, "identify_organizer", lambda candidate: _fixed_organizer())


def test_discovery_agent_dedups_within_a_single_run(db_session, monkeypatch):
    _patch_pipeline(monkeypatch)

    summary = orchestrator.run_discovery_agent(db_session, _config())

    assert summary.events_discovered == 2  # two queries both surfaced the same event
    assert summary.new_events == 1
    assert summary.duplicate_events == 1
    assert db_session.query(DiscoveredEvent).count() == 1
    assert db_session.query(DiscoveredOrganizer).count() == 1

    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "discovery").one()
    assert run.status == "completed"
    assert run.summary["new_events"] == 1


def test_discovery_agent_does_not_duplicate_across_runs(db_session, monkeypatch):
    _patch_pipeline(monkeypatch)

    orchestrator.run_discovery_agent(db_session, _config())
    second_summary = orchestrator.run_discovery_agent(db_session, _config())

    assert second_summary.new_events == 0
    assert second_summary.duplicate_events == 2
    assert db_session.query(DiscoveredEvent).count() == 1


def test_target_valid_events_rule_continues_until_target_reached(db_session, monkeypatch):
    """RULE: If user needs N valid events (e.g. 10), the agent must search until
    10 valid events are found, even if duplicates or raw candidate counts exceed N."""
    candidate_counter = 0

    def mock_extract(url, max_events, cities):
        nonlocal candidate_counter
        candidate_counter += 1
        if candidate_counter % 2 == 1:
            name = "Repeated Dupe Event"
        else:
            name = f"Unique Event {candidate_counter}"
        source = CandidateSource(url=f"https://example.test/events/{candidate_counter}", source_type="event_listing", source_website="example.test")
        return [
            ExtractedEventCandidate(
                name=name,
                date="2099-06-01",
                venue="Auditorium",
                city="Bengaluru",
                state="Karnataka",
                country="India",
                url=source.url,
                extraction_confidence=90,
                primary_source=source,
                sources=[source],
            )
        ]

    monkeypatch.setattr(orchestrator.listing_sources, "build_listing_urls", lambda *args, **kwargs: [f"https://example.test/page/{i}" for i in range(50)])
    monkeypatch.setattr(orchestrator.page_extractor, "extract_events_from_page", mock_extract)
    monkeypatch.setattr(orchestrator.organizer_identifier, "identify_organizer", lambda candidate: _fixed_organizer())

    cfg = DiscoveryConfig(
        cities=["Bengaluru"],
        categories=["Technology"],
        events_per_run=5,  # Raw cap is small (5), but target_valid_events is 10!
        target_valid_events=10,
        daily_limit=200,
    )

    summary = orchestrator.run_discovery_agent(db_session, cfg)
    assert summary.new_events == 10
    assert summary.accepted_events == 10
    assert summary.duplicate_events >= 5
