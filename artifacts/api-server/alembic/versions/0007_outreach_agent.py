"""Organizer Research & 100Times Promotion Agent ("Agent 2") — new
suppressed_contacts table, campaign_id/send_attempt_count columns on
outreach_messages, subject/message made nullable (rows now persist starting
at NEW, before drafting), and a data migration mapping the old
OutreachMessage.status values onto the new spec'd status flow.
"""

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, inspect

from backend.db import Base
from backend import models  # noqa: F401 - registers all model metadata

revision = "0007_outreach_agent"
down_revision = "0006_discovery_agent"
branch_labels = None
depends_on = None

# old OutreachMessage.status -> new status
_STATUS_MAP = {
    "NOT_CONTACTED": "PENDING_APPROVAL",
    "SENT": "DELIVERED",
    "FOLLOW_UP_SENT": "DELIVERED",
    "FAILED": "APPROVED",
    "REPLIED": "REPLIED",
    "NO_RESPONSE": "COMPLETED",
    "IGNORED": "REJECTED",
}

# The PRE-migration shape of outreach_messages, declared explicitly on its own
# MetaData. SQLite can't ALTER constraints in place (the new campaign_id FK,
# relaxing subject/message to nullable), so batch mode has to copy-and-move —
# and handing it this definition as `copy_from` avoids reflecting the live
# table, whose create_all-generated foreign keys are unnamed and would fail
# with "Constraint must have a name".
_old_meta = MetaData()
_OLD_OUTREACH_MESSAGES = Table(
    "outreach_messages",
    _old_meta,
    Column("id", Integer, primary_key=True),
    Column("event_id", Integer, ForeignKey("discovered_events.id"), nullable=False),
    Column("organizer_id", Integer, ForeignKey("discovered_organizers.id")),
    Column("recipient", Text),
    Column("subject", Text, nullable=False),
    Column("message", Text, nullable=False),
    Column("generated_by", String(30), nullable=False),
    Column("status", String(30), nullable=False),
    Column("failure_reason", Text),
    Column("sent_at", DateTime(timezone=True)),
    Column("last_contacted_at", DateTime(timezone=True)),
    Column("response_at", DateTime(timezone=True)),
    Column("follow_up_sent_at", DateTime(timezone=True)),
    Column("message_id", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def upgrade() -> None:
    bind = op.get_bind()

    # Brand-new table (suppressed_contacts) — create_all only creates what's missing.
    Base.metadata.create_all(bind=bind, checkfirst=True)

    inspector = inspect(bind)
    if "outreach_messages" not in inspector.get_table_names():
        return

    columns = {col["name"]: col for col in inspector.get_columns("outreach_messages")}
    # On a fresh database create_all already built the table in its final shape,
    # so there is nothing to rewrite — only an existing pre-0007 table needs it.
    needs_rewrite = (
        "campaign_id" not in columns
        or "send_attempt_count" not in columns
        or not columns["subject"]["nullable"]
        or not columns["message"]["nullable"]
    )

    if needs_rewrite:
        with op.batch_alter_table("outreach_messages", copy_from=_OLD_OUTREACH_MESSAGES) as batch_op:
            if "campaign_id" not in columns:
                # Batch mode requires an explicitly named constraint — an unnamed
                # FK fails with "Constraint must have a name" during the rewrite.
                batch_op.add_column(
                    Column(
                        "campaign_id",
                        Integer,
                        ForeignKey("outreach_campaigns.id", name="fk_outreach_messages_campaign_id"),
                        nullable=True,
                    )
                )
            if "send_attempt_count" not in columns:
                batch_op.add_column(Column("send_attempt_count", Integer, nullable=True))
            batch_op.alter_column("subject", existing_type=Text(), nullable=True)
            batch_op.alter_column("message", existing_type=Text(), nullable=True)

    # Rows that predate the column never got the ORM-side default.
    op.execute("UPDATE outreach_messages SET send_attempt_count = 0 WHERE send_attempt_count IS NULL")

    for old_status, new_status in _STATUS_MAP.items():
        op.execute(f"UPDATE outreach_messages SET status = '{new_status}' WHERE status = '{old_status}'")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "suppressed_contacts" in inspector.get_table_names():
        op.drop_table("suppressed_contacts")

    # Added columns / relaxed nullability / the status data migration are left in
    # place on downgrade, matching 0005/0006's asymmetric downgrade style.
