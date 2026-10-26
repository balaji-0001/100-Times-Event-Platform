import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
_root = str(Path(__file__).resolve().parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from backend.db import SessionLocal
from backend.models import AgentRun, DiscoveredEvent, DiscoveredOrganizer

db = SessionLocal()
run = db.query(AgentRun).filter(AgentRun.id == 128).first()
event_ids = run.summary.get('event_ids', [])
print(f"Total accepted event IDs in Run #128: {len(event_ids)}")

events = db.query(DiscoveredEvent).filter(DiscoveredEvent.id.in_(event_ids)).all()
for i, ev in enumerate(events, 1):
    org = db.get(DiscoveredOrganizer, ev.organizer_id) if ev.organizer_id else None
    contacts = org.contacts if org else []
    emails = [c.value for c in contacts if c.contact_type == 'email']
    phones = [c.value for c in contacts if c.contact_type == 'phone']
    linkedin = [c.value for c in contacts if c.contact_type == 'linkedin']
    primary_email = org.email or (emails[0] if emails else 'N/A')
    
    print(f"=== EVENT #{i:02d} (ID: {ev.id}) ===")
    print(f"Title:      {ev.name}")
    print(f"Date:       {ev.date or ev.start_date}")
    print(f"Location:   {ev.city or 'TBD'}, {ev.country or 'Global'}")
    print(f"Venue:      {ev.venue or 'TBD'}")
    print(f"Category:   {ev.category or 'Technology'}")
    print(f"Source URL: {ev.url}")
    if org:
        print(f"Organizer:  {org.name}")
        print(f"Email:      {primary_email}")
        print(f"Website:    {org.website or 'N/A'}")
        print(f"Phone:      {phones[0] if phones else 'N/A'}")
        print(f"LinkedIn:   {linkedin[0] if linkedin else 'N/A'}")
        print(f"Confidence: {org.confidence_score}%")
    print()
db.close()
