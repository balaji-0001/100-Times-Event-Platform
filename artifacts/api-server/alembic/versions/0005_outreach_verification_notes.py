"""Add verification_notes to discovered_events (event_verification.py)."""

from alembic import op
from sqlalchemy import Column, inspect
from sqlalchemy.types import JSON

from backend.db import Base
from backend import models  # noqa: F401 - registers all model metadata

revision = "0005_outreach_verification_notes"
down_revision = "0004_organizer_outreach"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)

    inspector = inspect(bind)
    if "discovered_events" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("discovered_events")}
        if "verification_notes" not in existing:
            op.add_column("discovered_events", Column("verification_notes", JSON, nullable=True))
            op.execute("UPDATE discovered_events SET verification_notes = '[]' WHERE verification_notes IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "discovered_events" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("discovered_events")}
        if "verification_notes" in existing:
            op.drop_column("discovered_events", "verification_notes")
