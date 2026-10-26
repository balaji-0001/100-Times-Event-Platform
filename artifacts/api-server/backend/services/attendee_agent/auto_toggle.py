"""Live, restart-free on/off switch for the attendee notification sweep.

Same `agent_settings` key/value pattern and same default-OFF-until-an-admin-
flips-it behaviour as every other agent's toggle. When on, the scheduler
runs `notifier.run_attendee_notifications` on its interval; when off, the
sweep only runs when an admin presses "Run now". Either way, nothing is ever
sent to an attendee who hasn't given notification consent.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import AgentSetting

_KEY = "attendee_notifications_auto_enabled"


def is_attendee_notifications_auto_enabled(db: Session) -> bool:
    row = db.get(AgentSetting, _KEY)
    if not row:
        return False
    return row.value.lower() in ("true", "1", "yes", "on")


def set_attendee_notifications_auto_enabled(db: Session, enabled: bool) -> bool:
    row = db.get(AgentSetting, _KEY)
    if not row:
        row = AgentSetting(key=_KEY, value="true" if enabled else "false")
        db.add(row)
    else:
        row.value = "true" if enabled else "false"
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return enabled
