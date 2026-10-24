"""Idempotent demo data loader for the development database."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from backend.core.security import hash_password
from backend.db import SessionLocal
from backend.models import (
    Category,
    City,
    Community,
    Connection,
    Event,
    Message,
    Notification,
    Organizer,
    PlatformRateLimit,
    Registration,
    Review,
    SavedEvent,
    ScheduleItem,
    Speaker,
    User,
    Venue,
)

IMAGE_IDS = [
    "photo-1504274066651-8d31a536b11a",
    "photo-1497366754035-f200968a6e72",
    "photo-1517245386807-bb43f82c33c4",
    "photo-1556761175-b413da4baf72",
    "photo-1497366216548-37526070297c",
    "photo-1551836022-4c4c79ecde51",
]


def image(image_id: str) -> str:
    return f"https://images.unsplash.com/{image_id}?auto=format&fit=crop&w=1200&q=82"


def get_or_create(db, model, lookup: dict, values: dict):
    item = db.scalar(select(model).filter_by(**lookup))
    if not item:
        item = model(**lookup, **values)
        db.add(item)
        db.flush()
    return item


def seed() -> None:
    db = SessionLocal()
    try:
        categories_data = [
            ("Pharmaceuticals", "pharmaceuticals", "Pharmaceutical companies, drug manufacturing, research, and industry developments.", "pill"),
            ("Healthcare", "healthcare", "Hospitals, healthcare providers, medical technology, and healthcare management.", "heart"),
            ("Energy and Power Generation", "energy-and-power-generation", "Conventional and renewable energy, power generation, and sector developments.", "zap"),
            ("Telecommunications", "telecommunications", "Telecom networks, operators, equipment, enterprise IT, and communications technology.", "radio"),
            ("Construction", "construction", "Construction, infrastructure projects, industry trends, and construction technology.", "hard-hat"),
            ("Mining", "mining", "Mining operations, mineral extraction, projects, equipment, and industry news.", "mountain"),
            ("Finance", "finance", "Financial-sector news, business developments, products, and services.", "briefcase"),
            ("Packaging", "packaging", "Packaging materials, machinery, manufacturers, suppliers, and industry innovations.", "package"),
            ("Transport and Logistics", "transport-and-logistics", "Railways, road transport, aviation, shipping, ports, and logistics.", "truck"),
            ("Oil and Gas", "oil-and-gas", "Oil and gas industry news, operations, technology, and business developments.", "flame"),
            ("Textiles", "textiles", "Textile industry news and developments, including businesses and professionals across the textile value chain.", "scissors"),
            ("Manufacturing", "manufacturing", "Manufacturing industry news, industrial operations, technology, and business developments.", "factory"),
            ("Other", "other", "Other industry events, summits, conferences, and exhibitions.", "layers"),
        ]
        categories = [
            get_or_create(db, Category, {"slug": slug}, {"name": name, "description": description, "icon": icon})
            for name, slug, description, icon in categories_data
        ]
        cities_data = [
            ("Bengaluru", "bengaluru", "India"), ("Hyderabad", "hyderabad", "India"), ("Mumbai", "mumbai", "India"),
            ("New Delhi", "new-delhi", "India"), ("Chennai", "chennai", "India"), ("Pune", "pune", "India"),
            ("Singapore", "singapore", "Singapore"), ("Dubai", "dubai", "UAE"), ("London", "london", "United Kingdom"),
            ("New York", "new-york", "United States"),
        ]
        cities = [
            get_or_create(db, City, {"slug": slug}, {"name": name, "country": country, "description": f"A high-signal event city for curious people in {name}."})
            for name, slug, country in cities_data
        ]
        organizer_data = [
            ("Orbit Collective", "orbit-collective", "Independent producers of high-signal gatherings for builders and leaders."),
            ("Nexus Forums", "nexus-forums", "Curated conversations where new markets and new ideas meet."),
            ("The Foundry Network", "the-foundry-network", "A global community for people making the next decade tangible."),
        ]
        organizers = [
            get_or_create(db, Organizer, {"slug": slug}, {"name": name, "description": description, "logo": name[:2].upper()})
            for name, slug, description in organizer_data
        ]
        venues_data = [
            ("HITEX Exhibition Centre", "hitex-exhibition-centre", "Izzat Nagar, Hyderabad", cities[1], 18000),
            ("KTPO Convention Centre", "ktpo-convention-centre", "Whitefield, Bengaluru", cities[0], 12000),
            ("Jio World Convention Centre", "jio-world-convention-centre", "Bandra Kurla Complex, Mumbai", cities[2], 16000),
        ]
        venues = [
            get_or_create(db, Venue, {"slug": slug}, {"name": name, "address": address, "city_id": city.id, "country": city.country, "capacity": capacity, "image": image(IMAGE_IDS[index % len(IMAGE_IDS)])})
            for index, (name, slug, address, city, capacity) in enumerate(venues_data)
        ]
        speaker_data = [
            ("Anika Rao", "anika-rao", "VP, Clinical Research", "Northstar Pharma", ["Drug Development", "Pharma Innovation"]),
            ("Rohan Mehta", "rohan-mehta", "Managing Director", "Arcwell Energy", ["Power Generation", "Renewable Infrastructure"]),
            ("Maya Fernandez", "maya-fernandez", "Chief Medical Officer", "Lumen Health", ["Health Systems", "Clinical Quality"]),
        ]
        speakers = [
            get_or_create(db, Speaker, {"slug": slug}, {"name": name, "title": title, "company": company, "expertise": expertise, "biography": "A generous, practical voice for people building more useful technology and resilient organizations.", "image": image(IMAGE_IDS[index % len(IMAGE_IDS)])})
            for index, (name, slug, title, company, expertise) in enumerate(speaker_data)
        ]
        demo_user = get_or_create(db, User, {"email": "demo@100times.in"}, {"name": "Aarav Mehta", "job_title": "Operations Director", "company": "Voxel Labs", "bio": "Industrial operations and technology leader.", "password_hash": hash_password("DemoPass123!"), "role": "USER", "country": "India"})
        get_or_create(db, User, {"email": "organizer@100times.in"}, {"name": "Orbit Organizer", "job_title": "Head of Programming", "company": "Orbit Collective", "bio": "Curator of conferences and spatial experiences.", "password_hash": hash_password("OrganizerPass123!"), "role": "ORGANIZER", "country": "India"})
        get_or_create(db, User, {"email": "balajiibalu09@gmail.com"}, {"name": "Platform Admin", "job_title": "Operations Lead", "company": "100 TIMES", "bio": "Platform stewardship and catalog quality.", "password_hash": hash_password("AdminPass123!"), "role": "ADMIN", "country": "India"})

        attendees_data = [
            ("Priya Sharma", "priya@pharma-today.org", "Lead Formulation Scientist", "Pharma Core", "Formulation research and sterile injectables.", "India"),
            ("Dev Patel", "dev@powerinfo.io", "Energy Systems Engineer", "GridWorks", "High-voltage transmission and power grid dispatch.", "India"),
            ("Tara Sen", "tara@worldfinance.co", "VP Investments", "Kite Capital", "Capital markets and asset management.", "Singapore"),
            ("Marcus Vance", "marcus@transportadvance.uk", "Logistics Director", "Cargo Signal", "Intermodal freight and automated supply chains.", "United Kingdom"),
        ]
        attendee_users = [
            get_or_create(db, User, {"email": email}, {"name": name, "job_title": title, "company": comp, "bio": bio, "country": country, "password_hash": hash_password("AttendeePass123!"), "role": "USER"})
            for name, email, title, comp, bio, country in attendees_data
        ]

        titles = [
            ("Global Pharma Innovations Summit", 0, "Conference"),
            ("Healthcare Quality Conclave", 1, "Summit"),
            ("Energy & Power Generation Expo", 2, "Exhibition"),
            ("NextGen Telecommunications Forum", 3, "Conference"),
            ("Infrastructure & Construction Conclave", 4, "Summit"),
            ("Future of Mining & Minerals Summit", 5, "Summit"),
            ("Global Finance & Investment Summit", 6, "Conference"),
            ("Sustainable Packaging Expo", 7, "Exhibition"),
            ("Transport & Logistics World", 8, "Trade show"),
            ("Oil & Gas Technology Conclave", 9, "Conference"),
            ("Global Textile Innovations Fair", 10, "Exhibition"),
            ("Advanced Manufacturing Expo", 11, "Trade show"),
        ]
        existing_count = int(db.scalar(select(__import__("sqlalchemy", fromlist=["func"]).func.count(Event.id))) or 0)
        for index in range(existing_count, 100):
            title, category_index, event_type = titles[index % len(titles)]
            city = cities[index % len(cities)]
            event = get_or_create(
                db, Event, {"slug": f"{title.lower().replace(' ', '-')}-{index + 1}"},
                {
                    "title": title, "description": "A focused day for practitioners building what comes next. Expect useful context, generous conversations, and a room full of people who prefer substance over spectacle.",
                    "event_type": event_type, "start_date": date.today() + timedelta(days=14 + index * 3),
                    "end_date": date.today() + timedelta(days=14 + index * 3 + (index % 3)), "start_time": "09:30 AM" if index % 2 == 0 else "10:00 AM",
                    "price": Decimal("0") if index % 5 == 0 else Decimal(str(1499 + (index % 4) * 1000)),
                    "image": image(IMAGE_IDS[index % len(IMAGE_IDS)]), "status": "published", "format": "online" if index % 6 == 0 else "in-person",
                    "category_id": categories[category_index].id, "organizer_id": organizers[index % len(organizers)].id, "venue_id": venues[index % len(venues)].id,
                },
            )
        db.flush()
        first_event = db.scalar(select(Event).order_by(Event.id))
        if first_event:
            if not db.scalar(select(Registration).where(Registration.user_id == demo_user.id, Registration.event_id == first_event.id)):
                db.add(Registration(user_id=demo_user.id, event_id=first_event.id, ticket_type="VIP", status="confirmed"))
                db.add(SavedEvent(user_id=demo_user.id, event_id=first_event.id))
                db.add(Notification(user_id=demo_user.id, title="Your seat is confirmed", message=f"You're registered for {first_event.title}.", is_read=False))
                db.add(Review(user_id=demo_user.id, event_id=first_event.id, rating=5, title="Ideas worth carrying home", comment="The conversations were unusually practical and the speakers stayed close to the work."))

            # Register attendees for the first event
            for att in attendee_users[:3]:
                if not db.scalar(select(Registration).where(Registration.user_id == att.id, Registration.event_id == first_event.id)):
                    db.add(Registration(user_id=att.id, event_id=first_event.id, ticket_type="Standard", status="confirmed"))

            # Seed schedule items for demo user
            sample_sessions = [
                ("09:30 AM", "Opening Keynote: The Shift in Systems", "Context and principles for engineering the next decade."),
                ("11:15 AM", "Panel: Designing for Agency & Intent", "How teams build tools that respect human attention."),
                ("02:00 PM", "Hands-on Lab: Real-time Data Architectures", "Live code and architectural trade-offs with lead engineers."),
            ]
            for stime, stitle, sdetail in sample_sessions:
                if not db.scalar(select(ScheduleItem).where(ScheduleItem.user_id == demo_user.id, ScheduleItem.event_id == first_event.id, ScheduleItem.session_title == stitle)):
                    db.add(ScheduleItem(user_id=demo_user.id, event_id=first_event.id, session_title=stitle, session_time=stime, session_detail=sdetail))

            # Seed connections
            priya = attendee_users[0]
            dev = attendee_users[1]
            if not db.scalar(select(Connection).where(Connection.requester_id == priya.id, Connection.addressee_id == demo_user.id)):
                db.add(Connection(requester_id=priya.id, addressee_id=demo_user.id, status="accepted"))
                db.flush()
                # Seed messages
                db.add(Message(sender_id=priya.id, recipient_id=demo_user.id, content="Hi Aarav! Looking forward to seeing your work at the Forum.", is_read=True))
                db.add(Message(sender_id=demo_user.id, recipient_id=priya.id, content="Thanks Priya! Excited for the design panel. Let's catch up during the morning break.", is_read=True))
                db.add(Message(sender_id=priya.id, recipient_id=demo_user.id, content="Perfect, see you at the exhibition lounge at 11!", is_read=False))

            if not db.scalar(select(Connection).where(Connection.requester_id == dev.id, Connection.addressee_id == demo_user.id)):
                db.add(Connection(requester_id=dev.id, addressee_id=demo_user.id, status="pending"))

            # Seed Approved Communities for Attendee Acquisition Agent
            communities_data = [
                ("reddit", "r/hyderabad", "r-hyderabad", "https://reddit.com/r/hyderabad", "Helpful discussion only. No low-effort self promotion. Direct event links allowed when directly answering user questions.", False, True, False, "low", 93),
                ("reddit", "r/bangalore", "r-bangalore", "https://reddit.com/r/bangalore", "Monthly promo thread available. Recommendations must answer questions genuinely.", False, True, False, "low", 95),
                ("reddit", "r/developersIndia", "r-developersindia", "https://reddit.com/r/developersIndia", "Tech-focused discussions, projects, hackathons. Strict spam filter.", False, True, False, "medium", 90),
                ("reddit", "r/mumbai", "r-mumbai", "https://reddit.com/r/mumbai", "City happenings and gatherings. Links permitted if contextual.", False, True, False, "low", 87),
                ("forum", "IndieHackers India", "indiehackers-india", "https://indiehackers.com/group/india", "Founder meetups, building in public, and tech networking.", True, True, False, "low", 91),
                ("discord", "Bengaluru Builders Discord", "discord-bengaluru-builders", "https://discord.com/channels/bengaluru-builders", "Authorized server. Event-discovery channel only, helpful replies, no cold DMs.", False, True, False, "low", 89),
                ("discord", "NCR Tech Discord", "discord-ncr-tech", "https://discord.com/channels/ncr-tech", "Authorized server with a dedicated events-discovery channel.", False, True, False, "low", 86),
                ("telegram", "Hyderabad Tech Community", "telegram-hyderabad-tech", "https://t.me/hyderabad_tech_community", "Public group. Community updates permitted, no unsolicited DMs.", False, True, False, "low", 88),
                ("telegram", "Mumbai Founders Telegram", "telegram-mumbai-founders", "https://t.me/mumbai_founders", "Founder-focused group. Genuine, on-topic recommendations only.", False, True, False, "medium", 85),
                ("x", "X / #TechMeetup", "x-techmeetup", "https://x.com/search?q=tech%20meetups", "Public search surface. Reply only when directly relevant, no spam threads.", False, True, False, "medium", 84),
                ("x", "X / #DesignEvents", "x-designevents", "https://x.com/search?q=design%20workshops", "Public search surface for design-community conversation.", False, True, False, "medium", 84),
                ("linkedin", "LinkedIn Group: Startup Founders India", "linkedin-startup-founders-india", "https://www.linkedin.com/groups/startup-founders-india/", "Professional group. Value-first comments only, no unsolicited outreach.", False, True, False, "low", 90),
                ("linkedin", "LinkedIn: Women in Tech India", "linkedin-women-in-tech-india", "https://www.linkedin.com/groups/women-in-tech-india/", "Professional group focused on career growth and community events.", False, True, False, "low", 92),
                ("instagram", "100.com Instagram Content Calendar", "instagram-content-calendar", "https://instagram.com/100times", "Owned channel. Content generated from the 100.com catalog, always human-approved before publishing.", True, True, False, "low", 90),
            ]
            for platform, name, slug, url, rules, promo, links, auto, risk, score in communities_data:
                get_or_create(
                    db,
                    Community,
                    {"slug": slug},
                    {
                        "platform": platform,
                        "name": name,
                        "url": url,
                        "rules_text": rules,
                        "promotion_allowed": promo,
                        "external_links_allowed": links,
                        "automation_allowed": auto,
                        "risk_level": risk,
                        "quality_score": score,
                        "last_checked": datetime.utcnow(),
                    },
                )

            # Admin-configurable per-platform daily ingestion caps (spec: rate
            # limit engine, editable via PATCH /acquisition/rate-limits/{platform}).
            rate_limit_defaults = [
                ("reddit", 25), ("discord", 25), ("telegram", 20), ("x", 25), ("linkedin", 10), ("instagram", 10),
            ]
            for plat, daily_limit in rate_limit_defaults:
                get_or_create(
                    db, PlatformRateLimit, {"platform": plat},
                    {"daily_limit": daily_limit, "updated_at": datetime.utcnow()},
                )

            # Process Initial High-Intent Discussions through Agent Pipeline
            from backend.services.acquisition_agent import AgentOrchestrator
            sample_discussions = [
                ("reddit", "r/hyderabad", "Where can I find AI workshops in Hyderabad this weekend?", "Looking to learn LLM engineering and meet local machine learning researchers or founders in Hyderabad. Any recommended workshops, summits, or hackathons?", "hyd_builder_99"),
                ("reddit", "r/bangalore", "Looking for startup networking events this weekend", "I recently moved to Bengaluru and want to meet people interested in startups, B2B SaaS, and venture building. Any recommended rooms or summits?", "arjun_blr"),
                ("reddit", "r/developersIndia", "Upcoming hackathons or developer conferences in India", "Does anyone know any upcoming developer conferences with hands-on architecture deep-dives and peer networking in Bengaluru or Hyderabad?", "student_dev_blr"),
            ]
            for plat, comm, title, content, author in sample_discussions:
                AgentOrchestrator.process_discussion(
                    db=db,
                    platform=plat,
                    community_name=comm,
                    title=title,
                    content=content,
                    author=author,
                )

            # Run the full connector-layer scan so Discord/Telegram/X/LinkedIn also
            # have demo opportunities out of the box (dedup keeps repeat seeds safe).
            from backend.services.social_agent.orchestrator import SocialAgentOrchestrator

            SocialAgentOrchestrator.run_discussion_cycle(db=db)

        db.commit()
        print("Seeded 100 TIMES demo data with Community Acquisition Agent initial opportunities.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
