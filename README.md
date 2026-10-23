# 100 TIMES — Autonomous Event Discovery, Trust & AI-Driven Growth Platform

**100 TIMES** is an enterprise-grade, full-stack event discovery marketplace, attendee networking ecosystem, and autonomous AI-driven growth platform. It pairs a modern global event marketplace (Conferences, Expos, Summits, Workshops, Organizers, Venues, Speakers, Cities, and Sectors) with an integrated suite of **Autonomous AI Agents** orchestrated via **LangGraph**, **Google Gemini**, **Anthropic Claude**, and **FastAPI** for continuous event discovery, organizer outreach, trust scoring, and multi-channel promotion.

---

## Key Pillars & Autonomous Agent Ecosystem

### 1. Global Event Discovery Marketplace & Desk
* **Rich Multi-Dimensional Discovery:** Filter and search global events by sector, city, format (`In-Person`, `Virtual`, `Hybrid`), date range, and popularity.
* **Comprehensive Directories:** Dedicated profile and detail pages for **Events**, **Organizers**, **Venues**, **Speakers**, **Cities**, and **Sectors**.
* **Role-Based Workspaces & Unified Auth:**
  * **Attendee Hub:** Track digital passes, saved events, reviews, networking, and personalized AI recommendations.
  * **Organiser Studio:** 25+ field event builder, automated Trust Agent verification, registration analytics, and attendee communication.
  * **Admin Operations Console (`/admin`):** Central command center for governing AI discovery agents, outreach approval queues, trust reviews, automations, and system telemetry.
* **Friendly Authentication UX:** Seamless account creation with sanitized error handling (no raw technical `401 Unauthorized` errors exposed to users, clear "No account details found" guidance with instant one-click registration).

### 2. Discovery Agent — Autonomous Event & Organizer Research
Discovers upcoming events and verifies organizers across the web and social networks using grounded LLM research and structured extraction:
1. **Query Seed Generation (`query_seeds.py`):** Generates targeted queries across industries, cities, and event formats.
2. **Multi-Source Scraping & Grounded Search:** Scans Google Search (Gemini grounding), Eventbrite, Meetup, Luma, LinkedIn, Facebook, X/Twitter, and Instagram public event channels.
3. **Structured Page Extraction (`page_extractor.py`):** Extracts complete event metadata (title, dates, city, venue, format, registration URL, sector, confidence score).
4. **Organizer Identification & Lead Enrichment:** Discovers official organization websites, domains, and verified contact emails.
5. **Validation & Deduplication (`validation.py`, `storage.py`):** Automatically drops low-confidence matches, validates schemas, and prevents duplicate records.

### 3. Outreach Agent (Agent 2) — Contextual B2B Invitation Engine
Automates personalized invitations to event organizers with strict human-in-the-loop moderation:
* **Eligibility & Threshold Gating:** Enforces match thresholds and contact completeness before drafting emails.
* **Cryptographic Attribution Tracking:** Generates unique tracking URLs (`/api/attribution/click/{token}`) that attribute onboarding stages directly to outreach campaigns.
* **Human-in-the-Loop Moderation:** All generated invitations wait in **Pending Approval** in the Admin Console before dispatch via SMTP.
* **Automated Multi-Stage Follow-ups:** Automatically schedules follow-up drafts if an organizer hasn't responded within configured intervals.

### 4. Trust Agent — Event Verification & Safety Scoring
Evaluates every submitted event for safety, legitimacy, and completeness:
* **Duplicate Detection:** Calculates similarity scores against existing catalog listings and external discovered events.
* **Completeness & Scam Analysis:** Analyzes description quality, location feasibility, organizer credentials, and suspicious phrases.
* **Moderation Queue (`/admin/trust-review`):** High-confidence legitimate events publish instantly; borderline or flagged submissions enter an administrative review queue with one-click Approve, Reject, or Request Changes actions.

### 5. Attendee Agent — Intent Matching & Community Engagement
Listens to permitted community signals (Telegram, Discord, Reddit, RSS) to extract structured attendee interest:
* **Structured Intent Extraction:** Parses user queries into `category`, `location`, `time_range`, `event_type`, and `preferences`.
* **Weighted Relevance Scoring:** Matches user intent against live platform events to draft helpful, context-rich recommendations.
* **Registration Automation:** Coordinates capacity limits, waitlists, RFC 5545 `.ics` calendar sync, and multi-stage reminders (`T-7d`, `T-24h`, `T-1h`).

