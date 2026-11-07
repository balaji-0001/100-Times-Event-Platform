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

from psycopg2.extras import Json, execute_values
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


def drop_all_foreign_keys(conn):
    sql = text("""
        SELECT tc.table_name, tc.constraint_name
        FROM information_schema.table_constraints AS tc
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';
    """)
    fks = conn.execute(sql).fetchall()
    logger.info("Temporarily dropping %d foreign key constraints for fast data load...", len(fks))
    for row in fks:
        try:
            conn.execute(text(f'ALTER TABLE "{row[0]}" DROP CONSTRAINT IF EXISTS "{row[1]}";'))
            conn.commit()
        except Exception:
            conn.rollback()


def restore_model_foreign_keys(conn):
    logger.info("Restoring foreign key constraints from models...")
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_key_constraints:
            col_names = ", ".join(f'"{c.name}"' for c in fk.columns)
            ref_col_names = ", ".join(f'"{elem.column.name}"' for elem in fk.elements)
            constraint_name = fk.name or f"fk_{table.name}_{list(fk.columns)[0].name}_{fk.referred_table.name}"
            try:
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD CONSTRAINT "{constraint_name}" '
                    f'FOREIGN KEY ({col_names}) REFERENCES "{fk.referred_table.name}" ({ref_col_names});'
                ))
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.warning("Notice on re-adding FK %s on %s: %s", constraint_name, table.name, e)


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
        drop_all_foreign_keys(tgt_conn)

        # Clear target tables up front
        logger.info("Clearing target tables up front...")
        all_tables_csv = ", ".join(f'"{t}"' for t in common_tables)
        try:
            tgt_conn.execute(text(f"TRUNCATE TABLE {all_tables_csv};"))
            tgt_conn.commit()
        except Exception:
            tgt_conn.rollback()
            for t in common_tables:
                try:
                    tgt_conn.execute(text(f'DELETE FROM "{t}";'))
                    tgt_conn.commit()
                except Exception:
                    tgt_conn.rollback()

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
            insert_query = f'INSERT INTO "{table_name}" ({cols_str}) VALUES %s'

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
                        row_vals = []
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

                            row_vals.append(val)
                        rows_batch.append(tuple(row_vals))

                    if rows_batch:
                        try:
                            raw_conn = tgt_conn.connection.dbapi_connection
                            raw_cursor = raw_conn.cursor()
                            execute_values(raw_cursor, insert_query, rows_batch, page_size=len(rows_batch))
                            raw_conn.commit()
                            tgt_conn.commit()
                            total_migrated_rows += len(rows_batch)
                            rows_batch = []
                        except Exception as e:
                            tgt_conn.rollback()
                            logger.error("Failed to insert into %s: %s", table_name, e)
                            raise

            logger.info("Table '%s' migrated successfully.", table_name)

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
        if hasattr(tgt_conn.connection, "dbapi_connection"):
            tgt_conn.connection.dbapi_connection.commit()

        # Restore all foreign key constraints from models
        restore_model_foreign_keys(tgt_conn)

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
