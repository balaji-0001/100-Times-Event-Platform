"""Community Discovery Agent ("Agent 5") tests — validation, dedup, the
candidate extractor's real-metadata-only discipline, and the orchestrator's
idempotent-run behaviour. No AI needed anywhere in this agent, same as
Agent 1."""

import httpx
import pytest

from backend.models import AgentRun, DiscoveredCommunity
from backend.services.community_agent import candidate_extractor, discovery_dedup, orchestrator, validation
from backend.services.community_agent.types import CandidateSource, CommunityDiscoveryConfig, ExtractedCommunityCandidate
from backend.services.discovery_agent import web_search

NEXT_YEAR_SOURCE = CandidateSource(url="https://t.me/example", source_type="search_result")


def _candidate(**overrides) -> ExtractedCommunityCandidate:
    values = dict(
        platform="telegram", name="Pune Tech Talks", canonical_url="https://t.me/punetechtalks",
        description="A community for Pune's tech meetups.", member_count=500, extraction_confidence=70,
        primary_source=CandidateSource(url="https://t.me/punetechtalks", source_type="invite_page"),
        sources=[NEXT_YEAR_SOURCE],
    )
    values.update(overrides)
    return ExtractedCommunityCandidate(**values)


# --- validation ---------------------------------------------------------


def test_validate_community_discovered_when_complete():
    status, notes, confidence = validation.validate_community(_candidate(rules_text="Promotion of local events welcome."), confidence_threshold=60)
    assert status == "DISCOVERED"
    assert confidence >= 60
    assert notes == []


def test_validate_community_flags_missing_rules_text_even_when_otherwise_complete():
    status, notes, _ = validation.validate_community(_candidate(), confidence_threshold=60)
    assert status == "DISCOVERED"  # still just a note, not escalated to NEEDS_REVIEW on its own
    assert any("rules" in n.lower() for n in notes)


def test_validate_community_needs_review_without_description():
    status, notes, confidence = validation.validate_community(_candidate(description=None), confidence_threshold=60)
    assert status == "NEEDS_REVIEW"
    assert any("description" in n.lower() for n in notes)


def test_validate_community_needs_review_without_member_count():
    status, notes, confidence = validation.validate_community(_candidate(member_count=None), confidence_threshold=60)
    assert status == "NEEDS_REVIEW"
    assert any("member" in n.lower() or "subscriber" in n.lower() for n in notes)


def test_validate_community_never_auto_approves():
    """No confidence level, however high, should ever produce anything but
    DISCOVERED/NEEDS_REVIEW — approval is always an explicit human action."""
    status, _, _ = validation.validate_community(_candidate(extraction_confidence=100, rules_text="promotion welcome"), confidence_threshold=0)
    assert status == "DISCOVERED"
    assert status not in ("APPROVED", "VERIFIED")


# --- dedup ---------------------------------------------------------------


def test_find_duplicate_community_matches_on_canonical_url(db_session):
    existing = DiscoveredCommunity(platform="telegram", name="Pune Tech Talks", canonical_url="https://t.me/punetechtalks")
    db_session.add(existing)
    db_session.flush()

    found = discovery_dedup.find_duplicate_community(db_session, canonical_url="https://t.me/punetechtalks", name="different name", platform="telegram")
    assert found is existing


def test_find_duplicate_community_matches_on_normalized_name_same_platform(db_session):
    existing = DiscoveredCommunity(platform="discord", name="Pune Tech, Talks!", canonical_url="https://discord.gg/abc")
    db_session.add(existing)
    db_session.flush()

    found = discovery_dedup.find_duplicate_community(db_session, canonical_url="https://discord.gg/xyz", name="pune tech talks", platform="discord")
    assert found is existing
    # a same-named community on a DIFFERENT platform is not a duplicate
    assert discovery_dedup.find_duplicate_community(db_session, canonical_url="https://t.me/other", name="pune tech talks", platform="telegram") is None


def test_find_duplicate_community_none_when_nothing_matches(db_session):
    assert discovery_dedup.find_duplicate_community(db_session, canonical_url="https://t.me/brandnew", name="Brand New Group", platform="telegram") is None


# --- candidate extractor: classification + never-invented metadata -------


def test_classify_platform():
    assert candidate_extractor.classify_platform("https://t.me/somechannel") == "telegram"
    assert candidate_extractor.classify_platform("https://discord.gg/abcd1234") == "discord"
    assert candidate_extractor.classify_platform("https://discord.com/invite/abcd1234") == "discord"
    assert candidate_extractor.classify_platform("https://example.com/page") is None


def test_extract_telegram_reads_real_og_tags_and_member_count(monkeypatch):
    html = (
        '<html><head><meta property="og:title" content="Pune Tech Talks">'
        '<meta property="og:description" content="A community for Pune\'s tech meetups."></head>'
        '<body>738 subscribers</body></html>'
    )
    monkeypatch.setattr(candidate_extractor, "fetch", lambda url: html)

    result = candidate_extractor.extract_community(CandidateSource(url="https://t.me/punetechtalks", source_type="search_result"))

    assert result is not None
    assert result.platform == "telegram"
    assert result.name == "Pune Tech Talks"
    assert result.description == "A community for Pune's tech meetups."
    assert result.member_count == 738


def test_extract_telegram_member_count_is_none_when_not_shown(monkeypatch):
    html = '<html><head><meta property="og:title" content="Private Group"></head><body>Join our chat</body></html>'
    monkeypatch.setattr(candidate_extractor, "fetch", lambda url: html)

    result = candidate_extractor.extract_community(CandidateSource(url="https://t.me/privategroup", source_type="search_result"))

    assert result is not None
    assert result.member_count is None  # never guessed


