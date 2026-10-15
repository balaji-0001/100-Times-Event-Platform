# Project Memory & Operational Knowledge Base (`memory.md`)

**Last Updated:** 2026-09-28  
**Workspace Root:** `C:\BALAJI\100-Times-Event-Platform\100-Times-Event-Platform`

---

## 1. Runtime & Environment Topology

| Component | Path / Command | Port / URL |
| :--- | :--- | :--- |
| **Backend API (FastAPI)** | `artifacts/api-server` → `.\backend\venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload` | `http://localhost:8000` (`/docs`, `/api/healthz`) |
| **Frontend App (React/Vite)** | `artifacts/100-times` → `pnpm.cmd --filter @workspace/100-times run dev` | `http://localhost:5174` (proxies `/api` → `127.0.0.1:8000`) |
| **Backend Python Venv** | `artifacts/api-server/backend/venv/Scripts/python.exe` | Python 3.11+ with FastAPI, SQLAlchemy, Pytest |
| **n8n Workflow JSONs** | `n8n/workflows/*.json` & `infra/n8n/workflows/*.json` | 8 importable JSON definitions |

---

## 2. Critical Technical Decisions & Lessons Learned

1. **PostgreSQL vs. SQLite Auto-Migration (`backend/db.py`):**
   - PostgreSQL requires `BOOLEAN DEFAULT FALSE`/`TRUE` (not integer `0`/`1`) and `TIMESTAMPTZ` in `ALTER TABLE` statements.
   - More importantly, in PostgreSQL, if an `ALTER TABLE ADD COLUMN` statement fails because the column already exists, the current transaction block enters an aborted state (`InFailedSqlTransaction`). Therefore, `sync_schema_columns(engine)` runs **each `ALTER TABLE` inside its own isolated `with eng.begin() as conn:` block**, ensuring idempotent schema upgrades across restarts.
2. **Trust Agent Duplicate Detection Calibration (`backend/services/trust_agent/agent.py`):**
   - Duplicate candidate matching compares normalized event titles, cities, and dates against both `Event` and `DiscoveredEvent`.
   - Exact or near-identical titles (`similarity >= 0.86`) in the same city/date trigger `DUPLICATE` status (`NEEDS_REVIEW`), while genuinely distinct events from the same organizer with complete fields and verified profiles score `>= 78` (`HIGH` confidence) and auto-publish to `PUBLISHED`.
3. **Timezone-Aware Reminder Calculation (`backend/services/registration_automation.py`):**
   - Reminders (`7d`, `24h`, `1h`) resolve the event's IANA timezone via `zoneinfo.ZoneInfo(event.timezone or "UTC")` and store UTC-normalized `scheduled_for` timestamps in `EventReminder`.
4. **Idempotent Automation & Secret Redaction (`backend/services/audit.py`):**
   - Every webhook or automation execution records a unique `idempotency_key` in `AutomationRun`. Repeated webhook deliveries return the stored result immediately without duplicating notifications or attendance updates.
   - `record_audit_log()` recursively sanitizes keys matching `password`, `secret`, `token`, `api_key`, `authorization`, or `cookie`.

---

## 3. Key Frontend Routes (`artifacts/100-times/src/App.tsx`)

- `/` — Public Event Discovery, Search, Category Filter, Event Modal & Registration Modal
- `/organizer` — Organizer Studio, Onboarding Profile, 12-Stage Lifecycle Bar & 7-Step Event Creation Wizard
- `/admin/trust-review` — Trust Agent (Agent 3) Moderation Queue & Decision Console
- `/admin/attendee-agent` — Attendee Agent Source Controls, Rate Limits & Live Intent Matcher
- `/admin/workflows` — 8 n8n Workflows Status & Idempotent Automation Run Monitor
- `/admin/audit-logs` — Redacted Security & Operational Audit Log Viewer
- `/ops/discovery` & `/ops/outreach` — Organizer Discovery & Outreach Pipeline Ops
