# Engineering, Security & Agent Governance Rules (`Rules.md`)

**Document Version:** 2.0  
**Scope:** Backend, Frontend, AI Agents, Database Migrations, and n8n Workflows

---

## 1. Core Architectural & Non-Regression Rules

1. **Preserve Existing Pipelines:** Never break or overwrite existing Organizer Discovery (`DiscoveredEvent`), Contact Enrichment (`OrganizerLead`), Outreach (`OutreachMessage`), or Attribution (`/api/attribution/*`) flows.
2. **Single Authentication System:** Always use the unified JWT + HTTP-only cookie authentication (`backend/routes/auth.py`). Never introduce duplicate auth tables or competing session middlewares.
3. **Non-Destructive Schema Evolution:** All database schema additions must be backward-compatible (`NULL`-safe or sensible defaults) and registered in `sync_schema_columns()` (`backend/db.py`) using isolated per-statement transaction blocks (`with eng.begin() as conn:`) so PostgreSQL never aborts subsequent alterations if a column already exists.

---

## 2. Trust Agent (Agent 3) Safety Rules

1. **No Blind Auto-Publishing:** The Trust Agent must **never** auto-publish an event unless:
   - `confidence == "HIGH"`
   - `score >= TRUST_AUTO_PUBLISH_MIN_SCORE` (default `78`)
   - `missing_fields` is empty
   - Zero critical scam/prohibited/duplicate warnings exist.
2. **Conservative Fallback:** Whenever evidence is incomplete, external URLs are unverifiable, or organizer identity is unverified, the Trust Agent must default to `NEEDS_REVIEW` (`MEDIUM` or `LOW` confidence) and route the submission to `/admin/trust-review`.
3. **Duplicate Detection Thresholds:** Events matching an existing `Event` or `DiscoveredEvent` on normalized title (`>= 0.86` similarity) within the same city and date window must be flagged as `DUPLICATE` (`DuplicateCandidate`) and held for human inspection.
4. **Mandatory Auditability:** Every automated Trust Agent evaluation and every human admin override (`APPROVE`, `REJECT`, `REQUEST_CHANGES`) must write both a `TrustDecision` row and a redacted `AuditLog` entry.

---

## 3. Attendee Agent Compliance & Anti-Spam Rules

1. **Zero Unauthorized Scraping or Mass Messaging:** The Attendee Agent only processes configured, permitted public community channels (`telegram`, `discord`, `reddit`, `community_rss`).
2. **Strict Rate Limiting:** Every source connector must respect `ATTENDEE_AGENT_RATE_LIMIT_PER_HOUR` and per-source caps configured in `/admin/attendee-agent`.
3. **Instant Kill-Switch:** Any community source can be toggled off immediately via `POST /api/attendee-agent/sources/{source}/toggle` without restarting the server.
4. **High-Relevance Threshold:** Only recommend events when relevance score meets the minimum match threshold (`>= 55/100`) and clearly matches the user's expressed intent (`category`, `location`, `time_range`).

---

## 4. Registration, Timezone & Reminder Rules

1. **Strict Capacity Enforcement:** Registration endpoints must atomically check `confirmed_count < capacity`. When `confirmed_count >= capacity`, new registrations must transition to `WAITLISTED` (never overbook).
2. **Timezone-Aware Scheduling:** All event times and reminder schedules (`T-7d`, `T-24h`, `T-1h`) must use IANA timezone identifiers via Python `zoneinfo.ZoneInfo` and store UTC-normalized timestamps.
3. **Cancelled Suppression:** Never send reminders (`7d`, `24h`, `1h`) if `registration.status == "CANCELLED"` or `event.status == "CANCELLED"`.
4. **Organizer Follow-Up Cap:** Post-event organizer follow-ups (Workflow 7) must wait `1 day` before follow-up #1, `+2 days` before follow-up #2, and strictly stop once `attempt_count >= max_attempts` (default `3`) or once the organizer responds.

---

## 5. Security, Idempotency & Secret Redaction Rules

1. **Webhook Idempotency:** Every n8n webhook and background automation action must pass a deterministic `idempotency_key` to `execute_idempotent_automation()`. Duplicate deliveries must return the cached `AutomationRun` result without re-sending emails or double-incrementing counters.
2. **Secret Redaction in Audit Logs:** `record_audit_log()` must recursively scrub any key containing `password`, `secret`, `token`, `api_key`, `authorization`, or `cookie` before persisting to `AuditLog`.
3. **Graceful Degradation:** Missing external API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `SMTP_PASSWORD`, `N8N_WEBHOOK_SECRET`, etc.) must never crash the server; services must fall back to deterministic rule engines and local database notification logging.
