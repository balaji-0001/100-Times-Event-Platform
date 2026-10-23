"""Candidate selection for Agent 2's research/draft batch — which
discovered events are actually appropriate for outreach right now.

Works identically regardless of `DiscoveredEvent.discovered_by` (the
social-listening pipeline and the Event Discovery Agent both feed the same
`discovered_events`/`discovered_organizers` tables). Deliberately allows
`NEEDS_REVIEW` verification through (not `VERIFIED`-only) since the
discovery agent defaults most rows to `NEEDS_REVIEW` — requiring full
verification here would starve the pipeline almost entirely.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import DiscoveredEvent, DiscoveredOrganizer, OutreachMessage
from backend.services.social_agent.outreach import duplicate_check, suppression
from backend.services.social_agent.outreach.types import OutreachRunConfig, OutreachRunSummary

_OVERFETCH_MULTIPLIER = 4


def find_eligible_candidates(
    db: Session, config: OutreachRunConfig
) -> tuple[list[tuple[DiscoveredEvent, DiscoveredOrganizer]], OutreachRunSummary]:
    summary = OutreachRunSummary()

    stmt = (
        select(DiscoveredEvent)
        .options(selectinload(DiscoveredEvent.organizer))
        .where(
            DiscoveredEvent.organizer_status == "FOUND",
            DiscoveredEvent.verification_status.in_(config.verification_statuses),
        )
        .order_by(DiscoveredEvent.discovered_at.desc())
        .limit(config.max_candidates * _OVERFETCH_MULTIPLIER)
    )
    candidates = db.execute(stmt).scalars().all()
    summary.candidates_considered = len(candidates)

    eligible: list[tuple[DiscoveredEvent, DiscoveredOrganizer]] = []
    for event in candidates:
        if len(eligible) >= config.max_candidates:
            break

        organizer = event.organizer
        if organizer is None or not organizer.email:
            summary.skipped_no_organizer += 1
            continue

        if config.categories:
            norm_cats = [c.strip().lower() for c in config.categories if c]
            if norm_cats and (not event.event_category or event.event_category.strip().lower() not in norm_cats):
                continue

        if config.cities:
            norm_cities = [c.strip().lower() for c in config.cities if c]
            event_city = (event.city or "").strip().lower()
            org_city = (organizer.city or "").strip().lower()
            if norm_cities and event_city not in norm_cities and org_city not in norm_cities:
                continue

        if config.states:
            norm_states = [s.strip().lower() for s in config.states if s]
            event_state = (event.state or "").strip().lower()
            org_state = (organizer.state or "").strip().lower()
            if norm_states and event_state not in norm_states and org_state not in norm_states:
                continue

        if config.countries:
            norm_countries = [c.strip().lower() for c in config.countries if c]
            from backend.services.discovery_agent.country_utils import normalize_country
            ev_country = (normalize_country(event.country or "") or "").lower()
            if norm_countries and ev_country not in norm_countries and (event.country or "").lower() not in norm_countries:
                continue

        if organizer.blocked or suppression.is_suppressed(db, organizer.email):
            summary.skipped_suppressed += 1
            continue

        already_has_message = db.execute(
            select(OutreachMessage.id).where(OutreachMessage.event_id == event.id)
        ).scalars().first()
        if already_has_message is not None:
            summary.skipped_duplicate += 1
            continue

        if duplicate_check.find_duplicate(db, organizer, event.name) is not None:
            summary.skipped_duplicate += 1
            continue

        eligible.append((event, organizer))

    return eligible, summary
