from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_url() -> str:
    url = get_settings().database_url
    if url.startswith("sqlite:///./") or url == "sqlite:///100times-dev.db":
        api_server_dir = Path(__file__).resolve().parent.parent
        db_file = api_server_dir / "100times-dev.db"
        return f"sqlite:///{db_file.as_posix()}"
    return url.replace("postgres://", "postgresql+psycopg://", 1).replace(
        "postgresql://", "postgresql+psycopg://", 1
    )


def _engine_options() -> dict:
    """Keep SQLite usable by FastAPI's worker threads without affecting PostgreSQL."""
    if _engine_url().startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


engine = create_engine(_engine_url(), future=True, **_engine_options())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def sync_schema_columns(target_engine=None) -> None:
    """Safely add any newly introduced columns to existing tables so that
    existing SQLite/PostgreSQL databases upgrade cleanly without data loss."""
    from sqlalchemy import inspect, text

    eng = target_engine or engine
    try:
        inspector = inspect(eng)
        existing_tables = set(inspector.get_table_names())
    except Exception:
        return

    alterations: dict[str, list[tuple[str, str]]] = {
        "organizers": [
            ("user_id", "INTEGER"),
            ("discovered_organizer_id", "INTEGER"),
            ("company_name", "TEXT"),
            ("contact_name", "TEXT"),
            ("lifecycle_stage", " VARCHAR(40) DEFAULT 'SIGNED_UP' NOT NULL"),
            ("verified", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("social_links", "JSON"),
            ("created_at", "DATETIME"),
        ],
        "events": [
            ("timezone", "VARCHAR(64) DEFAULT 'Asia/Kolkata' NOT NULL"),
            ("is_free", "BOOLEAN DEFAULT 1 NOT NULL"),
            ("capacity", "INTEGER"),
            ("lifecycle_state", "VARCHAR(40) DEFAULT 'PUBLISHED' NOT NULL"),
            ("full_address", "TEXT"),
            ("city_name", "TEXT"),
            ("state_name", "TEXT"),
            ("country_name", "TEXT DEFAULT 'India'"),
            ("online_meeting_url", "TEXT"),
            ("registration_url", "TEXT"),
            ("ticket_info", "JSON"),
            ("speaker_info", "JSON"),
            ("contact_info", "JSON"),
            ("social_links", "JSON"),
            ("terms_policy", "TEXT"),
            ("tags", "JSON"),
            ("target_audience", "TEXT"),
            ("trust_score", "INTEGER"),
            ("trust_status", "VARCHAR(30)"),
            ("trust_confidence", "VARCHAR(20)"),
            ("views_count", "INTEGER DEFAULT 0 NOT NULL"),
            ("updated_at", "DATETIME"),
        ],
        "registrations": [
            ("registration_code", "VARCHAR(64)"),
            ("attendee_name", "TEXT"),
            ("attendee_email", "TEXT"),
            ("attendee_phone", "TEXT"),
            ("company", "TEXT"),
            ("job_title", "TEXT"),
            ("country", "TEXT"),
            ("payment_status", "VARCHAR(30) DEFAULT 'not_required' NOT NULL"),
            ("calendar_added", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("checked_in_at", "DATETIME"),
            ("cancelled_at", "DATETIME"),
        ],
        "notifications": [
            ("channel", "VARCHAR(30) DEFAULT 'in_app' NOT NULL"),
            ("template_key", "VARCHAR(60)"),
            ("status", "VARCHAR(20) DEFAULT 'sent' NOT NULL"),
            ("metadata_json", "JSON"),
        ],
    }

    with eng.begin() as conn:
        for table_name, cols in alterations.items():
            if table_name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
            for col_name, col_def in cols:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
                    except Exception:
                        pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