def test_extract_telegram_returns_none_when_page_unreachable(monkeypatch):
    monkeypatch.setattr(candidate_extractor, "fetch", lambda url: None)
    assert candidate_extractor.extract_community(CandidateSource(url="https://t.me/doesnotexist", source_type="search_result")) is None


def test_extract_discord_reads_real_invite_api(monkeypatch):
    def fake_get(url, params=None, timeout=None, headers=None):
        assert "with_counts" in (params or {})
        return httpx.Response(200, json={
            "guild": {"name": "Pune Builders", "description": "Builders of Pune."},
            "approximate_member_count": 4200,
            "approximate_presence_count": 310,
        })
    monkeypatch.setattr(candidate_extractor.httpx, "get", fake_get)

    result = candidate_extractor.extract_community(CandidateSource(url="https://discord.gg/punebuilders", source_type="search_result"))

    assert result is not None
    assert result.platform == "discord"
    assert result.name == "Pune Builders"
    assert result.member_count == 4200


def test_extract_discord_invalid_invite_yields_no_candidate(monkeypatch):
    """A 404/410 (expired/revoked invite) must never produce a fabricated guild."""
    monkeypatch.setattr(candidate_extractor.httpx, "get", lambda *a, **k: httpx.Response(404))
    assert candidate_extractor.extract_community(CandidateSource(url="https://discord.gg/expiredcode", source_type="search_result")) is None


def test_extract_discord_network_error_yields_no_candidate(monkeypatch):
    def raise_error(*a, **k):
        raise httpx.ConnectError("boom")
    monkeypatch.setattr(candidate_extractor.httpx, "get", raise_error)
    assert candidate_extractor.extract_community(CandidateSource(url="https://discord.gg/whatever", source_type="search_result")) is None


def test_extract_community_unknown_platform_returns_none():
    assert candidate_extractor.extract_community(CandidateSource(url="https://example.com/nope", source_type="search_result")) is None


# --- orchestrator: idempotency + no AI anywhere --------------------------


def _config(**overrides) -> CommunityDiscoveryConfig:
    values = dict(cities=["Pune"], states=[], categories=["Finance"], search_depth=2, sources_per_query=2, daily_limit=50, confidence_threshold=60, seed_urls=[])
    values.update(overrides)
    return CommunityDiscoveryConfig(**values)


def test_run_discovers_and_persists_without_ai(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator.web_search, "search", lambda query, max_results: ["https://t.me/punefinancetalks"])
    monkeypatch.setattr(
        candidate_extractor, "fetch",
        lambda url: '<meta property="og:title" content="Pune Finance Talks"><meta property="og:description" content="Finance and fintech meetups.">500 subscribers',
    )

    summary = orchestrator.run_community_discovery_agent(db_session, _config())

    assert summary.new_communities == 1
    community = db_session.query(DiscoveredCommunity).one()
    assert community.name == "Pune Finance Talks"
    assert community.member_count == 500
    assert community.category == "Finance"  # categorized via the shared no-AI categorizer
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "community_discovery").one()
    assert run.status == "completed"
    assert run.error is None


def test_run_is_idempotent_on_rerun(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator.web_search, "search", lambda query, max_results: ["https://t.me/punefinancetalks"])
    monkeypatch.setattr(
        candidate_extractor, "fetch",
        lambda url: '<meta property="og:title" content="Pune Finance Talks"><meta property="og:description" content="Finance and fintech meetups.">500 subscribers',
    )

    orchestrator.run_community_discovery_agent(db_session, _config())
    second = orchestrator.run_community_discovery_agent(db_session, _config())

    assert second.new_communities == 0
    assert second.duplicate_communities == 1
    assert db_session.query(DiscoveredCommunity).count() == 1


def test_blocked_search_stops_but_keeps_what_was_found_and_reports_it(db_session, monkeypatch):
    calls = {"n": 0}

    def search(query, max_results):
        calls["n"] += 1
        if calls["n"] == 1:
            return ["https://t.me/punefinancetalks"]
        raise web_search.SearchBlocked("DuckDuckGo is asking for a captcha")

    monkeypatch.setattr(orchestrator.web_search, "search", search)
    monkeypatch.setattr(
        candidate_extractor, "fetch",
        lambda url: '<meta property="og:title" content="Pune Finance Talks"><meta property="og:description" content="Finance and fintech meetups.">500 subscribers',
    )

    summary = orchestrator.run_community_discovery_agent(db_session, _config(search_depth=5))

    assert summary.new_communities == 1
    run = db_session.query(AgentRun).filter(AgentRun.agent_type == "community_discovery").one()
    assert run.status == "completed"
    assert "captcha" in run.error


def test_run_respects_daily_limit(db_session, monkeypatch):
    monkeypatch.setattr(orchestrator.web_search, "search", lambda query, max_results: ["https://t.me/punefinancetalks", "https://t.me/otherchannel"])

    def fetch_fake(url):
        name = "Pune Finance Talks" if "punefinancetalks" in url else "Pune Banking Circle"
        return f'<meta property="og:title" content="{name}"><meta property="og:description" content="Finance investments desc">100 subscribers'
    monkeypatch.setattr(candidate_extractor, "fetch", fetch_fake)

    summary = orchestrator.run_community_discovery_agent(db_session, _config(daily_limit=1))

    assert summary.new_communities == 1
    assert db_session.query(DiscoveredCommunity).count() == 1
