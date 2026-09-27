"""Connector and publisher failure handling — network errors and platform
API error responses must degrade gracefully, never crash the caller, and
never be reported as success."""

import httpx

from backend.services.social_agent.connectors.telegram import TelegramConnector
from backend.services.social_agent.publishers.telegram import TelegramPublisher


def _fake_live_connector(monkeypatch) -> TelegramConnector:
    connector = TelegramConnector()
    monkeypatch.setattr(TelegramConnector, "credential", property(lambda self: "fake-token"))
    return connector


def _fake_live_publisher(monkeypatch) -> TelegramPublisher:
    publisher = TelegramPublisher()
    monkeypatch.setattr(TelegramPublisher, "credential", property(lambda self: "fake-token"))
    return publisher


def test_connector_discovery_survives_network_error(monkeypatch):
    connector = _fake_live_connector(monkeypatch)

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", _raise)

    signals = connector.discover_signals()
    assert signals == []  # degrades to empty, does not raise


def test_connector_discovery_survives_malformed_response(monkeypatch):
    connector = _fake_live_connector(monkeypatch)

    class FakeResponse:
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    signals = connector.discover_signals()
    assert signals == []


def test_publisher_reports_failure_on_network_error(monkeypatch):
    publisher = _fake_live_publisher(monkeypatch)

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", _raise)

    result = publisher.publish_reply("hello", "telegram_123_456")
    assert result.success is False
    assert result.published_url is None
    assert "failed" in result.message.lower()


def test_publisher_reports_failure_on_platform_error_response(monkeypatch):
    publisher = _fake_live_publisher(monkeypatch)

    class FakeResponse:
        def json(self):
            return {"ok": False, "description": "Bad Request: chat not found"}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    result = publisher.publish_reply("hello", "telegram_123_456")
    assert result.success is False
    assert result.published_url is None
    assert "chat not found" in result.message


def test_publisher_never_claims_success_without_ok_true(monkeypatch):
    publisher = _fake_live_publisher(monkeypatch)

    class FakeResponse:
        def json(self):
            # No "ok" key at all — malformed/unexpected shape.
            return {"result": {"message_id": 1}}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    result = publisher.publish_reply("hello", "telegram_123_456")
    assert result.success is False


def test_stub_publisher_marks_approval_required_platforms_distinctly():
    from backend.services.social_agent.publishers import get_publisher

    reddit_publisher = get_publisher("reddit")
    linkedin_publisher = get_publisher("linkedin")

    reddit_result = reddit_publisher.publish_reply("hi", "reddit_abc")
    linkedin_result = linkedin_publisher.publish_reply("hi", "linkedin_abc")

    assert reddit_result.success is False
    assert "approval" in reddit_result.message.lower()
    assert linkedin_result.success is False
    assert "manual publishing required" in linkedin_result.message.lower()


def test_discord_publisher_rejects_malformed_target_ref():
    """Discord has a real publisher (see `publishers/discord.py`) — unlike
    the approval-gated platforms above, it fails honestly on bad input
    rather than reporting NOT_CONFIGURED/APPROVAL_REQUIRED."""
    from backend.services.social_agent.publishers import get_publisher

    discord_publisher = get_publisher("discord")
    result = discord_publisher.publish_reply("hi", "discord_abc")

    assert result.success is False
    assert "guild/channel/message reference" in result.message.lower()
