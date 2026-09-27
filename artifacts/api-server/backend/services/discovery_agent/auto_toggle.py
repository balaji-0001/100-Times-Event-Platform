"""Live on/off switch for Agent 1's automatic discovery scan.

Toggleable from the admin console (`PATCH /discovery/auto`) and takes effect
immediately — no backend restart needed. Persisted in the `agent_settings`
table, so it also survives a restart. This is deliberately separate from
`ENABLE_BACKGROUND_SCHEDULER` in `core/config.py`, which is an env var that
gates the three legacy social-agent scheduler loops and still needs a
restart to change; the discovery scan's own loop always runs (see
`services/social_agent/scheduler.py`) and checks this flag on every tick.

Defaults to disabled (no row = off) — the same "nothing runs until you turn
it on" posture as the rest of this console.
"""

from sqlalchemy.orm import Session

from backend.models import AgentSetting

_SETTING_KEY = "discovery_auto_enabled"
_TRUE = "true"
_FALSE = "false"


def is_discovery_auto_enabled(db: Session) -> bool:
    row = db.get(AgentSetting, _SETTING_KEY)
    return row is not None and row.value == _TRUE


def set_discovery_auto_enabled(db: Session, enabled: bool) -> bool:
    row = db.get(AgentSetting, _SETTING_KEY)
    value = _TRUE if enabled else _FALSE
    if row is None:
        db.add(AgentSetting(key=_SETTING_KEY, value=value))
    else:
        row.value = value
    db.commit()
    return enabled
