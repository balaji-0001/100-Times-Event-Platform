"""Global Outbox recorder for dispatched and logged emails across the platform."""

from collections import deque
from datetime import datetime, timezone
import uuid

_OUTBOX_LIMIT = 200
_OUTBOX: deque[dict] = deque(maxlen=_OUTBOX_LIMIT)


def record_outbox(
    recipient: str,
    subject: str,
    body: str,
    html: str | None = None,
    provider: str = "smtp",
    status: str = "DELIVERED",
    message_id: str | None = None,
    error: str | None = None,
) -> dict:
    item = {
        "id": f"mail-{uuid.uuid4().hex[:8]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "html": html,
        "provider": provider,
        "status": status,
        "messageId": message_id,
        "error": error,
    }
    _OUTBOX.appendleft(item)
    return item


def get_outbox(limit: int = 50) -> list[dict]:
    return list(_OUTBOX)[:limit]


def clear_outbox() -> None:
    _OUTBOX.clear()

