"""Social connections: accounts connected with the platform's own sign-in.

Adds `social_connections` (Facebook Page + Instagram via Meta, LinkedIn).
New table only — no existing table changes, so `AUTO_CREATE_SCHEMA`
databases that never ran Alembic get the same schema from `create_all`.
"""

from alembic import op

revision = "0014_social_connections"
down_revision = "0013_attendee_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from backend.models import SocialConnection

    SocialConnection.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("social_connections")
