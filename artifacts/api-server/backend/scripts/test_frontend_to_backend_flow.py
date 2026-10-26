import sys
import time
from pathlib import Path
import httpx

sys.stdout.reconfigure(encoding="utf-8")

_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from backend.core.security import create_access_token

BASE_URL = "http://127.0.0.1:8000"

def test_flow():
    print("=" * 80, flush=True)
    print("TESTING COMPLETE FRONTEND-TO-BACKEND FLOW: WORLDWIDE DISCOVERY SEARCH", flush=True)
    print("=" * 80, flush=True)

    # 1. Admin Bearer token
    token = create_access_token(3, "ADMIN")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    print("Admin authentication: Bearer token generated for Admin User #3", flush=True)

    client = httpx.Client(base_url=BASE_URL, headers=headers, timeout=30.0)

    # Check if any run is currently active, stop it first to start clean
    active_check = client.get("/api/discovery/runs/active").json()
    if active_check.get("active"):
        active_id = active_check["run"]["id"]
        print(f"Stopping pre-existing run #{active_id}...", flush=True)
        client.post(f"/api/discovery/runs/{active_id}/stop")
        time.sleep(1)

    # 2. Trigger Worldwide search with targetValidEvents = 10, exactly like ManualResearchForm
    payload = {
        "targetValidEvents": 10,
        "eventsPerRun": 100,
        "sources": ["web", "event_platforms", "all"],
        "requireOrganizerEmail": True,
        "rejectNoOrganizer": True,
        "rejectPastEvents": True,
        "rejectUnmatchedCategory": True,
        "fallbackToOtherSector": False,
        "minTitleLength": 8,
        "minDescriptionLength": 20,
    }

    print("\nSending frontend discovery request to POST /api/discovery/run...", flush=True)
    start_res = client.post("/api/discovery/run", json=payload)
    assert start_res.status_code == 200, f"Failed to start discovery: {start_res.text}"
    start_data = start_res.json()
    run_id = start_data.get("runId")
    print(f"Discovery run triggered successfully: Run #{run_id} (Status: {start_data.get('status')})", flush=True)

    # 3. Poll active run status exactly like useActiveDiscoveryRun() in the frontend
    print("\nPolling live active run progress (simulating frontend polling)...", flush=True)
    max_wait = 360  # 6 minutes max
    start_time = time.time()
    last_accepted = -1
    final_summary = {}

    while time.time() - start_time < max_wait:
        poll_res = client.get("/api/discovery/runs/active")
        active_data = poll_res.json()
        is_active = active_data.get("active", False)
        active_run = active_data.get("run") or {}
        summary = active_run.get("summary") or {}
        accepted = summary.get("accepted_events", 0)
        discovered = summary.get("events_discovered", 0)

        if accepted != last_accepted:
            print(f"  [Progress] Candidates Explored: {discovered} | Valid Events Accepted: {accepted} / 10 | Status: {active_run.get('status', 'running')}", flush=True)
            last_accepted = accepted

        if not is_active:
            print("\nRun has finished processing!", flush=True)
            time.sleep(2)  # Give DB final flush time
            # Fetch the completed run details
            run_detail = client.get(f"/api/discovery/runs/{run_id}").json()
            final_summary = run_detail.get("summary") or {}
            break
        time.sleep(2)

    # 4. Fetch the organizers using GET /api/discovery/organizers (exact frontend hook useDiscoveredOrganizers)
    orgs_res = client.get("/api/discovery/organizers?limit=5000")
    assert orgs_res.status_code == 200
    org_map = {o["id"]: o for o in orgs_res.json()}

    # 5. Fetch the events for this run using GET /api/discovery/runs/{run_id}/events (exact frontend hook useDiscoveryRunEvents)
    print(f"\nFetching run events via GET /api/discovery/runs/{run_id}/events...", flush=True)
    events_res = client.get(f"/api/discovery/runs/{run_id}/events")
    assert events_res.status_code == 200, f"Failed to fetch run events: {events_res.text}"
    events = events_res.json()
    print(f"Events returned by API for Run #{run_id}: {len(events)}", flush=True)

    print("\n" + "=" * 80, flush=True)
    print(f"VERIFYING DISPLAYED EVENTS IN FRONTEND DISCOVERY PAGE (COUNT: {len(events)})", flush=True)
    print("=" * 80, flush=True)

    assert len(events) >= 10, f"Expected at least 10 valid events, got {len(events)}"

    for i, ev in enumerate(events[:10], 1):
        org = org_map.get(ev.get("organizerId")) or {}
        print(f"[{i:02d}] {ev.get('name')}", flush=True)
        print(f"     Date:       {ev.get('date') or ev.get('eventDate')}", flush=True)
        print(f"     Location:   {ev.get('city')}, {ev.get('country')} | Venue: {ev.get('venue')}", flush=True)
        print(f"     Category:   {ev.get('category')} / {ev.get('subcategory')}", flush=True)
        print(f"     Organizer:  {org.get('name')} | Email: {org.get('email')}", flush=True)
        print(f"     Status:     {ev.get('verificationStatus')} | Confidence: {ev.get('confidenceScore')}%", flush=True)
        print(f"     Source URL: {ev.get('url')}", flush=True)
        print("-" * 80, flush=True)

    print("\nSUCCESS: Complete frontend-to-backend flow verified with real worldwide search!", flush=True)

if __name__ == "__main__":
    test_flow()

