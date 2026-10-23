"""Community Discovery Agent ("Agent 5") — new tables (discovered_communities,
community_sources), a link column on communities, and extensions to
acquisition_opportunities so it can hold a standalone "community_promotion"
origin (Agent 4's new matching path) alongside its original "discussion_reply"
origin, without duplicating the approval/publish/click-attribution machinery.
"""

from alembic import op
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, inspect

from backend.db import Base
from backend import models  # noqa: F401 - registers all model metadata

revision = "0010_community_discovery"
down_revision = "0009_extended_platform_models"
branch_labels = None
depends_on = None

_COMMUNITIES_COLUMNS = [
    ("discovered_community_id", Integer),
]

_OPPORTUNITY_NEW_COLUMNS = [
    ("source_kind", String(30)),
    ("promoted_event_id", Integer),
    ("target_community_id", Integer),
    ("match_explanation", Text),
]


def _add_missing_columns(inspector, table: str, columns: list[tuple[str, object]]) -> None:
    if table not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns(table)}
    for name, col_type in columns:
        if name not in existing:
            op.add_column(table, Column(name, col_type, nullable=True))


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)

    inspector = inspect(bind)
    _add_missing_columns(inspector, "communities", _COMMUNITIES_COLUMNS)
    _add_missing_columns(inspector, "acquisition_opportunities", _OPPORTUNITY_NEW_COLUMNS)

    # Re-inspect so the backfill/constraint changes below see the new columns.
    inspector = inspect(bind)
    if "acquisition_opportunities" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("acquisition_opportunities")}

        # Every row that already exists came from the original discussion-reply flow.
        if "source_kind" in existing:
            op.execute("UPDATE acquisition_opportunities SET source_kind = 'discussion_reply' WHERE source_kind IS NULL")

        # discussion_id must become nullable so a community_promotion-origin row
        # (no inbound discussion at all) can be inserted.
        discussion_id_col = next((c for c in inspector.get_columns("acquisition_opportunities") if c["name"] == "discussion_id"), None)
        if discussion_id_col is not None and not discussion_id_col["nullable"]:
            op.alter_column("acquisition_opportunities", "discussion_id", existing_type=Integer, nullable=True)

    # Add the two new foreign keys as real constraints where the dialect supports it cheaply
    # (SQLite's ALTER TABLE can't add a constrained FK after the fact — the column alone,
    # already added above, is enough for ORM-level relationships to work either way).
    if bind.dialect.name != "sqlite" and "acquisition_opportunities" in inspector.get_table_names():
        existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("acquisition_opportunities") if fk["name"]}
        if "fk_acquisition_opportunities_promoted_event_id_events" not in existing_fks:
            op.create_foreign_key(
                "fk_acquisition_opportunities_promoted_event_id_events",
                "acquisition_opportunities", "events", ["promoted_event_id"], ["id"],
            )
        if "fk_acquisition_opportunities_target_community_id_communities" not in existing_fks:
            op.create_foreign_key(
                "fk_acquisition_opportunities_target_community_id_communities",
                "acquisition_opportunities", "communities", ["target_community_id"], ["id"],
            )
    if bind.dialect.name != "sqlite" and "communities" in inspector.get_table_names():
        existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("communities") if fk["name"]}
        if "fk_communities_discovered_community_id_discovered_communities" not in existing_fks:
            op.create_foreign_key(
                "fk_communities_discovered_community_id_discovered_communities",
                "communities", "discovered_communities", ["discovered_community_id"], ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for table in ("community_sources", "discovered_communities"):
        if table in inspector.get_table_names():
            op.drop_table(table)

    # New columns on communities/acquisition_opportunities, and the discussion_id
    # nullability relaxation, are left in place on downgrade, matching 0006's
    # asymmetric downgrade style.
