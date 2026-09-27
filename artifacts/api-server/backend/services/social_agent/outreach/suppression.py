"""Durable, email-keyed suppression list — checked before every outreach
send so an opted-out, restricted, or bounced address is never contacted
again, even if a later discovery run creates a fresh `DiscoveredOrganizer`
row with the same email (dedup should normally prevent that, but this
doesn't rely on it).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import SuppressedContact


def is_suppressed(db: Session, email: str | None) -> bool:
    if not email:
        return False
    normalized = email.strip().lower()
    return db.execute(select(SuppressedContact).where(SuppressedContact.email == normalized)).scalars().first() is not None


def suppress(db: Session, email: str, *, reason: str, note: str | None = None) -> SuppressedContact:
    normalized = email.strip().lower()
    existing = db.execute(select(SuppressedContact).where(SuppressedContact.email == normalized)).scalars().first()
    if existing is not None:
        return existing
    record = SuppressedContact(email=normalized, reason=reason, note=note)
    db.add(record)
    db.flush()
    return record
