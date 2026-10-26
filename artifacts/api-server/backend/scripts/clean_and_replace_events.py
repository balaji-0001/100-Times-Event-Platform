import sys
from pathlib import Path
_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from backend.db import SessionLocal
from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer, OrganizerContact, EventSource
from backend.services.discovery_agent.orchestrator import _process_candidate
from backend.services.discovery_agent.types import DiscoveryConfig, RunSummary, ExtractedEventCandidate, CandidateSource
from backend.services.discovery_agent import categorizer, organizer_identifier

def main():
    db = SessionLocal()
    try:
        # 1. Update event 1176 to Technology
        ev_1176 = db.get(DiscoveredEvent, 1176)
        if ev_1176:
            ev_1176.category = "Technology"
            db.add(ev_1176)
            db.commit()
            print("Updated event #1176 category to Technology")

        # 2. Remove events 1160, 1161, 1162, 1163, 1164 from DiscoveredEvent
        to_remove = [1160, 1161, 1162, 1163, 1164]
        for eid in to_remove:
            ev = db.get(DiscoveredEvent, eid)
            if ev:
                # Remove associated EventSources
                db.query(EventSource).filter(EventSource.discovered_event_id == eid).delete()
                db.delete(ev)
                print(f"Removed non-tech event #{eid}: {ev.name}")
        db.commit()

        # 3. Update Run 128 event_ids list
        run = db.get(AgentRun, 128)
        current_ids = [eid for eid in run.summary.get("event_ids", []) if eid not in to_remove]
        run.summary["event_ids"] = current_ids
        run.summary["accepted_events"] = len(current_ids)
        run.summary["new_events"] = len(current_ids)
        db.add(run)
        db.commit()
        print(f"Run 128 currently has {len(current_ids)} events: {current_ids}")

        # 4. Now discover 5 more valid Technology events to reach 20!
        needed = 20 - len(current_ids)
        print(f"Need {needed} more valid Technology events.")

        cfg = DiscoveryConfig(
            target_valid_events=20,
            require_organizer_email=True,
            reject_no_organizer=True,
            reject_past_events=True,
            min_title_length=8,
            min_description_length=20,
            cities=["London", "San Francisco", "New York", "Berlin", "Singapore"],
            categories=["Technology"],
            sources=["web", "event_platforms", "all"],
            is_manual=True,
        )

        from backend.services.discovery_agent import page_extractor
        tech_urls = [
            "https://conferencegrid.com/conferences/technology/london",
            "https://conferencegrid.com/conferences/technology/new-york",
            "https://conferencegrid.com/conferences/technology/san-francisco",
            "https://dev.events/",
        ]

        summary = RunSummary()
        summary.event_ids = list(current_ids)
        summary.accepted_events = len(current_ids)
        summary.new_events = len(current_ids)

        for page_url in tech_urls:
            if len(summary.event_ids) >= 20:
                break
            print(f"Extracting candidates from: {page_url}")
            try:
                candidates = page_extractor.extract_events_from_page(page_url, max_events=25, cities=cfg.cities)
                print(f"Found {len(candidates)} candidates on {page_url}")
                for cand in candidates:
                    if len(summary.event_ids) >= 20:
                        break
                    cand.category = "Technology"
                    _process_candidate(db, run, cand, cfg, summary, ["Technology"])
                    db.refresh(run)
            except Exception as e:
                print(f"Error scraping {page_url}: {e}")

        # Final check
        db.refresh(run)
        print("=" * 80)
        print(f"FINAL RUN 128 EVENT COUNT: {len(run.summary.get('event_ids', []))}")
        print("=" * 80)

    finally:
        db.close()

if __name__ == "__main__":
    main()
