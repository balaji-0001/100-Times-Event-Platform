"""Script to run Event Discovery Agent and find 20 valid events with proper organizer contacts."""

import sys
from pathlib import Path
_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_find_20_valid_events")

from backend.db import SessionLocal
from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer, OrganizerContact
from backend.services.discovery_agent.orchestrator import run_discovery_agent
from backend.services.discovery_agent.types import DiscoveryConfig


def main():
    db = SessionLocal()
    try:
        print("=" * 80)
        print("STARTING DISCOVERY RUN: TARGETING 20 VALID EVENTS WITH PROPER ORGANIZER CONTACTS")
        print("=" * 80)

        cfg = DiscoveryConfig(
            target_valid_events=20,
            require_organizer_email=True,
            reject_no_organizer=True,
            reject_past_events=True,
            min_title_length=8,
            min_description_length=20,
            events_per_run=200,
            cities=[
                "London", "New York", "San Francisco", "Mumbai", "Bengaluru",
                "Dubai", "Singapore", "Berlin", "Delhi", "Pune"
            ],
            categories=[
                "Technology", "Healthcare", "Finance", "Energy and Power Generation",
                "Pharmaceuticals", "Manufacturing", "Construction", "Telecommunications"
            ],
            sources=["web", "event_platforms", "all"],
            is_manual=True,
        )

        # Create AgentRun record
        run = AgentRun(
            agent_type="discovery",
            status="running",
            started_at=datetime.now(timezone.utc),
            config_snapshot={
                "target_valid_events": 20,
                "require_organizer_email": True,
                "reject_no_organizer": True,
                "cities": cfg.cities,
                "categories": cfg.categories,
            },
            summary={
                "events_discovered": 0,
                "accepted_events": 0,
                "new_events": 0,
                "organizers_found": 0,
                "contacts_found": 0,
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        print(f"Created Agent Run #{run.id}")

        summary = run_discovery_agent(db, cfg, run=run)
        db.refresh(run)

        print("\n" + "=" * 80)
        print(f"RUN #{run.id} SUMMARY: {run.status.upper()}")
        print("=" * 80)
        print(f"Events Discovered: {summary.events_discovered}")
        print(f"Accepted Events:   {summary.accepted_events}")
        print(f"New Events:        {summary.new_events}")
        print(f"Organizers Found:  {summary.organizers_found}")
        print(f"Contacts Found:    {summary.contacts_found}")
        print(f"Duplicates:        {summary.duplicate_events}")

        event_ids = summary.event_ids or []
        print(f"\nFETCHING DETAILS FOR {len(event_ids)} DISCOVERED EVENTS:\n")

        events = db.query(DiscoveredEvent).filter(DiscoveredEvent.id.in_(event_ids)).all() if event_ids else []
        for i, ev in enumerate(events, 1):
            org = db.get(DiscoveredOrganizer, ev.organizer_id) if ev.organizer_id else None
            contacts = org.contacts if org else []
            emails = [c.value for c in contacts if c.contact_type == "email"]
            phones = [c.value for c in contacts if c.contact_type == "phone"]
            linkedins = [c.value for c in contacts if c.contact_type == "linkedin"]

            print(f"[{i:02d}] {ev.name}")
            print(f"     Date:     {ev.date or 'TBD'}")
            print(f"     Location: {ev.city or 'Worldwide'}, {ev.country or 'Global'} | Venue: {ev.venue or 'TBD'}")
            print(f"     Category: {ev.category or 'Other'}")
            print(f"     Event URL:{ev.url}")
            if org:
                print(f"     Organizer: {org.name}")
                print(f"     Email:     {org.email or (emails[0] if emails else 'N/A')}")
                if org.website:
                    print(f"     Website:   {org.website}")
                if phones:
                    print(f"     Phone:     {phones[0]}")
                if linkedins:
                    print(f"     LinkedIn:  {linkedins[0]}")
            else:
                print(f"     Organizer: None")
            print("-" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    main()
