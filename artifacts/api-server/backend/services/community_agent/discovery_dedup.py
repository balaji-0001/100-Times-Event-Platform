"""Pre-insert duplicate detection for the Community Discovery Agent — run
BEFORE every `DiscoveredCommunity` insert so a re-run never creates
duplicate records. Mirrors `discovery_agent/discovery_dedup.py`'s approach:
match on canonical URL first (exact, cheap), then normalized name.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import DiscoveredCommunity

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return _NON_ALNUM.sub(" ", name.lower()).strip()


def find_duplicate_community(db: Session, *, canonical_url: str | None, name: str | None, platform: str | None) -> DiscoveredCommunity | None:
    if canonical_url:
        existing = db.execute(select(DiscoveredCommunity).where(DiscoveredCommunity.canonical_url == canonical_url)).scalars().first()
        if existing is not None:
            return existing

    if not name or not platform:
        return None

    normalized_target = normalize_name(name)
    candidates = db.execute(select(DiscoveredCommunity).where(DiscoveredCommunity.platform == platform)).scalars().all()
    for candidate in candidates:
        if normalize_name(candidate.name) == normalized_target:
            return candidate

    return None
