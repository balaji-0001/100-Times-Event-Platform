"""Agent 4 extension — standalone community-promotion posting.

Adds `communities.platform_ref`: the real internal chat/channel id a
publisher needs to post into a destination without replying to anything
("telegram_<chat_id>" / "discord_<guild_id>_<channel_id>"). Only ever set by
a human once the bot is actually connected — it cannot be derived from a
public invite link.
"""

from alembic import op
from sqlalchemy import Column, Text, inspect

revision = "0011_community_platform_ref"
down_revision = "0010_community_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "communities" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("communities")}
        if "platform_ref" not in existing:
            op.add_column("communities", Column("platform_ref", Text, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "communities" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("communities")}
        if "platform_ref" in existing:
            op.drop_column("communities", "platform_ref")
