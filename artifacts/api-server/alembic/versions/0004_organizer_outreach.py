"""Add Organizer Outreach tables: discovered_organizers, discovered_events,
outreach_messages."""

from alembic import op
from sqlalchemy import Boolean, Column

from backend.db import Base
from backend import models  # noqa: F401 - registers all model metadata

revision = "0004_organizer_outreach"
down_revision = "0003_pipeline_architecture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Brand-new tables — create_all only creates what's missing.
    Base.metadata.create_all(bind=bind, checkfirst=True)

    # `blocked` was added to DiscoveredOrganizer after the table shape was
    # otherwise finalized; guard it the same way 0002/0003 guard new columns
    # on tables that might already exist from a fresh create_all above.
    from sqlalchemy import inspect

    inspector = inspect(bind)
    if "discovered_organizers" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("discovered_organizers")}
        if "blocked" not in existing:
            op.add_column("discovered_organizers", Column("blocked", Boolean, nullable=True))
            op.execute("UPDATE discovered_organizers SET blocked = 0 WHERE blocked IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    from sqlalchemy import inspect

    inspector = inspect(bind)
    for table in ("outreach_messages", "discovered_events", "discovered_organizers"):
        if table in inspector.get_table_names():
            op.drop_table(table)
