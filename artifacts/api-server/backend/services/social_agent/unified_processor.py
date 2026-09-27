"""Unified Signal Processor.

Normalizes connector output and enforces the "never spam" guardrails that
apply before anything reaches the intent/matching pipeline: a per-platform
daily cap on how many new signals get ingested, configurable per platform
via the `platform_rate_limits` table (admin-editable, see
`PATCH /acquisition/rate-limits/{platform}`) rather than one flat env var.
Duplicate detection itself lives one level down, in the pipeline's
`normalize` stage, which skips any signal whose `external_id` has already
been recorded as a `Discussion`.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import Discussion, PlatformRateLimit
from backend.services.social_agent.connectors.base import PlatformConnector
from backend.services.social_agent.types import Signal


class CollectResult:
    __slots__ = ("signals", "skip_notes")

    def __init__(self, signals: list[Signal], skip_notes: list[str]) -> None:
        self.signals = signals
        self.skip_notes = skip_notes


def _get_or_create_rate_limit(db: Session, platform: str) -> PlatformRateLimit:
    row = db.scalar(select(PlatformRateLimit).where(PlatformRateLimit.platform == platform))
    if row:
        return row
    row = PlatformRateLimit(
        platform=platform,
        daily_limit=get_settings().social_agent_daily_cap_per_platform,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


class UnifiedSignalProcessor:
    @classmethod
    def collect(cls, connectors: list[PlatformConnector], db: Session) -> CollectResult:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        signals: list[Signal] = []
        skip_notes: list[str] = []

        for connector in connectors:
            rate_limit = _get_or_create_rate_limit(db, connector.platform)
            already_ingested_today = (
                db.scalar(
                    select(func.count(Discussion.id)).where(
                        Discussion.platform == connector.platform,
                        Discussion.created_at >= today_start,
                    )
                )
                or 0
            )
            remaining_capacity = max(rate_limit.daily_limit - already_ingested_today, 0)
            if remaining_capacity <= 0:
                skip_notes.append(
                    f"{connector.platform}: daily rate limit reached ({already_ingested_today}/{rate_limit.daily_limit}) — no new signals ingested"
                )
                continue

            available = connector.discover_signals()
            platform_signals = available[:remaining_capacity]
            signals.extend(platform_signals)
            if len(available) > remaining_capacity:
                skip_notes.append(
                    f"{connector.platform}: {len(available) - remaining_capacity} signal(s) skipped, remaining daily capacity was {remaining_capacity}"
                )

        db.commit()
        return CollectResult(signals=signals, skip_notes=skip_notes)
