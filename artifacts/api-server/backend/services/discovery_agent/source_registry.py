"""Comprehensive Source Registry for 100 TIMES Global Event Discovery.

Manages catalog of 74+ global event discovery sources, ticketing platforms,
exhibition organizers, venue calendars, industry associations, government trade portals,
and research tools.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models import EventDiscoverySource

logger = logging.getLogger("discovery_agent.source_registry")

# ---------------------------------------------------------------------------
# Master Source Catalog
# ---------------------------------------------------------------------------

ALL_CANDIDATE_SOURCES: list[dict[str, Any]] = [
    # =======================================================================
    # Category A: Global Event Discovery Websites (1 to 20)
    # =======================================================================
    {
        "id": "eventseye",
        "name": "EventsEye",
        "website_url": "https://www.eventseye.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Trade Fairs", "Exhibitions", "Manufacturing", "Energy", "Logistics"],
        "supported_countries": ["Worldwide", "Germany", "France", "United States", "China", "United Kingdom"],
        "supported_event_types": ["Trade Shows", "Exhibitions", "Fairs"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            # Read by the site-specific EventsEyeAdapter (country / country x industry lists).
            "listing_template": "https://www.eventseye.com/fairs/c1_trade-shows_{country}.html",
            "base_url": "https://www.eventseye.com",
        },
    },
    {
        "id": "clocate",
        "name": "Clocate",
        "website_url": "https://www.clocate.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Medical", "Science", "Technology", "Engineering", "Business"],
        "supported_countries": ["Worldwide", "United States", "United Kingdom", "Germany", "Singapore"],
        "supported_event_types": ["Conferences", "Seminars", "Summits"],
        "access_method": "schema_org",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"listing_template": "https://www.clocate.com/conferences/{city}/"},
    },
    {
        "id": "eventbrite",
        "name": "Eventbrite",
        "website_url": "https://www.eventbrite.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["All Industries", "Technology", "Networking", "Business", "Education"],
        "supported_countries": ["Worldwide", "United States", "United Kingdom", "India", "Australia", "Canada"],
        "supported_event_types": ["Conferences", "Seminars", "Workshops", "Meetups"],
        "access_method": "schema_org",
        "api_docs_url": "https://www.eventbrite.co.uk/platform/new/api",
        "api_auth_requirements": "None (Public Web JSON-LD)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "listing_template": "https://www.eventbrite.com/d/{country}--{city}/events/",
            "fallback_template": "https://www.eventbrite.com/d/{city}/events/",
        },
    },
    {
        "id": "meetup",
        "name": "Meetup",
        "website_url": "https://www.meetup.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Technology", "Developer", "Networking", "Startup", "Community"],
        "supported_countries": ["Worldwide", "United States", "India", "United Kingdom", "Germany"],
        "supported_event_types": ["Meetups", "User Groups", "Workshops", "Hackathons"],
        "access_method": "schema_org",
        "api_docs_url": "https://help.meetup.com/hc/en-us/articles/41453576628749",
        "api_auth_requirements": "None (Public Web JSON-LD)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"listing_template": "https://www.meetup.com/find/?location={city}&source=EVENTS"},
    },
    {
        "id": "tsnn",
        "name": "TSNN (Trade Show News Network)",
        "website_url": "https://www.tsnn.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Trade Shows", "B2B", "Exhibitions", "Conventions"],
        "supported_countries": ["United States", "North America", "Worldwide"],
        "supported_event_types": ["Trade Shows", "Conventions", "Expos"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.tsnn.com/events"},
    },
    {
        "id": "tradeshowradar",
        "name": "Trade Show Radar",
        "website_url": "https://www.tradeshowradar.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["B2B", "Industrial", "Manufacturing", "Automotive", "Technology"],
        "supported_countries": ["Worldwide", "United States", "Europe"],
        "supported_event_types": ["Trade Shows", "Expos"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"listing_url": "https://www.tradeshowradar.com/events"},  # /city/{city}/ pages 404 (checked 2026-10-27)
    },
    {
        "id": "expolya",
        "name": "Expolya",
        "website_url": "https://www.expolya.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Trade Fairs", "Exhibitions", "B2B"],
        "supported_countries": ["Worldwide", "Middle East", "Europe", "Asia"],
        "supported_event_types": ["Fairs", "Exhibitions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://expolya.com/expos"},  # read by ExpolyaAdapter; /fairs 404s (checked 2026-10-27)
    },
    {
        "id": "auma",
        "name": "AUMA",
        "website_url": "https://www.auma.de/en/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["German Trade Fairs", "Global Exhibitions", "Industrial Machinery"],
        "supported_countries": ["Germany", "Europe", "Worldwide"],
        "supported_event_types": ["Trade Fairs", "Exhibitions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Approved (Official Association)",
        "integration_status": "Approved",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"search_url": "https://www.auma.de/en/exhibit/find-your-exhibitions"},
    },
    {
        "id": "tradefairdates",
        "name": "TradeFairDates",
        "website_url": "https://www.tradefairdates.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Trade Shows", "Commercial Fairs", "Industrial", "Consumer Goods"],
        "supported_countries": ["Worldwide", "Germany", "United States", "China", "India", "Italy"],
        "supported_event_types": ["Trade Shows", "Fairs", "Exhibitions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"listing_url": "https://www.tradefairdates.com/trade-shows-by-countries.php"},  # read by TradeFairDatesAdapter (country pages)
    },
    {
        "id": "two_exhibitions",
        "name": "2Exhibitions",
        "website_url": "https://www.2exhibitions.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Exhibitions", "B2B Events", "Trade Fairs"],
        "supported_countries": ["Worldwide", "Asia", "Europe"],
        "supported_event_types": ["Exhibitions", "Trade Fairs"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.2exhibitions.com/events/"},  # current page (checked 2026-10-27): loads, but publishes no machine-readable event list
    },
    {
        "id": "conference_alerts",
        "name": "Conference Alerts",
        "website_url": "https://www.conferencealert.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Academic", "Science", "Technology", "Social Sciences"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Symposiums"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": None,
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"listing_template": "https://www.conferencealert.com/search.php?city={city}"},
    },
    {
        "id": "wikicfp",
        "name": "WikiCFP",
        "website_url": "http://www.wikicfp.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Computer Science", "Engineering", "Academic", "Science"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Call for Papers", "Conferences", "Workshops"],
        "access_method": "rss_ical",
        "api_docs_url": "http://www.wikicfp.com/cfp/",
        "api_auth_requirements": "None (Public RSS Feed)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"rss_url": "http://www.wikicfp.com/cfp/rss"},
    },
    {
        "id": "dev_events",
        "name": "dev.events",
        "website_url": "https://dev.events/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Software Development", "DevOps", "AI", "Cloud", "Web"],
        "supported_countries": ["Worldwide", "Europe", "North America", "Asia"],
        "supported_event_types": ["Conferences", "Meetups", "Summits"],
        "access_method": "schema_org",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public HTML/JSON)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"base_url": "https://dev.events/"},
    },

    # =======================================================================
    # Category B: Event Platforms and API Sources (21 to 30)
    # =======================================================================
    {
        "id": "ticketmaster_api",
        "name": "Ticketmaster Discovery API v2",
        "website_url": "https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/",
        "source_category": "Event Platform & API",
        "supported_industries": ["Entertainment", "Conferences", "Expos", "Sports", "Arts"],
        "supported_countries": ["Worldwide", "United States", "United Kingdom", "Canada", "Australia", "Europe"],
        "supported_event_types": ["Conferences", "Expos", "Concerts", "Festivals"],
        "access_method": "official_api",
        "api_docs_url": "https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/",
        "api_auth_requirements": "API Key (query parameter 'apikey')",
        "permission_status": "Approved (Official API)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {
            "endpoint": "https://app.ticketmaster.com/discovery/v2/events.json",
            "rate_limit_per_second": 5,
        },
    },
    {
        "id": "eventbrite_api",
        "name": "Eventbrite Platform API",
        "website_url": "https://www.eventbrite.co.uk/platform/new/api",
        "source_category": "Event Platform & API",
        "supported_industries": ["All Industries", "Business", "Tech", "Workshops"],
        "supported_countries": ["Worldwide", "United States", "United Kingdom", "India"],
        "supported_event_types": ["Conferences", "Seminars", "Workshops"],
        "access_method": "official_api",
        "api_docs_url": "https://www.eventbrite.co.uk/platform/new/api",
        "api_auth_requirements": "OAuth 2.0 Bearer Token / Private Token",
        "permission_status": "Approved",
        "integration_status": "Awaiting Credentials",
        "health_status": "untested",
        "is_enabled": False,
        "config": {"endpoint": "https://www.eventbriteapi.com/v3/events/search/"},
    },
    {
        "id": "meetup_api",
        "name": "Meetup GraphQL API",
        "website_url": "https://help.meetup.com/hc/en-us/articles/41453576628749-How-can-I-get-access-to-Meetup-s-API",
        "source_category": "Event Platform & API",
        "supported_industries": ["Technology", "Networking", "Community", "Professional"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Meetups", "Networking", "User Groups"],
        "access_method": "official_api",
        "api_docs_url": "https://www.meetup.com/api/",
        "api_auth_requirements": "OAuth 2.0 / Meetup Pro API Key",
        "permission_status": "Approved",
        "integration_status": "Awaiting Credentials",
        "health_status": "untested",
        "is_enabled": False,
        "config": {"endpoint": "https://api.meetup.com/gql"},
    },
    {
        "id": "sessionize",
        "name": "Sessionize",
        "website_url": "https://sessionize.com/",
        "source_category": "Event Platform & API",
        "supported_industries": ["Technology", "Developer Conferences", "Cloud", "AI"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Call for Speakers", "Summits"],
        "access_method": "official_api",
        "api_docs_url": "https://sessionize.com/playbook/api",
        "api_auth_requirements": "Per-Event Token / Public Embed Endpoint",
        "permission_status": "Approved",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"endpoint": "https://sessionize.com/api/v2/"},
    },
    {
        "id": "pretalx",
        "name": "Pretalx",
        "website_url": "https://pretalx.com/",
        "source_category": "Event Platform & API",
        "supported_industries": ["Open Source", "Software", "Academic", "Security"],
        "supported_countries": ["Worldwide", "Europe"],
        "supported_event_types": ["Conferences", "Schedule Calendars"],
        "access_method": "official_api",
        "api_docs_url": "https://docs.pretalx.org/api/",
        "api_auth_requirements": "Bearer Token / Public Schedule JSON",
        "permission_status": "Approved",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"api_format": "rest_json"},
    },
    {
        "id": "pretix",
        "name": "pretix",
        "website_url": "https://pretix.eu/",
        "source_category": "Event Platform & API",
        "supported_industries": ["Conferences", "Festivals", "Community", "Seminars"],
        "supported_countries": ["Worldwide", "Europe", "Germany"],
        "supported_event_types": ["Conferences", "Ticketing"],
        "access_method": "official_api",
        "api_docs_url": "https://docs.pretix.eu/en/latest/api/",
        "api_auth_requirements": "API Token",
        "permission_status": "Approved",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"api_format": "rest_json"},
    },
    {
        "id": "cvent",
        "name": "Cvent",
        "website_url": "https://www.cvent.com/",
        "source_category": "Event Platform & API",
        "supported_industries": ["Enterprise Events", "Corporate", "Trade Shows", "Healthcare"],
        "supported_countries": ["Worldwide", "United States", "Europe"],
        "supported_event_types": ["Conferences", "Trade Shows", "Corporate Summits"],
        "access_method": "official_api",
        "api_docs_url": "https://developers.cvent.com/",
        "api_auth_requirements": "OAuth 2.0 Client Credentials (Enterprise Agreement)",
        "permission_status": "Permission Review",
        "integration_status": "Awaiting Credentials",
        "health_status": "untested",
        "is_enabled": False,
        "config": {"endpoint": "https://api-platform.cvent.com/ea/"},
    },
    {
        "id": "bizzabo",
        "name": "Bizzabo",
        "website_url": "https://www.bizzabo.com/",
        "source_category": "Event Platform & API",
        "supported_industries": ["B2B Conferences", "Tech Summits", "Corporate Events"],
        "supported_countries": ["Worldwide", "United States"],
        "supported_event_types": ["B2B Conferences", "Summits"],
        "access_method": "official_api",
        "api_docs_url": "https://developer.bizzabo.com/",
        "api_auth_requirements": "API Key / Partner Access",
        "permission_status": "Permission Review",
        "integration_status": "Awaiting Credentials",
        "health_status": "untested",
        "is_enabled": False,
        "config": {"endpoint": "https://api.bizzabo.com/v1/"},
    },
    {
        "id": "swoogo",
        "name": "Swoogo",
        "website_url": "https://swoogo.events/",
        "source_category": "Event Platform & API",
        "supported_industries": ["Enterprise Events", "Corporate Meetings"],
        "supported_countries": ["Worldwide", "United States", "Europe"],
        "supported_event_types": ["Conferences", "Corporate Summits"],
        "access_method": "official_api",
        "api_docs_url": "https://swoogo.events/api",
        "api_auth_requirements": "API Key & Secret",
        "permission_status": "Permission Review",
        "integration_status": "Awaiting Credentials",
        "health_status": "untested",
        "is_enabled": False,
        "config": {"endpoint": "https://swoogo.events/api/v1/"},
    },
    {
        "id": "whova",
        "name": "Whova",
        "website_url": "https://whova.com/",
        "source_category": "Event Platform & API",
        "supported_industries": ["Academic", "Association Meetings", "Community"],
        "supported_countries": ["Worldwide", "United States"],
        "supported_event_types": ["Conferences", "Annual Meetings"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "Mobile/Web Login (No Public API)",
        "permission_status": "Permission Review",
        "integration_status": "Permission Review",
        "health_status": "untested",
        "is_enabled": False,
        "config": {},
    },

    # =======================================================================
    # Category C: International Exhibition Organizers (31 to 45)
    # =======================================================================
    {
        "id": "rx_global",
        "name": "RX Global",
        "website_url": "https://rxglobal.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Aerospace", "Healthcare", "Manufacturing", "Tech", "Security", "Jewelry"],
        "supported_countries": ["Worldwide", "United States", "Europe", "Asia", "Middle East"],
        "supported_event_types": ["Exhibitions", "Trade Shows", "B2B Events"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web Calendar)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://rxglobal.com/events"},
    },
    {
        "id": "informa_markets",
        "name": "Informa Markets",
        "website_url": "https://www.informamarkets.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Healthcare", "Pharma", "Agriculture", "Maritime", "Hospitality", "Construction"],
        "supported_countries": ["Worldwide", "Asia", "Europe", "Middle East", "United States"],
        "supported_event_types": ["Exhibitions", "Conferences", "Digital Marketplaces"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web Calendar)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.informamarkets.com/en/event-listing.html"},  # read by InformaMarketsAdapter via the page's own event feed
    },
    {
        "id": "clarion_events",
        "name": "Clarion Events",
        "website_url": "https://clarionevents.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Defense", "Energy", "Gaming", "Retail", "Life Sciences"],
        "supported_countries": ["Worldwide", "United Kingdom", "United States", "Europe"],
        "supported_event_types": ["Trade Shows", "Summits"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://clarionevents.com/events/"},
    },
    {
        "id": "terrapinn",
        "name": "Terrapinn",
        "website_url": "https://www.terrapinn.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Finance", "Aviation", "Energy", "Telecom", "Transport", "Solar"],
        "supported_countries": ["Worldwide", "United Kingdom", "United States", "Asia", "Middle East"],
        "supported_event_types": ["Conferences", "Exhibitions", "Summits"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.terrapinn.com/events"},
    },
    {
        "id": "messe_frankfurt_org",
        "name": "Messe Frankfurt (Organizer)",
        "website_url": "https://www.messefrankfurt.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Textiles", "Technology", "Consumer Goods", "Mobility", "Building"],
        "supported_countries": ["Germany", "Europe", "Worldwide", "Asia"],
        "supported_event_types": ["Trade Fairs", "Exhibitions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.messefrankfurt.com/frankfurt/en/event-search.html"},  # its event list loads from a script feed (not read; needs approval)
    },
    {
        "id": "deutsche_messe",
        "name": "Deutsche Messe",
        "website_url": "https://www.messe.de/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Industry 4.0", "Logistics", "Digital Economy", "Manufacturing"],
        "supported_countries": ["Germany", "Europe", "Worldwide"],
        "supported_event_types": ["Trade Fairs", "Industrial Expos"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.messe.de/de/messen/"},  # current page (checked 2026-10-27): loads, but publishes no machine-readable event list
    },
    {
        "id": "koelnmesse",
        "name": "Koelnmesse",
        "website_url": "https://www.koelnmesse.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Food", "Hardware", "Gaming", "Interiors", "Digital Media"],
        "supported_countries": ["Germany", "Europe", "Worldwide"],
        "supported_event_types": ["Trade Fairs", "B2B Expos"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.koelnmesse.com/current-dates/all-trade-fairs/"},  # read by KoelnmesseAdapter
    },
    {
        "id": "messe_duesseldorf",
        "name": "Messe Düsseldorf",
        "website_url": "https://www.messe-duesseldorf.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Machinery", "Medicine", "Retail", "Metals", "Plastics"],
        "supported_countries": ["Germany", "Europe", "Worldwide"],
        "supported_event_types": ["Trade Fairs"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.messe-duesseldorf.com/en/Trade_Fairs_Events/Trade_fairs_national_international"},  # read by MesseDuesseldorfAdapter (national + international)
    },
    {
        "id": "fiera_milano",
        "name": "Fiera Milano",
        "website_url": "https://www.fieramilano.it/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Design", "Fashion", "Machinery", "Food", "Tourism"],
        "supported_countries": ["Italy", "Europe", "Worldwide"],
        "supported_event_types": ["Exhibitions", "Conventions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.fieramilano.it/en/manifestazioni.html"},
    },
    {
        "id": "nuernbergmesse",
        "name": "NürnbergMesse",
        "website_url": "https://www.nuernbergmesse.de/en/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Packaging", "Organic Goods", "Security", "Construction"],
        "supported_countries": ["Germany", "Europe", "Worldwide"],
        "supported_event_types": ["Trade Fairs", "Congresses"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.nuernbergmesse.de/en/events"},  # current page (checked 2026-10-27): loads, but publishes no machine-readable event list
    },
    {
        "id": "gl_events",
        "name": "GL events",
        "website_url": "https://www.gl-events.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Hospitality", "Sports", "Industry", "Cultural"],
        "supported_countries": ["France", "Europe", "Worldwide", "Americas"],
        "supported_event_types": ["Trade Shows", "Congresses"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.gl-events.com/fr/agenda"},  # current page (checked 2026-10-27): loads, but publishes no machine-readable event list
    },
    {
        "id": "emerald",
        "name": "Emerald",
        "website_url": "https://www.emeraldx.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Design", "Technology", "Retail", "Food", "Sports"],
        "supported_countries": ["United States", "North America"],
        "supported_event_types": ["B2B Trade Shows", "Conferences"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.emeraldx.com/events/"},
    },
    {
        "id": "tarsus",
        "name": "Tarsus",
        "website_url": "https://www.tarsus.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Aviation", "Medical", "Labels & Packaging"],
        "supported_countries": ["Worldwide", "United States", "Europe", "Asia", "Middle East"],
        "supported_event_types": ["Exhibitions", "Conferences"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.tarsus.com/events"},
    },
    {
        "id": "dmg_events",
        "name": "dmg events",
        "website_url": "https://www.dmgevents.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Energy", "Construction", "Hospitality", "Design", "Coatings"],
        "supported_countries": ["Middle East", "Africa", "Asia", "Americas"],
        "supported_event_types": ["Trade Exhibitions", "Strategic Conferences"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.dmgevents.com/events/"},  # read by DmgEventsAdapter; /event-listing/ 404s (checked 2026-10-27)
    },
    {
        "id": "dwtc_org",
        "name": "Dubai World Trade Centre (Organizer)",
        "website_url": "https://www.dwtc.com/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Technology", "Healthcare", "Food", "Security", "Trade"],
        "supported_countries": ["United Arab Emirates", "Middle East", "Worldwide"],
        "supported_event_types": ["Exhibitions", "Summits", "Congresses"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.dwtc.com/en/"},  # events are published as JSON-LD on the homepage; /en/events/ lists none (checked 2026-10-27)
    },

    # =======================================================================
    # Category D: Industry Associations and Professional Conferences (46 to 55)
    # =======================================================================
    {
        "id": "gtr_events",
        "name": "GTR Events (Global Trade Review)",
        "website_url": "https://www.gtreview.com/events/",
        "source_category": "Industry Association",
        "supported_industries": ["Trade Finance", "Commodity", "Supply Chain", "Fintech"],
        "supported_countries": ["Worldwide", "United Kingdom", "Singapore", "United Arab Emirates", "United States"],
        "supported_event_types": ["Conferences", "Trade Forums"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.gtreview.com/events/"},
    },
    {
        "id": "cmt_events",
        "name": "CMT Events (Centre for Management Technology)",
        "website_url": "https://www.cmtevents.com/",
        "source_category": "Industry Association",
        "supported_industries": ["Plastics", "Energy", "Agriculture", "Chemicals"],
        "supported_countries": ["Asia", "Middle East", "Worldwide"],
        "supported_event_types": ["Conferences", "Summits"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.cmtevents.com/main.aspx"},
    },
    {
        "id": "ieee_events",
        "name": "IEEE Events",
        "website_url": "https://events.vtools.ieee.org/",
        "source_category": "Industry Association",
        "supported_industries": ["Electrical Engineering", "Computing", "AI", "Communications"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Symposiums", "Workshops"],
        "access_method": "official_api",
        "api_docs_url": "https://events.vtools.ieee.org/api/doc/events",
        "api_auth_requirements": "None (public API, at most one request a minute)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"api_url": "https://events.vtools.ieee.org/RST/events/api/public/v8/events/list"},
    },
    {
        "id": "acm",
        "name": "ACM (Association for Computing Machinery)",
        "website_url": "https://www.acm.org/",
        "source_category": "Industry Association",
        "supported_industries": ["Computing", "Software", "Information Technology", "AI"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Symposiums"],
        "access_method": "html_listing",
        "api_docs_url": "https://www.acm.org/conferences",
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.acm.org/conferences/conference-events"},
    },
    {
        "id": "spie_conferences",
        "name": "SPIE Conferences",
        "website_url": "https://spie.org/conferences-and-exhibitions",
        "source_category": "Industry Association",
        "supported_industries": ["Optics", "Photonics", "Lasers", "Imaging"],
        "supported_countries": ["Worldwide", "United States", "Europe"],
        "supported_event_types": ["Conferences", "Exhibitions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://spie.org/conferences-and-exhibitions"},
    },
    {
        "id": "acs",
        "name": "American Chemical Society (ACS)",
        "website_url": "https://www.acs.org/meetings.html",
        "source_category": "Industry Association",
        "supported_industries": ["Chemistry", "Pharma", "Materials Science"],
        "supported_countries": ["United States", "Worldwide"],
        "supported_event_types": ["National Meetings", "Conferences"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.acs.org/meetings.html"},
    },
    {
        "id": "asme",
        "name": "ASME",
        "website_url": "https://www.asme.org/conferences-events",
        "source_category": "Industry Association",
        "supported_industries": ["Mechanical Engineering", "Manufacturing", "Robotics"],
        "supported_countries": ["Worldwide", "United States"],
        "supported_event_types": ["Conferences", "Technical Forums"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.asme.org/conferences-events"},
    },
    {
        "id": "asce",
        "name": "ASCE",
        "website_url": "https://www.asce.org/",
        "source_category": "Industry Association",
        "supported_industries": ["Civil Engineering", "Infrastructure", "Construction"],
        "supported_countries": ["Worldwide", "United States"],
        "supported_event_types": ["Conferences", "Continuing Education"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.asce.org/education-and-events"},  # old path 404 (checked 2026-10-27)
    },
    {
        "id": "asco",
        "name": "ASCO (American Society of Clinical Oncology)",
        "website_url": "https://www.asco.org/",
        "source_category": "Industry Association",
        "supported_industries": ["Clinical Oncology", "Cancer Research", "Healthcare"],
        "supported_countries": ["United States", "Worldwide"],
        "supported_event_types": ["Annual Meeting", "Thematic Symposia"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://meetings.asco.org/"},
    },

    # =======================================================================
    # Category E: Exhibition Venue Calendars (56 to 65)
    # =======================================================================
    {
        "id": "dwtc_events",
        "name": "Dubai World Trade Centre Events",
        "website_url": "https://www.dwtc.com/en/events/",
        "source_category": "Venue Calendar",
        "supported_industries": ["Exhibitions", "Trade Shows", "Congresses", "Global Trade"],
        "supported_countries": ["United Arab Emirates", "Middle East"],
        "supported_event_types": ["Venue Events", "Exhibitions", "Summits"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.dwtc.com/en/"},  # events are published as JSON-LD on the homepage; /en/events/ lists none (checked 2026-10-27)
    },
    {
        "id": "excel_london",
        "name": "ExCeL London",
        "website_url": "https://www.excel.london/whats-on",
        "source_category": "Venue Calendar",
        "supported_industries": ["Exhibitions", "Conventions", "Trade Shows", "Defense", "Tech"],
        "supported_countries": ["United Kingdom", "London"],
        "supported_event_types": ["What's On", "Expos", "Conferences"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.excel.london/whats-on"},  # excel-london.co.uk no longer answers (checked 2026-10-27)
    },
    {
        "id": "javits_center",
        "name": "Javits Center",
        "website_url": "https://www.javitscenter.com/",
        "source_category": "Venue Calendar",
        "supported_industries": ["Trade Shows", "Conventions", "Exhibitions", "Auto", "Comic Con"],
        "supported_countries": ["United States", "New York"],
        "supported_event_types": ["Events Calendar", "Trade Shows"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.javitscenter.com/events/"},
    },
    {
        "id": "mccormick_place",
        "name": "McCormick Place",
        "website_url": "https://www.mccormickplace.com/",
        "source_category": "Venue Calendar",
        "supported_industries": ["Trade Shows", "Conventions", "Industrial", "Medical"],
        "supported_countries": ["United States", "Chicago"],
        "supported_event_types": ["Events Calendar", "B2B Trade Shows"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.mccormickplace.com/events/"},
    },
    {
        "id": "messe_frankfurt_venue",
        "name": "Messe Frankfurt Venue",
        "website_url": "https://www.messefrankfurt.com/",
        "source_category": "Venue Calendar",
        "supported_industries": ["Trade Fairs", "Congresses", "Automotive", "Light+Building"],
        "supported_countries": ["Germany", "Frankfurt"],
        "supported_event_types": ["Fairs", "Congresses"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.messefrankfurt.com/frankfurt/en/event-search.html"},  # its event list loads from a script feed (not read; needs approval)
    },
    {
        "id": "fira_barcelona",
        "name": "Fira Barcelona",
        "website_url": "https://www.firabarcelona.com/en/",
        "source_category": "Venue Calendar",
        "supported_industries": ["Mobile World Congress", "Smart City", "Industrial", "Food"],
        "supported_countries": ["Spain", "Barcelona", "Europe"],
        "supported_event_types": ["Trade Fairs", "Congresses"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.firabarcelona.com/en/events/"},
    },
    {
        "id": "singapore_expo",
        "name": "Singapore EXPO",
        "website_url": "https://www.singaporeexpo.com.sg/",
        "source_category": "Venue Calendar",
        "supported_industries": ["Trade Exhibitions", "Conferences", "Consumer Shows", "Fintech"],
        "supported_countries": ["Singapore", "Southeast Asia"],
        "supported_event_types": ["Events Calendar", "Trade Shows"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.singaporeexpo.com.sg/whats-on/events"},
    },
    {
        "id": "hkcec",
        "name": "Hong Kong Convention and Exhibition Centre",
        "website_url": "https://www.hkcec.com/",
        "source_category": "Venue Calendar",
        "supported_industries": ["International Fairs", "B2B Expos", "Conventions", "Jewellery"],
        "supported_countries": ["Hong Kong", "Asia"],
        "supported_event_types": ["Events Calendar", "Fairs"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.hkcec.com/en/event-calendar"},
    },
    {
        "id": "bitec_bangkok",
        "name": "BITEC Bangkok",
        "website_url": "https://www.bitec.co.th/",
        "source_category": "Venue Calendar",
        "supported_industries": ["Industrial Fairs", "Auto Shows", "Conferences", "Machinery"],
        "supported_countries": ["Thailand", "Southeast Asia"],
        "supported_event_types": ["Events Calendar", "Trade Shows"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Implemented",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.bitec.co.th/events"},
    },
    {
        "id": "india_expo_centre",
        "name": "India Expo Centre & Mart",
        "website_url": "https://indiaexpomart.com/",
        "source_category": "Venue Calendar",
        "supported_industries": ["Handicrafts", "Auto", "Renewable Energy", "Medical", "Textiles"],
        "supported_countries": ["India", "Greater Noida", "Delhi NCR"],
        "supported_event_types": ["Trade Expos", "Mart Events", "Conventions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://indiaexpomart.com/upcoming-events/"},  # indiaexpocentre.com now redirects here (checked 2026-10-27)
    },

    # =======================================================================
    # Category F: Government and International Trade Sources (66 to 70)
    # =======================================================================
    {
        "id": "us_ita",
        "name": "U.S. International Trade Administration",
        "website_url": "https://www.trade.gov/attend-event",
        "source_category": "Government & Trade",
        "supported_industries": ["International Trade", "Export", "Trade Missions", "Energy", "Aerospace"],
        "supported_countries": ["United States", "Worldwide"],
        "supported_event_types": ["Trade Missions", "Webinars", "Expos"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Approved (Official Government)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://www.trade.gov/attend-event"},
    },
    {
        "id": "globaledge",
        "name": "GlobalEDGE",
        "website_url": "https://globaledge.msu.edu/",
        "source_category": "Government & Trade",
        "supported_industries": ["International Business", "Trade", "Research", "Economics"],
        "supported_countries": ["Worldwide", "United States"],
        "supported_event_types": ["Trade Calendars", "Academic Programs"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Under Evaluation",
        "integration_status": "Under Evaluation",
        "health_status": "untested",
        "is_enabled": False,
        "config": {"calendar_url": "https://globaledge.msu.edu/academy/announcements"},
    },
    {
        "id": "intracen",
        "name": "International Trade Centre (ITC)",
        "website_url": "https://intracen.org/",
        "source_category": "Government & Trade",
        "supported_industries": ["Developing Markets", "SME Trade", "Export Development", "Women in Trade"],
        "supported_countries": ["Worldwide", "Geneva"],
        "supported_event_types": ["Workshops", "Trade Forums", "High-Level Dialogues"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Approved (UN / WTO Body)",
        "integration_status": "Approved",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://intracen.org/news-and-events/events"},
    },
    {
        "id": "european_commission",
        "name": "European Commission",
        "website_url": "https://commission.europa.eu/",
        "source_category": "Government & Trade",
        "supported_industries": ["European Trade", "Horizon Europe", "Green Deal", "Digital Single Market"],
        "supported_countries": ["European Union", "Worldwide"],
        "supported_event_types": ["Policy Conferences", "Info Days", "Workshops"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Approved (Official EU)",
        "integration_status": "Approved",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"calendar_url": "https://commission.europa.eu/get-involved/events_en"},  # moved (checked 2026-10-27); generic reader finds its events
    },
    {
        "id": "indian_trade_portal",
        "name": "India Trade Portal",
        "website_url": "https://indiantradeportal.in/",
        "source_category": "Government & Trade",
        "supported_industries": ["Indian Exports", "Bilateral Trade", "Exhibition Calendars", "Engineering"],
        "supported_countries": ["India", "Worldwide"],
        "supported_event_types": ["Trade Fairs", "Buyer-Seller Meets", "Delegations"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"calendar_url": "https://indiantradeportal.in/"},
    },

    # =======================================================================
    # Category G: Additional Search and Research Tools (71 to 74)
    # =======================================================================
    {
        "id": "google_search",
        "name": "Google Search Engine",
        "website_url": "https://www.google.com/",
        "source_category": "Search & Research Tool",
        "supported_industries": ["All Industries"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Search Discovery", "Official Event Link Discovery"],
        "access_method": "search_engine",
        "api_docs_url": "https://developers.google.com/custom-search/v1/overview",
        "api_auth_requirements": "Custom Search API Key & CX ID / Headless Verification",
        "permission_status": "Permitted (Public Web / Search)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"search_role": "supplementary_seed_generator"},
    },
    {
        "id": "bing_search",
        "name": "Bing Search Engine",
        "website_url": "https://www.bing.com/",
        "source_category": "Search & Research Tool",
        "supported_industries": ["All Industries"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Search Discovery", "Official Event Link Discovery"],
        "access_method": "search_engine",
        "api_docs_url": "https://www.microsoft.com/en-us/bing/apis/bing-web-search-api",
        "api_auth_requirements": "Bing Web Search API Key / Public Queries",
        "permission_status": "Permitted (Public Web / Search)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"search_role": "supplementary_seed_generator"},
    },
    {
        "id": "linkedin_search",
        "name": "LinkedIn Search & Events",
        "website_url": "https://www.linkedin.com/",
        "source_category": "Search & Research Tool",
        "supported_industries": ["Professional", "Corporate", "Technology"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Public Event Announcements", "Organizer Company Profiles"],
        "access_method": "search_engine",
        "api_docs_url": None,
        "api_auth_requirements": "Public Web / Headless Browser Verification",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"search_role": "organizer_and_event_discovery"},
    },
    {
        "id": "google_maps",
        "name": "Google Maps",
        "website_url": "https://maps.google.com/",
        "source_category": "Search & Research Tool",
        "supported_industries": ["Venues", "Locations", "Convention Centres"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Location & Venue Verification"],
        "access_method": "interactive_search",
        "api_docs_url": "https://developers.google.com/maps",
        "api_auth_requirements": "Google Maps Platform API Key",
        "permission_status": "Under Evaluation",
        "integration_status": "Under Evaluation",
        "health_status": "untested",
        "is_enabled": False,
        "config": {"search_role": "venue_geocoding_and_verification"},
    },

    # =======================================================================
    # Existing Platform Sources (Preserved)
    # =======================================================================
    {
        "id": "allevents",
        "name": "AllEvents.in",
        "website_url": "https://allevents.in/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["All Industries", "Business", "Entertainment", "Workshops"],
        "supported_countries": ["India", "Worldwide"],
        "supported_event_types": ["Conferences", "Workshops", "Meetups"],
        "access_method": "schema_org",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web JSON-LD)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"listing_template": "https://allevents.in/{city}"},
    },
    {
        "id": "skillboxes",
        "name": "Skillboxes",
        "website_url": "https://www.skillboxes.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Entertainment", "Music", "Festivals", "Culture"],
        "supported_countries": ["India"],
        "supported_event_types": ["Festivals", "Performances", "Conferences"],
        "access_method": "schema_org",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "healthy",
        "is_enabled": True,
        "config": {"listing_template": "https://www.skillboxes.com/events"},
    },
    # =======================================================================
    # Added 2026-10-28: event directories found by web research and checked
    # with this catalogue's own listing reader (robots.txt allows the page;
    # at least two upcoming events with schema.org data / linked event pages).
    # =======================================================================
    {
        # Country pages with linked event pages (checked 2026-10-28: UAE, India, Germany, United States)
        "id": "industryevents",
        "name": "IndustryEvents",
        "website_url": "https://www.industryevents.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["All Industries", "Business", "Technology", "Healthcare", "Manufacturing", "Energy", "Construction"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Exhibitions", "Trade Shows", "Summits"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://www.industryevents.com/events/country/{country}"},
    },
    {
        # Country pages with schema.org events (checked 2026-10-28: Germany, India, United States, UAE)
        "id": "conferencegrid",
        "name": "ConferenceGrid",
        "website_url": "https://conferencegrid.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["All Industries", "Business", "Technology", "Healthcare", "Manufacturing", "Energy", "Construction"],
        "supported_countries": ["Worldwide"],
        "supported_event_types": ["Conferences", "Summits", "Trade Shows"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://conferencegrid.com/conferences/{country}"},
    },
    {
        # Medical conference country pages (checked 2026-10-28: India, Germany, UAE; the United States page does not exist)
        "id": "convene_md",
        "name": "Convene.md (medical conferences)",
        "website_url": "https://convene.md/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Healthcare", "Pharmaceuticals", "Medical"],
        "supported_countries": ["India", "Germany", "United Arab Emirates"],
        "supported_event_types": ["Conferences", "Congresses", "Workshops"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://convene.md/country/{country}/"},
    },
    {
        # Tech conference country pages (checked 2026-10-28: UAE, India, Germany; no United States events found)
        "id": "getonsite",
        "name": "OnSite (tech conferences)",
        "website_url": "https://getonsite.dev/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Technology", "AI", "Software", "Business"],
        "supported_countries": ["United Arab Emirates", "India", "Germany"],
        "supported_event_types": ["Conferences", "Summits", "Exhibitions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://getonsite.dev/conferences/in/{country}"},
    },
    {
        # Trade show country pages (checked 2026-10-28: UAE, India, Germany; no United States events found)
        "id": "tradeshowbuzz",
        "name": "TradeShowBuzz",
        "website_url": "https://tradeshowbuzz.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["All Industries", "Business", "Technology", "Healthcare", "Manufacturing", "Energy", "Construction"],
        "supported_countries": ["United Arab Emirates", "India", "Germany"],
        "supported_event_types": ["Trade Shows", "Exhibitions", "Conferences"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://tradeshowbuzz.com/countries/{country}"},
    },
    {
        # German tech conference listing with schema.org events (checked 2026-10-28)
        "id": "hackevents",
        "name": "HackEvents (tech conferences, Germany)",
        "website_url": "https://www.hackevents.net/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Technology", "AI", "Software", "Cybersecurity"],
        "supported_countries": ["Germany"],
        "supported_event_types": ["Conferences", "Meetups", "Hackathons"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://www.hackevents.net/de/conferences"},
    },
    {
        # European trade fair calendar (checked 2026-10-28: ART COLOGNE, electronica, EuroTier …)
        "id": "eventas",
        "name": "Eventas trade fair calendar",
        "website_url": "https://www.eventas.eu/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["All Industries", "Business", "Technology", "Healthcare", "Manufacturing", "Energy", "Construction"],
        "supported_countries": ["Germany"],
        "supported_event_types": ["Trade Fairs", "Exhibitions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://www.eventas.eu/en/trade-fair-calendar"},
    },
    {
        # Medical conference listing for India (checked 2026-10-28; its other country pages use their own slugs)
        "id": "medicaleventsnow",
        "name": "Medical Events Now",
        "website_url": "https://medicaleventsnow.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Healthcare", "Pharmaceuticals", "Medical"],
        "supported_countries": ["India"],
        "supported_event_types": ["Conferences", "Congresses", "CME"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://medicaleventsnow.com/events/india"},
    },
    {
        # US construction industry event listing (checked 2026-10-28)
        "id": "pilars_events",
        "name": "Pilars construction events",
        "website_url": "https://pilars.ai/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Construction", "Real Estate", "Technology"],
        "supported_countries": ["United States"],
        "supported_event_types": ["Conferences", "Conventions", "Expos"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://pilars.ai/events"},
    },
    {
        # Indian building & construction exhibitions with schema.org events (checked 2026-10-28)
        "id": "theexpoco",
        "name": "The Expo Co (building & construction exhibitions, India)",
        "website_url": "https://theexpoco.com/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["Construction", "Building Materials", "Interiors"],
        "supported_countries": ["India"],
        "supported_event_types": ["Exhibitions", "Trade Shows"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://theexpoco.com/building-construction-exhibitions"},
    },
    {
        # UAE medical congress organiser's events page (checked 2026-10-28)
        "id": "mco_events",
        "name": "MCO medical congresses (UAE)",
        "website_url": "https://mco.ae/",
        "source_category": "International Exhibition Organizer",
        "supported_industries": ["Healthcare", "Pharmaceuticals", "Medical"],
        "supported_countries": ["United Arab Emirates"],
        "supported_event_types": ["Congresses", "Conferences"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://mco.ae/events/"},
    },
    {
        # Indian expos & fairs selection (checked 2026-10-28; other countries use different page names)
        "id": "tradefest_india",
        "name": "Tradefest (India expos & fairs)",
        "website_url": "https://tradefest.io/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["All Industries", "Business", "Technology", "Healthcare", "Manufacturing", "Energy", "Construction"],
        "supported_countries": ["India"],
        "supported_event_types": ["Exhibitions", "Trade Fairs", "Conferences"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://tradefest.io/en/selection/best-expos-exhibitions-fairs-in-india"},
    },
    {
        # German trade fair calendar for 2027 (checked 2026-10-28; the page is per year)
        "id": "instaff_exhibitions",
        "name": "InStaff exhibition calendar (Germany)",
        "website_url": "https://en.instaff.jobs/",
        "source_category": "Global Event Discovery",
        "supported_industries": ["All Industries", "Business", "Technology", "Healthcare", "Manufacturing", "Energy", "Construction"],
        "supported_countries": ["Germany"],
        "supported_event_types": ["Trade Fairs", "Exhibitions"],
        "access_method": "html_listing",
        "api_docs_url": None,
        "api_auth_requirements": "None (Public Web)",
        "permission_status": "Permitted (Public Web)",
        "integration_status": "Operational",
        "health_status": "untested",
        "is_enabled": True,
        "config": {"listing_template": "https://en.instaff.jobs/exhibitions/2027"},
    },
]


def seed_or_sync_source_registry(db: Session) -> dict[str, int]:
    """Ensures every candidate source is registered in `event_discovery_sources`.

    Preserves any existing admin configurations, executions, or counters.
    """
    created = 0
    updated = 0

    for item in ALL_CANDIDATE_SOURCES:
        source_id = item["id"]
        existing = db.get(EventDiscoverySource, source_id)
        if not existing:
            new_source = EventDiscoverySource(
                id=source_id,
                name=item["name"],
                website_url=item["website_url"],
                source_category=item["source_category"],
                supported_industries=item["supported_industries"],
                supported_countries=item["supported_countries"],
                supported_event_types=item["supported_event_types"],
                access_method=item["access_method"],
                api_docs_url=item.get("api_docs_url"),
                api_auth_requirements=item.get("api_auth_requirements"),
                permission_status=item.get("permission_status", "Permitted (Public Web)"),
                integration_status=item.get("integration_status", "Not Evaluated"),
                health_status=item.get("health_status", "untested"),
                is_enabled=item.get("is_enabled", True),
                config=item.get("config", {}),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(new_source)
            created += 1
        else:
            # Sync metadata fields without overwriting user counters or custom toggles
            existing.name = item["name"]
            existing.website_url = item["website_url"]
            existing.source_category = item["source_category"]
            existing.supported_industries = item["supported_industries"]
            existing.supported_countries = item["supported_countries"]
            existing.supported_event_types = item["supported_event_types"]
            existing.access_method = item["access_method"]
            if item.get("api_docs_url"):
                existing.api_docs_url = item["api_docs_url"]
            if item.get("api_auth_requirements"):
                existing.api_auth_requirements = item["api_auth_requirements"]
            # If still Not Evaluated, update to the curated baseline status
            if existing.integration_status in ("Not Evaluated", "Testing"):
                existing.integration_status = item.get("integration_status", existing.integration_status)
            updated += 1

    db.commit()
    return {"created": created, "updated": updated, "total": len(ALL_CANDIDATE_SOURCES)}


def get_registry_summary_stats(db: Session) -> dict[str, Any]:
    """Computes exact source registry summary statistics as required by Section 9."""
    sources = db.scalars(select(EventDiscoverySource)).all()
    if not sources:
        seed_or_sync_source_registry(db)
        sources = db.scalars(select(EventDiscoverySource)).all()

    total_sources = len(sources)

    # Categories breakdown
    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_health: dict[str, int] = {}
    by_access_method: dict[str, int] = {}

    sources_evaluated = 0
    sources_approved = 0
    sources_integrated = 0
    sources_tested = 0
    operational_sources = 0
    awaiting_credentials = 0
    permission_review = 0
    temporarily_unavailable = 0
    unsupported = 0
    enabled_sources = 0

    for s in sources:
        cat = s.source_category
        status = s.integration_status
        health = s.health_status
        method = s.access_method

        by_category[cat] = by_category.get(cat, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_health[health] = by_health.get(health, 0) + 1
        by_access_method[method] = by_access_method.get(method, 0) + 1

        if s.is_enabled:
            enabled_sources += 1

        if status != "Not Evaluated":
            sources_evaluated += 1

        if status in ("Approved", "Implemented", "Testing", "Operational"):
            sources_approved += 1

        if status in ("Implemented", "Testing", "Operational"):
            sources_integrated += 1

        if s.last_successful_execution or s.events_extracted > 0 or status == "Operational":
            sources_tested += 1

        if status == "Operational":
            operational_sources += 1
        elif status == "Awaiting Credentials":
            awaiting_credentials += 1
        elif status == "Permission Review":
            permission_review += 1
        elif status == "Temporarily Unavailable":
            temporarily_unavailable += 1
        elif status == "Unsupported":
            unsupported += 1

    return {
        "total_sources": total_sources,
        "sources_evaluated": sources_evaluated,
        "sources_approved": sources_approved,
        "sources_integrated": sources_integrated,
        "sources_tested": sources_tested,
        "operational_sources": operational_sources,
        "awaiting_credentials": awaiting_credentials,
        "permission_review": permission_review,
        "temporarily_unavailable": temporarily_unavailable,
        "unsupported": unsupported,
        "enabled_sources": enabled_sources,
        "by_category": by_category,
        "by_status": by_status,
        "by_health": by_health,
        "by_access_method": by_access_method,
        "status_breakdown": by_status,
        "category_breakdown": by_category,
        "access_method_breakdown": by_access_method,
    }


def list_sources(
    db: Session,
    category: str | None = None,
    status: str | None = None,
    health: str | None = None,
    access_method: str | None = None,
    is_enabled: bool | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[EventDiscoverySource], int]:
    """Retrieves paginated and filtered sources from the registry."""
    stmt = select(EventDiscoverySource)

    if category and category != "__all__":
        stmt = stmt.where(EventDiscoverySource.source_category == category)
    if status and status != "__all__":
        stmt = stmt.where(EventDiscoverySource.integration_status == status)
    if health and health != "__all__":
        stmt = stmt.where(EventDiscoverySource.health_status == health)
    if access_method and access_method != "__all__":
        stmt = stmt.where(EventDiscoverySource.access_method == access_method)
    if is_enabled is not None:
        stmt = stmt.where(EventDiscoverySource.is_enabled == is_enabled)
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(EventDiscoverySource.name).like(term),
                func.lower(EventDiscoverySource.id).like(term),
                func.lower(EventDiscoverySource.website_url).like(term),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    stmt = stmt.order_by(
        EventDiscoverySource.is_enabled.desc(),
        EventDiscoverySource.source_category.asc(),
        EventDiscoverySource.name.asc(),
    ).offset(offset).limit(limit)

    results = db.scalars(stmt).all()
    return list(results), total


def get_source(db: Session, source_id: str) -> EventDiscoverySource | None:
    return db.get(EventDiscoverySource, source_id)


def update_source(db: Session, source_id: str, updates: dict[str, Any]) -> EventDiscoverySource | None:
    source = db.get(EventDiscoverySource, source_id)
    if not source:
        return None

    allowed_fields = (
        "is_enabled",
        "integration_status",
        "permission_status",
        "health_status",
        "api_docs_url",
        "api_auth_requirements",
        "config",
    )
    for field in allowed_fields:
        if field in updates and updates[field] is not None:
            setattr(source, field, updates[field])

    source.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(source)
    return source


def record_source_execution(
    db: Session,
    source_id: str,
    events_found: int = 0,
    events_extracted: int = 0,
    unique_events: int = 0,
    events_discovered: int | None = None,
    success: bool = True,
    error: str | None = None,
    health_status: str | None = None,
) -> None:
    """Updates telemetry and last execution metrics for a source."""
    source = db.get(EventDiscoverySource, source_id)
    if not source:
        return

    found = events_discovered if events_discovered is not None else events_found
    source.events_discovered += found
    source.events_extracted += events_extracted or found
    source.unique_events_discovered += unique_events

    if error or not success:
        source.last_error = error or "Execution failed"
        source.health_status = health_status or ("failing" if (events_extracted or found) == 0 else "degraded")
    else:
        source.last_successful_execution = datetime.now(timezone.utc)
        source.last_error = None
        source.health_status = health_status or "healthy"
        if source.integration_status in ("Implemented", "Testing", "Approved"):
            source.integration_status = "Operational"

    source.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
