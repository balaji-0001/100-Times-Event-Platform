"""Event Discovery Agent — pre-insert dedup tests. These guard the
idempotency requirement: a re-run (or a run resumed after a crash) must
never create duplicate `DiscoveredEvent`/`DiscoveredOrganizer` rows."""

from datetime import datetime, timezone

from backend.models import DiscoveredEvent, DiscoveredOrganizer
from backend.services.discovery_agent import discovery_dedup


def test_normalize_name_ignores_case_and_punctuation():
    assert discovery_dedup.normalize_name("Pune Tech, Summit!") == "pune tech summit"
    assert discovery_dedup.normalize_name("  ") == ""
    assert discovery_dedup.normalize_name(None) == ""


def test_extract_domain_strips_www_and_scheme():
    assert discovery_dedup.extract_domain("https://www.example.test/page") == "example.test"
    assert discovery_dedup.extract_domain("example.test") == "example.test"
    assert discovery_dedup.extract_domain(None) is None


def test_find_duplicate_event_matches_on_exact_url(db_session):
    existing = DiscoveredEvent(
        name="Pune Tech Summit", url="https://example.test/pune-tech-summit",
        discovered_by="web_discovery_agent", created_at=datetime.now(timezone.utc),
    )
    db_session.add(existing)
    db_session.flush()

    found = discovery_dedup.find_duplicate_event(db_session, name="A Different Name", url="https://example.test/pune-tech-summit")
    assert found is not None
    assert found.id == existing.id


def test_find_duplicate_event_matches_on_normalized_name_and_city(db_session):
    existing = DiscoveredEvent(
        name="Pune Tech Summit 2026", city="Pune", date="2026-11-01",
        discovered_by="web_discovery_agent", created_at=datetime.now(timezone.utc),
    )
    db_session.add(existing)
    db_session.flush()

    found = discovery_dedup.find_duplicate_event(db_session, name="pune tech summit 2026!!", city="Pune", date=None)
    assert found is not None
    assert found.id == existing.id


def test_find_duplicate_event_does_not_match_same_name_different_city_and_date(db_session):
    existing = DiscoveredEvent(
        name="Startup Meetup", city="Mumbai", date="2026-05-01",
        discovered_by="web_discovery_agent", created_at=datetime.now(timezone.utc),
    )
    db_session.add(existing)
    db_session.flush()

    found = discovery_dedup.find_duplicate_event(db_session, name="Startup Meetup", city="Delhi", date="2026-06-01")
    assert found is None


def test_find_duplicate_organizer_matches_on_exact_email(db_session):
    existing = DiscoveredOrganizer(name="Pune Riders", email="hello@puneriders.test", created_at=datetime.now(timezone.utc))
    db_session.add(existing)
    db_session.flush()

    found = discovery_dedup.find_duplicate_organizer(db_session, name="Different Name", email="hello@puneriders.test")
    assert found is not None
    assert found.id == existing.id


def test_find_duplicate_organizer_matches_on_website_domain(db_session):
    existing = DiscoveredOrganizer(name="Pune Riders", website="https://www.puneriders.test/about", created_at=datetime.now(timezone.utc))
    db_session.add(existing)
    db_session.flush()

    found = discovery_dedup.find_duplicate_organizer(db_session, name="Different Name", website="https://puneriders.test")
    assert found is not None
    assert found.id == existing.id


def test_find_duplicate_organizer_returns_none_when_nothing_matches(db_session):
    db_session.add(DiscoveredOrganizer(name="Pune Riders", email="hello@puneriders.test", created_at=datetime.now(timezone.utc)))
    db_session.flush()

    found = discovery_dedup.find_duplicate_organizer(db_session, name="Bangalore Cyclists", email="team@blrcyclists.test")
    assert found is None
