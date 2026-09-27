"""Agent settings — new `agent_settings` key/value table, used first for the
live on/off toggle for Agent 1's automatic discovery scan (see
`services/discovery_agent/auto_toggle.py`).
"""

from alembic import op
from sqlalchemy import inspect

from backend.db import Base
from backend import models  # noqa: F401 - registers all model metadata

revision = "0008_agent_settings"
down_revision = "0007_outreach_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "agent_settings" in inspector.get_table_names():
        op.drop_table("agent_settings")