### 6. Social & Community Promotions
* **Multi-Platform Publishing:** Publishes promotional event briefs to Telegram channels/groups, Discord servers, LinkedIn, Instagram, Facebook, and X.
* **Configurable Cadence & Safety:** Platform-specific rate limiting, customizable targeting by sector, and automated toggle controls.

### 7. Automations & Observability Command Center
* **Unified Automations Dashboard (`/admin/automations`):** Real-time monitoring and toggles for Discovery, Outreach, Trust, and Social agents.
* **Observability & Telemetry (`/admin/observability`):** System health metrics, error rates, agent run history, and audit trails.
* **n8n Workflow Integration:** Eight production n8n workflows for event registration, confirmations, reminders, cancellations, and organizer retention.

---

## System Architecture

```mermaid
flowchart TB
    subgraph Frontend["Frontend — React 19 + TypeScript + Vite + Tailwind CSS"]
        MP["Public Event Marketplace\n(Explore, Sectors, Cities, Organizers, Venues, AI Concierge)"]
        HUB["Attendee Hub & Organiser Studio\n(/dashboard, /organizer)"]
        ADMIN["Admin Operations Console\n(/admin: Discovery, Outreach, Trust, Automations, Observability)"]
    end

    subgraph Backend["Backend — FastAPI + SQLAlchemy 2.0 (Python 3.11+)"]
        API["REST API Routers (/api/*)\nauth | events | discovery | outreach | trust | attendee-agent | automations | observability"]
        DISC["Discovery Agent\n(Web, Social, Eventbrite, Luma)"]
        OUT["Outreach Engine\n(AI Drafting -> Approval -> SMTP)"]
        TRUST["Trust Agent\n(Completeness, Deduplication, Safety)"]
        ATT["Attendee Agent\n(Signal Extraction, Intent Matching)"]
        SOC["Social & Community Promotion Engine"]
        LLM["Unified AI Client Boundary (Gemini / Anthropic)"]
    end

    subgraph Storage["Data & Infrastructure"]
        MYSQL[("MySQL 8.0 (Docker Port 3306)\n58 Production Tables")]
        N8N["n8n Workflow Engine (Port 5678)"]
    end

    MP -->|"@workspace/api-client-react"| API
    HUB -->|"@workspace/api-client-react"| API
    ADMIN -->|"Admin JWT API"| API
    API --> DISC
    API --> OUT
    API --> TRUST
    API --> ATT
    API --> SOC
    DISC --> LLM
    OUT --> LLM
    TRUST --> LLM
    ATT --> LLM
    SOC --> LLM
    API --> MYSQL
    N8N <--> API
```

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, Wouter Router, TanStack React Query, Lucide Icons |
| **Backend API** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2.0, Alembic, PyJWT, passlib / bcrypt |
| **Database** | MySQL 8.0 (Docker container `100times-mysql` on port `3306`), PyMySQL |
| **AI Orchestration** | LangGraph, Google GenAI SDK (`google-genai` with search grounding), Anthropic Claude SDK |
| **Automation** | n8n workflow engine (port 5678), in-process async schedulers |
| **Client Libraries** | `@workspace/api-client-react` (auto-generated typed React Query hooks and custom fetch) |

---

## Repository Structure

