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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
