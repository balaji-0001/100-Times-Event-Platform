import re
import sqlite3
from pathlib import Path

dump_path = Path("artifacts/api-server/100times_database_dump.sql")
db_path = Path("artifacts/api-server/100times-dev.db")

# Parse columns from dump
dump_cols = {}
with open(dump_path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

create_stmts = re.findall(r"CREATE TABLE `(\w+)` \((.*?)\) ENGINE", text, re.DOTALL)
for tbl, body in create_stmts:
    cols = []
    for line in body.split("\n"):
        line = line.strip()
        m = re.match(r"^`(\w+)`", line)
        if m:
            cols.append(m.group(1))
    dump_cols[tbl] = cols

# Connect to SQLite
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

mismatches = []
for tbl, d_cols in dump_cols.items():
    cursor.execute(f"PRAGMA table_info(`{tbl}`);")
    db_col_info = cursor.fetchall()
    db_col_names = [r[1] for r in db_col_info]
    
    missing_in_db = [c for c in d_cols if c not in db_col_names]
    if missing_in_db:
        print(f"Table {tbl} is missing columns in DB: {missing_in_db}")
        mismatches.append((tbl, missing_in_db))

conn.close()
