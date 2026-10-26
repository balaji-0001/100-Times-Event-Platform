import {
  Building,
  Building2,
  Globe,
  Landmark,
  Search,
  Ticket,
  Users,
} from 'lucide-react';

export const DEFAULT_LISTING_URLS = [
  'https://allevents.in/{city}',
  'https://www.eventbrite.com/d/{country}--{city}/events/',
  'https://www.eventbrite.com/d/{city}/events/',
  'https://www.meetup.com/find/?location={city}&source=EVENTS',
  'https://10times.com/{city}',
  'https://www.skillboxes.com/events',
];

export interface OperationalSourceItem {
  id: string;
  name: string;
  url: string;
  tag: string;
}

export interface SourceCategoryGroup {
  slug: string;
  name: string;
  description: string;
  icon: any;
  operationalCount: number;
  totalCount: number;
  sources: OperationalSourceItem[];
}

export const SOURCE_REGISTRY_CATEGORIES: SourceCategoryGroup[] = [
  {
    slug: 'global_event_discovery',
    name: 'Global Event Discovery',
    description: 'Worldwide directories, conference alerts, trade fair registries, and developer event hubs.',
    icon: Globe,
    operationalCount: 14,
    totalCount: 22,
    sources: [
      { id: 'dev_events', name: 'dev.events', url: 'https://dev.events/', tag: 'Tech & Dev Summits' },
      { id: 'wikicfp', name: 'WikiCFP', url: 'http://www.wikicfp.com/', tag: 'Academic & Tech Calls' },
      { id: '10times', name: '10Times', url: 'https://10times.com/', tag: 'Global Business Expos' },
      { id: 'eventseye', name: 'EventsEye', url: 'https://www.eventseye.com/', tag: 'Trade Shows & Exhibitions' },
      { id: 'clocate', name: 'Clocate', url: 'https://www.clocate.com/', tag: 'International Conferences' },
      { id: 'tradeshowradar', name: 'Trade Show Radar', url: 'https://www.tradeshowradar.com/', tag: 'Global B2B Radar' },
      { id: 'tradefairdates', name: 'TradeFairDates', url: 'https://www.tradefairdates.com/', tag: 'Worldwide Fair Dates' },
      { id: 'biztradeshows', name: 'BizTradeShows', url: 'https://www.biztradeshows.com/', tag: 'Industry Trade Fairs' },
      { id: 'all_conference_alert', name: 'All Conference Alert', url: 'https://www.allconferencealert.com/', tag: 'Global Conference Alerts' },
      { id: 'conference_alerts', name: 'Conference Alerts', url: 'https://www.conferencealert.com/', tag: 'Academic & Industry Events' },
      { id: 'eventbrite', name: 'Eventbrite', url: 'https://www.eventbrite.com/', tag: 'Ticketing & Community' },
      { id: 'meetup', name: 'Meetup', url: 'https://www.meetup.com/', tag: 'Professional Communities' },
      { id: 'allevents', name: 'AllEvents.in', url: 'https://allevents.in/', tag: 'Global City Listings' },
      { id: 'skillboxes', name: 'Skillboxes', url: 'https://www.skillboxes.com/', tag: 'Conferences & Workshops' },
    ],
  },
  {
    slug: 'event_platform_api',
    name: 'Event Platform & API',
    description: 'Official enterprise event discovery and ticketing APIs with structured metadata.',
    icon: Ticket,
    operationalCount: 1,
    totalCount: 10,
    sources: [
      { id: 'ticketmaster_api', name: 'Ticketmaster Discovery API v2', url: 'https://developer.ticketmaster.com', tag: 'Official REST API' },
    ],
  },
  {
    slug: 'international_exhibition_organizer',
    name: 'International Exhibition Organizer',
    description: 'World-leading commercial trade show and B2B exhibition organizers.',
    icon: Building2,
    operationalCount: 6,
    totalCount: 15,
    sources: [
      { id: 'rx_global', name: 'RX Global (Reed Exhibitions)', url: 'https://rxglobal.com/', tag: 'Global Exhibition Leader' },
      { id: 'informa_markets', name: 'Informa Markets', url: 'https://www.informamarkets.com/', tag: 'Global B2B Marketplaces' },
      { id: 'terrapinn', name: 'Terrapinn', url: 'https://www.terrapinn.com/', tag: 'Business Conferences & Expos' },
      { id: 'messe_frankfurt_org', name: 'Messe Frankfurt (Organizer)', url: 'https://www.messefrankfurt.com/', tag: 'International Trade Fairs' },
      { id: 'dmg_events', name: 'dmg events', url: 'https://www.dmgevents.com/', tag: 'Energy & Construction' },
      { id: 'dwtc_org', name: 'Dubai World Trade Centre (Organizer)', url: 'https://www.dwtc.com/', tag: 'Middle East Premier Expos' },
    ],
  },
  {
    slug: 'industry_association',
    name: 'Industry Association',
    description: 'Professional engineering bodies, trade finance councils, and research societies.',
    icon: Users,
    operationalCount: 3,
    totalCount: 10,
    sources: [
      { id: 'gtr_events', name: 'GTR Events (Global Trade Review)', url: 'https://www.gtreview.com/events/', tag: 'Trade & Supply Chain Finance' },
      { id: 'ieee_events', name: 'IEEE Events', url: 'https://events.ieee.org/', tag: 'Engineering & Computing' },
      { id: 'acm', name: 'ACM (Association for Computing Machinery)', url: 'https://www.acm.org/', tag: 'Computer Science Summits' },
    ],
  },
  {
    slug: 'venue_calendar',
    name: 'Venue Calendar',
    description: 'Official convention, expo centre, and mart exhibition calendars worldwide.',
    icon: Building,
    operationalCount: 6,
    totalCount: 10,
    sources: [
      { id: 'dwtc_events', name: 'Dubai World Trade Centre Events', url: 'https://www.dwtc.com/en/events/', tag: 'Dubai / MENA Hub' },
      { id: 'excel_london', name: 'ExCeL London', url: 'https://www.excel-london.co.uk/visitor/whats-on/', tag: 'London / UK Hub' },
      { id: 'javits_center', name: 'Javits Center (New York)', url: 'https://www.javitscenter.com/', tag: 'New York / US Mega Venue' },
      { id: 'mccormick_place', name: 'McCormick Place (Chicago)', url: 'https://www.mccormickplace.com/', tag: 'Chicago / North America Hub' },
      { id: 'messe_frankfurt_venue', name: 'Messe Frankfurt Venue', url: 'https://www.messefrankfurt.com/', tag: 'Frankfurt / European Hub' },
      { id: 'india_expo_centre', name: 'India Expo Centre & Mart', url: 'https://indiaexpocentre.com/', tag: 'Delhi NCR / India Venue' },
    ],
  },
  {
    slug: 'government_trade',
    name: 'Government & Trade',
    description: 'National trade promotion portals, export development councils, and commercial services.',
    icon: Landmark,
    operationalCount: 2,
    totalCount: 5,
    sources: [
      { id: 'us_ita', name: 'U.S. International Trade Administration', url: 'https://www.trade.gov/attend-event', tag: 'US Commerce Dept' },
      { id: 'indian_trade_portal', name: 'India Trade Portal', url: 'https://indiantradeportal.in/', tag: 'Ministry of Commerce' },
    ],
  },
  {
    slug: 'search_research_tool',
    name: 'Search & Research Tool',
    description: 'Live search engine queries and official business social feeds.',
    icon: Search,
    operationalCount: 3,
    totalCount: 4,
    sources: [
      { id: 'google_search', name: 'Google Search Engine', url: 'https://www.google.com/', tag: 'Global Web Index' },
      { id: 'bing_search', name: 'Bing Search Engine', url: 'https://www.bing.com/', tag: 'Microsoft Search Index' },
      { id: 'linkedin_search', name: 'LinkedIn Search & Events', url: 'https://www.linkedin.com/', tag: 'Corporate Network' },
    ],
  },
];

export const ALL_OPERATIONAL_IDS = SOURCE_REGISTRY_CATEGORIES.flatMap((c) => c.sources.map((s) => s.id));
export const CONSUMER_AGGREGATOR_IDS = ['10times', 'eventbrite', 'meetup', 'allevents', 'skillboxes'];

export const DEFAULT_ACTIVE_SOURCES: string[] = Array.from(
  new Set([
    'web',
    'google_search',
    'bing_search',
    'global_adapters',
    'consumer_aggregators',
    'event_platforms',
    'ticketmaster',
    'ticketmaster_api',
    ...ALL_OPERATIONAL_IDS,
  ])
);
