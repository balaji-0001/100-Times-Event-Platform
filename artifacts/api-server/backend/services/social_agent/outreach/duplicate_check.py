"""Duplicate/contact check — prevents a second *initial* outreach message
to the same organizer about the same event (matched by organizer identity
+ event name), per the spec's "same Organizer, Event, or Contact/email"
rule. A message that hasn't progressed anywhere yet, or was REJECTED, is
NOT treated as a duplicate (a fresh attempt should be allowed); anything
already in flight or resolved (drafted-and-beyond, sent, bounced, replied,
opted out, following up, or completed) is."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import DiscoveredEvent, DiscoveredOrganizer, OutreachMessage

_DUPLICATE_STATUSES = (
    "PENDING_APPROVAL", "APPROVED", "SENT", "DELIVERED", "BOUNCED",
    "REPLIED", "OPTED_OUT", "FOLLOW_UP_DUE", "COMPLETED",
)


def find_duplicate(db: Session, organizer: DiscoveredOrganizer, event_name: str | None) -> OutreachMessage | None:
    if not event_name:
        # No event name to compare against — fall back to "any prior
        # non-failed outreach to this organizer at all" as the safer default.
        stmt = select(OutreachMessage).where(
            OutreachMessage.organizer_id == organizer.id,
            OutreachMessage.status.in_(_DUPLICATE_STATUSES),
        )
        return db.execute(stmt).scalars().first()

    stmt = (
        select(OutreachMessage)
        .join(DiscoveredEvent, OutreachMessage.event_id == DiscoveredEvent.id)
        .where(
            OutreachMessage.organizer_id == organizer.id,
            DiscoveredEvent.name.isnot(None),
            DiscoveredEvent.name.ilike(event_name),
            OutreachMessage.status.in_(_DUPLICATE_STATUSES),
        )
    )
    return db.execute(stmt).scalars().first()
