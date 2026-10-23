# Product Requirements Document (PRD) — 100 TIMES Event Platform

**Document Version:** 2.0  
**Status:** Implemented & Verified  
**Platform:** 100 TIMES Autonomous Event Discovery, Trust, Attendee Matching & Automation Platform

---

## 1. Executive Summary & Product Vision

**100 TIMES** is an end-to-end, AI-native event ecosystem that automates both sides of the event marketplace:
1. **Supply Side (Organizers):** Autonomous discovery of high-value events across the web, verified contact enrichment, personalized outreach with cryptographic attribution links, frictionless **Organizer Onboarding**, a **25+ field Event Studio**, automated **Trust Agent (Agent 3)** safety/legitimacy/duplicate evaluation, one-click SEO publishing, and automated post-event retention loops.
2. **Demand Side (Attendees):** Autonomous **Attendee Agent** that listens to permitted public community signals (Telegram, Discord, Reddit, Community RSS), extracts structured attendee intent (`category`, `location`, `time_range`, `event_type`, `preferences`), computes weighted relevance against live platform events, and drafts compliant recommendations—followed by full **Registration Automation**, capacity/waitlist management, RFC 5545 `.ics` calendar invites, and timezone-aware `T-7d`, `T-24h`, and `T-1h` reminders via **n8n**.

---

## 2. Target Personas

| Persona | Role | Core Goals | Key Pain Points Solved |
| :--- | :--- | :--- | :--- |
| **Event Organizer** | Conference host, community lead, workshop creator | Publish events quickly, build trust, maximize attendance, automate reminders & follow-ups | Slow manual approvals, fragmented registration tools, high attendee no-show rates |
| **Event Attendee** | Developer, founder, executive, enthusiast | Discover relevant local/online events without noise, seamless registration, calendar sync | Missing out on niche events, spammy platforms, timezone confusion |
| **Trust & Safety Moderator** | Platform Admin (`ADMIN` role) | Keep the platform free of scams, duplicates, and incomplete listings with minimal manual toil | Reviewing every submission from scratch without structured risk signals or duplicate detection |
| **Growth & Ops Engineer** | Platform Operator | Monitor discovery pipelines, outreach attribution, Attendee Agent rate limits, and n8n workflows | Lack of end-to-end observability, duplicate webhook executions, unredacted logs |

---

## 3. Core Functional Requirements

### 3.1 Organizer Discovery, Outreach & Attribution (Agents 1 & 2)
- **Multi-Source Event Discovery:** Discover external events via SerpAPI, Eventbrite, Meetup, Luma, and Google Search queries (`DiscoveredEvent`).
- **Organizer Lead & Contact Enrichment:** Extract and verify organizer emails/domains (`OrganizerLead`).
- **Personalized Outreach & Attribution:** Generate contextual outreach messages (`OutreachMessage`) containing unique attribution tokens (`/api/attribution/click/{token}`) that pre-fill the Organizer Onboarding flow.

### 3.2 Organizer Onboarding & 12-Stage Lifecycle
- **Authentication & RBAC:** Unified JWT/cookie session management supporting `ORGANIZER`, `ADMIN`, and `ATTENDEE` roles without duplicate auth stacks.
- **Organization & Profile Setup:** Capture organization name, description, website, verified email, phone, social links, and default IANA timezone (`Organization`, `OrganizerProfile`).
- **12-Stage Organizer Progression:** Automatically track and advance organizers through:
  1. `DISCOVERY`
  2. `OUTREACH_SENT`
  3. `CLICKED_LINK`
  4. `ACCOUNT_CREATED`
  5. `PROFILE_COMPLETED`
  6. `EVENT_DRAFT_CREATED`
  7. `EVENT_SUBMITTED`
  8. `TRUST_APPROVED`
  9. `EVENT_PUBLISHED`
  10. `REGISTRATIONS_ACTIVE`
  11. `EVENT_COMPLETED`
  12. `REPEAT_ORGANIZER`

### 3.3 Rich Event Creation & Draft Studio
- **Complete 25+ Field Schema:** Title, description, organizer, organization, category, date, start/end time, IANA timezone, attendance mode (`offline` / `online` / `hybrid`), venue name, full street address, city, state, country, online meeting URL, external registration URL, free/paid toggle, ticket price, ticket tier details, capacity, speaker roster, banner image URL, contact info, social links, terms/cancellation policy, tags, and target audience.
- **Draft & Edit Support:** Save incomplete events as `DRAFT` at any time; edit existing drafts or resubmit events flagged for `NEEDS_REVIEW` without losing data.

### 3.4 Trust Agent (Agent 3) — Automated Moderation & Duplicate Guard
- **Multi-Signal Inspection:** Evaluate organizer verification, domain reputation, field completeness, URL safety, duplicate similarity against existing `Event` and `DiscoveredEvent` records, submission velocity bursts, and prohibited/scam language.
- **Structured Output Contract:** Return `{ status, score, confidence, reasons, warnings, duplicate_candidates, missing_fields, recommended_action }`.
- **Conservative Decision Matrix:**
  - `HIGH` confidence + `score >= 78` + zero critical warnings → `APPROVED` (auto-publish to `PUBLISHED` / `REGISTRATION_OPEN`).
  - `MEDIUM` or `LOW` confidence → `NEEDS_REVIEW` (routed to Admin Trust Review Queue).
  - Duplicate match (`>= 0.86` similarity) → `DUPLICATE`.
  - Prohibited/illegal/scam indicators → `REJECTED`.

