"""Event Discovery & Organizer Research Agent — new tables (event_sources,
organizer_contacts, agent_runs, outreach_campaigns) and richer structured
columns on discovered_events/discovered_organizers (services/discovery_agent/).
"""

from alembic import op
from sqlalchemy import Column, Date, DateTime, Integer, String, Text, inspect

from backend.db import Base
from backend import models  # noqa: F401 - registers all model metadata

revision = "0006_discovery_agent"
down_revision = "0005_outreach_verification_notes"
branch_labels = None
depends_on = None

_DISCOVERED_EVENT_COLUMNS = [
    ("event_description", Text),
    ("subcategory", Text),
    ("event_date", Date),
    ("start_time", Text),
    ("end_time", Text),
    ("venue", Text),
    ("city", Text),
    ("state", Text),
    ("country", Text),
    ("ticket_url", Text),
    ("source_website", Text),
    ("event_format", String(20)),
    ("confidence_score", Integer),
    ("verification_status", String(20)),
    ("discovery_status", String(20)),
    ("discovered_by", String(30)),
    ("discovered_at", DateTime(timezone=True)),
    ("last_updated_at", DateTime(timezone=True)),
]

_DISCOVERED_ORGANIZER_COLUMNS = [
    ("organizer_type", String(30)),
    ("city", Text),
    ("state", Text),
    ("phone", Text),
    ("confidence_score", Integer),
    ("verified_at", DateTime(timezone=True)),
    ("last_updated_at", DateTime(timezone=True)),
]


def _add_missing_columns(inspector, table: str, columns: list[tuple[str, object]]) -> None:
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    for name, col_type in columns:
        if name not in existing:
            op.add_column(table, Column(name, col_type, nullable=True))


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)

    inspector = inspect(bind)
    _add_missing_columns(inspector, "discovered_events", _DISCOVERED_EVENT_COLUMNS)
    _add_missing_columns(inspector, "discovered_organizers", _DISCOVERED_ORGANIZER_COLUMNS)

    # Re-inspect after adding columns so the backfill below sees them.
    inspector = inspect(bind)
    if "discovered_events" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("discovered_events")}
        if "country" in existing:
            op.execute("UPDATE discovered_events SET country = 'India' WHERE country IS NULL")
        if "confidence_score" in existing:
            op.execute("UPDATE discovered_events SET confidence_score = 0 WHERE confidence_score IS NULL")
        if "verification_status" in existing:
            op.execute("UPDATE discovered_events SET verification_status = 'UNVERIFIED' WHERE verification_status IS NULL")
        if "discovery_status" in existing:
            op.execute("UPDATE discovered_events SET discovery_status = 'NEW' WHERE discovery_status IS NULL")
        if "discovered_by" in existing:
            op.execute("UPDATE discovered_events SET discovered_by = 'social_pipeline' WHERE discovered_by IS NULL")
        if "discovered_at" in existing:
            op.execute("UPDATE discovered_events SET discovered_at = created_at WHERE discovered_at IS NULL")

    if "discovered_organizers" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("discovered_organizers")}
        if "confidence_score" in existing:
            op.execute("UPDATE discovered_organizers SET confidence_score = 0 WHERE confidence_score IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for table in ("outreach_campaigns", "agent_runs", "organizer_contacts", "event_sources"):
        if table in inspector.get_table_names():
            op.drop_table(table)

    # Added columns on discovered_events/discovered_organizers are left in
    # place on downgrade, matching 0005's asymmetric downgrade style.
