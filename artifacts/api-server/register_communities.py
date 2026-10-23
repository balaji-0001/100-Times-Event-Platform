import sys, os, io, json
from datetime import datetime, timezone
from pathlib import Path
import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
API_SERVER_DIR = Path(__file__).resolve().parent
if str(API_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(API_SERVER_DIR))

from backend.db import SessionLocal
from backend.core.config import get_settings
from backend.models import DiscoveredCommunity, Community, CommunitySource

settings = get_settings()
token = settings.telegram_bot_token

candidates = [
    {"handle": "bangalore_jobs", "city": "Bengaluru", "state": "Karnataka", "category": "Technology & Careers", "topics": ["jobs", "bengaluru", "tech", "networking"]},
    {"handle": "pythonindia", "city": "National", "state": "India", "category": "Developers & Software", "topics": ["python", "developers", "coding", "tech"]},
    {"handle": "delhistartups", "city": "Delhi NCR", "state": "Delhi", "category": "Startups & Entrepreneurship", "topics": ["startups", "delhi", "entrepreneurs", "business"]},
    {"handle": "bangalorestartups", "city": "Bengaluru", "state": "Karnataka", "category": "Startups & Technology", "topics": ["startups", "bengaluru", "venture", "tech"]},
    {"handle": "ai_india", "city": "National", "state": "India", "category": "AI & Machine Learning", "topics": ["ai", "machine learning", "data science", "nlp"]},
    {"handle": "computer_science_and_programming", "city": "National", "state": "India", "category": "Computer Science & Engineering", "topics": ["programming", "algorithms", "software", "tech"]},
    {"handle": "grandindiastartup", "city": "National", "state": "India", "category": "Startups & Entrepreneurship", "topics": ["startups", "founders", "investors", "growth"]},
    {"handle": "StartupLanes", "city": "National", "state": "India", "category": "Startups & Networking", "topics": ["startups", "founders", "networking", "funding"]},
    {"handle": "entrepreneurialjourney", "city": "National", "state": "India", "category": "Business & Startups", "topics": ["business", "startups", "scaling", "founders"]},
    {"handle": "carvestartuplabs", "city": "National", "state": "India", "category": "Incubator & Startups", "topics": ["incubator", "startups", "labs", "innovation"]},
    {"handle": "businessindiatelegramgroup", "city": "National", "state": "India", "category": "Business & Finance", "topics": ["business", "finance", "markets", "india"]},
    {"handle": "joingroupforEntrepreneurs", "city": "National", "state": "India", "category": "Startups & Entrepreneurs", "topics": ["entrepreneurs", "startups", "global", "india"]}
]

db = SessionLocal()

print("Verifying Telegram communities and updating database...", flush=True)

verified_communities = []

for c in candidates:
    handle = c["handle"]
    try:
        resp = httpx.get(f"https://api.telegram.org/bot{token}/getChat", params={"chat_id": f"@{handle}"}, timeout=5.0)
        data = resp.json()
        if not data.get("ok"):
            print(f"Skipping @{handle}: {data.get('description')}", flush=True)
            continue
        
        chat = data["result"]
        chat_id = chat.get("id")
        title = chat.get("title") or handle
        chat_type = chat.get("type")
        desc = chat.get("description") or f"Public {chat_type} for {title}"
        invite_url = f"https://t.me/{handle}"
        
        # Get member count if available
        cnt_resp = httpx.get(f"https://api.telegram.org/bot{token}/getChatMemberCount", params={"chat_id": f"@{handle}"}, timeout=5.0)
        member_count = cnt_resp.json().get("result") if cnt_resp.json().get("ok") else None
        
        # Check if already in DiscoveredCommunity
        disc = db.query(DiscoveredCommunity).filter(
            (DiscoveredCommunity.canonical_url == invite_url) | (DiscoveredCommunity.name == title)
        ).first()
        
        if not disc:
            disc = DiscoveredCommunity(
                platform="telegram",
                name=title,
                canonical_url=invite_url,
                invite_url=invite_url,
                description=desc,
                category=c["category"],
                subcategory=c.get("subcategory", "General"),
                topics=c["topics"],
                language="English",
                city=c["city"],
                state=c["state"],
                country="India",
                member_count=member_count,
                promotion_allowed=True,
                automation_allowed=True,
                risk_level="low",
                confidence_score=95,
                discovery_status="NEW",
                verification_notes=[f"Verified via Telegram API: {chat_type} (ID: {chat_id}) with {member_count} members."],
                approval_status="APPROVED",
                connection_status="CONNECTED",
                discovered_at=datetime.now(timezone.utc),
                last_checked_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
            db.add(disc)
            db.flush()
        else:
            disc.name = title
            disc.description = desc
            disc.member_count = member_count or disc.member_count
            disc.city = c["city"]
            disc.state = c["state"]
            disc.category = c["category"]
            disc.topics = c["topics"]
            disc.approval_status = "APPROVED"
            disc.connection_status = "CONNECTED"
            disc.promotion_allowed = True
            disc.automation_allowed = True
            disc.last_checked_at = datetime.now(timezone.utc)
            db.flush()
            
        # Materialize/update in Community table
        comm = db.query(Community).filter(
            (Community.discovered_community_id == disc.id) | (Community.platform_ref == f"telegram_{chat_id}")
        ).first()
        
        if not comm:
            comm = Community(
                platform="telegram",
                name=title,
                slug=f"telegram-{disc.id}-{handle}"[:200],
                url=invite_url,
                rules_text="Be respectful and share relevant tech/startup events.",
                promotion_allowed=True,
                external_links_allowed=True,
                automation_allowed=True,
                risk_level="low",
                quality_score=95,
                discovered_community_id=disc.id,
                platform_ref=f"telegram_{chat_id}",
                created_at=datetime.now(timezone.utc)
            )
            db.add(comm)
            db.flush()
            disc.community_id = comm.id
        else:
            comm.name = title
            comm.platform_ref = f"telegram_{chat_id}"
            comm.promotion_allowed = True
            comm.automation_allowed = True
            disc.community_id = comm.id
            
        db.commit()
        
        info = {
            "disc_id": disc.id,
            "comm_id": comm.id,
            "handle": f"@{handle}",
            "title": title,
            "type": chat_type,
            "chat_id": chat_id,
            "member_count": member_count,
            "city": c["city"],
            "category": c["category"],
            "invite_url": invite_url
        }
        verified_communities.append(info)
        print(f"Registered: {title} ({info['handle']}) | {chat_type} | ID: {chat_id} | Members: {member_count}", flush=True)

    except Exception as exc:
        print(f"Error processing {handle}: {exc}", flush=True)
        db.rollback()

db.close()

out_file = API_SERVER_DIR / "registered_telegram_communities.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(verified_communities, f, indent=2, ensure_ascii=False)

print(f"\nSuccessfully verified and registered {len(verified_communities)} communities in DB!", flush=True)

