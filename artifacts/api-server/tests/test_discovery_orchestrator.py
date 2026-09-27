"""Event Discovery Agent orchestrator — end-to-end idempotency test. Search
and extraction are monkeypatched to always return the SAME candidate event,
which exercises dedup both within one run (several queries surface the same
event) and across two separate runs (a re-run must not duplicate what the
first run already stored) — the restartable/idempotent requirement."""

from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer
from backend.services.discovery_agent import orchestrator
from backend.services.discovery_agent.types import CandidateSource, DiscoveryConfig, ExtractedEventCandidate, OrganizerCandidate
from tests.conftest import FakeAIClient


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
    monkeypatch.setattr(orchestrator, "get_ai_client", lambda: FakeAIClient(configured=True))
    monkeypatch.setattr(orchestrator.source_finder, "find_candidate_sources", lambda query, ai_client, max_results: [_fixed_candidate().primary_source])
    monkeypatch.setattr(orchestrator.page_extractor, "extract_event_from_page", lambda source, ai_client: _fixed_candidate())
    monkeypatch.setattr(orchestrator.organizer_identifier, "identify_organizer", lambda candidate, ai_client: _fixed_organizer())


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


def test_discovery_agent_fails_honestly_without_api_key(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator, "get_ai_client", lambda: FakeAIClient(configured=False))

    summary = orchestrator.run_discovery_agent(db_session, _config())

    assert summary.new_events == 0
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "discovery").one()
    assert run.status == "failed"
    assert "AI provider is not configured" in run.error
    assert db_session.query(DiscoveredEvent).count() == 0
