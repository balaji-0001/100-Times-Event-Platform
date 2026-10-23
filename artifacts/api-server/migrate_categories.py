import sys
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta

API_SERVER_DIR = Path(__file__).resolve().parent
if str(API_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(API_SERVER_DIR))

from backend.db import SessionLocal
from backend.models import Category, Event, DiscoveredCommunity, DiscoveredEvent

CATEGORIES_DATA = [
    (
        "Pharmaceuticals",
        "pharmaceuticals",
        "Pharmaceutical companies, drug manufacturing, research, and industry developments.",
        "pill"
    ),
    (
        "Healthcare",
        "healthcare",
        "Hospitals, healthcare providers, medical technology, and healthcare management.",
        "heart"
    ),
    (
        "Medical Science",
        "medical-science",
        "Medical science and healthcare-related information for professional audiences.",
        "activity"
    ),
    (
        "Energy and Power Generation",
        "energy-and-power-generation",
        "Conventional and renewable energy, power generation, and sector developments.",
        "zap"
    ),
    (
        "Telecommunications",
        "telecommunications",
        "Telecom networks, operators, equipment, enterprise IT, and communications technology.",
        "radio"
    ),
    (
        "Construction",
        "construction",
        "Construction, infrastructure projects, industry trends, and construction technology.",
        "hard-hat"
    ),
    (
        "Mining",
        "mining",
        "Mining operations, mineral extraction, projects, equipment, and industry news.",
        "mountain"
    ),
    (
        "Finance",
        "finance",
        "Financial-sector news, business developments, products, and services.",
        "briefcase"
    ),
    (
        "Packaging",
        "packaging",
        "Packaging materials, machinery, manufacturers, suppliers, and industry innovations.",
        "package"
    ),
    (
        "Transport and Logistics",
        "transport-and-logistics",
        "Railways, road transport, aviation, shipping, ports, and logistics.",
        "truck"
    ),
    (
        "Oil and Gas",
        "oil-and-gas",
        "Oil and gas industry news, operations, technology, and business developments.",
        "flame"
    ),
    (
        "Textiles",
        "textiles",
        "Textile industry news and developments, including businesses and professionals across the textile value chain.",
        "scissors"
    ),
    (
        "Manufacturing",
        "manufacturing",
        "Manufacturing industry news, industrial operations, technology, and business developments.",
        "factory"
    ),
    (
        "Hospitality Management",
        "hospitality-management",
        "Hospitality management and related industry developments for professional audiences.",
        "coffee"
    ),
]

db = SessionLocal()

print("1. Creating / updating the 14 approved sectors in Category table...")
target_categories = {}
for name, slug, description, icon in CATEGORIES_DATA:
    cat = db.query(Category).filter((Category.slug == slug) | (Category.name == name)).first()
    if not cat:
        cat = Category(name=name, slug=slug, description=description, icon=icon)
        db.add(cat)
        db.flush()
    else:
        cat.name = name
        cat.slug = slug
        cat.description = description
        cat.icon = icon
        db.flush()
    target_categories[name] = cat

allowed_ids = {c.id for c in target_categories.values()}

# Remap existing events
category_mapping = {
    "Artificial Intelligence": "Telecommunications",
    "Data Science": "Telecommunications",
    "Information Technology": "Telecommunications",
    "Business & Finance": "Finance",
    "Startup": "Finance",
    "Healthcare": "Healthcare",
    "Manufacturing": "Manufacturing",
    "Education": "Medical Science",
    "Marketing": "Hospitality Management",
}

all_target_list = list(target_categories.values())

print("2. Remapping existing events in DB...")
for i, event in enumerate(db.query(Event).all()):
    if event.category_id not in allowed_ids:
        old_name = event.category.name if event.category else None
        target_name = category_mapping.get(old_name)
        if target_name and target_name in target_categories:
            event.category_id = target_categories[target_name].id
        else:
            # Distribute across remaining categories
            event.category_id = all_target_list[i % len(all_target_list)].id

# Clean up DiscoveredEvent categories if any
for de in db.query(DiscoveredEvent).all():
    if de.category not in target_categories:
        de.category = category_mapping.get(de.category, "Manufacturing")

# Clean up DiscoveredCommunity categories if any
for dc in db.query(DiscoveredCommunity).all():
    if dc.category not in target_categories:
        dc.category = category_mapping.get(dc.category, "Finance")

db.commit()

print("3. Removing old obsolete categories...")
obsolete = db.query(Category).filter(~Category.id.in_(allowed_ids)).all()
for obs in obsolete:
    print(f"   Deleting old category: {obs.name} (id: {obs.id})")
    db.delete(obs)
db.commit()

print(f"\nCompleted! Active categories count in DB: {db.query(Category).count()}")
for c in db.query(Category).order_by(Category.id).all():
    event_cnt = db.query(Event).filter(Event.category_id == c.id).count()
    print(f"  [{c.id}] {c.name} | slug: {c.slug} | icon: {c.icon} | events: {event_cnt}")

db.close()

