# Implementation Guide & Codebase Walkthrough (`implementation.md`)

**Document Version:** 2.0  
**Status:** Complete & Verified (`195 passed` pytest tests, `0` frontend build errors)

---

## 1. File-by-File Implementation Map

### 1.1 Database Models & Auto-Migration
- [`artifacts/api-server/backend/models.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/models.py)
  - Extended `Organizer`, `Event`, `Registration`, and `Notification`.
  - Implemented 16 new models: `Organization`, `OrganizerProfile`, `EventLocation`, `Ticket`, `Attendee`, `AttendeeIntent`, `EventMatch`, `TrustReview`, `TrustDecision`, `DuplicateCandidate`, `AgentMessage`, `AutomationRun`, `EventReminder`, `OrganizerFollowup`, `AttendeeFeedback`, `AuditLog`.
- [`artifacts/api-server/backend/db.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/db.py)
  - Added `sync_schema_columns(engine)` to automatically apply non-destructive `ALTER TABLE` statements across PostgreSQL and SQLite.

### 1.2 Backend Agents & Domain Services
- [`artifacts/api-server/backend/services/trust_agent/agent.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/services/trust_agent/agent.py)
  - Implements **Trust Agent (Agent 3)** (`evaluate_event_trust`, `admin_decide_trust_review`), duplicate candidate detection, scam/prohibited keyword scanning, submission velocity checks, and auto-publishing vs. human review routing.
- [`artifacts/api-server/backend/services/attendee_agent/agent.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/services/attendee_agent/agent.py)
  - Implements **Attendee Agent** (`extract_attendee_intent`, `match_events_for_intent`, `process_attendee_signal`, `run_attendee_discovery_cycle`, `set_source_enabled`).
- [`artifacts/api-server/backend/services/registration_automation.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/services/registration_automation.py)
  - Implements registration validation, capacity/waitlist enforcement, `zoneinfo.ZoneInfo` reminder scheduling (`T-7d`, `T-24h`, `T-1h`), event cancellation, event reschedule diffing, attendance/no-show marking, and multi-touch organizer follow-ups.
- [`artifacts/api-server/backend/services/notifications.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/services/notifications.py)
  - Implements all 16 email/in-app notification templates + RFC 5545 `.ics` calendar generator (`generate_ics_content`, `generate_calendar_links`).
- [`artifacts/api-server/backend/services/lifecycle.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/services/lifecycle.py)
  - Implements the 13-state Event Lifecycle machine and 12-stage Organizer Lifecycle machine.
- [`artifacts/api-server/backend/services/audit.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/services/audit.py)
  - Implements `record_audit_log()` with recursive secret/token redaction.

### 1.3 FastAPI Routers
- [`artifacts/api-server/backend/routes/platform_ops.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/routes/platform_ops.py) — Organizer Onboarding, Trust Agent, Attendee Agent, Feedback, Attendance, Calendar `.ics`, and Admin Observability routes.
- [`artifacts/api-server/backend/routes/webhooks_n8n.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/routes/webhooks_n8n.py) — Secured idempotent n8n webhook endpoints (`/api/webhooks/n8n/*`).
- [`artifacts/api-server/backend/routes/events.py`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/api-server/backend/routes/events.py) — Extended event creation (`DRAFT` vs `SUBMITTED`), editing, SEO slug generation, and automated registration flow.

### 1.4 Frontend Application (`artifacts/100-times/src`)
- [`src/organizer/OrganizerStudio.tsx`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/100-times/src/organizer/OrganizerStudio.tsx) — Complete Organizer Studio, Onboarding Profile, 12-Stage Progress Tracker, and 7-Step Event Creation Wizard.
- [`src/ops/TrustReviewPage.tsx`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/100-times/src/ops/TrustReviewPage.tsx) — Admin Trust Review moderation queue (`/admin/trust-review`).
- [`src/ops/AttendeeAgentPage.tsx`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/100-times/src/ops/AttendeeAgentPage.tsx) — Admin Attendee Agent console (`/admin/attendee-agent`).
- [`src/ops/WorkflowsLogsPage.tsx`](file:///c:/BALAJI/100-Times-Event-Platform/100-Times-Event-Platform/artifacts/100-times/src/ops/WorkflowsLogsPage.tsx) — Admin n8n Workflows & Audit Logs (`/admin/workflows`, `/admin/audit-logs`).

### 1.5 n8n Workflows (`/n8n/workflows/` & `/infra/n8n/workflows/`)
- `01-event-registration.json` through `08-attendance.json`.

---

## 2. How to Run & Verify

```powershell
# 1. Start Backend (http://localhost:8000)
cd C:\BALAJI\100-Times-Event-Platform\100-Times-Event-Platform\artifacts\api-server
.\backend\venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 2. Start Frontend (http://localhost:5174)
cd C:\BALAJI\100-Times-Event-Platform\100-Times-Event-Platform
pnpm.cmd --filter @workspace/100-times run dev

# 3. Run Full Pytest Suite (195 tests)
cd C:\BALAJI\100-Times-Event-Platform\100-Times-Event-Platform\artifacts\api-server
.\backend\venv\Scripts\python.exe -m pytest tests/ -q
```
