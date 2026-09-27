from datetime import datetime, timezone

from backend.models import Discussion, PlatformRateLimit
from backend.services.social_agent.connectors.reddit import RedditConnector
from backend.services.social_agent.unified_processor import UnifiedSignalProcessor


def test_rate_limit_skips_when_daily_cap_reached(db_session, seeded_catalog):
    db_session.add(PlatformRateLimit(platform="reddit", daily_limit=1, updated_at=datetime.now(timezone.utc)))
    db_session.add(
        Discussion(
            community_id=seeded_catalog["community"].id,
            platform="reddit",
            external_id="reddit_existing_1",
            url="https://reddit.com",
            title="Existing",
            content="Existing",
            intent_classification="HIGH_INTENT",
            intent_confidence=0.9,
            status="processed",
            pipeline_status="PENDING_APPROVAL",
        )
    )
    db_session.commit()

    result = UnifiedSignalProcessor.collect([RedditConnector()], db_session)

    assert result.signals == []
    assert any("daily rate limit reached" in note for note in result.skip_notes)


def test_rate_limit_allows_signals_under_the_cap(db_session, seeded_catalog):
    db_session.add(PlatformRateLimit(platform="reddit", daily_limit=25, updated_at=datetime.now(timezone.utc)))
    db_session.commit()

    result = UnifiedSignalProcessor.collect([RedditConnector()], db_session)

    assert len(result.signals) > 0
    assert result.skip_notes == []
