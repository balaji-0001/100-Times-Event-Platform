"""Database Migration Utility: MySQL / SQLite to PostgreSQL for 100 Times Platform.

Migrates all tables and records from a source database (MySQL or SQLite)
to a PostgreSQL database (local or hosted on Render/Railway/AWS).
Preserves primary key IDs, JSON structures, and updates PostgreSQL SERIAL sequences.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from psycopg2.extras import Json
from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.orm import Session

# Add api-server to path so we can import Base and models
api_server_dir = Path(__file__).resolve().parent.parent / "artifacts" / "api-server"
if str(api_server_dir) not in sys.path:
    sys.path.insert(0, str(api_server_dir))

from backend.core.config import get_settings
from backend.db import sync_schema_columns
from backend.models import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db_migrator")


def normalize_pg_url(url: str) -> str:
    """Ensures Render/Heroku postgres:// URLs use the postgresql+psycopg2 driver."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def normalize_mysql_url(url: str) -> str:
    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+pymysql://", 1)
    return url


def migrate(source_url: str, target_url: str, create_schema: bool = True) -> None:
    source_url = normalize_mysql_url(source_url)
    target_url = normalize_pg_url(target_url)

    logger.info("Source DB: %s", source_url.split("@")[-1] if "@" in source_url else source_url)
    logger.info("Target DB: %s", target_url.split("@")[-1] if "@" in target_url else target_url)

    src_engine = create_engine(source_url)
    tgt_engine = create_engine(target_url)

    if create_schema:
        logger.info("Initializing schema and synchronizing columns on target PostgreSQL database...")
        Base.metadata.create_all(bind=tgt_engine)
        sync_schema_columns(tgt_engine)
        with tgt_engine.connect() as check_conn:
            try:
                check_conn.execute(text("ALTER TABLE agent_settings ALTER COLUMN value TYPE TEXT;"))
                check_conn.commit()
            except Exception:
                pass
        logger.info("Schema initialized successfully.")

    src_insp = inspect(src_engine)
    tgt_insp = inspect(tgt_engine)

    src_tables = set(src_insp.get_table_names())
    tgt_tables = set(tgt_insp.get_table_names())

    common_tables = [t for t in src_tables if t in tgt_tables]
    # Filter out alembic_version if present
    common_tables = [t for t in common_tables if t != "alembic_version"]

    model_table_order = [t.name for t in Base.metadata.sorted_tables]
    # Sort tables in topological dependency order (parents before children)
    common_tables = sorted(
        common_tables,
        key=lambda name: model_table_order.index(name) if name in model_table_order else 9999,
    )

    logger.info("Found %d common tables to migrate in topological dependency order.", len(common_tables))

    with tgt_engine.connect() as tgt_conn:
        has_replica_role = False
        try:
            tgt_conn.execute(text("SET session_replication_role = 'replica';"))
            tgt_conn.commit()
            has_replica_role = True
            logger.info("Superuser mode: session_replication_role set to 'replica'.")
        except Exception:
            logger.info("Managed Cloud DB: using strict topological dependency order for foreign keys.")

        # Truncate/delete target tables up front (children before parents)
        logger.info("Clearing target tables up front...")
        all_tables_csv = ", ".join(f'"{t}"' for t in reversed(common_tables))
        try:
            tgt_conn.execute(text(f"TRUNCATE TABLE {all_tables_csv} CASCADE;"))
            tgt_conn.commit()
        except Exception as e:
            logger.info("TRUNCATE CASCADE not permitted; deleting rows from child tables first...")
            for t in reversed(common_tables):
                try:
                    tgt_conn.execute(text(f'DELETE FROM "{t}";'))
                    tgt_conn.commit()
                except Exception:
                    pass

        total_migrated_rows = 0

        for table_name in common_tables:
            # Check source row count
            with src_engine.connect() as src_conn:
                src_count = src_conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`" if "mysql" in source_url else f"SELECT COUNT(*) FROM \"{table_name}\"")).scalar() or 0

            if src_count == 0:
                continue

            # Inspect columns
            src_cols = {c["name"]: c for c in src_insp.get_columns(table_name)}
            tgt_cols = {c["name"]: c for c in tgt_insp.get_columns(table_name)}
            matching_cols = [c for c in src_cols if c in tgt_cols]

            cols_str = ", ".join(f'"{c}"' for c in matching_cols)
            placeholders = ", ".join(f":{c}" for c in matching_cols)
            insert_stmt = text(f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})')

            logger.info("Migrating table '%s' (%d rows)...", table_name, src_count)

            with src_engine.connect() as src_conn:
                result = src_conn.execute(text(f"SELECT * FROM `{table_name}`" if "mysql" in source_url else f"SELECT * FROM \"{table_name}\""))
                rows_batch = []
                batch_size = 500

                while True:
                    rows = result.fetchmany(batch_size)
                    if not rows:
                        break

                    for row in rows:
                        row_dict = dict(row._mapping)
                        filtered = {}
                        for col in matching_cols:
                            val = row_dict.get(col)
                            target_type = str(tgt_cols[col]["type"]).upper()

                            if val is not None:
                                if "BOOL" in target_type and isinstance(val, int):
                                    val = bool(val)
                                elif "JSON" in target_type:
                                    if isinstance(val, str):
                                        try:
                                            val = json.loads(val)
                                        except Exception:
                                            pass
                                    val = Json(val)
                                elif "ARRAY" in target_type:
                                    if isinstance(val, str):
                                        try:
                                            val = json.loads(val)
                                        except Exception:
                                            pass
                                    if isinstance(val, list):
                                        val = list(val)
                                elif isinstance(val, (dict, list)):
                                    val = Json(val)

                            filtered[col] = val
                        rows_batch.append(filtered)

                    if rows_batch:
                        tgt_conn.execute(insert_stmt, rows_batch)
                        tgt_conn.commit()
                        total_migrated_rows += len(rows_batch)
                        rows_batch = []

            logger.info("Table '%s' migrated successfully.", table_name)

        # Restore constraints if superuser
        if has_replica_role:
            logger.info("Restoring session_replication_role to 'origin'...")
            try:
                tgt_conn.execute(text("SET session_replication_role = 'origin';"))
                tgt_conn.commit()
            except Exception:
                pass

        # Update all SERIAL sequences so auto-increment IDs work correctly
        logger.info("Updating PostgreSQL SERIAL sequences...")
        update_sequences_sql = text("""
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            FOR r IN (
                SELECT table_name, column_name 
                FROM information_schema.columns 
                WHERE column_default LIKE 'nextval%' AND table_schema = 'public'
            ) LOOP
                EXECUTE format('SELECT setval(pg_get_serial_sequence(''%I'', ''%I''), COALESCE(MAX(%I), 1)) FROM %I',
                               r.table_name, r.column_name, r.column_name, r.table_name);
            END LOOP;
        END $$;
        """)
        tgt_conn.execute(update_sequences_sql)
        tgt_conn.commit()

    logger.info("=======================================================")
    logger.info("Migration Completed Successfully!")
    logger.info("Total rows migrated across all tables: %d", total_migrated_rows)
    logger.info("=======================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate 100 Times DB to PostgreSQL")
    parser.add_argument("--source-url", default=None, help="Source DB URL (default from .env)")
    parser.add_argument(
        "--target-url",
        default="postgresql://postgres:postgres@127.0.0.1:5433/100times",
        help="Target PostgreSQL DB URL (local port 5433 or Render external URL)",
    )
    args = parser.parse_args()

    source = args.source_url or get_settings().database_url
    migrate(source, args.target_url)
