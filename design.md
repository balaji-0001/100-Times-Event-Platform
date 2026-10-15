# UI/UX & System Design Specification (`design.md`)

**Document Version:** 2.0  
**Design System:** 100 TIMES Obsidian & Gold Luxury Editorial Interface

---

## 1. Aesthetic Direction & Visual Language

100 TIMES combines an **editorial dark-luxury marketplace** for attendees and organizers with a **high-density mission-control telemetry console** for platform administrators.

### 1.1 Color Palette & Surface Tokens
| Token Role | Hex / Tailwind Value | Usage |
| :--- | :--- | :--- |
| **Primary Background** | `#07080C` / `bg-slate-950` | Deep obsidian canvas across studio and ops consoles |
| **Elevated Surface** | `#0F1219` / `bg-slate-900/90` | Cards, wizard steps, moderation panels, modals |
| **Primary Accent (Gold/Amber)** | `#F59E0B` / `amber-500` | Primary CTAs, organizer lifecycle highlights, active tabs |
| **Trust Approved (Emerald)** | `#10B981` / `emerald-500` | `APPROVED`, `PUBLISHED`, `HIGH` confidence badges |
| **Needs Review (Amber)** | `#F59E0B` / `amber-400` | `NEEDS_REVIEW`, `MEDIUM` confidence, waitlist badges |
| **Rejected / Alert (Rose)** | `#F43F5E` / `rose-500` | `REJECTED`, `DUPLICATE`, scam warnings, cancellations |
| **Agent Telemetry (Cyan/Indigo)** | `#06B6D4` / `cyan-400` | Attendee Agent intent signals, n8n webhook activity |

### 1.2 Typography
- **Display / Headings:** Geometric sans-serif with tight tracking (`tracking-tight font-semibold`) for event titles and dashboard headers.
- **Data / Telemetry / Codes:** Monospace (`font-mono`) for registration codes (`100T-XXXXXXXX`), idempotency keys, trust scores, and timestamps.

---

## 2. Screen-by-Screen UX Architecture

### 2.1 Organizer Studio (`/organizer` — `OrganizerStudio.tsx`)
1. **12-Stage Lifecycle Progress Bar:** Persistent horizontal stepper at the top of the studio illuminating the organizer's real-time journey from `DISCOVERY` to `REPEAT_ORGANIZER`.
2. **Onboarding & Organization Profile Drawer:** Captures organization name, website, verified email, phone, default IANA timezone, and social profiles.
3. **7-Step Event Creation & Trust Agent Wizard:**
   - **Step 1 — Essentials:** Title, Category, Summary, Target Audience, Tags.
   - **Step 2 — Date & Timezone:** Event Date, Start/End Time, IANA Timezone (`Asia/Kolkata`, `America/New_York`, `UTC`, etc.).
   - **Step 3 — Location & Mode:** `Offline`, `Online`, or `Hybrid` selector; Venue Name, Full Address, City, State, Country, and Online Meeting URL.
   - **Step 4 — Tickets & Capacity:** Free vs. Paid toggle, Price, Currency, Capacity limit, External Registration URL, Ticket Tiers.
   - **Step 5 — Speakers & Media:** Banner Image URL with preview, Speaker roster (`name`, `role`, `topic`), Contact Info, Social Links, Terms/Cancellation Policy.
   - **Step 6 — Trust Agent Pre-Flight & Submission:** Save as `DRAFT` or submit to **Trust Agent (Agent 3)** for instant verification.
   - **Step 7 — Instant Verdict Card:** Displays live Trust Score (`0–100`), Confidence (`HIGH`/`MEDIUM`/`LOW`), Reasons, Warnings, SEO Public Link (if auto-published), or `"Your event is under review"` banner.

### 2.2 Admin Trust Review Console (`/admin/trust-review` — `TrustReviewPage.tsx`)
- **Left Pane — Moderation Queue:** Filterable by `NEEDS_REVIEW`, `APPROVED`, `REJECTED`, `DUPLICATE` with color-coded score pills.
- **Right Pane — Deep Inspection & Decision Panel:**
  - Organizer identity & verification status.
  - Structured Trust Agent breakdown (`score`, `confidence`, `reasons`, `warnings`, `missing_fields`).
  - **Duplicate Candidates Table:** Side-by-side similarity score and matched fields (`title`, `city`, `date`).
  - **Action Bar:** One-click **Approve & Publish**, **Request Changes**, or **Reject** with mandatory reviewer notes and live audit trail.

### 2.3 Admin Attendee Agent Console (`/admin/attendee-agent` — `AttendeeAgentPage.tsx`)
- **Source Control Cards:** Per-platform toggle switches (`telegram`, `discord`, `reddit`, `community_rss`) with hourly rate-limit utilization bars.
- **Interactive Intent Sandbox:** Paste any natural-language community message (e.g. *"Looking for AI conferences in Hyderabad next month"*), inspect the extracted JSON intent, view ranked `EventMatch` results with relevance percentages, and preview the generated compliant recommendation message.

### 2.4 n8n Workflows & Audit Logs (`/admin/workflows` & `/admin/audit-logs` — `WorkflowsLogsPage.tsx`)
- **8 Workflow Cards:** Shows webhook endpoint, trigger event, status badge, and one-click test trigger for all 8 n8n workflows.
- **Idempotent Automation Runs:** Real-time table of `AutomationRun` executions with `idempotency_key` and payload inspection.
- **Redacted Audit Log Viewer:** Searchable security trail of all platform actions with automatic secret masking.
