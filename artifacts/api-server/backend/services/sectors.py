"""Sectors 100 TIMES no longer lists events in.

Technology was removed on 2026-10-29. Its category row and old events stay
in the database (hidden, not deleted), but it is never offered on the site,
in the organiser form or in discovery: the categorizer still recognises
technology events so discovery can reject them, instead of misfiling them
under another sector.
"""

REMOVED_SECTORS: tuple[str, ...] = ("Technology",)
REMOVED_SECTOR_SLUGS: frozenset[str] = frozenset({"technology"})
REMOVED_SECTOR_NOTE = "Technology events aren't listed on 100 TIMES (sector removed)."


def is_removed_sector(value: str | None) -> bool:
    """True for a removed sector's name or slug, in any letter case."""
    v = (value or "").strip().lower()
    return bool(v) and (v in REMOVED_SECTOR_SLUGS or v in {s.lower() for s in REMOVED_SECTORS})
