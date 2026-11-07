import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add api-server to path
api_dir = Path("artifacts/api-server").resolve()
sys.path.insert(0, str(api_dir))

from backend.db import SessionLocal
from backend.models import EventDiscoverySource

VERIFIED_DIRECTORIES = [
    {
        "id": "tradefairindex",
        "name": "TradeFairIndex",
        "website_url": "https://tradefairindex.com/",
        "source_category": "Multi-sector trade fair directory",
        "supported_industries": ["Construction", "Manufacturing", "Transport and Logistics", "Healthcare", "Packaging", "Energy and Power Generation", "Textiles"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Trade Fairs", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Multi-sector trade fair directory",
            "event_coverage": "Trade fairs and exhibitions searchable by industry and country",
            "verification_notes": "Verified: live directory shows upcoming fairs, industry filters and event source/verification dates.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "globalexpodesk",
        "name": "GlobalExpoDesk",
        "website_url": "https://globalexpodesk.com/industries",
        "source_category": "Multi-sector trade fair directory",
        "supported_industries": ["Construction", "Energy and Power Generation", "Healthcare", "Pharmaceuticals", "Manufacturing", "Mining", "Packaging", "Textiles", "Transport and Logistics", "Other"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Expos", "Trade Shows"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Multi-sector trade fair directory",
            "event_coverage": "Upcoming expos categorized by industry",
            "verification_notes": "Verified: live industry index lists the relevant categories and upcoming event counts.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "worldwidetradeconferences",
        "name": "Worldwide Trade Conferences",
        "website_url": "https://worldwidetradeconferences.com/",
        "source_category": "Multi-sector conference directory",
        "supported_industries": ["Construction", "Energy and Power Generation", "Finance", "Healthcare", "Manufacturing", "Mining", "Pharmaceuticals", "Telecommunications", "Transport and Logistics", "Other"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Summits", "B2B Events"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Multi-sector conference directory",
            "event_coverage": "Trade conferences, industry summits and B2B events",
            "verification_notes": "Verified: live directory states upcoming trade events and provides industry filters/source links.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "rxglobal",
        "name": "RX Global Events Finder",
        "website_url": "https://rxglobal.com/events",
        "source_category": "Event organizer event finder",
        "supported_industries": ["Construction", "Energy and Power Generation", "Finance", "Healthcare", "Manufacturing", "Mining", "Packaging", "Pharmaceuticals", "Telecommunications", "Textiles", "Transport and Logistics", "Other"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Exhibitions", "Fairs", "Conferences"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Event organizer event finder",
            "event_coverage": "Events across multiple industries and countries",
            "verification_notes": "Verified: live event finder includes industry filters across many requested sectors; mostly RX-organized events.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Organizer-owned event listings"
        }
    },
    {
        "id": "informaconnect",
        "name": "Informa Connect Events",
        "website_url": "https://informaconnect.com/events/",
        "source_category": "Event organizer event finder",
        "supported_industries": ["Finance", "Healthcare", "Pharmaceuticals", "Energy and Power Generation", "Manufacturing", "Transport and Logistics", "Other"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Digital Events"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Event organizer event finder",
            "event_coverage": "Conferences, events and digital events by sector",
            "verification_notes": "Verified: live event finder has sector filters and current upcoming listings; mostly Informa-organized events.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Organizer-owned event listings"
        }
    },
    {
        "id": "exposignal",
        "name": "ExpoSignal",
        "website_url": "https://www.exposignal.com/",
        "source_category": "B2B event discovery directory",
        "supported_industries": ["Manufacturing", "Construction", "Energy and Power Generation", "Oil and Gas", "Packaging", "Telecommunications", "Textiles", "Transport and Logistics", "Other"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Expos", "Conferences", "Trade Fairs"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "B2B event discovery directory",
            "event_coverage": "Verified B2B events by industry",
            "verification_notes": "Verified: site presents event discovery, industry filters and source provenance/change history.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "expogage",
        "name": "ExpoGage Events",
        "website_url": "https://www.expogage.com/events",
        "source_category": "B2B event database",
        "supported_industries": ["Construction", "Healthcare", "Manufacturing", "Transport and Logistics", "Other"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["B2B Events", "Expos"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "B2B event database",
            "event_coverage": "B2B events searchable by topic, country and event type",
            "verification_notes": "Verified: live event database displays upcoming events and sector filters; some features may require a request.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "sibbuild",
        "name": "SibBuild Event Atlas",
        "website_url": "https://sibbuild.com/",
        "source_category": "Dedicated construction event directory",
        "supported_industries": ["Construction"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Trade Shows", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated construction event directory",
            "event_coverage": "Construction trade shows, exhibitions and building materials events",
            "verification_notes": "Verified: dedicated construction event directory with upcoming events, organizer sources and last-verified dates.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "oilgasevents",
        "name": "Oil & Gas Events",
        "website_url": "https://oilgasevents.com/",
        "source_category": "Dedicated oil and gas event directory",
        "supported_industries": ["Oil and Gas", "Energy and Power Generation"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Exhibitions", "Technical Meetings"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated oil and gas event directory",
            "event_coverage": "Global oil and gas conferences, exhibitions and technical meetings",
            "verification_notes": "Verified: live calendar shows upcoming events and organizer source links.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "worldofrenewables",
        "name": "World of Renewables Events",
        "website_url": "https://worldofrenewables.com/events/",
        "source_category": "Dedicated renewable energy event calendar",
        "supported_industries": ["Energy and Power Generation"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Summits"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated renewable energy event calendar",
            "event_coverage": "Renewables, hydrogen and clean energy events",
            "verification_notes": "Dedicated events URL identified; confirm listings and freshness before production use.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "fintechnews",
        "name": "Fintech News — Fintech Events Worldwide",
        "website_url": "https://fintechnews.sg/fintech-events-worldwide/",
        "source_category": "Dedicated fintech event calendar",
        "supported_industries": ["Finance"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Summits", "Expos", "Awards", "Webinars"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated fintech event calendar",
            "event_coverage": "Global fintech conferences, summits, expos, awards and webinars",
            "verification_notes": "Verified: live calendar describes 400+ events across 57 countries and links event listings to organizer pages.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "yardfintech",
        "name": "YARD FinTech & PayTech Calendar",
        "website_url": "https://www.yard.global/calendar/fintech/",
        "source_category": "Dedicated finance event calendar",
        "supported_industries": ["Finance"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Expos"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated finance event calendar",
            "event_coverage": "Fintech, payments and digital finance events",
            "verification_notes": "Verified: live continuously updated calendar with event dates, locations and submission option.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "financexmagazine",
        "name": "FinanceX Magazine Event Calendar",
        "website_url": "https://www.financexmagazine.com/event",
        "source_category": "Dedicated financial services event calendar",
        "supported_industries": ["Finance"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Summits"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated financial services event calendar",
            "event_coverage": "Banking, payments, regulation, wealth, capital markets and fintech events",
            "verification_notes": "Verified: live 2026 financial services event calendar.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "globalfintechcalendar",
        "name": "Global Fintech Calendar",
        "website_url": "https://globalfintechcalendar.com/",
        "source_category": "Dedicated fintech event calendar",
        "supported_industries": ["Finance"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Seminars"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated fintech event calendar",
            "event_coverage": "Fintech and financial services events",
            "verification_notes": "Dedicated event-calendar site identified; validate current event records before production.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "docthub",
        "name": "Docthub Events",
        "website_url": "https://events.docthub.com/",
        "source_category": "Dedicated healthcare event directory",
        "supported_industries": ["Healthcare"],
        "supported_countries": ["Worldwide", "India"],
        "supported_event_types": ["Medical Conferences", "CME", "Workshops"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated healthcare event directory",
            "event_coverage": "Medical conferences, CME, workshops and healthcare events",
            "verification_notes": "Verified: live healthcare event platform with event search, specialties and organizer details.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "thefasti",
        "name": "theFasti Medical Conferences",
        "website_url": "https://thefasti.com/h/research-conferences.html",
        "source_category": "Dedicated medical conference directory",
        "supported_industries": ["Healthcare"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Medical Conferences", "Research Conferences"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated medical conference directory",
            "event_coverage": "Medical and clinical research conferences by specialty",
            "verification_notes": "Verified: live independent directory links to organizer pages and reports rechecked meetings.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "medicalist",
        "name": "MedicaList Medical Conferences",
        "website_url": "https://medicalist.org/events/find.php",
        "source_category": "Dedicated medical conference directory",
        "supported_industries": ["Healthcare"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Medical Conferences"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated medical conference directory",
            "event_coverage": "Medical conferences searchable by specialty and country",
            "verification_notes": "Verified: live conference finder with medical specialties and country filters.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "convene_md",
        "name": "convene.md",
        "website_url": "https://convene.md/",
        "source_category": "Dedicated medical conference directory",
        "supported_industries": ["Healthcare"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Medical Conferences", "CME Meetings"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated medical conference directory",
            "event_coverage": "Medical conferences and CME meetings",
            "verification_notes": "Verified: live calendar lists medical meetings and says dates are verified against organizers.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "conferencealert_health",
        "name": "Conference Alert — Health",
        "website_url": "https://www.conferencealert.com/health",
        "source_category": "Health conference directory",
        "supported_industries": ["Healthcare"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Seminars"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Health conference directory",
            "event_coverage": "Health and medical conferences by country and date",
            "verification_notes": "Verified: live health-conference listing page; check individual listing accuracy.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "pharmafocusasia",
        "name": "Pharma Focus Asia Events",
        "website_url": "https://www.pharmafocusasia.com/events",
        "source_category": "Dedicated pharmaceutical event listing",
        "supported_industries": ["Pharmaceuticals"],
        "supported_countries": ["Asia", "Worldwide"],
        "supported_event_types": ["Conferences", "Exhibitions", "Trade Shows"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated pharmaceutical event listing",
            "event_coverage": "Pharmaceutical conferences, exhibitions and trade shows",
            "verification_notes": "Dedicated pharma events page and current event listings visible on site.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "cphi_global",
        "name": "CPHI Global Events",
        "website_url": "https://www.cphi.com/global-events/",
        "source_category": "Pharmaceutical event calendar",
        "supported_industries": ["Pharmaceuticals"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Exhibitions", "Conferences"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Pharmaceutical event calendar",
            "event_coverage": "Global pharmaceutical exhibitions and industry events",
            "verification_notes": "Dedicated global events page; organizer portfolio rather than an independent directory.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Organizer-owned event listings"
        }
    },
    {
        "id": "athenabda",
        "name": "Athena BDA Pharma Conference Calendar",
        "website_url": "https://athenabda.com/pharma-conference-calendar",
        "source_category": "Dedicated pharma conference calendar",
        "supported_industries": ["Pharmaceuticals"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Biotech Events"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated pharma conference calendar",
            "event_coverage": "Pharmaceutical and biotech conferences",
            "verification_notes": "Dedicated pharma conference calendar URL identified; verify current listing freshness.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "minerallink",
        "name": "MineralLink Critical Minerals Events",
        "website_url": "https://minerallink.org/events",
        "source_category": "Dedicated mining and minerals event calendar",
        "supported_industries": ["Mining"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Trade Fairs", "Conferences", "Summits"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated mining and minerals event calendar",
            "event_coverage": "Critical minerals trade fairs, conferences, summits and policy forums",
            "verification_notes": "Verified: live calendar lists mining and critical-minerals events and says dates are checked against organizers.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "miningevents",
        "name": "MiningEvents",
        "website_url": "https://miningevents.com/",
        "source_category": "Dedicated mining event directory",
        "supported_industries": ["Mining"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Meetings"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated mining event directory",
            "event_coverage": "Mining investment conferences and meetings",
            "verification_notes": "Dedicated event directory identified; verify current active listings.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "eventsmine",
        "name": "EventsMine",
        "website_url": "https://www.eventsmine.com/",
        "source_category": "Dedicated mining event directory",
        "supported_industries": ["Mining"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated mining event directory",
            "event_coverage": "Mining industry events",
            "verification_notes": "Dedicated event directory identified; verify current active listings.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "min_eng",
        "name": "Minerals Engineering International Events",
        "website_url": "https://www.min-eng.com/",
        "source_category": "Mining and mineral-processing event calendar",
        "supported_industries": ["Mining"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Technical Events"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Mining and mineral-processing event calendar",
            "event_coverage": "Mineral processing conferences and technical events",
            "verification_notes": "Calendar is identified as a dedicated event resource; confirm current page and dates.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "paperdna",
        "name": "PaperDNA Events",
        "website_url": "https://paperdna.ai/events/",
        "source_category": "Dedicated paper and packaging event calendar",
        "supported_industries": ["Packaging"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Trade Shows", "Conferences"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated paper and packaging event calendar",
            "event_coverage": "Paper, packaging, printing and tissue trade shows and conferences",
            "verification_notes": "Verified: live calendar lists upcoming events with dates and venues.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "pkgoutside",
        "name": "PKG Outside Events",
        "website_url": "https://www.pkgoutside.com/events",
        "source_category": "Dedicated packaging and printing event calendar",
        "supported_industries": ["Packaging"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Exhibitions", "Trade Shows"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated packaging and printing event calendar",
            "event_coverage": "Printing and packaging exhibitions with dates, venues and organizer links",
            "verification_notes": "Verified: live events page lists international exhibitions and official organizer links.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "specialistprinting",
        "name": "Specialist Printing — Find an Event",
        "website_url": "https://www.specialistprinting.com/events/",
        "source_category": "Dedicated printing event calendar",
        "supported_industries": ["Packaging", "Manufacturing"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Industrial Events", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated printing event calendar",
            "event_coverage": "Printing, label, package-printing and related industrial events",
            "verification_notes": "Verified: live global printing event list with dates and locations.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "thepackman",
        "name": "The Packman — Save Your Date",
        "website_url": "https://thepackman.in/save-your-date/",
        "source_category": "Dedicated packaging event listing",
        "supported_industries": ["Packaging"],
        "supported_countries": ["India", "Worldwide"],
        "supported_event_types": ["Exhibitions", "Conferences"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated packaging event listing",
            "event_coverage": "Packaging, printing and converting exhibitions",
            "verification_notes": "Dedicated event listing page identified; validate current/upcoming entries.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "texdates",
        "name": "TexDates",
        "website_url": "https://texdates.com/",
        "source_category": "Dedicated textile and fashion event directory",
        "supported_industries": ["Textiles"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Trade Fairs", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated textile and fashion event directory",
            "event_coverage": "Textile, apparel, fashion, sourcing, machinery and technical textile events",
            "verification_notes": "Verified: live textile event calendar; site says listings are curated and human-reviewed. Check commercial reuse terms.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "supplychainconferences",
        "name": "Supply Chain Conferences",
        "website_url": "https://supplychainconferences.com/",
        "source_category": "Dedicated supply chain event directory",
        "supported_industries": ["Transport and Logistics"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Summits", "Trade Shows"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated supply chain event directory",
            "event_coverage": "Supply chain, logistics, warehousing conferences, summits and trade shows",
            "verification_notes": "Verified: live directory shows upcoming events by region, country, month and topic; updated regularly.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "logisticsbuyer",
        "name": "Logistics Buyer Event Calendar",
        "website_url": "https://logistics-buyer.com/event-calendar/",
        "source_category": "Dedicated logistics event calendar",
        "supported_industries": ["Transport and Logistics"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated logistics event calendar",
            "event_coverage": "Logistics, freight, transportation and warehousing events",
            "verification_notes": "Dedicated event-calendar URL identified; verify live listings before production.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "aircargoweek",
        "name": "Air Cargo Week Events",
        "website_url": "https://aircargoweek.com/events/",
        "source_category": "Dedicated air cargo event listing",
        "supported_industries": ["Transport and Logistics"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Dedicated air cargo event listing",
            "event_coverage": "Air freight and cargo logistics events",
            "verification_notes": "Dedicated events URL identified; verify current listing page.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "gartner_supplychain",
        "name": "Gartner Supply Chain Events",
        "website_url": "https://www.gartner.com/en/supply-chain/events",
        "source_category": "Supply chain event calendar",
        "supported_industries": ["Transport and Logistics"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Webinars"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Supply chain event calendar",
            "event_coverage": "Supply chain conferences and webinars",
            "verification_notes": "Dedicated event listing page; mostly organizer-owned events.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Directory / event calendar"
        }
    },
    {
        "id": "networkxevent",
        "name": "Network X",
        "website_url": "https://www.networkxevent.com/",
        "source_category": "Telecom event website",
        "supported_industries": ["Telecommunications"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Telecom event website",
            "event_coverage": "Telecom networks, broadband and mobile communications events",
            "verification_notes": "Dedicated event site for its own event; not a multi-organizer directory.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Organizer-owned event listings"
        }
    },
    {
        "id": "telecomsworldasia",
        "name": "Telecoms World Asia",
        "website_url": "https://www.terrapinn.com/conference/telecoms-world-asia/",
        "source_category": "Telecom event website",
        "supported_industries": ["Telecommunications"],
        "supported_countries": ["Asia", "Worldwide"],
        "supported_event_types": ["Conferences", "Exhibitions"],
        "access_method": "html_listing",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "source_type": "Telecom event website",
            "event_coverage": "Telecommunications conferences and exhibitions",
            "verification_notes": "Dedicated event website for its own event; not a multi-organizer directory.",
            "verification_status": "Event-focused page verified or identified; recheck before crawling",
            "directory_type": "Organizer-owned event listings"
        }
    }
]

def save_to_active_db():
    print("Saving to active database via SessionLocal (MySQL)...")
    s = SessionLocal()
    added = 0
    updated = 0
    now = datetime.now(timezone.utc)
    for d in VERIFIED_DIRECTORIES:
        src = s.get(EventDiscoverySource, d["id"])
        # Also check by website_url if ID is different
        if not src:
            src = s.query(EventDiscoverySource).filter_by(website_url=d["website_url"]).first()
        
        if not src:
            src = EventDiscoverySource(
                id=d["id"],
                name=d["name"],
                website_url=d["website_url"],
                source_category=d["source_category"],
                supported_industries=d["supported_industries"],
                supported_countries=d["supported_countries"],
                supported_event_types=d["supported_event_types"],
                access_method=d["access_method"],
                permission_status=d["permission_status"],
                integration_status=d["integration_status"],
                health_status=d["health_status"],
                is_enabled=d["is_enabled"],
                config=d["config"],
                created_at=now,
                updated_at=now,
            )
            s.add(src)
            added += 1
        else:
            src.name = d["name"]
            src.website_url = d["website_url"]
            src.source_category = d["source_category"]
            src.supported_industries = d["supported_industries"]
            src.supported_countries = d["supported_countries"]
            src.supported_event_types = d["supported_event_types"]
            src.is_enabled = True
            src.config = {**src.config, **d["config"]}
            src.updated_at = now
            updated += 1
    
    s.commit()
    total = s.query(EventDiscoverySource).count()
    s.close()
    print(f"Active DB: Added {added}, Updated {updated}. Total sources now: {total}")

def save_to_sqlite():
    db_file = api_dir / "100times-dev.db"
    print(f"Syncing to fallback SQLite DB at {db_file}...")
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    added = 0
    updated = 0
    
    for d in VERIFIED_DIRECTORIES:
        cur.execute("SELECT id FROM event_discovery_sources WHERE id = ? OR website_url = ?", (d["id"], d["website_url"]))
        row = cur.fetchone()
        
        ind_json = json.dumps(d["supported_industries"])
        cnt_json = json.dumps(d["supported_countries"])
        evt_json = json.dumps(d["supported_event_types"])
        cfg_json = json.dumps(d["config"])
        
        if not row:
            cur.execute("""
                INSERT INTO event_discovery_sources (
                    id, name, website_url, source_category, supported_industries,
                    supported_countries, supported_event_types, access_method,
                    permission_status, integration_status, health_status, is_enabled,
                    config, created_at, updated_at, origin, events_discovered,
                    events_extracted, unique_events_discovered, events_verified,
                    events_needs_review, events_rejected, consecutive_failures
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'verified_directory', 0, 0, 0, 0, 0, 0, 0)
            """, (
                d["id"], d["name"], d["website_url"], d["source_category"],
                ind_json, cnt_json, evt_json, d["access_method"],
                d["permission_status"], d["integration_status"], d["health_status"],
                1 if d["is_enabled"] else 0, cfg_json, now_str, now_str
            ))
            added += 1
        else:
            existing_id = row[0]
            cur.execute("""
                UPDATE event_discovery_sources SET
                    name = ?, website_url = ?, source_category = ?, supported_industries = ?,
                    supported_countries = ?, supported_event_types = ?, is_enabled = 1,
                    config = ?, updated_at = ?
                WHERE id = ?
            """, (
                d["name"], d["website_url"], d["source_category"],
                ind_json, cnt_json, evt_json, cfg_json, now_str, existing_id
            ))
            updated += 1
            
    conn.commit()
    cur.execute("SELECT count(*) FROM event_discovery_sources;")
    total = cur.fetchone()[0]
    conn.close()
    print(f"SQLite DB: Added {added}, Updated {updated}. Total sources now: {total}")

if __name__ == "__main__":
    save_to_active_db()
    save_to_sqlite()
