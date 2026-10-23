"""Real Telegram publisher — the one platform with a genuine, working
publish integration in this codebase (no approval gate, just a bot token).

Follows the full four-step flow: validate_connection (getMe) ->
validate_publish_permission (getChatMember) -> publish_reply (sendMessage,
threaded via reply_to_message_id) -> verify_publication (trusts sendMessage's
own success response, which is Telegram's real confirmation).
"""

import time
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

    def _published_url(self, sent_chat: dict, chat_id: str, sent_message_id: int | None) -> str | None:
        """A message-specific link when Telegram supports one (public
        channel or supergroup); otherwise, for a private chat, a real
        conversation-level link (opens the actual chat, just not scrolled
        to one message — Telegram has no public link format for a
        message inside a private chat or a non-super, unlinked group, so
        there is honestly nothing more specific to point at)."""
        if sent_chat.get("username"):
            return f"https://t.me/{sent_chat['username']}/{sent_message_id}"
        if str(chat_id).startswith("-100"):
            return f"https://t.me/c/{str(chat_id)[4:]}/{sent_message_id}"
        if sent_chat.get("type") == "private":
            me = self._call("getMe")
            bot_username = me["result"].get("username") if me and me.get("ok") else None
            return f"https://t.me/{bot_username}" if bot_username else None
        return None  # a basic (non-super) group with no username — Telegram has no public link for this at all

    def validate_connection(self) -> dict[str, Any]:
        if not self.credential:
            return {"connected": False, "message": "TELEGRAM_BOT_TOKEN not configured."}
        data = self._call("getMe")
        if data and data.get("ok"):
            return {"connected": True, "message": f"Connected as @{data['result'].get('username')}"}
        return {"connected": False, "message": "Telegram rejected the configured bot token."}

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        """`target_ref` is "telegram_<chat_id>" for a standalone post or
        "telegram_<chat_id>_<message_id>" for a reply — only the chat id
        matters for this check, so both formats accepted."""
        if target_ref.startswith("telegram_user_") or (not self.credential and _settings_credential("telegram_session_string")):
            from backend.services.social_agent.publishers.telegram_user import TelegramUserPublisher
            return TelegramUserPublisher().validate_publish_permission(target_ref)

        parts = target_ref.split("_")
        if len(parts) < 2 or parts[0] != "telegram":
            return {"allowed": False, "message": "Missing chat reference — cannot verify permission."}
        chat_id = parts[1]

        # 1. Fetch chat metadata to determine chat type and permissions
        chat_info = self._call("getChat", chat_id=chat_id)
        if not chat_info or not chat_info.get("ok"):
            err_desc = (chat_info.get("description") if chat_info else None) or "Network or API failure"
            if "chat not found" in err_desc.lower():
                return {"allowed": False, "message": f"Chat not found ({chat_id}). Ensure @HundredTimesAgentBot is added to the chat."}
            return {"allowed": False, "message": f"Could not inspect target chat: {err_desc}"}

        chat_result = chat_info["result"]
        chat_type = chat_result.get("type", "group")

        # Private direct message (1-on-1 with user who started bot)
        if chat_type == "private":
            return {"allowed": True, "message": "Direct message chat: messages allowed."}

        # 2. Check bot's own identity and membership in group/channel
        me = self._call("getMe")
        bot_id = me["result"]["id"] if me and me.get("ok") else None
        if bot_id is None:
            return {"allowed": False, "message": "Could not resolve the bot's own identity to check chat membership."}

        data = self._call("getChatMember", chat_id=chat_id, user_id=bot_id)
        if not data or not data.get("ok"):
            err_desc = (data.get("description") if data else None) or "Unknown error"
            if "CHAT_ADMIN_REQUIRED" in err_desc or "member list is inaccessible" in err_desc:
                if chat_type == "channel":
                    return {
                        "allowed": False,
                        "requires_admin": True,
                        "message": "CHAT_ADMIN_REQUIRED: This is a Telegram channel. @HundredTimesAgentBot must be promoted to an Administrator with 'Post Messages' rights to publish.",
                    }
                return {
                    "allowed": False,
                    "requires_admin": True,
                    "message": f"CHAT_ADMIN_REQUIRED: {err_desc}. Please promote @HundredTimesAgentBot to Administrator.",
                }
            return {"allowed": False, "message": f"Could not verify the bot's membership in the target chat: {err_desc}"}

        member = data["result"]
        status = member.get("status")

        if status in ("kicked", "left"):
            return {
                "allowed": False,
                "message": f"Bot is not in this chat (status: {status}). Please invite @HundredTimesAgentBot to the group/channel.",
            }

        # Channels: posting strictly requires administrator status with can_post_messages
        if chat_type == "channel":
            if status not in ("administrator", "creator"):
                return {
                    "allowed": False,
                    "requires_admin": True,
                    "message": "CHAT_ADMIN_REQUIRED: Telegram channels require the bot to be an Administrator to post.",
                }
            if not member.get("can_post_messages", True):
                return {
                    "allowed": False,
                    "requires_admin": True,
                    "message": "CHAT_ADMIN_REQUIRED: The bot is an admin in this channel but lacks 'Post Messages' permission.",
                }
            return {"allowed": True, "message": "Bot is an administrator with posting rights in this channel."}

        # Groups & Supergroups:
        chat_perms = chat_result.get("permissions") or {}
        regular_members_can_send = chat_perms.get("can_send_messages", True)

        if status in ("administrator", "creator"):
            return {"allowed": True, "message": f"Bot is an {status} in this group."}

        if status == "member":
            if not regular_members_can_send:
                return {
                    "allowed": False,
                    "requires_admin": True,
                    "message": "CHAT_ADMIN_REQUIRED: Regular members cannot send messages in this group. Please promote @HundredTimesAgentBot to Administrator.",
                }
            return {"allowed": True, "message": "Bot is an active member with message-posting rights."}

        if status == "restricted":
            can_send = member.get("can_send_messages", False)
            if not can_send:
                return {
                    "allowed": False,
                    "requires_admin": True,
                    "message": "CHAT_ADMIN_REQUIRED: Bot has restricted permissions in this group and cannot send messages. An administrator must lift restrictions.",
                }
            return {"allowed": True, "message": "Bot is restricted but has message-posting permission."}

        return {"allowed": False, "message": f"Bot membership status in target chat: {status}"}

    def _format_error_message(self, description: str) -> str:
        if "CHAT_ADMIN_REQUIRED" in description or "not enough rights" in description.lower():
            return f"CHAT_ADMIN_REQUIRED: Telegram rejected message ({description}). Administrator privileges with 'Post Messages' rights are required."
        return f"Telegram API error: {description}"

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        if target_ref.startswith("telegram_user_") or (not self.credential and _settings_credential("telegram_session_string")):
            from backend.services.social_agent.publishers.telegram_user import TelegramUserPublisher
            return TelegramUserPublisher().publish_reply(text, target_ref)

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
            err_desc = data.get("description", "unknown error")
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message=self._format_error_message(err_desc),
            )

        sent = data["result"]
        sent_chat = sent.get("chat", {})
        sent_message_id = sent.get("message_id")
        published_url = self._published_url(sent_chat, chat_id, sent_message_id)

        return PublishResult(
            success=True, platform=self.platform, published_url=published_url,
            message="Published successfully via the Telegram Bot API.",
        )

    def publish_post(self, text: str, target_ref: str, **kwargs: Any) -> PublishResult:
        """Same as `publish_reply` but with no `reply_to_message_id` — a
        standalone announcement, for Agent 4's community-promotion
        extension. `target_ref` is just "telegram_<chat_id>" (no message id,
        since there's nothing to reply to)."""
        is_dry_run = kwargs.get("is_dry_run", False)
        if is_dry_run:
            chat_id = target_ref.split("_")[1] if "_" in target_ref else target_ref
            return PublishResult(
                success=True,
                platform=self.platform,
                published_url=f"https://t.me/c/{chat_id}/12345" if str(chat_id).startswith("-100") else "https://t.me/event_promotions_dry_run",
                message="[DRY-RUN] Telegram channel broadcast simulated successfully. Bot API was not called.",
                post_id=f"dry_run_tg_{int(time.time())}",
            )

        if target_ref.startswith("telegram_user_") or (not self.credential and _settings_credential("telegram_session_string")):
            from backend.services.social_agent.publishers.telegram_user import TelegramUserPublisher
            return TelegramUserPublisher().publish_post(text, target_ref)

        if not self.credential:
            return PublishResult(success=False, platform=self.platform, published_url=None, message="TELEGRAM_BOT_TOKEN not configured.")

        parts = target_ref.split("_")
        if len(parts) < 2 or parts[0] != "telegram":
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Cannot publish: missing the target chat reference.",
            )
        chat_id = parts[1]

        data = self._call("sendMessage", chat_id=chat_id, text=text)
        if not data:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Telegram API request failed (network error or invalid response).",
            )
        if not data.get("ok"):
            err_desc = data.get("description", "unknown error")
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message=self._format_error_message(err_desc),
            )

        sent = data["result"]
        sent_chat = sent.get("chat", {})
        sent_message_id = sent.get("message_id")
        published_url = self._published_url(sent_chat, chat_id, sent_message_id)

        return PublishResult(
            success=True, platform=self.platform, published_url=published_url,
            message="Published successfully via the Telegram Bot API.",
        )
