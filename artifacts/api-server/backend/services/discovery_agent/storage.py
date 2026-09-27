"""Persistence layer for the Event Discovery Agent — the only place that
writes `DiscoveredEvent`/`DiscoveredOrganizer`/`event_sources`/
`organizer_contacts` rows for this agent. Always dedup-checks before
inserting (via `discovery_dedup`), and commits after each item so a run
that crashes partway through leaves real, non-duplicated progress behind
rather than an all-or-nothing transaction.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import DiscoveredEvent, DiscoveredOrganizer, EventSource, OrganizerContact
from backend.services.discovery_agent import discovery_dedup
from backend.services.discovery_agent.types import ExtractedEventCandidate, OrganizerCandidate, RunSummary

_CONTACT_FIELDS = ("email", "phone", "linkedin", "website")


def get_or_create_organizer(db: Session, candidate: OrganizerCandidate, summary: RunSummary) -> DiscoveredOrganizer | None:
    if not candidate.name:
        return None

    existing = discovery_dedup.find_duplicate_organizer(db, name=candidate.name, email=candidate.email, website=candidate.website)
    if existing is not None:
        organizer = existing
        if candidate.organizer_type and not organizer.organizer_type:
            organizer.organizer_type = candidate.organizer_type
        organizer.last_updated_at = datetime.now(timezone.utc)
    else:
        organizer = DiscoveredOrganizer(
            name=candidate.name,
            email=candidate.email,
            website=candidate.website,
            linkedin=candidate.linkedin,
            phone=candidate.phone,
            organizer_type=candidate.organizer_type,
            confidence_score=candidate.confidence_score,
            source_url=candidate.sources[0].url if candidate.sources else None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(organizer)
        db.flush()
        summary.new_organizers += 1
    summary.organizers_found += 1

    source_url = candidate.sources[0].url if candidate.sources else None
    values = {"email": candidate.email, "phone": candidate.phone, "linkedin": candidate.linkedin, "website": candidate.website}
    for contact_type in _CONTACT_FIELDS:
        value = values[contact_type]
        if not value:
            continue
        stmt = select(OrganizerContact).where(
            OrganizerContact.discovered_organizer_id == organizer.id,
            OrganizerContact.contact_type == contact_type,
            OrganizerContact.value == value,
        )
        if db.execute(stmt).scalars().first() is not None:
            continue
        db.add(
            OrganizerContact(
                discovered_organizer_id=organizer.id,
                contact_type=contact_type,
                value=value,
                source_url=source_url,
                confidence_score=candidate.confidence_score,
                is_primary=(contact_type == "email"),
                created_at=datetime.now(timezone.utc),
            )
        )
        summary.contacts_found += 1

    return organizer


def persist_event(
    db: Session,
    *,
    candidate: ExtractedEventCandidate,
    organizer: OrganizerCandidate | None,
    verification_status: str,
    verification_notes: list[str],
    confidence_score: int,
    event_date,
    summary: RunSummary,
) -> DiscoveredEvent | None:
    """Returns the persisted row, or `None` if this was a duplicate (already
    counted in `summary.duplicate_events`) and nothing new was written."""
    summary.events_discovered += 1

    duplicate = discovery_dedup.find_duplicate_event(
        db,
        name=candidate.name,
        organizer_name=organizer.name if organizer else None,
        date=candidate.date,
        city=candidate.city,
        url=candidate.ticket_url or candidate.url,
    )
    if duplicate is not None:
        summary.duplicate_events += 1
        return None

    organizer_row = get_or_create_organizer(db, organizer, summary) if organizer and organizer.found else None

    if verification_status == "NEEDS_REVIEW":
        summary.events_needing_review += 1

    primary = candidate.primary_source
    event = DiscoveredEvent(
        name=candidate.name,
        event_description=candidate.event_description,
        category=candidate.category,
        subcategory=candidate.subcategory,
        date=candidate.date,
        event_date=event_date,
        start_time=candidate.start_time,
        end_time=candidate.end_time,
        venue=candidate.venue,
        location=candidate.venue or candidate.city,
        city=candidate.city,
        state=candidate.state,
        country=candidate.country or "India",
        url=candidate.url,
        ticket_url=candidate.ticket_url,
        source_website=primary.source_website if primary else None,
        event_format=candidate.event_format,
        organizer_id=organizer_row.id if organizer_row else None,
        source_url=primary.url if primary else candidate.url,
        match_score=confidence_score,
        confidence_score=confidence_score,
        organizer_status="FOUND" if (organizer_row and organizer_row.email) else ("NOT_FOUND" if organizer else "PENDING"),
        verification_status=verification_status,
        discovery_status="NEW",
        discovered_by="web_discovery_agent",
        verification_notes=verification_notes,
        discovered_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.flush()
    summary.new_events += 1

    seen_urls = set()
    all_sources = list(candidate.sources) + [s for s in (organizer.sources if organizer else [])]
    for source in all_sources:
        if source.url in seen_urls:
            continue
        seen_urls.add(source.url)
        db.add(
            EventSource(
                discovered_event_id=event.id,
                source_website=source.source_website,
                source_url=source.url,
                source_type=source.source_type,
                extracted_fields=candidate.raw_evidence if primary and source.url == primary.url else None,
                fetched_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
        )

    db.commit()
    return event
