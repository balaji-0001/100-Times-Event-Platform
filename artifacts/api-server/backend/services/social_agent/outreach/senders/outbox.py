"""Global Outbox recorder for dispatched and logged emails across the platform."""

import re
import uuid
from collections import deque
from datetime import datetime, timezone

_OUTBOX_LIMIT = 200
_OUTBOX: deque[dict] = deque(maxlen=_OUTBOX_LIMIT)
# One-time secrets in links (password reset, e-mail verification) must not be
# readable by whoever opens the admin Outbox inspector.
_SECRET_PARAM_RE = re.compile(r"([?&](?:token|code|key|secret)=)[^&\s\"'<>]+", re.IGNORECASE)


def _redact(text: str | None) -> str | None:
    return _SECRET_PARAM_RE.sub(lambda m: m.group(1) + "[redacted]", text) if text else text


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
        "body": _redact(body),
        "html": _redact(html),
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

