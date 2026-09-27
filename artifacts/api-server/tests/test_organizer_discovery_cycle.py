"""Tests for the Organizer Agent's fully-automatic entry point: no manually
typed discussion required. Covers the seed-cap/aggregation wiring in
`SocialAgentOrchestrator.run_organizer_discovery_cycle`, and the dedup guard
in `discovery_pipeline.run_discovery_pipeline` that keeps a scheduled tick
from re-processing (and re-billing AI calls for) the same fixed signal every
time it fires."""

from datetime import datetime, timezone

from backend.models import PlatformRateLimit
from backend.services.social_agent import orchestrator as orchestrator_module
from backend.services.social_agent.pipeline import discovery_pipeline, intent_extraction
from tests.conftest import FakeAIClient


def test_organizer_discovery_cycle_respects_seed_cap_and_aggregates(db_session, monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "organizer_discovery_max_seeds_per_cycle", 1)
    db_session.add(PlatformRateLimit(platform="reddit", daily_limit=25, updated_at=datetime.now(timezone.utc)))
    db_session.commit()

    calls = []

    def _fake_run_discovery_pipeline(db, platform, community_name, title, content, url=""):
        calls.append((platform, community_name, title))
        return {
            "opportunitiesCreated": [{"opportunityId": 1, "kind": "NEW_EVENT_CANDIDATE"}],
            "candidates": [{"organizerOutreach": {"outcome": "DRAFTED_PENDING_APPROVAL"}}],
            "message": "ok",
        }

    monkeypatch.setattr(orchestrator_module.discovery_pipeline, "run_discovery_pipeline", _fake_run_discovery_pipeline)

    result = orchestrator_module.SocialAgentOrchestrator.run_organizer_discovery_cycle(db_session, platforms=["reddit"])

    # RedditConnector's mock data has 2 fixed signals — the cap of 1 must be respected.
    assert len(calls) == 1
    assert result["seedsProcessed"] == 1
    assert result["opportunitiesCreated"] == 1
    assert result["outreachDrafted"] == 1


def test_organizer_discovery_cycle_never_processes_more_than_available_signals(db_session, monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "organizer_discovery_max_seeds_per_cycle", 100)
    db_session.add(PlatformRateLimit(platform="reddit", daily_limit=25, updated_at=datetime.now(timezone.utc)))
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        orchestrator_module.discovery_pipeline, "run_discovery_pipeline",
        lambda db, platform, community_name, title, content, url="": calls.append(1) or {"opportunitiesCreated": [], "candidates": [], "message": "ok"},
    )

    from backend.services.social_agent.connectors.reddit import RedditConnector

    result = orchestrator_module.SocialAgentOrchestrator.run_organizer_discovery_cycle(db_session, platforms=["reddit"])

    assert result["seedsProcessed"] == len(calls)
    # A huge cap must still be bounded by however many signals the connector actually returned.
    assert result["seedsProcessed"] == len(RedditConnector().discover_signals())


def test_discovery_pipeline_skips_reprocessing_the_same_seed(db_session, monkeypatch):
    """Without this guard, a scheduled tick would re-run the whole AI-heavy
    search+extraction on the same fixed signal every time it fires."""
    monkeypatch.setattr(intent_extraction, "get_ai_client", lambda: FakeAIClient(configured=False))

    kwargs = dict(
        platform="reddit", community_name="r/test", title="Any pottery workshops nearby?",
        content="Looking for pottery workshops in my city.", url="https://reddit.com/r/test/abc123",
    )

    first = discovery_pipeline.run_discovery_pipeline(db_session, **kwargs)
    assert "already processed" not in first["message"].lower()

    second = discovery_pipeline.run_discovery_pipeline(db_session, **kwargs)
    assert "already processed" in second["message"].lower()
