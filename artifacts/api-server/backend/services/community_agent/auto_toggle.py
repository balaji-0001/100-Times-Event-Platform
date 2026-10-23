"""Live, restart-free on/off switch for Agent 5's automatic discovery scan.
Exact mirror of `services/discovery_agent/auto_toggle.py` — same
`agent_settings` key/value table, same default-OFF-until-an-admin-flips-it
behaviour.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models import AgentSetting

_KEY = "community_discovery_auto_enabled"


def is_community_discovery_auto_enabled(db: Session) -> bool:
    row = db.get(AgentSetting, _KEY)
    if not row:
        return False
    return row.value.lower() in ("true", "1", "yes", "on")


def set_community_discovery_auto_enabled(db: Session, enabled: bool) -> bool:
    row = db.get(AgentSetting, _KEY)
    if not row:
        row = AgentSetting(key=_KEY, value="true" if enabled else "false")
        db.add(row)
    else:
        row.value = "true" if enabled else "false"
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return enabled
