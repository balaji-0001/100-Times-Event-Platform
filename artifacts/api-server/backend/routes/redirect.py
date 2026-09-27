"""Real click-tracking redirect service.

This is the actual attribution mechanism the content generators' links point
to — `GET /r/{opportunity_id}` records a real `ClickEvent` row (with an
anonymous session id persisted in a cookie, not just a `?ref=` query string)
and then 302s the visitor to the matched event page. No external
credentials needed — this is our own domain's own redirect.

Mounted at the app root (no `/api` prefix) so the generated links stay
short, matching the spec's `/r/{opportunity_id}` shape.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db import get_db
from backend.models import AcquisitionOpportunity, AcquisitionReferralEvent, ClickEvent, Discussion
from backend.services.social_agent.attribution import SESSION_COOKIE_NAME

router = APIRouter(tags=["redirect"])

SESSION_COOKIE = SESSION_COOKIE_NAME
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


@router.get("/r/{opportunity_id}")
def redirect_and_track_click(opportunity_id: int, request: Request, db: Session = Depends(get_db)):
    op = db.scalar(
        select(AcquisitionOpportunity)
        .options(selectinload(AcquisitionOpportunity.discussion).selectinload(Discussion.community))
        .where(AcquisitionOpportunity.id == opportunity_id)
    )
    if not op:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    first_match = op.matching_events[0] if op.matching_events else None
    destination = f"https://100times.in/events/{first_match['slug']}" if first_match else "https://100times.in/events"

    session_id = request.cookies.get(SESSION_COOKIE) or uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    db.add(
        ClickEvent(
            opportunity_id=op.id,
            anonymous_session_id=session_id,
            destination_url=destination,
            created_at=now,
        )
    )
    # Also record on the existing referral-event ledger so today's analytics
    # (which already read from it) immediately reflect real redirect clicks.
    db.add(
        AcquisitionReferralEvent(
            opportunity_id=op.id,
            event_id=first_match["id"] if first_match else None,
            event_type="click",
            visitor_id=session_id,
            created_at=now,
        )
    )
    db.commit()

    response = RedirectResponse(url=destination, status_code=302)
    response.set_cookie(
        SESSION_COOKIE, session_id, max_age=SESSION_COOKIE_MAX_AGE, httponly=True, samesite="lax"
    )
    return response
