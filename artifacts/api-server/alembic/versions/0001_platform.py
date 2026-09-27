"""Create the platform schema, including networking connections."""

from alembic import op
from sqlalchemy import inspect

from backend.db import Base
from backend import models  # noqa: F401

revision = "0001_platform"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The original workspace schema may already exist from the starter app.
    # create_all is intentionally used here so this migration is safe on both
    # a fresh database and an existing Replit development database.
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "connections" in inspector.get_table_names():
        op.drop_table("connections")