"""Attendee Agent: preferences, per-event activity, notification ledger.

Adds `attendee_preferences`, `attendee_event_activity` and
`attendee_notification_log`. New tables only — no existing table changes,
so `AUTO_CREATE_SCHEMA` databases that never ran Alembic get the same
schema from `create_all`.
"""

from alembic import op

revision = "0013_attendee_agent"
down_revision = "0012_event_promotions"
branch_labels = None
depends_on = None

_TABLES = ("attendee_preferences", "attendee_event_activity", "attendee_notification_log")


def upgrade() -> None:
    from backend.models import AttendeeEventActivity, AttendeeNotificationLog, AttendeePreference

    bind = op.get_bind()
    for model in (AttendeePreference, AttendeeEventActivity, AttendeeNotificationLog):
        model.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
