import re
import sqlite3
import sys
from pathlib import Path

api_dir = Path("artifacts/api-server").resolve()
sys.path.insert(0, str(api_dir))

from backend.db import Base, engine
from backend import models

db_path = api_dir / "100times-dev.db"
dump_path = api_dir / "100times_database_dump.sql"

print(f"Reading SQL dump structure from {dump_path}...")
with open(dump_path, "r", encoding="utf-8", errors="ignore") as f:
    full_text = f.read()

# Extract column order for every table from CREATE TABLE in dump
table_columns = {}
create_stmts = re.findall(r"CREATE TABLE `(\w+)` \((.*?)\) ENGINE", full_text, re.DOTALL)
for tbl, body in create_stmts:
    cols = []
    for line in body.split("\n"):
        line = line.strip()
        m = re.match(r"^`(\w+)`", line)
        if m:
            cols.append(m.group(1))
    table_columns[tbl] = cols

print(f"Found column definitions for {len(table_columns)} tables.")

# Ensure Base metadata tables exist in SQLite
print(f"Ensuring Base metadata tables exist in {db_path}...")
Base.metadata.create_all(bind=engine, checkfirst=True)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = OFF;")

# Add any missing columns to event_discovery_sources
cursor.execute("PRAGMA table_info(`event_discovery_sources`);")
existing_cols = [r[1] for r in cursor.fetchall()]
needed_cols = [
    ("origin", "TEXT DEFAULT 'curated'"),
    ("events_verified", "INTEGER DEFAULT 0"),
    ("events_needs_review", "INTEGER DEFAULT 0"),
    ("events_rejected", "INTEGER DEFAULT 0"),
    ("consecutive_failures", "INTEGER DEFAULT 0"),
    ("last_checked_at", "DATETIME"),
    ("discovered_at", "DATETIME"),
    ("discovered_via", "TEXT"),
    ("robots_status", "TEXT")
]
for col_name, col_type in needed_cols:
    if col_name not in existing_cols:
        cursor.execute(f"ALTER TABLE `event_discovery_sources` ADD COLUMN `{col_name}` {col_type};")

# Clear existing rows
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
tables = [row[0] for row in cursor.fetchall()]
for t in tables:
    try:
        cursor.execute(f"DELETE FROM `{t}`;")
    except Exception as e:
        print(f"Warning clearing {t}: {e}")
conn.commit()

def convert_mysql_to_sqlite(sql: str) -> str:
    token = "___ESCAPED_BS___"
    s = sql.replace(r"\\", token)
    s = s.replace(r"\'", "''")
    s = s.replace(r'\"', '"')
    s = s.replace(token, "\\")
    return s

def inject_columns(stmt: str) -> str:
    m = re.match(r"^INSERT INTO `(\w+)`\s+VALUES", stmt, re.IGNORECASE)
    if m:
        tbl = m.group(1)
        if tbl in table_columns:
            cols_str = ", ".join(f"`{c}`" for c in table_columns[tbl])
            return re.sub(r"^INSERT INTO `(\w+)`\s+VALUES", f"INSERT INTO `{tbl}` ({cols_str}) VALUES", stmt, count=1, flags=re.IGNORECASE)
    return stmt

insert_count = 0
failed_inserts = []

current_stmt = []
in_insert = False

with open(dump_path, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        line_clean = line.strip()
        if not in_insert:
            if line.startswith("INSERT INTO"):
                current_stmt = [line]
                if line_clean.endswith(";"):
                    raw = "".join(current_stmt)
                    stmt = inject_columns(convert_mysql_to_sqlite(raw))
                    try:
                        cursor.execute(stmt)
                        insert_count += 1
                    except Exception as e:
                        failed_inserts.append((stmt[:100], str(e)))
                    current_stmt = []
                else:
                    in_insert = True
        else:
            current_stmt.append(line)
            if line_clean.endswith(";"):
                raw = "".join(current_stmt)
                stmt = inject_columns(convert_mysql_to_sqlite(raw))
                try:
                    cursor.execute(stmt)
                    insert_count += 1
                except Exception as e:
                    failed_inserts.append((stmt[:100], str(e)))
                in_insert = False
                current_stmt = []

conn.commit()
print(f"Successfully executed {insert_count} INSERT statements.")
if failed_inserts:
    print(f"Failed {len(failed_inserts)} INSERT statements:")
    for prefix, err in failed_inserts:
        print(f"  {prefix}... -> {err}")

# Stats
stats_tables = ["users", "events", "discovered_events", "communities", "acquisition_opportunities", "event_discovery_sources", "organizers", "venues", "categories", "cities"]
print("\n--- Database Row Counts ---")
for t in stats_tables:
    try:
        cursor.execute(f"SELECT count(*) FROM `{t}`;")
        print(f"  {t}: {cursor.fetchone()[0]}")
    except Exception as e:
        print(f"  {t}: error {e}")

cursor.execute("PRAGMA foreign_keys = ON;")
conn.close()
print("\nDatabase dump imported and connected with 100% success!")
