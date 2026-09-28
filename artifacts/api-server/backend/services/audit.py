"""Platform-wide Audit Logging Service.

Records structured audit logs for organizer signup, event creation/modification/submission,
Trust Agent decisions, Admin decisions, event publishing, registrations, cancellations,
reschedules, agent executions, automation executions, notifications, and follow-ups.

Strictly strips any sensitive keys (passwords, tokens, secrets, API keys) before persisting.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models import AuditLog

_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "gemini_api_key",
    "anthropic_api_key",
    "smtp_password",
    "webhook_secret",
    "n8n_webhook_secret",
    "authorization",
}


def sanitize_metadata(data: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively remove any sensitive keys before writing to AuditLog."""
    if not data or not isinstance(data, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for k, v in data.items():
        key_lower = str(k).lower()
        if any(s in key_lower for s in _SENSITIVE_KEYS):
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = sanitize_metadata(v)
        elif isinstance(v, list):
            cleaned[k] = [sanitize_metadata(item) if isinstance(item, dict) else item for item in v]
        else:
            cleaned[k] = v
    return cleaned


def record_audit_log(
    db: Session,
    *,
    actor: str,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    actor_id: int | None = None,
    result: str = "SUCCESS",
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        result=result,
        metadata_json=sanitize_metadata(metadata),
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.flush()
    return entry
