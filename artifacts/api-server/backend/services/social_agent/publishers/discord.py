"""Real Discord publisher.

Follows the same four-step flow as the Telegram publisher:
validate_connection (GET /users/@me) -> validate_publish_permission
(best-effort: can we still see the target channel?) -> publish_reply
(POST /channels/{id}/messages, threaded via message_reference) ->
verify_publication (trusts the API's own success response).

`validate_publish_permission` is deliberately labeled best-effort: computing
a Discord bot's exact effective permissions in a channel requires resolving
guild role permissions plus per-channel overwrites, which this does not
attempt. Instead it checks that the channel is still visible to the bot at
all (`GET /channels/{id}` succeeding) — a real, if partial, signal; it never
claims a stronger guarantee than that.
"""

import time
from typing import Any

import httpx

from backend.services.social_agent.connectors.base import _settings_credential
from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.types import PublishResult

_API_BASE = "https://discord.com/api/v10"


class DiscordPublisher(PlatformPublisher):
    platform = "discord"

    @property
    def credential(self) -> str | None:
        return _settings_credential("discord_bot_token")

    @property
    def is_real(self) -> bool:
        return bool(self.credential)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bot {self.credential}"}

    def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response | None:
        token = self.credential
        if not token:
            return None
        try:
            return httpx.request(method, f"{_API_BASE}{path}", headers=self._headers(), timeout=10, **kwargs)
        except httpx.HTTPError:
            return None

    def validate_connection(self) -> dict[str, Any]:
        if not self.credential:
            return {"connected": False, "message": "DISCORD_BOT_TOKEN not configured."}
        resp = self._call("GET", "/users/@me")
        if resp is not None and resp.status_code == 200:
            data = resp.json()
            return {"connected": True, "message": f"Connected as {data.get('username', 'bot')}#{data.get('discriminator', '0')}"}
        return {"connected": False, "message": "Discord rejected the configured bot token."}

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        """`target_ref` is "discord_<guild_id>_<channel_id>" for a
        standalone post or "discord_<guild_id>_<channel_id>_<message_id>"
        for a reply — only the channel id matters here, so both accepted."""
        if target_ref.startswith("discord_user_") or (not self.credential and _settings_credential("discord_user_token")):
            from backend.services.social_agent.publishers.discord_user import DiscordUserPublisher
            return DiscordUserPublisher().validate_publish_permission(target_ref)

        parts = target_ref.split("_")
        if len(parts) < 3 or parts[0] != "discord":
            return {"allowed": False, "message": "Missing guild/channel reference — cannot verify permission."}
        channel_id = parts[2]

        resp = self._call("GET", f"/channels/{channel_id}")
        if resp is not None and resp.status_code == 200:
            return {"allowed": True, "message": "Channel is visible to the bot (best-effort check — not a full permission resolution)."}
        if _settings_credential("discord_user_token"):
            from backend.services.social_agent.publishers.discord_user import DiscordUserPublisher
            return DiscordUserPublisher().validate_publish_permission(target_ref)
        return {"allowed": False, "message": "Could not confirm the bot can still see the target channel."}

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        if target_ref.startswith("discord_user_") or (not self.credential and _settings_credential("discord_user_token")):
            from backend.services.social_agent.publishers.discord_user import DiscordUserPublisher
            return DiscordUserPublisher().publish_reply(text, target_ref)

        if not self.credential:
            return PublishResult(success=False, platform=self.platform, published_url=None, message="DISCORD_BOT_TOKEN not configured.")

        parts = target_ref.split("_")
        if len(parts) < 4 or parts[0] != "discord":
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Cannot publish: missing the original guild/channel/message reference.",
            )
        guild_id, channel_id, message_id = parts[1], parts[2], parts[3]

        resp = self._call(
            "POST", f"/channels/{channel_id}/messages",
            json={"content": text, "message_reference": {"message_id": message_id, "channel_id": channel_id}},
        )
        if resp is None:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Discord API request failed (network error or invalid response).",
            )
        if resp.status_code not in (200, 201):
            try:
                detail = resp.json().get("message", "unknown error")
            except ValueError:
                detail = f"HTTP {resp.status_code}"
            return PublishResult(success=False, platform=self.platform, published_url=None, message=f"Discord API error: {detail}")

        sent = resp.json()
        sent_message_id = sent.get("id")
        published_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{sent_message_id}"

        return PublishResult(
            success=True, platform=self.platform, published_url=published_url,
            message="Published successfully via the Discord Bot API.",
        )

    def publish_post(self, text: str, target_ref: str, **kwargs: Any) -> PublishResult:
        """Same as `publish_reply` but with no `message_reference` — a
        standalone announcement, for Agent 4's community-promotion
        extension. `target_ref` is "discord_<guild_id>_<channel_id>" (no
        message id, since there's nothing to reply to)."""
        is_dry_run = kwargs.get("is_dry_run", False)
        if is_dry_run:
            return PublishResult(
                success=True,
                platform=self.platform,
                published_url="https://discord.com/channels/dry_run_guild/dry_run_channel/12345",
                message="[DRY-RUN] Discord server announcement simulated successfully. Bot API was not called.",
                post_id=f"dry_run_discord_{int(time.time())}",
            )

        # Check if a webhook URL is provided directly
        webhook_url = kwargs.get("webhook_url") or _settings_credential("discord_promotion_webhook_url")
        if webhook_url and (not target_ref or not target_ref.startswith("discord_")):
            try:
                w_resp = httpx.post(webhook_url, json={"content": text}, timeout=10)
                if w_resp.status_code in (200, 204):
                    post_id = f"discord_wh_{int(time.time())}"
                    return PublishResult(
                        success=True,
                        platform=self.platform,
                        published_url="https://discord.com/channels/webhook",
                        message="Published successfully via Discord Webhook.",
                        post_id=post_id,
                    )
            except httpx.HTTPError as exc:
                return PublishResult(success=False, platform=self.platform, published_url=None, message=f"Discord webhook error: {str(exc)}")

        if target_ref.startswith("discord_user_") or (not self.credential and _settings_credential("discord_user_token")):
            from backend.services.social_agent.publishers.discord_user import DiscordUserPublisher
            return DiscordUserPublisher().publish_post(text, target_ref)

        if not self.credential:
            return PublishResult(success=False, platform=self.platform, published_url=None, message="DISCORD_BOT_TOKEN not configured.")

        parts = target_ref.split("_")
        if len(parts) < 3 or parts[0] != "discord":
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Cannot publish: missing the target guild/channel reference.",
            )
        guild_id, channel_id = parts[1], parts[2]

        resp = self._call("POST", f"/channels/{channel_id}/messages", json={"content": text})
        if resp is None:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Discord API request failed (network error or invalid response).",
            )
        if resp.status_code not in (200, 201):
            try:
                detail = resp.json().get("message", "unknown error")
            except ValueError:
                detail = f"HTTP {resp.status_code}"
            return PublishResult(success=False, platform=self.platform, published_url=None, message=f"Discord API error: {detail}")

        sent = resp.json()
        sent_message_id = sent.get("id")
        published_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{sent_message_id}"

        return PublishResult(
            success=True, platform=self.platform, published_url=published_url,
            message="Published successfully via the Discord Bot API.",
        )
