# Project Task Tracker & Verification Checklist (`task.md`)

**Status:** 100% Completed & Verified  
**Test Suite:** `195 passed` (`pytest tests/ -q`) | **Frontend Build:** `✓ 1789 modules transformed`

---

## Phase 1 — Codebase Audit & Schema Evolution
- [x] Inspect existing Organizer Discovery (`DiscoveredEvent`), Outreach (`OutreachMessage`), Attribution (`AttributionRecord`), and RBAC auth flows.
- [x] Extend `Organizer`, `Event`, `Registration`, and `Notification` models with backward-compatible columns (`timezone`, `lifecycle_state`, `trust_score`, `trust_status`, `trust_confidence`, `is_free`, `capacity`, `full_address`, `city_name`, `state_name`, `country_name`, `online_meeting_url`, `registration_url`, `ticket_info`, `speaker_info`, `contact_info`, `social_links`, `terms_policy`, `tags`, `target_audience`, `views_count`, `registration_code`, `payment_status`, `calendar_added`).
- [x] Add 16 new SQLAlchemy models (`Organization`, `OrganizerProfile`, `EventLocation`, `Ticket`, `Attendee`, `AttendeeIntent`, `EventMatch`, `TrustReview`, `TrustDecision`, `DuplicateCandidate`, `AgentMessage`, `AutomationRun`, `EventReminder`, `OrganizerFollowup`, `AttendeeFeedback`, `AuditLog`).
- [x] Implement dual-dialect (`PostgreSQL` & `SQLite`) non-destructive auto-migration in `backend/db.py` (`sync_schema_columns`).

## Phase 2 — Organizer Onboarding & 12-Stage Lifecycle
- [x] Preserve existing JWT/cookie authentication (`SIGNUP`, `LOGIN`, `LOGOUT`, `ME`).
- [x] Implement Organizer Onboarding Profile API (`/api/organizer/onboarding/profile`) saving `Organization` and `OrganizerProfile`.
- [x] Implement 12-stage Organizer Lifecycle tracker (`DISCOVERY` → `REPEAT_ORGANIZER`) in `backend/services/lifecycle.py`.

## Phase 3 — Rich Event Creation (25+ Fields) & Draft System
- [x] Support saving incomplete events as `DRAFT` and editing existing drafts without re-entering data.
- [x] Capture all 25+ required fields including venue, full address, city/state/country, online/offline/hybrid mode, IANA timezone, tickets, capacity, speakers, banner, contact, social links, terms, tags, and target audience.

## Phase 4 — Trust Agent (Agent 3) & Admin Moderation
- [x] Build `backend/services/trust_agent/agent.py` (`evaluate_event_trust`, `admin_decide_trust_review`).
- [x] Inspect organizer verification, field completeness, URL safety, submission velocity, prohibited/scam keywords, and duplicate candidates across `Event` and `DiscoveredEvent`.
- [x] Auto-publish `HIGH` confidence safe events (`score >= 78`); route `MEDIUM`/`LOW` confidence or duplicates to `NEEDS_REVIEW`.
- [x] Build `/admin/trust-review` (`TrustReviewPage.tsx`) with Approve, Reject, Request Changes, and Audit History.

## Phase 5 — Event Publishing, SEO & Calendar Sync
- [x] Generate collision-free SEO event slugs, OpenGraph/JSON-LD metadata, and shareable URLs.
- [x] Generate RFC 5545 `.ics` feeds (`/api/events/{id}/calendar.ics`) alongside Google Calendar and Outlook deep links.

## Phase 6 — Registration Automation & Timezone-Aware Reminders
- [x] Enforce capacity limits and automatic `WAITLISTED` assignment when full.
- [x] Issue unique confirmation codes (`100T-XXXXXXXX`) and send confirmation notifications.
- [x] Schedule timezone-aware `T-7d`, `T-24h`, and `T-1h` reminders via `zoneinfo.ZoneInfo`; suppress reminders if cancelled.
- [x] Implement event cancellation, reschedule detection, attendance/no-show tracking, and post-event organizer follow-ups (1-day wait, +2-day wait, max attempts cap).

## Phase 7 — Attendee Agent (Public Community Intent Matching)
- [x] Build `backend/services/attendee_agent/agent.py` with per-source enable/disable and rate limits (`telegram`, `discord`, `reddit`, `community_rss`).
- [x] Extract structured intent (`category`, `location`, `time_range`, `event_type`, `preferences`), compute weighted relevance against published events, and draft compliant recommendations.
- [x] Build `/admin/attendee-agent` (`AttendeeAgentPage.tsx`).

## Phase 8 — 8 Reusable n8n Workflows & Idempotent Webhooks
- [x] Create `/api/webhooks/n8n/*` endpoints backed by `execute_idempotent_automation()`.
- [x] Export all 8 importable n8n JSON workflows to `/n8n/workflows/` and `/infra/n8n/workflows/`.
- [x] Build `/admin/workflows` and `/admin/audit-logs` (`WorkflowsLogsPage.tsx`).

## Phase 9 — Testing, Build Verification & Documentation
- [x] Add end-to-end pytest integration suite (`tests/test_complete_platform_flow.py`) and verify all `195 passed` tests.
- [x] Verify Vite/TypeScript production build (`pnpm --filter @workspace/100-times run build`).
- [x] Create `PRD.md`, `architecture.md`, `Rules.md`, `design.md`, `task.md`, `memory.md`, `trd.md` (`trd..md`), and `implementation.md` (`implemention.md`).
