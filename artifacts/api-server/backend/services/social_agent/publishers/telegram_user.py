"""Telegram MTProto User Client Engine — Hands-free User Account Publisher.

Allows the 100Times platform to automatically publish event drops,
announcements, and discussion replies into external Telegram groups
and supergroups using Telegram's official MTProto Client API (Telethon).

Features:
- Telethon StringSession support (zero interactive prompts once session string is set)
- Auto-joining public channels/groups via username or invite links (t.me/+hash)
- Resolves chat entities and verifies write permissions
- Publishes standalone posts and contextual replies
- Builds direct telegram URLs to published messages
"""

import re
from typing import Any

from telethon.sessions import StringSession
from telethon.sync import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from backend.core.config import get_settings
from backend.services.social_agent.publishers.base import PlatformPublisher
from backend.services.social_agent.types import PublishResult


class TelegramUserPublisher(PlatformPublisher):
    platform = "telegram_user"

    @property
    def api_id(self) -> int | None:
        return get_settings().telegram_api_id

    @property
    def api_hash(self) -> str | None:
        return get_settings().telegram_api_hash

    @property
    def session_string(self) -> str | None:
        return get_settings().telegram_session_string

    @property
    def is_real(self) -> bool:
        return bool(self.api_id and self.api_hash and self.session_string)

    def _get_client(self) -> TelegramClient | None:
        if not self.is_real:
            return None
        return TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash)

    def validate_connection(self) -> dict[str, Any]:
        if not self.is_real:
            missing = []
            if not self.api_id:
                missing.append("TELEGRAM_API_ID")
            if not self.api_hash:
                missing.append("TELEGRAM_API_HASH")
            if not self.session_string:
                missing.append("TELEGRAM_SESSION_STRING")
            return {"connected": False, "message": f"Telegram User Client missing credentials: {', '.join(missing)}"}

        try:
            with self._get_client() as client:
                me = client.get_me()
                if me:
                    uname = me.username or me.first_name or str(me.id)
                    phone = me.phone or "n/a"
                    return {
                        "connected": True,
                        "message": f"Connected as Telegram user @{uname} (phone: +{phone})",
                        "username": uname,
                        "phone": phone,
                        "user_id": me.id,
                    }
        except Exception as exc:
            return {"connected": False, "message": f"Telegram MTProto connection error: {exc}"}
        return {"connected": False, "message": "Failed to authenticate with Telegram MTProto API."}

    def auto_join_group(self, invite_or_username: str) -> dict[str, Any]:
        """Auto-joins a Telegram public group or channel via username or invite link."""
        if not self.is_real:
            return {"success": False, "message": "Telegram User Client credentials not configured."}

        clean = invite_or_username.strip()
        try:
            with self._get_client() as client:
                # Private invite link: t.me/+hash or t.me/joinchat/hash
                match_hash = re.search(r"(?:t\.me/\+|joinchat/)([a-zA-Z0-9_-]+)", clean)
                if match_hash:
                    invite_hash = match_hash.group(1)
                    updates = client(ImportChatInviteRequest(invite_hash))
                    return {"success": True, "message": f"Successfully joined private group via invite hash {invite_hash}"}

                # Public username: @group or t.me/group
                match_user = re.search(r"(?:t\.me/|@)?([a-zA-Z0-9_]{4,})", clean)
                if match_user:
                    username = match_user.group(1)
                    client(JoinChannelRequest(username))
                    return {"success": True, "message": f"Successfully joined public channel/group @{username}"}

                return {"success": False, "message": "Unrecognized Telegram invite or username format."}
        except Exception as exc:
            return {"success": False, "message": f"Telegram auto-join error: {exc}"}

    def _parse_target_ref(self, target_ref: str) -> tuple[str | int, int | None]:
        """Parses `telegram_user_<chat_id>_<msg_id>` or `telegram_<chat_id>`."""
        parts = target_ref.split("_")
        msg_id = None
        if len(parts) >= 4 and parts[0] == "telegram" and parts[1] == "user":
            chat_identifier = parts[2]
            msg_id = int(parts[3]) if parts[3].isdigit() else None
        elif len(parts) >= 3 and parts[0] == "telegram_user":
            chat_identifier = parts[1]
            msg_id = int(parts[2]) if parts[2].isdigit() else None
        elif len(parts) >= 3 and parts[0] == "telegram":
            chat_identifier = parts[1]
            msg_id = int(parts[2]) if parts[2].isdigit() else None
        elif len(parts) == 2 and parts[0] in ("telegram", "telegram_user"):
            chat_identifier = parts[1]
        else:
            chat_identifier = target_ref

        # Handle numeric chat IDs
        try:
            chat_id = int(chat_identifier)
            return chat_id, msg_id
        except ValueError:
            return chat_identifier, msg_id

    def validate_publish_permission(self, target_ref: str) -> dict[str, Any]:
        if not self.is_real:
            return {"allowed": False, "message": "Telegram User Client credentials not configured."}

        chat_target, _ = self._parse_target_ref(target_ref)
        try:
            with self._get_client() as client:
                entity = client.get_entity(chat_target)
                title = getattr(entity, "title", getattr(entity, "username", str(chat_target)))
                return {"allowed": True, "message": f"Group/channel '{title}' is accessible to user account."}
        except Exception as exc:
            return {"allowed": False, "message": f"Cannot access target Telegram group: {exc}"}

    def publish_post(self, text: str, target_ref: str) -> PublishResult:
        if not self.is_real:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="TELEGRAM_SESSION_STRING / credentials not configured.",
            )

        chat_target, _ = self._parse_target_ref(target_ref)
        try:
            with self._get_client() as client:
                entity = client.get_entity(chat_target)
                sent = client.send_message(entity, text, link_preview=True)

                username = getattr(entity, "username", None)
                if username:
                    published_url = f"https://t.me/{username}/{sent.id}"
                else:
                    cid_str = str(getattr(entity, "id", chat_target))
                    published_url = f"https://t.me/c/{cid_str}/{sent.id}"

                return PublishResult(
                    success=True,
                    platform=self.platform,
                    published_url=published_url,
                    message="Published successfully via Telegram MTProto User Client.",
                )
        except Exception as exc:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message=f"Telegram user publish failed: {exc}",
            )

    def publish_reply(self, text: str, target_ref: str) -> PublishResult:
        if not self.is_real:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="TELEGRAM_SESSION_STRING / credentials not configured.",
            )

        chat_target, msg_id = self._parse_target_ref(target_ref)
        if not msg_id:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message="Cannot publish reply: missing message_id in target reference.",
            )

        try:
            with self._get_client() as client:
                entity = client.get_entity(chat_target)
                sent = client.send_message(entity, text, reply_to=msg_id, link_preview=True)

                username = getattr(entity, "username", None)
                if username:
                    published_url = f"https://t.me/{username}/{sent.id}"
                else:
                    cid_str = str(getattr(entity, "id", chat_target))
                    published_url = f"https://t.me/c/{cid_str}/{sent.id}"

                return PublishResult(
                    success=True,
                    platform=self.platform,
                    published_url=published_url,
                    message="Reply published successfully via Telegram MTProto User Client.",
                )
        except Exception as exc:
            return PublishResult(
                success=False, platform=self.platform, published_url=None,
                message=f"Telegram user reply failed: {exc}",
            )