```text
100-Times-Event-Platform/
├── artifacts/
│   ├── 100-times/                        # React 19 + Vite Frontend
│   │   ├── src/
│   │   │   ├── App.tsx                   # Main application router, Header, AuthPage & Marketplace
│   │   │   ├── ops/                      # Admin Operations Console:
│   │   │   │   ├── OpsLayout.tsx         # Admin navigation & search layout
│   │   │   │   ├── DashboardPage.tsx     # Operations overview & agent metrics
│   │   │   │   ├── DiscoveryPage.tsx     # Discovered events & organizer leads
│   │   │   │   ├── OutreachPage.tsx      # Outreach campaigns & review queue
│   │   │   │   ├── TrustReviewPage.tsx   # Trust & safety verification queue
│   │   │   │   ├── AutomationsPage.tsx   # Live agent toggle controls & schedules
│   │   │   │   ├── ObservabilityPage.tsx # Telemetry, health & execution metrics
│   │   │   │   └── SettingsPage.tsx      # Target sectors, limits & API configurations
│   │   │   ├── organizer/                # Organiser Studio workspace
│   │   │   └── components/               # UI components (CountrySelect, ErrorBoundary, etc.)
│   │   └── package.json
│   └── api-server/                       # FastAPI Backend + Autonomous Agents
│       ├── backend/
│       │   ├── core/                     # Config, security, rate limiters, telemetry
│       │   ├── routes/                   # API routers (auth, events, discovery, outreach, automations, etc.)
│       │   ├── services/
│       │   │   ├── discovery_agent/      # Agent 1: Multi-source web & social discovery
│       │   │   ├── social_agent/         # Outreach drafting, social connectors & promotion pipelines
│       │   │   ├── attendee_agent/       # Attendee signal parser & event recommendation
│       │   │   ├── community_agent/      # Community discovery & promotion
│       │   │   └── guardrails.py         # Content moderation & safety enforcement
│       │   ├── models.py                 # 58 SQLAlchemy ORM database models
│       │   ├── schemas.py                # Pydantic schemas & data contracts
│       │   └── main.py                   # FastAPI application entrypoint
│       ├── alembic/                      # Database migrations
│       ├── tests/                        # Comprehensive Pytest test suite
│       └── .env.example                  # Environment configuration template
├── lib/
│   ├── api-client-react/                 # Generated React Query hooks & customFetch
│   └── api-spec/                         # OpenAPI specification
├── n8n/workflows/                        # 8 production n8n automation workflows
├── docker-compose.yml                    # Docker Compose stack
├── start_dev.py                          # Unified development launcher script
└── README.md                             # Platform documentation
```

---

## Local Development & Quickstart

### Prerequisites
* **Python 3.11+**
* **Node.js 20+** and **pnpm** (`npm install -g pnpm`)
* **Docker Desktop** (running)

### 1. Database Setup (MySQL 8.0 Container)
Start the MySQL 8.0 Docker container:
```bash
docker run -d --name 100times-mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=Balaji@01 -e MYSQL_DATABASE=100times mysql:8.0
```

### 2. Configure Backend Environment
Copy the backend `.env.example` file:
```bash
cp artifacts/api-server/.env.example artifacts/api-server/.env
```
Ensure `DATABASE_URL` is configured:
```env
DATABASE_URL=mysql+pymysql://root:Balaji%4001@127.0.0.1:3306/100times?charset=utf8mb4
```

### 3. Install Dependencies
**Backend:**
```bash
cd artifacts/api-server
python -m pip install -r requirements.txt
cd ../..
```

**Frontend:**
```bash
pnpm install
```

### 4. Launch Services
**Start FastAPI Backend:**
```bash
cd artifacts/api-server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**Start Vite Frontend:**
```bash
cd artifacts/100-times
npx vite --host 0.0.0.0 --port 5174
```

* **Frontend Marketplace & Admin:** [http://localhost:5174](http://localhost:5174)
* **Backend API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Viewing the Database

### Option A: VS Code Database Client Extension
1. Open the **Database** panel in your VS Code sidebar.
2. Click **Create Connection** / **`+`** ➔ select **MySQL**.
3. Enter connection settings:
   * **Host:** `127.0.0.1`
   * **Port:** `3306`
   * **Username:** `root`
   * **Password:** `Balaji@01`
   * **Database:** `100times`
4. Expand `100times` ➔ `TABLE` to view all 58 tables and interact with live records.

### Option B: Terminal CLI via Docker
Connect directly to the interactive MySQL shell:
```bash
docker exec -it 100times-mysql mysql -u root -p"Balaji@01" 100times
```
Run queries:
```sql
SHOW TABLES;
SELECT id, name, email, role, created_at FROM users;
SELECT id, name, city, start_date, lifecycle_state FROM events;
```

---

## Running Automated Tests

Run the complete backend test suite:
```bash
cd artifacts/api-server
pytest
```

---

## Security & Privacy Policy
* All sensitive credentials, tokens, and database credentials are excluded from version control via strict `.gitignore` rules.
* Human approval gates are enforced for all external email campaigns and borderline trust decisions.
* Built-in SSRF protection, rate limiting, and input sanitization protect all public and administrative endpoints.
