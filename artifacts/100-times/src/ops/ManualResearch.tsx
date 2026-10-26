import { useEffect, useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { keys } from './api';
import { Link } from 'wouter';
import {
  AlertTriangle,
  Building2,
  Eye,
  Calendar,
  CalendarX,
  Check,
  Compass,
  Facebook,
  FilterX,
  Globe,
  Instagram,
  Layers,
  Linkedin,
  MapPin,
  Mail,
  MessageCircle,
  Phone,
  Radio,
  Search,
  Send,
  Share2,
  Shield,
  ShieldAlert,
  Sliders,
  Tag,
  Square,
  Ticket,
  Twitter,
} from 'lucide-react';
import { useCategories, useDiscoveryAutoStatus, useRunDiscovery, useActiveDiscoveryRun, useStopDiscoveryRun } from './api';
import { GeoChecklistSelector } from './GeoChecklistSelector';
import { DiscoverySourcesManager } from './DiscoverySourcesManager';
import { DEFAULT_ACTIVE_SOURCES } from './discoverySourcesConfig';
import { Btn, DL, Drawer, ErrorState, Notice, inputClass } from './ui';

const num = (v: string, fallback: number) => {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : fallback;
};

const DEFAULT_CATEGORIES = [
  'Construction',
  'Energy and Power Generation',
  'Finance',
  'Healthcare',
  'Manufacturing',
  'Mining',
  'Oil and Gas',
  'Packaging',
  'Pharmaceuticals',
  'Telecommunications',
  'Textiles',
  'Transport and Logistics',
  'Other',
];

interface SourceOption {
  id: string;
  name: string;
  description: string;
  icon: any;
  badge?: string;
}

const AVAILABLE_SOURCES: SourceOption[] = [
  {
    id: 'web',
    name: 'Web & Industry Portals',
    description: 'Conference listing sites, trade associations, industry councils, and sector publications.',
    icon: Globe,
    badge: 'Primary',
  },
  {
    id: 'linkedin',
    name: 'LinkedIn Events & Posts',
    description: 'Public LinkedIn events, conference announcements, and organizer company updates.',
    icon: Linkedin,
  },
  {
    id: 'facebook',
    name: 'Facebook Events',
    description: 'Public Facebook events, industry groups, and conference pages.',
    icon: Facebook,
  },
  {
    id: 'instagram',
    name: 'Instagram Announcements',
    description: 'Event promo flyers, summit registration posts, and conference handles.',
    icon: Instagram,
  },
  {
    id: 'twitter',
    name: 'Twitter / X',
    description: 'Official conference handles, event announcement hashtags, and summit threads.',
    icon: Twitter,
  },
  {
    id: 'telegram',
    name: 'Telegram Channels & Groups',
    description: 'Public Telegram channels, event broadcasts, and conference community hubs.',
    icon: Send,
  },
  {
    id: 'reddit',
    name: 'Reddit Megathreads & Communities',
    description: 'Industry conference megathreads, regional meetup calendars, and event roundups.',
    icon: MessageCircle,
  },
  {
    id: 'event_platforms',
    name: 'Ticketing & Event Portals',
    description: 'Eventbrite, Meetup, Lu.ma, Townscript, and Allevents public listings.',
    icon: Ticket,
  },
];

function ToggleSwitch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
        checked ? 'bg-accent' : 'bg-foreground/20'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

function FilterRuleRow({
  icon: Icon,
  title,
  description,
  checked,
  onChange,
  badge,
  disabled,
}: {
  icon: any;
  title: string;
  description: string;
  checked: boolean;
  onChange: (val: boolean) => void;
  badge?: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3 p-3 rounded-lg border border-foreground/10 bg-card/60 hover:bg-card/90 transition-colors">
      <div className="flex items-start gap-2.5">
        <div className="p-1.5 rounded-md bg-accent/10 text-accent mt-0.5 shrink-0">
          <Icon size={14} />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground text-xs">{title}</span>
            {badge && (
              <span className="px-1.5 py-0.2 text-[9px] font-medium tracking-wide uppercase rounded bg-foreground/10 text-muted-foreground">
                {badge}
              </span>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{description}</p>
        </div>
      </div>
      <div className="pt-0.5 shrink-0">
        <ToggleSwitch checked={checked} onChange={onChange} disabled={disabled} />
      </div>
    </div>
  );
}

export function ManualResearchForm() {
  const queryClient = useQueryClient();
  const run = useRunDiscovery();
  const auto = useDiscoveryAutoStatus();
  const activeRun = useActiveDiscoveryRun();
  const stopRun = useStopDiscoveryRun();

  // Invalidate queries when an active discovery run finishes so newly discovered events display immediately
  const prevActiveRef = useRef<boolean>(false);
  useEffect(() => {
    const isCurrentlyActive = Boolean(activeRun.data?.active);
    if (prevActiveRef.current && !isCurrentlyActive) {
      queryClient.invalidateQueries({ queryKey: keys.events });
      queryClient.invalidateQueries({ queryKey: keys.discoveryRuns });
      queryClient.invalidateQueries({ queryKey: keys.discoveryStats });
      queryClient.invalidateQueries({ queryKey: keys.discoveryActiveRun });
      queryClient.invalidateQueries({ queryKey: ['discoveryRunEvents'] });
    }
    prevActiveRef.current = isCurrentlyActive;
  }, [activeRun.data?.active, queryClient]);
  const categoriesQuery = useCategories();
  const allAvailableCategories = categoriesQuery.data?.map((c) => c.name) || DEFAULT_CATEGORIES;

  const [activeTab, setActiveTab] = useState<'scope' | 'sources' | 'rejection'>('scope');

  // Geographic and sector scope state
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>(allAvailableCategories);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [depth, setDepth] = useState('12');
  const [perQuery, setPerQuery] = useState('5');
  const [eventsPerRun, setEventsPerRun] = useState('250');
  const [targetValidEvents, setTargetValidEvents] = useState('50');

  // Sources state
  const [selectedSources, setSelectedSources] = useState<string[]>(DEFAULT_ACTIVE_SOURCES);
  const [listingUrls, setListingUrls] = useState<string[]>([]);
  const [ticketmasterApiKey, setTicketmasterApiKey] = useState('');
  const [ticketmasterEnabled, setTicketmasterEnabled] = useState(false);

  // Rejection rules state
  const [fallbackToOtherSector, setFallbackToOtherSector] = useState(false);
  const [rejectNoOrganizer, setRejectNoOrganizer] = useState(true);
  const [requireOrganizerEmail, setRequireOrganizerEmail] = useState(true);
  const [requireOrganizerPhone, setRequireOrganizerPhone] = useState(false);
  const [requireOrganizerWebsite, setRequireOrganizerWebsite] = useState(false);
  const [rejectPastEvents, setRejectPastEvents] = useState(true);
  const [rejectUnparseableDates, setRejectUnparseableDates] = useState(true);
  const [rejectMissingLocation, setRejectMissingLocation] = useState(false);
  const [rejectMissingTicketUrl, setRejectMissingTicketUrl] = useState(false);
  const [rejectUnmatchedCategory, setRejectUnmatchedCategory] = useState(true);
  const [minTitleLength, setMinTitleLength] = useState('8');
  const [minDescriptionLength, setMinDescriptionLength] = useState('20');
  const [minConfidenceScore, setMinConfidenceScore] = useState('20');
  const [blacklistedKeywords, setBlacklistedKeywords] = useState('');
  const [excludedDomains, setExcludedDomains] = useState('');

  const result = run.data as Record<string, unknown> | undefined;

  // Initialize defaults from saved automated discovery settings if available
  useEffect(() => {
    if (auto.data) {
      if (auto.data.countries && auto.data.countries.length > 0) {
        setSelectedCountries(auto.data.countries);
      } else if (auto.data.country) {
        setSelectedCountries([auto.data.country]);
      }
      if (auto.data.states && auto.data.states.length > 0) setSelectedStates(auto.data.states);
      if (auto.data.cities && auto.data.cities.length > 0) setSelectedCities(auto.data.cities);
      if (auto.data.categories && auto.data.categories.length > 0) setSelectedCategories(auto.data.categories);
      if (auto.data.sources && auto.data.sources.length > 0) setSelectedSources(auto.data.sources);
      if (auto.data.listingUrls && auto.data.listingUrls.length > 0) setListingUrls(auto.data.listingUrls);
      if (auto.data.ticketmasterApiKey !== undefined) setTicketmasterApiKey(auto.data.ticketmasterApiKey || '');
      if (auto.data.ticketmasterEnabled !== undefined) setTicketmasterEnabled(Boolean(auto.data.ticketmasterEnabled));

      if (auto.data.eventsPerRun) setEventsPerRun(String(auto.data.eventsPerRun));
      if (auto.data.targetValidEvents) setTargetValidEvents(String(auto.data.targetValidEvents));
      if (auto.data.fallbackToOtherSector !== undefined) setFallbackToOtherSector(auto.data.fallbackToOtherSector);
      if (auto.data.rejectNoOrganizer !== undefined) setRejectNoOrganizer(auto.data.rejectNoOrganizer);
      if (auto.data.requireOrganizerEmail !== undefined) setRequireOrganizerEmail(auto.data.requireOrganizerEmail);
      if (auto.data.requireOrganizerPhone !== undefined) setRequireOrganizerPhone(auto.data.requireOrganizerPhone);
      if (auto.data.requireOrganizerWebsite !== undefined) setRequireOrganizerWebsite(auto.data.requireOrganizerWebsite);
      if (auto.data.rejectPastEvents !== undefined) setRejectPastEvents(auto.data.rejectPastEvents);
      if (auto.data.rejectUnparseableDates !== undefined) setRejectUnparseableDates(auto.data.rejectUnparseableDates);
      if (auto.data.rejectMissingLocation !== undefined) setRejectMissingLocation(auto.data.rejectMissingLocation);
      if (auto.data.rejectMissingTicketUrl !== undefined) setRejectMissingTicketUrl(auto.data.rejectMissingTicketUrl);
      if (auto.data.rejectUnmatchedCategory !== undefined) setRejectUnmatchedCategory(auto.data.rejectUnmatchedCategory);
      if (auto.data.minTitleLength !== undefined) setMinTitleLength(String(auto.data.minTitleLength));
      if (auto.data.minDescriptionLength !== undefined) setMinDescriptionLength(String(auto.data.minDescriptionLength));
      if (auto.data.minConfidenceScore !== undefined) setMinConfidenceScore(String(auto.data.minConfidenceScore));
      if (auto.data.blacklistedKeywords) setBlacklistedKeywords(auto.data.blacklistedKeywords.join(', '));
      if (auto.data.excludedDomains) setExcludedDomains(auto.data.excludedDomains.join(', '));
    }
  }, [auto.data]);

  const toggleCategory = (cat: string) => {
    if (run.isPending) return;
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const selectAllCategories = () => setSelectedCategories([...allAvailableCategories]);
  const clearCategories = () => setSelectedCategories([]);

  const toggleSource = (sourceId: string) => {
    if (run.isPending) return;
    setSelectedSources((prev) =>
      prev.includes(sourceId) ? prev.filter((s) => s !== sourceId) : [...prev, sourceId]
    );
  };

  const selectAllSources = () => setSelectedSources(AVAILABLE_SOURCES.map((s) => s.id));
  const clearSources = () => setSelectedSources(['web']);

  const start = () => {
    const parsedKeywords = blacklistedKeywords
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean);

    const parsedDomains = excludedDomains
      .split(',')
      .map((d) => d.trim().replace(/^https?:\/\//i, '').replace(/\/.*$/, ''))
      .filter(Boolean);

    run.mutate({
      country: selectedCountries.length ? selectedCountries[0] : undefined,
      countries: selectedCountries.length ? selectedCountries : undefined,
      states: selectedStates.length ? selectedStates : undefined,
      cities: selectedCities.length ? selectedCities : undefined,
      categories: selectedCategories.length > 0 ? selectedCategories : undefined,
      sources: selectedSources.length ? selectedSources : ['web'],
      listingUrls: listingUrls.length ? listingUrls : undefined,
      ticketmasterApiKey: ticketmasterApiKey ? ticketmasterApiKey.trim() : undefined,
      ticketmasterEnabled: ticketmasterEnabled,
      eventsPerRun: num(eventsPerRun, 50),
      targetValidEvents: num(targetValidEvents, 25),
      searchDepth: num(depth, 6),
      sourcesPerQuery: num(perQuery, 4),
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
      fallbackToOtherSector,
      rejectNoOrganizer,
      requireOrganizerEmail,
      requireOrganizerPhone,
      requireOrganizerWebsite,
      rejectPastEvents,
      rejectUnparseableDates,
      rejectMissingLocation,
      rejectMissingTicketUrl,
      rejectUnmatchedCategory,
      minTitleLength: Number(minTitleLength) || 0,
      minDescriptionLength: Number(minDescriptionLength) || 0,
      minConfidenceScore: Number(minConfidenceScore) || 0,
      blacklistedKeywords: parsedKeywords,
      excludedDomains: parsedDomains,
    });
  };

  const active = activeRun.data?.active ? activeRun.data.run : null;
  const activeSummary = active?.summary || {};

  return (
    <div className="grid gap-4 text-xs">
      {active && (
        <div className="rounded-xl border border-accent/40 bg-accent/5 p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent"></span>
              </span>
              <span className="font-semibold text-foreground text-sm">
                Discovery Run #{active.id} Executing in Backend
              </span>
            </div>
            <span className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded bg-accent/20 text-accent">
              Active Background Task
            </span>
          </div>

          <div className="mt-3 rounded-lg border border-accent/20 bg-background/80 p-3">
            <p className="text-[11px] text-muted-foreground leading-relaxed">
              ⚡ <strong>Safe to close or switch tabs:</strong> This research run is processing autonomously on the server. You can close this drawer or navigate anywhere in 100 TIMES — it will not be interrupted.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 mt-4">
            <div className="rounded-lg border border-foreground/10 bg-card p-3">
              <span className="text-[10px] text-muted-foreground block font-mono uppercase">Candidates Explored</span>
              <span className="text-xl font-bold text-foreground mt-1 block">{activeSummary.events_discovered ?? 0}</span>
            </div>
            <div className="rounded-lg border border-accent/30 bg-accent/10 p-3">
              <span className="text-[10px] text-accent block font-mono uppercase font-semibold">Valid Events Accepted</span>
              <span className="text-xl font-bold text-accent mt-1 block">{activeSummary.accepted_events ?? activeSummary.new_events ?? 0}</span>
            </div>
            <div className="rounded-lg border border-foreground/10 bg-card p-3">
              <span className="text-[10px] text-muted-foreground block font-mono uppercase">Needs Review</span>
              <span className="text-xl font-bold text-foreground mt-1 block">{activeSummary.events_needing_review ?? 0}</span>
            </div>
            <div className="rounded-lg border border-foreground/10 bg-card p-3">
              <span className="text-[10px] text-muted-foreground block font-mono uppercase">Duplicates Skipped</span>
              <span className="text-xl font-bold text-muted-foreground mt-1 block">{activeSummary.duplicate_events ?? 0}</span>
            </div>
            <div className="rounded-lg border border-foreground/10 bg-card p-3">
              <span className="text-[10px] text-muted-foreground block font-mono uppercase">Rejected</span>
              <span className="text-xl font-bold text-red-500 mt-1 block">{activeSummary.rejected_events ?? 0}</span>
            </div>
            <div className="rounded-lg border border-foreground/10 bg-card p-3">
              <span className="text-[10px] text-muted-foreground block font-mono uppercase">Organizers Found</span>
              <span className="text-xl font-bold text-foreground mt-1 block">{activeSummary.organizers_found ?? 0}</span>
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 mt-4 pt-3 border-t border-accent/20">
            <Btn
              variant="danger"
              size="sm"
              loading={stopRun.isPending}
              onClick={() => stopRun.mutate(active.id)}
            >
              <Square size={12} className="fill-current" /> Stop Discovery Run
            </Btn>
            <div className="flex items-center gap-3 font-mono-face text-[10px] uppercase tracking-wider">
              <Link href="/admin/discovery/events" className="text-accent hover:underline font-bold">
                View Discovered Events →
              </Link>
            </div>
          </div>
        </div>
      )}
      <div className="flex items-center gap-2 border-b border-foreground/10 pb-3">
        <button
          type="button"
          onClick={() => setActiveTab('scope')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            activeTab === 'scope'
              ? 'bg-accent text-accent-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-foreground/5 hover:text-foreground'
          }`}
        >
          <Compass size={13} /> Scope & Geography
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('sources')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            activeTab === 'sources'
              ? 'bg-accent text-accent-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-foreground/5 hover:text-foreground'
          }`}
        >
          <Share2 size={13} /> Sources & Websites
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('rejection')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            activeTab === 'rejection'
              ? 'bg-accent text-accent-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-foreground/5 hover:text-foreground'
          }`}
        >
          <ShieldAlert size={13} /> Event Rejection & Sector Rules
        </button>
      </div>

      {activeTab === 'scope' && (
        <div className="grid gap-3.5">
          <GeoChecklistSelector
            selectedCountries={selectedCountries}
            onCountriesChange={setSelectedCountries}
            selectedStates={selectedStates}
            onStatesChange={setSelectedStates}
            selectedCities={selectedCities}
            onCitiesChange={setSelectedCities}
            disabled={run.isPending}
          />

          <div>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <Layers size={13} className="text-accent" /> Target Sectors
              </span>
              <div className="flex gap-2 text-[10px]">
                <button
                  type="button"
                  onClick={selectAllCategories}
                  className="text-accent hover:underline font-medium"
                  disabled={run.isPending}
                >
                  Select all
                </button>
                <span>•</span>
                <button
                  type="button"
                  onClick={clearCategories}
                  className="text-muted-foreground hover:underline"
                  disabled={run.isPending}
                >
                  Clear
                </button>
              </div>
            </div>
            <span className="block text-[11px] text-muted-foreground mt-0.5 mb-2">
              Select which sectors to discover in this run
            </span>
            <div className="flex flex-wrap gap-1.5">
              {allAvailableCategories.map((cat) => {
                const active = selectedCategories.includes(cat);
                return (
                  <button
                    type="button"
                    key={cat}
                    onClick={() => toggleCategory(cat)}
                    disabled={run.isPending}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium border transition-colors ${
                      active
                        ? 'border-accent bg-accent/15 text-accent font-semibold'
                        : 'border-foreground/15 bg-card text-muted-foreground hover:border-foreground/30'
                    }`}
                  >
                    {active && <Check size={11} />}
                    {cat}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label>
              <span className="font-semibold text-foreground text-[11px]">From Date</span>{' '}
              <span className="text-muted-foreground text-[10px]">(optional event start)</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className={`${inputClass} mt-1`}
                disabled={run.isPending}
              />
            </label>
            <label>
              <span className="font-semibold text-foreground text-[11px]">To Date</span>{' '}
              <span className="text-muted-foreground text-[10px]">(optional event end)</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className={`${inputClass} mt-1`}
                disabled={run.isPending}
              />
            </label>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <label>
              <span className="font-semibold text-foreground text-[11px]">Events for this run</span>
              <input
                type="number"
                min={1}
                max={500}
                value={eventsPerRun}
                onChange={(e) => setEventsPerRun(e.target.value)}
                className={`${inputClass} mt-1`}
                disabled={run.isPending}
              />
              <span className="text-[10px] text-muted-foreground mt-0.5 block">Max events to discover</span>
            </label>
            <label>
              <span className="font-semibold text-foreground text-[11px]">Valid events to find</span>
              <input
                type="number"
                min={1}
                max={500}
                value={targetValidEvents}
                onChange={(e) => setTargetValidEvents(e.target.value)}
                className={`${inputClass} mt-1`}
                disabled={run.isPending}
              />
              <span className="text-[10px] text-muted-foreground mt-0.5 block">Searches all sources until {targetValidEvents || 50} valid events found</span>
            </label>
            <label>
              <span className="font-semibold text-foreground text-[11px]">Search queries</span>
              <input
                type="number"
                min={1}
                max={100}
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
                className={`${inputClass} mt-1`}
                disabled={run.isPending}
              />
              <span className="text-[10px] text-muted-foreground mt-0.5 block">Queries dispatched</span>
            </label>
            <label>
              <span className="font-semibold text-foreground text-[11px]">Pages per query</span>
              <input
                type="number"
                min={1}
                max={20}
                value={perQuery}
                onChange={(e) => setPerQuery(e.target.value)}
                className={`${inputClass} mt-1`}
                disabled={run.isPending}
              />
              <span className="text-[10px] text-muted-foreground mt-0.5 block">Result links opened</span>
            </label>
          </div>
        </div>
      )}

      {activeTab === 'sources' && (
        <div className="grid gap-3">
          <DiscoverySourcesManager
            compact={true}
            onChange={(s) => {
              setListingUrls(s.listingUrls);
              setTicketmasterApiKey(s.ticketmasterApiKey);
              setTicketmasterEnabled(s.ticketmasterEnabled);
              setSelectedSources(s.sources);
            }}
          />
        </div>
      )}

      {activeTab === 'rejection' && (
        <div className="grid gap-3.5">
          {/* Sector Handling & Other Sector Fallback */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <Layers size={13} className="text-accent" /> Sector Assignment & Unmatched Events
            </h4>
            <div className="grid gap-2">
              <FilterRuleRow
                icon={Layers}
                title="Add Unmatched Events to 'Other' Sector"
                description="When events outside your target sectors are discovered, assign them to the 'Other' sector instead of rejecting them, keeping them available on the platform."
                checked={fallbackToOtherSector}
                onChange={setFallbackToOtherSector}
                badge="Recommended"
                disabled={run.isPending}
              />
              {!fallbackToOtherSector && (
                <FilterRuleRow
                  icon={FilterX}
                  title="Reject Unmatched Categories / Sectors"
                  description="Rejects events whose sector does not match the 100 TIMES target categories."
                  checked={rejectUnmatchedCategory}
                  onChange={setRejectUnmatchedCategory}
                  disabled={run.isPending}
                />
              )}
            </div>
          </div>

          {/* Organizer Requirements */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <Building2 size={13} className="text-accent" /> Organizer Requirements
            </h4>
            <div className="grid gap-2">
              <FilterRuleRow
                icon={Building2}
                title="Reject Events with No Organizer"
                description="Immediately rejects candidate pages where no verified organizer was identified."
                checked={rejectNoOrganizer}
                onChange={setRejectNoOrganizer}
                badge="Recommended"
                disabled={run.isPending}
              />
              <FilterRuleRow
                icon={Mail}
                title="Require Verified Public Organizer Email"
                description="Mandatory email check. Rejects events if no deliverability-verified public organizer email was found."
                checked={requireOrganizerEmail}
                onChange={setRequireOrganizerEmail}
                badge="Mandatory"
                disabled={run.isPending}
              />
              <FilterRuleRow
                icon={Phone}
                title="Require Organizer Phone Number"
                description="Rejects events that do not contain an official phone number."
                checked={requireOrganizerPhone}
                onChange={setRequireOrganizerPhone}
                disabled={run.isPending}
              />
              <FilterRuleRow
                icon={Globe}
                title="Require Official Organizer Website"
                description="Rejects events where the organizer lacks an official web domain or homepage link."
                checked={requireOrganizerWebsite}
                onChange={setRequireOrganizerWebsite}
                disabled={run.isPending}
              />
            </div>
          </div>

          {/* Dates & Schedule */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <CalendarX size={13} className="text-accent" /> Date & Schedule Validation
            </h4>
            <div className="grid gap-2">
              <FilterRuleRow
                icon={CalendarX}
                title="Reject Past or Expired Events"
                description="Rejects events whose start date has already passed."
                checked={rejectPastEvents}
                onChange={setRejectPastEvents}
                badge="Active"
                disabled={run.isPending}
              />
              <FilterRuleRow
                icon={AlertTriangle}
                title="Reject Ambiguous / Unparseable Dates"
                description="Rejects events where the date could not be parsed into a definitive calendar date."
                checked={rejectUnparseableDates}
                onChange={setRejectUnparseableDates}
                badge="Recommended"
                disabled={run.isPending}
              />
            </div>
          </div>

          {/* Location & Ticket Links */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <MapPin size={13} className="text-accent" /> Location & Ticket Links
            </h4>
            <div className="grid gap-2">
              <FilterRuleRow
                icon={MapPin}
                title="Reject Missing Location (Offline/Hybrid)"
                description="Rejects in-person or hybrid events that lack both venue name and city."
                checked={rejectMissingLocation}
                onChange={setRejectMissingLocation}
                disabled={run.isPending}
              />
              <FilterRuleRow
                icon={Tag}
                title="Require Ticket or Registration URL"
                description="Rejects events that do not have a working registration or ticket URL."
                checked={rejectMissingTicketUrl}
                onChange={setRejectMissingTicketUrl}
                disabled={run.isPending}
              />
            </div>
          </div>

          {/* Thresholds */}
          <div className="grid grid-cols-3 gap-2">
            <label>
              <span className="font-semibold text-foreground text-[11px]">Min Title Length</span>
              <input
                type="number"
                min={0}
                max={50}
                value={minTitleLength}
                onChange={(e) => setMinTitleLength(e.target.value)}
                className={`${inputClass} mt-1`}
                placeholder="8 chars"
                disabled={run.isPending}
              />
            </label>
            <label>
              <span className="font-semibold text-foreground text-[11px]">Min Description Length</span>
              <input
                type="number"
                min={0}
                max={200}
                value={minDescriptionLength}
                onChange={(e) => setMinDescriptionLength(e.target.value)}
                className={`${inputClass} mt-1`}
                placeholder="20 chars"
                disabled={run.isPending}
              />
            </label>
            <label>
              <span className="font-semibold text-foreground text-[11px]">Min AI Confidence</span>
              <input
                type="number"
                min={0}
                max={100}
                value={minConfidenceScore}
                onChange={(e) => setMinConfidenceScore(e.target.value)}
                className={`${inputClass} mt-1`}
                placeholder="50"
                disabled={run.isPending}
              />
            </label>
          </div>

          {/* Blocklists */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <FilterX size={13} className="text-accent" /> Spam & Domain Blocklists
            </h4>
            <div className="grid gap-2">
              <label>
                <span className="font-semibold text-foreground text-[11px]">Blacklisted Spam Keywords</span>
                <textarea
                  rows={2}
                  value={blacklistedKeywords}
                  onChange={(e) => setBlacklistedKeywords(e.target.value)}
                  className={`${inputClass} mt-1`}
                  placeholder="e.g. airdrop, crypto giveaway, casino, betting, get rich quick, mlm"
                  disabled={run.isPending}
                />
              </label>

              <label>
                <span className="font-semibold text-foreground text-[11px]">Excluded Domains</span>
                <textarea
                  rows={2}
                  value={excludedDomains}
                  onChange={(e) => setExcludedDomains(e.target.value)}
                  className={`${inputClass} mt-1`}
                  placeholder="e.g. spam-listings.com, scam-events.org, bit.ly"
                  disabled={run.isPending}
                />
              </label>
            </div>
          </div>
        </div>
      )}

      <Notice tone="info">
        Launches an active discovery scan querying selected sources across specified cities and sectors. 
        Limits this run to <strong>{num(eventsPerRun, 50)} events</strong> and <strong>{num(depth, 6)} search queries</strong>.
      </Notice>

      <div className="flex items-center gap-3 pt-2 border-t border-foreground/10">
        <Btn
          variant="primary"
          loading={run.isPending}
          disabled={Boolean(active)}
          onClick={start}
        >
          <Search size={13} /> {run.isPending ? 'Starting…' : active ? 'Run Already In Progress' : 'Run manual research'}
        </Btn>
        <Link href="/admin/discovery/events">
          <Btn variant="secondary">
            <Eye size={13} /> View Discoveries
          </Btn>
        </Link>
        {active && (
          <Btn
            variant="danger"
            size="sm"
            loading={stopRun.isPending}
            onClick={() => stopRun.mutate(active.id)}
          >
            <Square size={12} className="fill-current" /> Stop Run
          </Btn>
        )}
        {run.isPending && (
          <span className="text-[11px] text-muted-foreground animate-pulse">
            Starting background discovery run...
          </span>
        )}
      </div>

      {run.isError && <ErrorState error={run.error} title="Research run failed" />}

      {result && (
        <div className="rounded-xl border border-foreground/10 bg-background p-4 mt-2">
          <DL
            rows={[
              ['Run ID', String(result.runId ?? '—')],
              ['Status', String(result.status ?? '—')],
              ['Events Discovered', String(result.events_discovered ?? 0)],
              ['New Events Accepted', String(result.new_events ?? result.accepted_events ?? 0)],
              ['Rejected Events', String(result.rejected_events ?? 0)],
              ['Duplicates Skipped', String(result.duplicate_events ?? 0)],
              ['Organizers Found', `${result.organizers_found ?? 0} (${result.new_organizers ?? 0} new)`],
              ['Contacts Found', String(result.contacts_found ?? 0)],
              ['Needs Review', String(result.events_needing_review ?? 0)],
            ]}
          />
          <div className="mt-3 flex gap-3 font-mono-face text-[10px] uppercase tracking-wider">
            <Link href={result.runId ? `/admin/discovery/events?run=${result.runId}` : '/admin/discovery'} className="text-accent hover:underline font-bold">
              View Discoveries{result.new_events ? ` (${result.new_events} new)` : result.accepted_events ? ` (${result.accepted_events} accepted)` : ''} →
            </Link>
            <Link href="/admin/activity" className="text-accent hover:underline">
              Run Details →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export function ManualResearchButton({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const [open, setOpen] = useState(false);
  const activeRun = useActiveDiscoveryRun();
  const isRunning = Boolean(activeRun.data?.active);
  const acceptedCount = activeRun.data?.run?.summary?.accepted_events ?? 0;

  return (
    <div className="flex items-center gap-2">
      <Link href="/admin/discovery/events">
        <Btn variant="secondary" size={size}>
          <Eye size={size === 'sm' ? 11 : 13} /> View Discoveries
        </Btn>
      </Link>
      <Btn
        variant={isRunning ? "secondary" : "primary"}
        size={size}
        onClick={() => setOpen(true)}
        className={isRunning ? "relative border-accent/50 text-accent font-semibold" : ""}
      >
        {isRunning ? (
          <>
            <span className="relative flex h-2 w-2 mr-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
            </span>
            Running ({acceptedCount} found)
          </>
        ) : (
          <>
            <Search size={size === 'sm' ? 11 : 13} /> Run manual research
          </>
        )}
      </Btn>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        kicker="Organizer Discovery · Automation"
        title="Run Manual Research"
        width="max-w-3xl"
      >
        <p className="mb-4 text-xs text-muted-foreground">
          Configure sources, sectors, and rejection filters for this one-time research run. Discovered events will be categorized, validated, and saved in New Discoveries.
        </p>
        <ManualResearchForm />
      </Drawer>
    </div>
  );
}
