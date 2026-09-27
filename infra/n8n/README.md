# n8n <-> FastAPI integration

n8n is a thin orchestration/scheduling layer in front of FastAPI. **All business logic
(AI calls, qualification, matching, publishing, database writes) lives in FastAPI** —
n8n workflows only trigger it and move data between calls. No workflow in this folder
computes a score, calls Claude, or talks to a platform API directly.

## Running n8n locally

```
docker compose up -d n8n postgres
```

n8n is then reachable at **http://localhost:5678**. FastAPI keeps running natively
(`py -3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`, the same command
used throughout local development) — it is *not* required to be containerized for
n8n to reach it.

### Networking note

Because n8n runs inside a Docker container while FastAPI runs on your host machine,
the workflows use `http://host.docker.internal:8000` (Docker Desktop's built-in DNS
name for "the host machine"), **not** `http://localhost:8000` — `localhost` inside
the n8n container would refer to the container itself, not your host.

If you later run FastAPI via `docker compose --profile full up` (the `fastapi`
service in `docker-compose.yml`) instead of natively, switch the workflow URLs to
`http://fastapi:8000` — Docker Compose's internal service-name DNS — since at that
point both containers share the same Docker network.

## Importing the workflows

In the n8n UI: **Workflows -> Import from File**, and pick each JSON file in
`infra/n8n/workflows/`. (They're also mounted read-only inside the container at
`/home/node/workflows` if you prefer importing via n8n's CLI.)

## The six workflows

| Workflow | Trigger | Calls | What it's for |
|---|---|---|---|
| `discovery_webhook.json` | Webhook (`POST /webhook/100times/discover`) | `POST /api/acquisition/discussions/discover` | **The generic, topic-agnostic acquisition agent.** Receives one discussion (any platform, any topic — `{platform, communityName, title, content, url?}`) and returns the full trace: the topic Claude understood, the dynamic search queries it generated, the candidates found on the selected platform, and any opportunities queued for human approval. This workflow has zero topic-specific logic — it's a pure passthrough to FastAPI, which does all the understanding/searching/matching. |
| `discovery.json` | Schedule (every 15 min) | `POST /api/acquisition/run-scan` | Runs a full passive discovery cycle across the connectors (each connector's own `discover_signals()`, not a topic-driven search). Everything from connector discovery through content generation and approval-queue creation happens inside this one FastAPI call. |
| `processing_webhook.json` | Webhook (`POST /webhook/100times/submit-signal`) | `POST /api/acquisition/test-discussion` | Lets something *outside* the normal scan cycle submit a single signal and get back the direct-match pipeline result (matches the signal itself against the catalog — no platform search). Useful for testing the older single-discussion-direct-match path. |
| `publishing_dispatch.json` | Schedule (every 5 min) | `GET /api/acquisition/opportunities?approval_status=scheduled`, then `POST /api/acquisition/opportunities/{id}/publish` per due item | Makes "Schedule" actually mean something: today, scheduling an opportunity only records a timestamp — nothing fires the publish when that time arrives. This workflow polls for scheduled-and-due opportunities and calls the exact same publish endpoint a manual "Publish Now" click would. The human's original schedule decision is still what authorized this — n8n just fires it at the chosen time instead of requiring a second click. The only logic in this workflow is a date comparison and a loop; the real publish flow (validate connection -> validate permission -> publish -> verify) is entirely inside FastAPI. |
| `analytics.json` | Schedule (daily) | `GET /api/acquisition/analytics`, then `POST /api/acquisition/analytics/insights` | Collects the real, code-calculated funnel numbers, then optionally asks Claude for a short qualitative summary (Claude narrates, never computes — the numbers come from real DB aggregation regardless of whether `ANTHROPIC_API_KEY` is set). Wire your own Slack/Email node after the insight call if you want it delivered somewhere. |
| `outreach_followup.json` | Schedule (daily) | `POST /api/acquisition/outreach/process-followups` | Organizer Outreach's 7-day follow-up sweep (see `backend/services/social_agent/outreach/`): sends the one allowed follow-up to organizers who haven't replied, and marks stale follow-ups `NO_RESPONSE` as a terminal status. The initial outreach itself isn't scheduled here — it fires automatically inside `run-scan`/`discover` whenever the discovery pipeline finds a genuinely new event candidate above the match-score threshold with a publicly findable organizer contact. |

**No separate workflow for Human Approval or Tracking:**
- Approval is the human dashboard (`/admin/acquisition`) — already real-time; there's
  no batch/scheduled step to add here in this pass. A future workflow could poll
  pending items and send a Slack/email nudge, but that's a notification nicety, not
  something the pipeline depends on.
- Click tracking is inherently synchronous: `GET /r/{opportunity_id}` (see
  `backend/routes/redirect.py`) records a real `ClickEvent` the instant someone
  clicks, and redirects them. There's nothing for a scheduled workflow to do.

## Authentication

None of these endpoints currently require a bearer token (this mirrors the rest of
the admin API today). If you add auth to the acquisition routes later, add an HTTP
Header Auth credential in n8n and attach it to each HTTP Request node.

## Environment variables

Set in the root `.env` (used by `docker-compose.yml`) or exported before running
`docker compose up`:

```
N8N_ENCRYPTION_KEY=   # required — n8n uses this to encrypt stored credentials; generate a random 32+ char string and keep it stable (rotating it invalidates existing saved credentials)
```
