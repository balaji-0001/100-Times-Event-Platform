"""Live, restart-free on/off switch for Agent 1's automatic discovery scan.

Backed by the `agent_settings` key/value table (see `models.AgentSetting`),
not `core/config.py` — an env var needs a backend restart to change, this
takes effect on the very next scheduler tick (`services/social_agent/
scheduler.py`'s always-on `event-discovery` loop checks it every tick) and
survives a restart because it's a DB row, not process memory.

Defaults to OFF when no row exists yet: a fresh database should never start
spending AI credits on a timer until an admin explicitly flips this on from
the console. Mirrors the same get/set-via-`AgentSetting` pattern already
used by `services/attendee_agent/agent.py`'s per-source toggles — callers
are expected to `db.commit()` after `set_discovery_auto_enabled` (this
module only flushes), same as that sibling pattern.
"""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import AgentSetting

_KEY = "discovery_auto_enabled"
_KEY_SETTINGS = "discovery_auto_settings"


def is_discovery_auto_enabled(db: Session) -> bool:
    row = db.get(AgentSetting, _KEY)
    if not row:
        return False
    return row.value.lower() in ("true", "1", "yes", "on")


def set_discovery_auto_enabled(db: Session, enabled: bool) -> bool:
    row = db.get(AgentSetting, _KEY)
    if not row:
        row = AgentSetting(key=_KEY, value="true" if enabled else "false")
        db.add(row)
    else:
        row.value = "true" if enabled else "false"
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return enabled


def get_discovery_auto_settings(db: Session) -> dict:
    """Retrieves saved automated discovery scope settings (country, cities, categories, etc.)."""
    row = db.get(AgentSetting, _KEY_SETTINGS)
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def set_discovery_auto_settings(db: Session, settings_dict: dict) -> dict:
    """Updates saved automated discovery scope settings in `agent_settings`."""
    current = get_discovery_auto_settings(db)
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
