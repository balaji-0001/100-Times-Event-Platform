"""Telegram connector — discovery/read side only (see `publishers/telegram.py`
for the real publish integration).

Not connected (no TELEGRAM_BOT_TOKEN): returns no signals.

Live mode (TELEGRAM_BOT_TOKEN set): long-polls `getUpdates` for real
messages in chats/groups the bot has been added to (the group owner must
add the bot and either disable privacy mode via @BotFather's /setprivacy or
make the bot an admin — otherwise Telegram only forwards commands/mentions,
not full group chat, to the bot).

The bot token is read only from `TELEGRAM_BOT_TOKEN` (via Settings) and is
never logged, hardcoded, or included in any response body. No approval gate
— Telegram bots need only a token from @BotFather.
"""

from typing import Any

import httpx

from backend.services.social_agent.connectors.base import PlatformConnector, _settings_credential
from backend.services.social_agent.types import Signal

_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramConnector(PlatformConnector):
    platform = "telegram"
    description = "Permitted local-event Telegram channels and groups."
    requires_approval = False

    @property
    def credential(self) -> str | None:
        return _settings_credential("telegram_bot_token")

    def _call(self, method: str, **params: Any) -> dict | None:
        token = self.credential
        if not token:
            return None
        url = _API_BASE.format(token=token, method=method)
        try:
            response = httpx.post(url, json=params, timeout=10)
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    def validate_connection(self) -> dict[str, Any]:
        if not self.is_live:
            return {"connected": False, "checked": False, "message": "TELEGRAM_BOT_TOKEN not configured."}
        data = self._call("getMe")
        if data and data.get("ok"):
            return {"connected": True, "checked": True, "message": f"Connected as @{data['result'].get('username')}"}
        return {"connected": False, "checked": True, "message": "Telegram rejected the configured bot token."}

    def _fetch_pending_updates(self, max_pages: int = 5, page_size: int = 100) -> list[dict]:
        """Pages through everything `getUpdates` currently has buffered (up
        to `max_pages` * `page_size`, a safety cap — not an unbounded loop),
        then acknowledges it all in one call so the next poll doesn't refetch
        the same backlog. This is "as broadly as the Bot API legitimately
        allows": a bot only ever receives messages from chats it has been
        added to, so this can't and doesn't claim to reach private/unrelated
        chats — see the module docstring."""
        if not self.is_live:
            return []

        all_updates: list[dict] = []
        offset: int | None = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"timeout": 0, "allowed_updates": ["message"], "limit": page_size}
            if offset is not None:
                params["offset"] = offset
            data = self._call("getUpdates", **params)
            if not data or not data.get("ok"):
                break
            updates = data.get("result", [])
            if not updates:
                break
            all_updates.extend(updates)
            offset = updates[-1]["update_id"] + 1
            if len(updates) < page_size:
                break

        if offset is not None:
            self._call("getUpdates", offset=offset, timeout=0)

        return all_updates

    def _updates_to_signals(self, updates: list[dict]) -> list[Signal]:
        signals: list[Signal] = []
        for update in updates:
            message = update.get("message")
            if not message or not message.get("text"):
                continue

            chat = message.get("chat", {})
            sender = message.get("from", {})
            chat_id = chat.get("id")
            message_id = message.get("message_id")
            if chat_id is None or message_id is None:
                continue

            text = message["text"]
            username = chat.get("username")
            signals.append(
                Signal(
                    platform="telegram",
                    community_name=chat.get("title") or username or f"chat_{chat_id}",
                    title=text[:120],
                    content=text,
                    author=sender.get("username") or sender.get("first_name") or "telegram_user",
                    url=f"https://t.me/{username}/{message_id}" if username else "",
                    external_id=f"telegram_{chat_id}_{message_id}",
                )
            )
        return signals

    def discover_signals(self) -> list[Signal]:
        if not self.is_live:
            return []  # not connected (TELEGRAM_BOT_TOKEN unset): no discussions — never sample data in the real tables
        return self._updates_to_signals(self._fetch_pending_updates())
