"""Unit tests for Discord User Automation Engine and Telegram MTProto User Client."""

from unittest.mock import MagicMock, patch

import pytest

from backend.services.social_agent.publishers.discord_user import DiscordUserPublisher
from backend.services.social_agent.publishers.telegram_user import TelegramUserPublisher
from backend.services.social_agent.publishers import get_publisher


def test_publisher_registration():
    discord_user_pub = get_publisher("discord_user")
    assert isinstance(discord_user_pub, DiscordUserPublisher)

    telegram_user_pub = get_publisher("telegram_user")
    assert isinstance(telegram_user_pub, TelegramUserPublisher)


def test_discord_user_connection_validation():
    pub = DiscordUserPublisher()

    # Missing token
    with patch.object(DiscordUserPublisher, "credential", None):
        res = pub.validate_connection()
        assert res["connected"] is False
        assert "not configured" in res["message"]

    # Valid token
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "123456789", "username": "test_automator"}

    with patch.object(DiscordUserPublisher, "credential", "mock_user_token"):
        with patch.object(pub, "_call", return_value=mock_resp):
            res = pub.validate_connection()
            assert res["connected"] is True
            assert "test_automator" in res["message"]
            assert res["user_id"] == "123456789"


def test_discord_user_publish_post():
    pub = DiscordUserPublisher()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "987654321"}

    with patch.object(DiscordUserPublisher, "credential", "mock_user_token"):
        with patch.object(pub, "_call", return_value=mock_resp):
            with patch.object(pub, "_simulate_human_typing"):
                res = pub.publish_post("Exciting Tech Event!", "discord_user_11111_22222")
                assert res.success is True
                assert res.platform == "discord_user"
                assert res.published_url == "https://discord.com/channels/11111/22222/987654321"


def test_discord_user_auto_join_server():
    pub = DiscordUserPublisher()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"guild": {"id": "55555", "name": "AI Builders Community"}}

    with patch.object(DiscordUserPublisher, "credential", "mock_user_token"):
        with patch.object(pub, "_call", return_value=mock_resp):
            res = pub.auto_join_server("https://discord.gg/python-devs")
            assert res["success"] is True
            assert res["guild_id"] == "55555"
            assert "AI Builders Community" in res["message"]


def test_telegram_user_connection_validation():
    pub = TelegramUserPublisher()

    # Missing credentials
    with patch.object(TelegramUserPublisher, "is_real", False):
        res = pub.validate_connection()
        assert res["connected"] is False
        assert "missing credentials" in res["message"]

    # Connected
    mock_me = MagicMock()
    mock_me.username = "event_ambassador"
    mock_me.first_name = "Alex"
    mock_me.phone = "1234567890"
    mock_me.id = 99999

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get_me.return_value = mock_me

    with patch.object(TelegramUserPublisher, "is_real", True):
        with patch.object(pub, "_get_client", return_value=mock_client):
            res = pub.validate_connection()
            assert res["connected"] is True
            assert "event_ambassador" in res["message"]
            assert res["phone"] == "1234567890"


def test_telegram_user_publish_post():
    pub = TelegramUserPublisher()
    mock_sent = MagicMock()
    mock_sent.id = 777

    mock_entity = MagicMock()
    mock_entity.username = "bangalore_startups"

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get_entity.return_value = mock_entity
    mock_client.send_message.return_value = mock_sent

    with patch.object(TelegramUserPublisher, "is_real", True):
        with patch.object(pub, "_get_client", return_value=mock_client):
            res = pub.publish_post("Join us at Pharma Summit 2026", "telegram_user_bangalore_startups")
            assert res.success is True
            assert res.platform == "telegram_user"
            assert res.published_url == "https://t.me/bangalore_startups/777"

