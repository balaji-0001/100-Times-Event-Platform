"""Live, restart-free on/off switch for Agent 2's automatic work.

Mirrors `services/discovery_agent/auto_toggle.py` exactly, same
`agent_settings` key/value table (see `models.AgentSetting`), same
default-OFF-until-an-admin-flips-it behaviour. One switch controls both of
Agent 2's scheduled ticks (see `services/social_agent/scheduler.py`):
drafting new outreach candidates, and the follow-up sweep for messages that
got no reply. Neither tick ever sends an email — both only ever land a
message at PENDING_APPROVAL (or FOLLOW_UP_DUE); a human still has to
approve and send, same as every manually-triggered outreach run.
"""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import AgentSetting

_KEY = "outreach_auto_enabled"
_KEY_SETTINGS = "outreach_auto_settings"


def is_outreach_auto_enabled(db: Session) -> bool:
    row = db.get(AgentSetting, _KEY)
    if not row:
        return False
    return row.value.lower() in ("true", "1", "yes", "on")


def set_outreach_auto_enabled(db: Session, enabled: bool) -> bool:
    row = db.get(AgentSetting, _KEY)
    if not row:
        row = AgentSetting(key=_KEY, value="true" if enabled else "false")
        db.add(row)
    else:
        row.value = "true" if enabled else "false"
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return enabled


def get_outreach_auto_settings(db: Session) -> dict:
    """Retrieves saved automated outreach scope and cadence settings."""
    row = db.get(AgentSetting, _KEY_SETTINGS)
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def set_outreach_auto_settings(db: Session, settings_dict: dict) -> dict:
    """Updates saved automated outreach scope settings in `agent_settings`."""
    current = get_outreach_auto_settings(db)
    current.update({k: v for k, v in settings_dict.items() if v is not None})
    val = json.dumps(current)
    row = db.get(AgentSetting, _KEY_SETTINGS)
    if not row:
        row = AgentSetting(key=_KEY_SETTINGS, value=val)
        db.add(row)
    else:
        row.value = val
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return current
