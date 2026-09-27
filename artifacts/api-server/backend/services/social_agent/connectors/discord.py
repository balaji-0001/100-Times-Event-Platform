"""Discord connector — discovery/read side only (see `publishers/discord.py`
for the real publish integration).

Mock mode (no DISCORD_BOT_TOKEN): returns curated sample signals.

Live mode (DISCORD_BOT_TOKEN set): uses the real Discord Bot REST API —
`GET /users/@me/guilds` to list servers the bot has been added to, then
`GET /guilds/{id}/channels` per server for its text channels, then
`GET /channels/{id}/messages` per channel for recent messages. This can only
ever see servers/channels the bot has actually been invited into with
`View Channel` + `Read Message History` permissions (granted via the OAuth2
bot-invite flow) — it does not and cannot browse arbitrary public Discord
servers the bot hasn't joined.

The `Message Content Intent` must be enabled for the bot in the Discord
Developer Portal, or message text will come back empty even for channels
the bot can otherwise see.

No local cursor/offset is stored between calls (Discord's REST API has no
Telegram-style server-side acknowledgment mechanism) — each call re-fetches
the most recent messages per channel; the pipeline's own `Discussion.
external_id` dedup (see `pipeline/normalize.py`) already makes re-seeing the
same message harmless, so this keeps state management simple.
"""

from typing import Any

import httpx

from backend.services.social_agent.connectors.base import PlatformConnector, _settings_credential
from backend.services.social_agent.types import Signal

_API_BASE = "https://discord.com/api/v10"
_GUILD_TEXT_CHANNEL = 0
_MAX_GUILDS = 10
_MAX_CHANNELS_PER_GUILD = 8
_MESSAGES_PER_CHANNEL = 20


class DiscordConnector(PlatformConnector):
    platform = "discord"
    description = "Permitted channels in authorized event-discovery Discord servers."
    requires_approval = False

    @property
    def credential(self) -> str | None:
        return _settings_credential("discord_bot_token")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bot {self.credential}"}

    def _get(self, path: str, **params: Any) -> Any:
        token = self.credential
        if not token:
            return None
        try:
            response = httpx.get(f"{_API_BASE}{path}", headers=self._headers(), params=params, timeout=10)
            if response.status_code != 200:
                return None
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    def validate_connection(self) -> dict[str, Any]:
        if not self.is_live:
            return {"connected": False, "checked": False, "message": "DISCORD_BOT_TOKEN not configured."}
        me = self._get("/users/@me")
        if me and me.get("id"):
            return {"connected": True, "checked": True, "message": f"Connected as {me.get('username', 'bot')}#{me.get('discriminator', '0')}"}
        return {"connected": False, "checked": True, "message": "Discord rejected the configured bot token."}

    def discover_signals(self) -> list[Signal]:
        if not self.is_live:
            return self._mock_signals()

        guilds = self._get("/users/@me/guilds") or []
        signals: list[Signal] = []

        for guild in guilds[:_MAX_GUILDS]:
            guild_id = guild.get("id")
            guild_name = guild.get("name", "Discord Server")
            if not guild_id:
                continue

            channels = self._get(f"/guilds/{guild_id}/channels") or []
            text_channels = [c for c in channels if c.get("type") == _GUILD_TEXT_CHANNEL][:_MAX_CHANNELS_PER_GUILD]

            for channel in text_channels:
                channel_id = channel.get("id")
                channel_name = channel.get("name", "general")
                if not channel_id:
                    continue

                messages = self._get(f"/channels/{channel_id}/messages", limit=_MESSAGES_PER_CHANNEL)
                if not messages:
                    continue

                for message in messages:
                    author = message.get("author") or {}
                    if author.get("bot"):
                        continue
                    text = (message.get("content") or "").strip()
                    message_id = message.get("id")
                    if not text or not message_id:
                        continue

                    signals.append(
                        Signal(
                            platform="discord",
                            community_name=f"{guild_name} #{channel_name}",
                            title=text[:120],
                            content=text,
                            author=author.get("username") or "discord_user",
                            url=f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
                            external_id=f"discord_{guild_id}_{channel_id}_{message_id}",
                        )
                    )

        return signals

    def _mock_signals(self) -> list[Signal]:
        return [
            Signal(
                platform="discord",
                community_name="Bengaluru Builders Discord",
                title="Are there any AI hackathons happening in Bengaluru this month?",
                content="Our study group wants to join hackathons or workshops focused on machine learning and LLM systems around Bengaluru. Does anyone know any upcoming ones with good mentors?",
                author="blr_study_grp",
                url="https://discord.com/channels/bengaluru-builders/events-discovery",
                external_id="discord_mock_blr_hackathon_1",
            ),
            Signal(
                platform="discord",
                community_name="NCR Tech Discord",
                title="Where can I find startup networking events in New Delhi?",
                content="New to Delhi and want startup networking events for founders and early engineers. Also open to any developer events or hackathons nearby.",
                author="delhi_newcomer",
                url="https://discord.com/channels/ncr-tech/general",
                external_id="discord_mock_delhi_networking_1",
            ),
        ]
