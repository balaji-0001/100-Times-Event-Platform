"""Attendee profiles: attendee personal details stored apart from organiser data.

Creates `attendee_profiles` and seeds one row per existing attendee account
(role USER) from the profile fields that used to live on `users`. Nothing is
removed from `users`; the copy is skipped for accounts that already have a row.
"""

from alembic import op

revision = "0015_attendee_profiles"
down_revision = "0014_social_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from backend.models import AttendeeProfile

    bind = op.get_bind()
    AttendeeProfile.__table__.create(bind, checkfirst=True)
    op.execute(
        """
        INSERT INTO attendee_profiles (user_id, country, job_title, company, bio, created_at, updated_at)
        SELECT u.id, u.country, u.job_title, u.company, u.bio, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM users u
        WHERE UPPER(u.role) = 'USER'
          AND NOT EXISTS (SELECT 1 FROM attendee_profiles p WHERE p.user_id = u.id)
        """
    )


def downgrade() -> None:
    op.drop_table("attendee_profiles")
