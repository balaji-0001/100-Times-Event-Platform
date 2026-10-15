"""Extended platform models — 16 new platform tables and extended lifecycle/trust columns.

Tables added:
- organizations
- organizer_profiles
- event_locations
- tickets
- attendees
- attendee_intents
- event_matches
- trust_reviews
- trust_decisions
- duplicate_candidates
- agent_messages
- automation_runs
- event_reminders
- organizer_followups
- attendee_feedback
- audit_logs

Columns added to existing tables:
- events: lifecycle_state, trust_score, trust_status, trust_confidence
- organizers: lifecycle_stage
- registrations: registration_code, calendar_added, checked_in_at, cancelled_at
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from backend.db import Base
from backend import models  # noqa: F401 - registers all model metadata

revision = "0009_extended_platform_models"
down_revision = "0008_agent_settings"
branch_labels = None
depends_on = None

NEW_TABLES_REVERSE = [
    "audit_logs",
    "attendee_feedback",
    "organizer_followups",
    "event_reminders",
    "automation_runs",
    "agent_messages",
    "duplicate_candidates",
    "trust_decisions",
    "trust_reviews",
    "event_matches",
    "attendee_intents",
    "attendees",
    "tickets",
    "event_locations",
    "organizer_profiles",
    "organizations",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Create any missing new model tables
    Base.metadata.create_all(bind=bind, checkfirst=True)

    # 2. Add columns to existing tables if missing
    if "events" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("events")}
        if "lifecycle_state" not in existing_cols:
            op.add_column("events", sa.Column("lifecycle_state", sa.String(40), server_default="PUBLISHED", nullable=False))
        if "trust_score" not in existing_cols:
            op.add_column("events", sa.Column("trust_score", sa.Integer(), nullable=True))
        if "trust_status" not in existing_cols:
            op.add_column("events", sa.Column("trust_status", sa.String(30), nullable=True))
        if "trust_confidence" not in existing_cols:
            op.add_column("events", sa.Column("trust_confidence", sa.String(20), nullable=True))

    if "organizers" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("organizers")}
        if "lifecycle_stage" not in existing_cols:
            op.add_column("organizers", sa.Column("lifecycle_stage", sa.String(40), server_default="SIGNED_UP", nullable=False))

    if "registrations" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("registrations")}
        if "registration_code" not in existing_cols:
            op.add_column("registrations", sa.Column("registration_code", sa.String(64), nullable=True))
            op.create_index("ix_registrations_registration_code", "registrations", ["registration_code"])
        if "calendar_added" not in existing_cols:
            op.add_column("registrations", sa.Column("calendar_added", sa.Boolean(), server_default=sa.false(), nullable=False))
        if "checked_in_at" not in existing_cols:
            op.add_column("registrations", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
        if "cancelled_at" not in existing_cols:
            op.add_column("registrations", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Drop new tables in reverse dependency order
    for table_name in NEW_TABLES_REVERSE:
        if table_name in existing_tables:
            op.drop_table(table_name)

