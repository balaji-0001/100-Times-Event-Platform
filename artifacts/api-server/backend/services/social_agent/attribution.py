"""Attribution: links a real Registration back to the ClickEvent (and
therefore the AcquisitionOpportunity) that drove it, if one exists within
the configured attribution window.

Attribution model: Click -> anonymous session (cookie) -> event page ->
Registration -> Conversion. This is the real path — `simulate-conversion`
in routes/acquisition.py is a dev/testing tool only.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import ClickEvent, Registration, RegistrationAttribution

SESSION_COOKIE_NAME = "hundredtimes_sid"


def attribute_registration(
    db: Session, registration: Registration, session_id: str | None, event_id: int
) -> RegistrationAttribution | None:
    if not session_id:
        return None

    already = db.scalar(select(RegistrationAttribution).where(RegistrationAttribution.registration_id == registration.id))
    if already:
        return already

    window_start = datetime.now(timezone.utc) - timedelta(days=get_settings().click_attribution_window_days)

    click = db.scalar(
        select(ClickEvent)
        .where(ClickEvent.anonymous_session_id == session_id, ClickEvent.created_at >= window_start)
        .order_by(ClickEvent.created_at.desc())
    )
    if not click:
        return None

    attribution = RegistrationAttribution(
        registration_id=registration.id,
        click_id=click.id,
        opportunity_id=click.opportunity_id,
        event_id=event_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(attribution)
    return attribution
