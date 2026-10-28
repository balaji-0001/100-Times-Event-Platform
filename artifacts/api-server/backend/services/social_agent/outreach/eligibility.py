"""Candidate selection for Agent 2's research/draft batch — which
discovered events are actually appropriate for outreach right now.
Works identically regardless of `DiscoveredEvent.discovered_by` (the
social-listening pipeline and the Event Discovery Agent both feed the same
`discovered_events`/`discovered_organizers` tables). Deliberately allows
`NEEDS_REVIEW` verification through (not `VERIFIED`-only) since the
discovery agent defaults most rows to `NEEDS_REVIEW` — requiring full
verification here would starve the pipeline almost entirely.

The hard conditions (organizer e-mail found, not blocked, event not over,
no draft yet, in the selected sectors) are applied in SQL, so events that
were already drafted can never crowd out the ones still waiting. Earlier the
newest N rows were fetched first and filtered afterwards: once those were
all drafted, every batch drafted nothing while older events waited forever.
"""

from datetime import date

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.models import DiscoveredEvent, DiscoveredOrganizer, OutreachMessage
from backend.services.social_agent.outreach import duplicate_check, suppression
from backend.services.social_agent.outreach.types import OutreachRunConfig, OutreachRunSummary

_PAGE_SIZE = 200


def _norm(values: list[str] | None) -> list[str]:
    return [v.strip().lower() for v in (values or []) if v and v.strip()]


def _waiting_events(config: OutreachRunConfig):
    """Events with a found organizer e-mail, in an allowed verification state,
    that have no outreach message yet (any status) — before date, sector,
    location and suppression rules."""
    has_message = exists().where(OutreachMessage.event_id == DiscoveredEvent.id)
    return (
        select(DiscoveredEvent)
        .join(DiscoveredOrganizer, DiscoveredOrganizer.id == DiscoveredEvent.organizer_id)
        .where(
            DiscoveredEvent.organizer_status == "FOUND",
            DiscoveredEvent.verification_status.in_(config.verification_statuses),
            DiscoveredOrganizer.email.isnot(None),
            DiscoveredOrganizer.email != "",
            ~has_message,
        )
    )


def _upcoming():
    # Unknown dates stay eligible (the organizer can still list it); past events don't.
    return or_(DiscoveredEvent.event_date.is_(None), DiscoveredEvent.event_date >= date.today())


def _matches_location(event: DiscoveredEvent, organizer: DiscoveredOrganizer, config: OutreachRunConfig) -> bool:
    cities = _norm(config.cities)
    if cities and (event.city or "").strip().lower() not in cities and (organizer.city or "").strip().lower() not in cities:
        return False
    states = _norm(config.states)
    if states and (event.state or "").strip().lower() not in states and (organizer.state or "").strip().lower() not in states:
        return False
    countries = _norm(config.countries)
    if countries:
        from backend.services.discovery_agent.country_utils import normalize_country

        ev_country = (normalize_country(event.country or "") or "").lower()
        if ev_country not in countries and (event.country or "").lower() not in countries:
            return False
    return True


def find_eligible_candidates(
    db: Session, config: OutreachRunConfig
) -> tuple[list[tuple[DiscoveredEvent, DiscoveredOrganizer]], OutreachRunSummary]:
    summary = OutreachRunSummary()

    # Counted, not scanned: already drafted (any status) and blocked organizers.
    counted = (
        select(func.count(DiscoveredEvent.id))
        .join(DiscoveredOrganizer, DiscoveredOrganizer.id == DiscoveredEvent.organizer_id)
        .where(DiscoveredEvent.organizer_status == "FOUND", DiscoveredEvent.verification_status.in_(config.verification_statuses))
    )
    summary.skipped_duplicate = int(db.scalar(counted.where(exists().where(OutreachMessage.event_id == DiscoveredEvent.id))) or 0)
    waiting = _waiting_events(config)
    summary.skipped_suppressed = int(db.scalar(
        select(func.count()).select_from(waiting.where(DiscoveredOrganizer.blocked.is_(True)).subquery())
    ) or 0)
    summary.skipped_past_event = int(db.scalar(
        select(func.count()).select_from(waiting.where(DiscoveredEvent.event_date < date.today()).subquery())
    ) or 0)

    stmt = waiting.where(DiscoveredOrganizer.blocked.is_(False), _upcoming())
    categories = _norm(config.categories)
    if categories:
        stmt = stmt.where(func.lower(func.trim(DiscoveredEvent.category)).in_(categories))
    stmt = stmt.options(selectinload(DiscoveredEvent.organizer)).order_by(DiscoveredEvent.discovered_at.desc(), DiscoveredEvent.id.desc())

    eligible: list[tuple[DiscoveredEvent, DiscoveredOrganizer]] = []
    offset = 0
    while len(eligible) < config.max_candidates:
        page = db.execute(stmt.offset(offset).limit(_PAGE_SIZE)).scalars().all()
        if not page:
            break
        offset += len(page)
        for event in page:
            summary.candidates_considered += 1
            organizer = event.organizer
            if not _matches_location(event, organizer, config):
                continue
            if suppression.is_suppressed(db, organizer.email):
                summary.skipped_suppressed += 1
                continue
            # Same organizer already contacted about an event of the same name (another row).
            if duplicate_check.find_duplicate(db, organizer, event.name) is not None:
                summary.skipped_duplicate += 1
                continue
            eligible.append((event, organizer))
            if len(eligible) >= config.max_candidates:
                break

    summary.candidates_considered += summary.skipped_duplicate
    return eligible, summary


def outreach_backlog(db: Session, config: OutreachRunConfig) -> dict[str, object]:
    """Why discovered events with an organizer e-mail have no outreach draft
    yet — shown on the Outreach page so the admin can see what's waiting."""
    rows = db.execute(_waiting_events(config).options(selectinload(DiscoveredEvent.organizer)).limit(5000)).scalars().all()
    categories = _norm(config.categories)
    today = date.today()
    counts = {"waiting": len(rows), "ready": 0, "past_event": 0, "outside_sectors": 0, "outside_locations": 0, "suppressed": 0}
    for event in rows:
        organizer = event.organizer
        if event.event_date is not None and event.event_date < today:
            counts["past_event"] += 1
        elif organizer.blocked or suppression.is_suppressed(db, organizer.email):
            counts["suppressed"] += 1
        elif categories and (event.category or "").strip().lower() not in categories:
            counts["outside_sectors"] += 1
        elif not _matches_location(event, organizer, config):
            counts["outside_locations"] += 1
        else:
            counts["ready"] += 1
    return {**counts, "sectors": list(config.categories or []), "countries": list(config.countries or []),
            "states": list(config.states or []), "cities": list(config.cities or [])}
