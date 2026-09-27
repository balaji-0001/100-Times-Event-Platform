# 100 TIMES FastAPI backend

Run these commands from `artifacts/api-server`.

## Local SQLite development (default)

`.env` configures `sqlite:///./100times-dev.db`. On startup, the development
settings create the schema and seed the demo data, so no database service is
required.

```powershell
python -m pip install -r requirements.txt
python run.py
```

Or with direct uvicorn:
```powershell
python -m uvicorn backend.main:app --reload
```

## Local PostgreSQL development

Install PostgreSQL 16+ and ensure its service is running. In `psql`, create a
role and database (choose your own password):

```sql
CREATE ROLE 100times_user WITH LOGIN PASSWORD 'choose-a-local-password';
CREATE DATABASE 100times OWNER 100times_user;
```

Copy `.env.example` to `.env` and set a URL like:

```text
DATABASE_URL=postgresql+psycopg://100times_user:choose-a-local-password@127.0.0.1:5432/100times
```

Apply the tracked schema migration and seed demo records:

```powershell
python -m alembic upgrade head
python -m backend.seed
```

Use `AUTO_CREATE_SCHEMA=false` and `SEED_DEMO_DATA=false` after migration-based
setup if you do not want startup initialization. PostgreSQL URLs using
`postgres://` or `postgresql://` are normalized to the installed `psycopg`
driver automatically.
