"""Add social media acquisition agent columns: content_payload, scheduled_at,
published_at, published_url on acquisition_opportunities."""

from alembic import op
from sqlalchemy import Column, DateTime, Text, inspect
from sqlalchemy.types import JSON

revision = "0002_social_agent_extensions"
down_revision = "0001_platform"
branch_labels = None
depends_on = None

TABLE = "acquisition_opportunities"
NEW_COLUMNS = {
    "content_payload": JSON(),
    "scheduled_at": DateTime(timezone=True),
    "published_at": DateTime(timezone=True),
    "published_url": Text(),
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}
    for name, col_type in NEW_COLUMNS.items():
        if name not in existing_columns:
            op.add_column(TABLE, Column(name, col_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if TABLE not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}
    for name in NEW_COLUMNS:
        if name in existing_columns:
            op.drop_column(TABLE, name)
