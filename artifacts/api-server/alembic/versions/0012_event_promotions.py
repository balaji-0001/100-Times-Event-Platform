"""Social Event Promotions across Instagram, Facebook, LinkedIn, Telegram, and Discord.

Adds `event_promotion_jobs` and `platform_promotion_settings` tables.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0012_event_promotions"
down_revision = "0011_community_platform_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "platform_promotion_settings" not in tables:
        op.create_table(
            "platform_promotion_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("platform", sa.String(50), nullable=False, unique=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("auto_publish", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("default_destination", sa.Text(), nullable=True),
            sa.Column("rate_limit_per_day", sa.Integer(), nullable=False, server_default="20"),
            sa.Column("custom_prompt_template", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_platform_promotion_settings_platform", "platform_promotion_settings", ["platform"])

    if "event_promotion_jobs" not in tables:
        op.create_table(
            "event_promotion_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
            sa.Column("platform", sa.String(50), nullable=False),
            sa.Column("destination_ref", sa.Text(), nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default="PENDING_APPROVAL"),
            sa.Column("is_dry_run", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("media_urls", sa.JSON(), nullable=True),
            sa.Column("utm_params", sa.JSON(), nullable=True),
            sa.Column("tracking_url", sa.Text(), nullable=True),
            sa.Column("external_post_id", sa.Text(), nullable=True),
            sa.Column("published_url", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("approved_by", sa.Text(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("event_id", "platform", name="uq_event_promotion_platform"),
        )
        op.create_index("ix_event_promotion_jobs_event_id", "event_promotion_jobs", ["event_id"])
        op.create_index("ix_event_promotion_jobs_platform", "event_promotion_jobs", ["platform"])
        op.create_index("ix_event_promotion_jobs_status", "event_promotion_jobs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "event_promotion_jobs" in tables:
        op.drop_table("event_promotion_jobs")
    if "platform_promotion_settings" in tables:
        op.drop_table("platform_promotion_settings")

