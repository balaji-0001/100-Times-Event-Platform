"""Real Telegram publisher — the one platform with a genuine, working
publish integration in this codebase (no approval gate, just a bot token).

Follows the full four-step flow: validate_connection (getMe) ->
validate_publish_permission (getChatMember) -> publish_reply (sendMessage,
threaded via reply_to_message_id) -> verify_publication (trusts sendMessage's
own success response, which is Telegram's real confirmation).
"""

from typing import Any

import httpx

from backend.services.social_agent.connectors.base import _settings_credential
from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.types import PublishResult

_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramPublisher(PlatformPublisher):
    platform = "telegram"

    @property
    def credential(self) -> str | None:
        return _settings_credential("telegram_bot_token")

    @property
    def is_real(self) -> bool:
        return bool(self.credential)

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
        if not self.credential:
            return {"connected": False, "message": "TELEGRAM_BOT_TOKEN not configured."}
        data = self._call("getMe")
        if data and data.get("ok"):
            return {"connected": True, "message": f"Connected as @{data['result'].get('username')}"}
        return {"connected": False, "message": "Telegram rejected the configured bot token."}

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        parts = target_ref.split("_")
        if len(parts) < 3 or parts[0] != "telegram":
            return {"allowed": False, "message": "Missing chat/message reference — cannot verify permission."}
        chat_id = parts[1]

        me = self._call("getMe")
        bot_id = me["result"]["id"] if me and me.get("ok") else None
        if bot_id is None:
            return {"allowed": False, "message": "Could not resolve the bot's own identity to check chat membership."}

        data = self._call("getChatMember", chat_id=chat_id, user_id=bot_id)
        if data and data.get("ok"):
            status = data["result"].get("status")
            allowed = status in ("member", "administrator", "creator")
            return {"allowed": allowed, "message": f"Bot membership status in target chat: {status}"}
        return {"allowed": False, "message": "Could not verify the bot's membership in the target chat."}

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        if not self.credential:
            return PublishResult(success=False, platform=self.platform, published_url=None, message="TELEGRAM_BOT_TOKEN not configured.")

        parts = target_ref.split("_")
        if len(parts) < 3 or parts[0] != "telegram":
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Cannot publish: missing the original chat/message reference.",
            )
        chat_id, message_id = parts[1], parts[2]

        data = self._call("sendMessage", chat_id=chat_id, text=text, reply_to_message_id=int(message_id))
        if not data:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Telegram API request failed (network error or invalid response).",
            )
        if not data.get("ok"):
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message=f"Telegram API error: {data.get('description', 'unknown error')}",
            )

        sent = data["result"]
        sent_chat = sent.get("chat", {})
        sent_message_id = sent.get("message_id")
        if sent_chat.get("username"):
            published_url = f"https://t.me/{sent_chat['username']}/{sent_message_id}"
        elif str(chat_id).startswith("-100"):
            # Supergroup deep link format: t.me/c/<id-without-the--100-prefix>/<message_id>
            published_url = f"https://t.me/c/{str(chat_id)[4:]}/{sent_message_id}"
        else:
            published_url = None  # private/basic group with no public link format

        return PublishResult(
            success=True, platform=self.platform, published_url=published_url,
            message="Published successfully via the Telegram Bot API.",
        )
