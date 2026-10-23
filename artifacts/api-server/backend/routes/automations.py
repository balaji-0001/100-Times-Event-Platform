"""Automation requests — a simple, honest queue for "I want X automated"
asks from the console's Automations page. There is no engine here that
turns a description into running code: a developer reads the request and,
if they build it, moves its status along and leaves a short note. The route
intentionally does nothing clever — create, list, and one status-update
endpoint for a developer to use once the work is actually done.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.dependencies import require_roles
from backend.models import AutomationRequest, User
from backend.schemas import AutomationRequestCreate, AutomationRequestOut

router = APIRouter(prefix="/automations", tags=["automations"])

_admin = Depends(require_roles("ADMIN"))
_VALID_STATUSES = ("NEW", "IN_PROGRESS", "DONE", "DECLINED")


@router.get("/requests", response_model=list[AutomationRequestOut])
def list_automation_requests(db: Session = Depends(get_db), _user: User = _admin) -> list[AutomationRequestOut]:
    rows = db.execute(select(AutomationRequest).order_by(AutomationRequest.created_at.desc())).scalars().all()
    return [AutomationRequestOut.model_validate(row) for row in rows]


@router.post("/requests", response_model=AutomationRequestOut, status_code=status.HTTP_201_CREATED)
def create_automation_request(payload: AutomationRequestCreate, db: Session = Depends(get_db), user: User = _admin) -> AutomationRequestOut:
    row = AutomationRequest(description=payload.description.strip(), status="NEW", requested_by=user.email)
    db.add(row)
    db.commit()
    db.refresh(row)
    return AutomationRequestOut.model_validate(row)


@router.patch("/requests/{request_id}", response_model=AutomationRequestOut)
def update_automation_request_status(
    request_id: int, new_status: str, note: str | None = None, db: Session = Depends(get_db), _user: User = _admin
) -> AutomationRequestOut:
    """For a developer to mark progress once real work has been done —
    not called by anything automatically."""
    if new_status not in _VALID_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"status must be one of {_VALID_STATUSES}")
    row = db.get(AutomationRequest, request_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Automation request not found")
    row.status = new_status
    if note is not None:
        row.note = note
    db.commit()
    db.refresh(row)
    return AutomationRequestOut.model_validate(row)
