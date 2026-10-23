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


# --- Telegram: honest published_url fallback for chats with no public link format ---


def test_publish_post_to_public_channel_returns_message_specific_link(monkeypatch):
    publisher = _fake_live_publisher(monkeypatch)

    class FakeResponse:
        def json(self):
            return {"ok": True, "result": {"message_id": 42, "chat": {"id": -1001, "type": "channel", "username": "mychannel"}}}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    result = publisher.publish_post("hello", "telegram_-1001")

    assert result.success is True
    assert result.published_url == "https://t.me/mychannel/42"


def test_publish_post_to_supergroup_returns_message_specific_link(monkeypatch):
    publisher = _fake_live_publisher(monkeypatch)

    class FakeResponse:
        def json(self):
            return {"ok": True, "result": {"message_id": 7, "chat": {"id": -1001234567890, "type": "supergroup"}}}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    result = publisher.publish_post("hello", "telegram_-1001234567890")

    assert result.success is True
    assert result.published_url == "https://t.me/c/1234567890/7"


def test_publish_post_to_private_chat_falls_back_to_bot_conversation_link(monkeypatch):
    """A private 1:1 chat has no per-message public URL — Telegram simply
    doesn't support one — so the honest next-best thing is a real link to
    the actual conversation (the bot's own t.me link), not a blank field."""
    publisher = _fake_live_publisher(monkeypatch)
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        class R:
            def json(self):
                if "getMe" in url:
                    return {"ok": True, "result": {"username": "HundredTimesAgentBot"}}
                return {"ok": True, "result": {"message_id": 3, "chat": {"id": 1327001890, "type": "private", "first_name": "Balaji"}}}
        return R()

    monkeypatch.setattr(httpx, "post", fake_post)

    result = publisher.publish_post("hello", "telegram_1327001890")

    assert result.success is True
    assert result.published_url == "https://t.me/HundredTimesAgentBot"


def test_publish_post_to_basic_group_with_no_username_has_no_link(monkeypatch):
    """A non-super, unlinked basic group has no public link format at all —
    this must stay honestly `None`, never a guessed/fabricated URL."""
    publisher = _fake_live_publisher(monkeypatch)

    class FakeResponse:
        def json(self):
            return {"ok": True, "result": {"message_id": 5, "chat": {"id": -555, "type": "group"}}}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    result = publisher.publish_post("hello", "telegram_-555")

    assert result.success is True
    assert result.published_url is None
