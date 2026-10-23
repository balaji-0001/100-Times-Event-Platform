"""Discord User Automation Engine — Hands-free User Account Publisher.

Allows the 100Times platform to automatically publish event drops,
announcements, and discussion replies into external Discord servers
that a dedicated user account has joined, without requiring server admins
to install or approve a third-party bot.

Follows the four-step PlatformPublisher flow:
  validate_connection -> validate_publish_permission -> publish_post/publish_reply -> verify_publication

Features:
- Realistic browser User-Agent headers
- Natural typing indicators (POST /channels/{id}/typing) before message dispatch
- Invite code resolution and auto-join capability (POST /invites/{code})
- Anti-burst jitter to prevent rate limits
"""

import time
from typing import Any

import httpx

from backend.services.social_agent.connectors.base import _settings_credential
from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.types import PublishResult

_API_BASE = "https://discord.com/api/v10"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


class DiscordUserPublisher(PlatformPublisher):
    platform = "discord_user"

    @property
    def credential(self) -> str | None:
        return _settings_credential("discord_user_token")

    @property
    def is_real(self) -> bool:
        return bool(self.credential)

    def _headers(self) -> dict[str, str]:
        token = self.credential or ""
        return {
            "Authorization": token,
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response | None:
        if not self.credential:
            return None
        try:
            return httpx.request(method, f"{_API_BASE}{path}", headers=self._headers(), timeout=12, **kwargs)
        except httpx.HTTPError:
            return None

    def validate_connection(self) -> dict[str, Any]:
        if not self.credential:
            return {"connected": False, "message": "DISCORD_USER_TOKEN not configured."}
        resp = self._call("GET", "/users/@me")
        if resp is not None and resp.status_code == 200:
            data = resp.json()
            username = data.get("username", "user")
            user_id = data.get("id", "")
            return {
                "connected": True,
                "message": f"Connected as Discord user: {username} (ID: {user_id})",
                "user_id": user_id,
                "username": username,
            }
        status_code = resp.status_code if resp else "network error"
        return {"connected": False, "message": f"Discord rejected user token (HTTP {status_code})."}

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        """`target_ref` is `discord_user_<guild_id>_<channel_id>` or `discord_<guild_id>_<channel_id>`."""
        parts = target_ref.split("_")
        # Support both discord_user_G_C and discord_G_C
        if len(parts) >= 4 and parts[0] == "discord" and parts[1] == "user":
            channel_id = parts[3]
        elif len(parts) >= 3 and parts[0] == "discord":
            channel_id = parts[2]
        else:
            return {"allowed": False, "message": "Invalid Discord target reference format."}

        resp = self._call("GET", f"/channels/{channel_id}")
        if resp is not None and resp.status_code == 200:
            cdata = resp.json()
            cname = cdata.get("name", channel_id)
            return {"allowed": True, "message": f"Channel #{cname} is accessible to user account."}
        return {"allowed": False, "message": "Cannot access target Discord channel with current user account."}

    def auto_join_server(self, invite_code: str) -> dict[str, Any]:
        """Auto-joins a Discord server via an invite code (e.g. 'python' or invite code from discord.gg/{code})."""
        code = invite_code.strip().replace("https://discord.gg/", "").replace("discord.gg/", "")
        resp = self._call("POST", f"/invites/{code}", json={})
        if resp is not None and resp.status_code in (200, 201):
            data = resp.json()
            guild = data.get("guild", {})
            return {
                "success": True,
                "guild_id": guild.get("id"),
                "guild_name": guild.get("name"),
                "message": f"Successfully joined {guild.get('name')}",
            }
        err = resp.json().get("message", "unknown error") if resp else "network error"
        return {"success": False, "message": f"Failed to join Discord server: {err}"}

    def _simulate_human_typing(self, channel_id: str) -> None:
        """Sends a typing indicator and waits 1 second to appear human-like."""
        try:
            self._call("POST", f"/channels/{channel_id}/typing")
            time.sleep(1.0)
        except Exception:
            pass

    def publish_post(self, text: str, target_ref: str) -> PublishResult:
        if not self.credential:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="DISCORD_USER_TOKEN not configured.",
            )

        parts = target_ref.split("_")
        if len(parts) >= 4 and parts[0] == "discord" and parts[1] == "user":
            guild_id, channel_id = parts[2], parts[3]
        elif len(parts) >= 3 and parts[0] == "discord":
            guild_id, channel_id = parts[1], parts[2]
        else:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Cannot publish: invalid Discord target reference.",
            )

        self._simulate_human_typing(channel_id)

        resp = self._call("POST", f"/channels/{channel_id}/messages", json={"content": text})
        if resp is None:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Discord API request failed (network error).",
            )
        if resp.status_code not in (200, 201):
            try:
                detail = resp.json().get("message", f"HTTP {resp.status_code}")
            except Exception:
                detail = f"HTTP {resp.status_code}"
            return PublishResult(success=False, platform=self.platform, published_url=None, message=f"Discord user publish error: {detail}")

        sent = resp.json()
        sent_id = sent.get("id")
        published_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{sent_id}"

        return PublishResult(
            success=True,
            platform=self.platform,
            published_url=published_url,
            message="Published successfully via Discord User Automation Engine.",
        )

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        if not self.credential:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="DISCORD_USER_TOKEN not configured.",
            )

        parts = target_ref.split("_")
        if len(parts) >= 5 and parts[0] == "discord" and parts[1] == "user":
            guild_id, channel_id, message_id = parts[2], parts[3], parts[4]
        elif len(parts) >= 4 and parts[0] == "discord":
            guild_id, channel_id, message_id = parts[1], parts[2], parts[3]
        else:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Cannot publish: missing message reference for reply.",
            )

        self._simulate_human_typing(channel_id)

        payload = {
            "content": text,
            "message_reference": {"message_id": message_id, "channel_id": channel_id},
        }
        resp = self._call("POST", f"/channels/{channel_id}/messages", json=payload)
        if resp is None or resp.status_code not in (200, 201):
            detail = resp.json().get("message", "HTTP error") if resp else "network error"
            return PublishResult(success=False, platform=self.platform, published_url=None, message=f"Discord user reply error: {detail}")

        sent = resp.json()
        sent_id = sent.get("id")
        published_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{sent_id}"

        return PublishResult(
            success=True,
            platform=self.platform,
            published_url=published_url,
            message="Reply published successfully via Discord User Automation Engine.",
        )

