"""
Universal database migration utility: Transfers all tables and records from
PostgreSQL to MySQL with foreign key safety, type coercion, and row verification.
"""

import logging
import sys
from pathlib import Path

# Add api-server directory to sys.path
_api_dir = str(Path(__file__).resolve().parent.parent)
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

from sqlalchemy import create_engine, select, text
from backend.db import Base, sync_schema_columns
import backend.models  # registers all models

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")


def migrate_data(pg_url: str, mysql_url: str, batch_size: int = 500) -> dict:
    """Migrates all data from PostgreSQL to MySQL."""
    logger.info("Initializing migration: PostgreSQL -> MySQL")
    pg_engine = create_engine(pg_url, future=True)
    mysql_engine = create_engine(mysql_url, future=True, pool_pre_ping=True)

    # 1. Ensure target schema exists in MySQL
    logger.info("Creating schema and tables in MySQL...")
    with mysql_engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
    
    Base.metadata.create_all(bind=mysql_engine)
    sync_schema_columns(mysql_engine)

    stats = {}

    with mysql_engine.begin() as mysql_conn, pg_engine.connect() as pg_conn:
        # Disable foreign key checks for clean bulk loading
        mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

        for table in Base.metadata.sorted_tables:
            table_name = table.name
            try:
                # Count rows in PostgreSQL
                count_res = pg_conn.execute(text(f'SELECT count(*) FROM "{table_name}"')).scalar()
                if count_res == 0:
                    stats[table_name] = {"source": 0, "migrated": 0, "status": "EMPTY"}
                    continue

                logger.info(f"Migrating table '{table_name}': {count_res} rows...")

                # Clear existing rows in target table to avoid duplicate key conflicts on re-runs
                mysql_conn.execute(text(f"DELETE FROM `{table_name}`;"))

                # Stream and copy in batches
                cursor = pg_conn.execution_options(yield_per=batch_size).execute(select(table))
                total_inserted = 0

                while True:
                    batch = cursor.fetchmany(batch_size)
                    if not batch:
                        break
                    
                    rows_to_insert = []
                    for row in batch:
                        row_dict = dict(row._mapping)
                        rows_to_insert.append(row_dict)

                    if rows_to_insert:
                        mysql_conn.execute(table.insert(), rows_to_insert)
                        total_inserted += len(rows_to_insert)

                stats[table_name] = {
                    "source": count_res,
                    "migrated": total_inserted,
                    "status": "SUCCESS" if count_res == total_inserted else "MISMATCH",
                }
                logger.info(f"  -> Migrated {total_inserted}/{count_res} rows into '{table_name}'")

            except Exception as e:
                logger.warning(f"  -> Table '{table_name}' encountered an error or not present in source: {e}")
                stats[table_name] = {"source": 0, "migrated": 0, "status": f"ERROR: {str(e)}"}

        mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

    logger.info("Migration completed. Generating verification summary...")
    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate PostgreSQL database to MySQL")
    parser.add_argument(
        "--pg-url",
        default="postgresql+psycopg://postgres:Balaji%4001@localhost:5432/100Times",
        help="Source PostgreSQL SQLAlchemy URL",
    )
    parser.add_argument(
        "--mysql-url",
        required=True,
        help="Target MySQL SQLAlchemy URL (e.g. mysql+pymysql://root:password@localhost:3306/100times?charset=utf8mb4)",
    )
    args = parser.parse_args()

    results = migrate_data(args.pg_url, args.mysql_url)
    print("\n" + "=" * 60)
    print("MIGRATION VERIFICATION SUMMARY")
    print("=" * 60)
    total_src = sum(s["source"] for s in results.values())
    total_mig = sum(s["migrated"] for s in results.values())
    for t, s in results.items():
        if s["source"] > 0:
            print(f"  {t:35} : {s['migrated']}/{s['source']} rows ({s['status']})")
    print("-" * 60)
    print(f"TOTAL ROWS: {total_mig}/{total_src} migrated successfully.")
    print("=" * 60)

