# Technical Requirements Document (TRD) — 100 TIMES Event Platform

**Document Version:** 2.0  
**Status:** Production-Ready & Verified

---

## 1. System Stack & Runtime Specifications

| Layer | Technology | Version / Specification |
| :--- | :--- | :--- |
| **Backend Runtime** | Python + FastAPI + Uvicorn | Python 3.11+, ASGI async/sync hybrid |
| **ORM & Database** | SQLAlchemy 2.0 + PostgreSQL / SQLite | Auto-migrating schema via `sync_schema_columns()` |
| **Frontend Framework** | React + TypeScript + Vite + Tailwind CSS | React 19, Vite 7.3 (`port 5174`), Wouter Router |
| **AI / LLM Client** | Unified AI Client (`backend/ai_client.py`) | Supports Gemini (`google-genai`), OpenAI, and deterministic fallback |
| **Workflow Engine** | n8n + Secured REST Webhooks | 8 JSON workflows communicating via `/api/webhooks/n8n/*` |
| **Timezone & Calendar** | `zoneinfo.ZoneInfo` + RFC 5545 `VCALENDAR` | Full IANA timezone support + downloadable `.ics` invites |

---

## 2. Data Contracts & Core Schemas

### 2.1 Trust Agent Output Contract (`TrustEvaluationResult`)
```json
{
  "status": "APPROVED | NEEDS_REVIEW | REJECTED | DUPLICATE",
  "score": 88,
  "confidence": "HIGH | MEDIUM | LOW",
  "reasons": [
    "Organizer profile and organization details are verified",
    "All 25+ core event metadata fields are present and valid"
  ],
  "warnings": [],
  "duplicate_candidates": [
    {
      "candidate_event_id": 42,
      "similarity_score": 0.91,
      "matched_fields": ["title", "city", "date"]
    }
  ],
  "missing_fields": [],
  "recommended_action": "AUTO_PUBLISH | ADMIN_REVIEW | REJECT"
}
```

### 2.2 Attendee Agent Structured Intent Contract (`AttendeeIntentPayload`)
```json
{
  "category": "AI",
  "location": "Hyderabad",
  "time_range": "next month",
  "event_type": "conference",
  "preferences": ["networking", "offline", "ai"]
}
```

### 2.3 n8n Webhook Envelope & Security Headers
- **Endpoint Prefix:** `/api/webhooks/n8n/{workflow_slug}`
- **Headers:**
  - `X-N8N-Webhook-Secret`: Validated against `N8N_WEBHOOK_SECRET` when configured.
  - `X-Idempotency-Key`: Optional header (or body `idempotency_key`) enforced against `automation_runs.idempotency_key`.

---

## 3. API Endpoint Specifications

| Domain | Method & Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| **Onboarding** | `POST /api/organizer/onboarding/profile` | `ORGANIZER` / `ADMIN` | Create/update `Organization` & `OrganizerProfile` and advance lifecycle |
| **Organizer Events** | `GET /api/organizer/events` | `ORGANIZER` / `ADMIN` | List organizer's events across all states with Trust Agent results |
| **Event Creation** | `POST /api/events` | `ORGANIZER` / `ADMIN` | Create event (`save_as_draft=true` for `DRAFT`, `false` for Trust Agent evaluation) |
| **Trust Agent** | `POST /api/trust-agent/events/{id}/evaluate` | `ORGANIZER` / `ADMIN` | Run Trust Agent (Agent 3) on an event |
| **Trust Moderation** | `POST /api/trust-agent/events/{id}/decide` | `ADMIN` | Approve, Reject, or Request Changes on a held event |
| **Registration** | `POST /api/events/{id}/register` | Public / `ATTENDEE` | Register attendee, enforce capacity/waitlist, schedule reminders |
| **Calendar Feed** | `GET /api/events/{id}/calendar.ics` | Public | Download RFC 5545 `.ics` calendar invite |
| **Attendee Agent** | `POST /api/attendee-agent/process-signal` | `ADMIN` | Extract intent, match events, and generate recommendation |
| **Attendee Sources** | `POST /api/attendee-agent/sources/{source}/toggle` | `ADMIN` | Enable/disable community source and adjust hourly rate limit |
| **n8n Webhooks** | `POST /api/webhooks/n8n/{workflow}` | Webhook Secret | Execute idempotent workflow (`registration`, `confirmation`, `reminders`, `cancellation`, `reschedule`, `post-event-attendee`, `organizer-followup`, `attendance`) |

---

## 4. Non-Functional & Quality Requirements
- **Idempotency Guarantee:** 100% deduplication of repeated webhook payloads via unique index `ix_automation_runs_idempotency_key`.
- **Test Verification:** 195 automated pytest unit and end-to-end integration tests passing in `< 30s`.
- **Zero-Downtime Startup:** Automatic schema synchronization on FastAPI startup without manual Alembic intervention required for local development.