### 3.5 Event Publishing & SEO
- **Automated SEO Slug & Metadata:** Generate collision-free slugs, OpenGraph/Twitter social cards, JSON-LD `Event` schema, shareable links, and downloadable `.ics` / Google Calendar / Outlook links.
- **Status Transparency:** Show `"Event published successfully"` for auto-approved events or `"Your event is under review"` for held submissions.

### 3.6 Registration Automation & Timezone-Aware Reminders
- **Overbooking & Waitlist Protection:** Automatically assign `CONFIRMED` when capacity is available or `WAITLISTED` when full.
- **Registration Artifacts:** Issue unique confirmation codes (`100T-XXXXXXXX`), RFC 5545 `.ics` attachments, and organizer notifications.
- **Timezone-Aware Reminder Schedule:** Automatically schedule and dispatch `T-7d`, `T-24h`, and `T-1h` reminders converted to the event/attendee IANA timezone; automatically suppress reminders if registration or event is `CANCELLED`.

### 3.7 Attendee Agent — Intent Discovery & Matching
- **Compliant Public Signal Ingestion:** Support configurable sources (`telegram`, `discord`, `reddit`, `community_rss`) with per-source enable/disable switches and hourly rate limits.
- **Structured Intent Extraction:** Parse natural-language requests (e.g., *"I want AI conferences in Hyderabad next month"*) into `{ category, location, time_range, event_type, preferences }`.
- **Relevance Matching & Drafting:** Score published events across category, city/online mode, date window, and tags; persist `EventMatch` and draft non-spammy recommendations.

### 3.8 n8n Automation & Post-Event Loops
- **8 Reusable Workflows:** Registration (`01`), Confirmation (`02`), Reminders (`03`), Cancellation (`04`), Reschedule (`05`), Post-Event Attendee Feedback (`06`), Organizer Multi-Touch Follow-Up (`07` with +1d and +2d retries), and Attendance/No-Show Tracking (`08`).

### 3.9 Community Discovery Agent (Agent 5) — Sector-Targeted Community Ingestion
- **Strict 12-Sector Focus:** Discovers public Telegram channels/groups and Discord servers solely for the 12 approved platform sectors (Pharmaceuticals, Healthcare, Energy and Power Generation, Telecommunications, Construction, Mining, Finance, Packaging, Transport and Logistics, Oil and Gas, Textiles, Manufacturing).
- **Two-Stage Ingestion Pipeline:**
  1. *Stage 1: Sector Seed Ingestion:* Discovers and validates curated industry directories and sector channels across all 12 categories, ensuring baseline coverage even if external search engines throttle.
  2. *Stage 2: Web Search Discovery:* Generates sector-specific query seeds (`site:t.me {keyword} India`, `site:discord.gg {keyword} India`, qualifiers, and city pairings) interleaved round-robin across all 12 sectors.
- **Strict Qualification Gate:** Only communities verified to belong to one of the 12 approved sectors are persisted; candidates categorized as "Other" or non-approved domains are strictly skipped.
- **Approval & Connection Workflow:** Discovered communities are ingested into the Admin Community Discovery queue (`DISCOVERED` or `NEEDS_REVIEW`), where admins review metadata and authorize promotion.

### 3.10 Fully Automated Multi-Mode Social Publishing (Bot & User-Level)
- **Bot Mode Publishing:** Uses official Discord and Telegram Bot APIs for communities and channels where the 100Times bot is an authorized member/admin.
- **Hands-Free User-Level Automation:**
  - **Discord User Automation Engine (`DiscordUserPublisher`):** Publishes event drops into external Discord servers where a dedicated user account is a member via `DISCORD_USER_TOKEN`. Simulates natural human typing delays, includes jitter, and supports server auto-joining via invite links (`/invites/{code}`) without requiring server admins to install a bot.
  - **Telegram MTProto User Client (`TelegramUserPublisher`):** Utilizes `Telethon` MTProto client API with `StringSession` to auto-join public groups and dispatch automated event recommendations completely hands-free.
  - **Intelligent Routing & Fallback:** Core publishers seamlessly detect user-mode target references and credentials to automatically route messages without manual intervention.

---

## 4. Success Metrics & KPIs
- **Organizer Onboarding Conversion:** % of attributed outreach clicks completing profile + first event submission.
- **Trust Agent Precision:** 0 false-positive auto-publications of scam/prohibited events; >75% auto-approval rate for verified complete listings.
- **Attendee Show-Up Rate:** Reduction in `NO_SHOW` rate via automated `.ics` calendar sync and `T-7d`/`T-24h`/`T-1h` reminders.
- **Repeat Organizer Rate:** % of organizers transitioning from `EVENT_COMPLETED` to `REPEAT_ORGANIZER` via Workflow 7.
