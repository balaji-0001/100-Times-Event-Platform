"""Add pipeline state-machine columns to discussions/acquisition_opportunities,
and create the new pipeline_executions, pipeline_stage_logs, click_events,
registration_attributions, and platform_rate_limits tables."""

from alembic import op
from sqlalchemy import Column, Integer, String, Text, inspect
from sqlalchemy.types import JSON

from backend.db import Base
from backend import models  # noqa: F401 - registers all model metadata

revision = "0003_pipeline_architecture"
down_revision = "0002_social_agent_extensions"
branch_labels = None
depends_on = None

DISCUSSION_COLUMNS = {
    "pipeline_status": String(40),
    "ai_intent": JSON(),
    "qualification_score": Integer(),
    "qualification_breakdown": JSON(),
    "rejection_reason": Text(),
    "ai_extraction_retry_count": Integer(),
}

OPPORTUNITY_COLUMNS = {
    "content_generated_by": String(30),
    "policy_notes": JSON(),
}


def _add_missing_columns(bind, table: str, columns: dict) -> None:
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    for name, col_type in columns.items():
        if name not in existing:
            op.add_column(table, Column(name, col_type, nullable=True))


def upgrade() -> None:
    bind = op.get_bind()

    _add_missing_columns(bind, "discussions", DISCUSSION_COLUMNS)
    _add_missing_columns(bind, "acquisition_opportunities", OPPORTUNITY_COLUMNS)

    # Backfill sane defaults on existing rows for the new NOT-NULL-in-model columns.
    op.execute("UPDATE discussions SET pipeline_status = 'PENDING_APPROVAL' WHERE pipeline_status IS NULL")
    op.execute("UPDATE discussions SET qualification_score = 0 WHERE qualification_score IS NULL")
    op.execute("UPDATE discussions SET ai_extraction_retry_count = 0 WHERE ai_extraction_retry_count IS NULL")
    op.execute("UPDATE acquisition_opportunities SET policy_notes = '[]' WHERE policy_notes IS NULL")

    # Brand-new tables — create_all only creates what's missing.
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for table in ("platform_rate_limits", "registration_attributions", "click_events", "pipeline_stage_logs", "pipeline_executions"):
        if table in inspector.get_table_names():
            op.drop_table(table)

    for table, columns in (("discussions", DISCUSSION_COLUMNS), ("acquisition_opportunities", OPPORTUNITY_COLUMNS)):
        if table not in inspector.get_table_names():
            continue
        existing = {col["name"] for col in inspector.get_columns(table)}
        for name in columns:
            if name in existing:
                op.drop_column(table, name)
