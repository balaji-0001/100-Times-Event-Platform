import { useEffect, useState, useMemo } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Eye,
  EyeOff,
  Globe,
  KeyRound,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Ticket,
  Trash2,
  XCircle,
} from 'lucide-react';
import { useDiscoveryAutoStatus, useSetDiscoveryAuto, useTestTicketmaster } from './api';
import { Badge, Btn, Notice, inputClass } from './ui';
import {
  DEFAULT_LISTING_URLS,
  OperationalSourceItem,
  SourceCategoryGroup,
  SOURCE_REGISTRY_CATEGORIES,
  ALL_OPERATIONAL_IDS,
  CONSUMER_AGGREGATOR_IDS,
  DEFAULT_ACTIVE_SOURCES,
} from './discoverySourcesConfig';

function getDomainFromUrl(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl.replace(/\{city\}|\{country\}/g, 'city'));
    return parsed.hostname.replace(/^www\./, '');
  } catch {
    return 'custom';
  }
}

export interface DiscoverySourcesState {
  listingUrls: string[];
  ticketmasterApiKey: string;
  ticketmasterEnabled: boolean;
  sources: string[];
}

export function DiscoverySourcesManager({
  onSaved,
  onChange,
  compact = false,
  showSaveButton = true,
}: {
  onSaved?: () => void;
  onChange?: (state: DiscoverySourcesState) => void;
  compact?: boolean;
  showSaveButton?: boolean;
}) {
  const auto = useDiscoveryAutoStatus();
  const setAuto = useSetDiscoveryAuto();
  const testTm = useTestTicketmaster();

  // Listing URLs state
  const [listingUrls, setListingUrls] = useState<string[]>(DEFAULT_LISTING_URLS);
  const [newUrlInput, setNewUrlInput] = useState('');
  const [urlError, setUrlError] = useState<string | null>(null);

  // Ticketmaster API state
  const [ticketmasterEnabled, setTicketmasterEnabled] = useState(false);
  const [ticketmasterApiKey, setTicketmasterApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [tmTestResult, setTmTestResult] = useState<{
    success: boolean;
    message: string;
    totalEvents?: number;
  } | null>(null);

  // Selected source IDs / preset tokens
  const [selectedSources, setSelectedSources] = useState<string[]>(DEFAULT_ACTIVE_SOURCES);

  // Expanded category accordions
  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({
    global_event_discovery: false,
    venue_calendar: false,
    international_exhibition_organizer: false,
  });

  const [saveSuccess, setSaveSuccess] = useState(false);

  // Sync state from server on load
  useEffect(() => {
    if (auto.data) {
      if (auto.data.listingUrls && auto.data.listingUrls.length > 0) {
        setListingUrls(auto.data.listingUrls);
      }
      if (auto.data.ticketmasterApiKey !== undefined) {
        setTicketmasterApiKey(auto.data.ticketmasterApiKey || '');
      }
      if (auto.data.ticketmasterEnabled !== undefined) {
        setTicketmasterEnabled(Boolean(auto.data.ticketmasterEnabled));
      }
      if (auto.data.sources && auto.data.sources.length > 0) {
        // If server stored sources, use them; ensure global_adapters and web are active if present
        setSelectedSources(auto.data.sources);
      }
    }
  }, [auto.data]);

  // Propagate state changes to parent when onChange is provided
  useEffect(() => {
    if (onChange) {
      onChange({
        listingUrls,
        ticketmasterApiKey,
        ticketmasterEnabled,
        sources: selectedSources,
      });
    }
  }, [listingUrls, ticketmasterApiKey, ticketmasterEnabled, selectedSources, onChange]);

  // Preset Strategy status helpers
  const isWebSearchOn = selectedSources.includes('web') || selectedSources.includes('google_search') || selectedSources.includes('bing_search');
  const isGlobalAdaptersOn = selectedSources.includes('global_adapters');
  const isConsumerAggregatorsOn = selectedSources.includes('consumer_aggregators') || CONSUMER_AGGREGATOR_IDS.some((id) => selectedSources.includes(id));

  const toggleWebSearch = () => {
    const webIds = ['web', 'google_search', 'bing_search', 'linkedin_search'];
    if (isWebSearchOn) {
      setSelectedSources((prev) => prev.filter((id) => !webIds.includes(id)));
    } else {
      setSelectedSources((prev) => Array.from(new Set([...prev, ...webIds])));
    }
  };

  const toggleGlobalAdapters = () => {
    const b2bIds = [
      'global_adapters',
      'dev_events',
      'wikicfp',
      'eventseye',
      'clocate',
      'tradeshowradar',
      'tradefairdates',
      'biztradeshows',
      'all_conference_alert',
      'conference_alerts',
      'rx_global',
      'informa_markets',
      'terrapinn',
      'messe_frankfurt_org',
      'dmg_events',
      'dwtc_org',
      'gtr_events',
      'ieee_events',
      'acm',
      'dwtc_events',
      'excel_london',
      'javits_center',
      'mccormick_place',
      'messe_frankfurt_venue',
      'india_expo_centre',
      'us_ita',
      'indian_trade_portal',
    ];
    if (isGlobalAdaptersOn) {
      setSelectedSources((prev) => prev.filter((id) => !b2bIds.includes(id)));
    } else {
      setSelectedSources((prev) => Array.from(new Set([...prev, ...b2bIds])));
    }
  };

  const toggleConsumerAggregators = () => {
    const aggIds = ['consumer_aggregators', 'event_platforms', ...CONSUMER_AGGREGATOR_IDS];
    if (isConsumerAggregatorsOn) {
      setSelectedSources((prev) => prev.filter((id) => !aggIds.includes(id)));
    } else {
      setSelectedSources((prev) => Array.from(new Set([...prev, ...aggIds])));
    }
  };

  const toggleSourceId = (id: string) => {
    setSelectedSources((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const toggleCategoryMaster = (cat: SourceCategoryGroup) => {
    const catSourceIds = cat.sources.map((s) => s.id);
    const allSelected = catSourceIds.every((id) => selectedSources.includes(id));
    if (allSelected) {
      // Deselect all in category
      setSelectedSources((prev) => prev.filter((id) => !catSourceIds.includes(id) && id !== cat.slug));
    } else {
      // Select all in category
      setSelectedSources((prev) => Array.from(new Set([...prev, ...catSourceIds, cat.slug])));
    }
  };

  const toggleCategoryAccordion = (slug: string) => {
    setExpandedCategories((prev) => ({ ...prev, [slug]: !prev[slug] }));
  };

  // Quick Action presets
  const handleSelectAllOperational = () => {
    setSelectedSources([
      'web',
      'global_adapters',
      'consumer_aggregators',
      'event_platforms',
      'ticketmaster',
      ...ALL_OPERATIONAL_IDS,
    ]);
  };

  const handleSelectB2BOnly = () => {
    // Pure B2B conferences, official venues, trade directories, and web search — excluding consumer noise
    const b2bOnly = [
      'web',
      'global_adapters',
      'dev_events',
      'wikicfp',
      'eventseye',
      'clocate',
      'tradeshowradar',
      'tradefairdates',
      'biztradeshows',
      'all_conference_alert',
      'conference_alerts',
      'rx_global',
      'informa_markets',
      'terrapinn',
      'messe_frankfurt_org',
      'dmg_events',
      'dwtc_org',
      'gtr_events',
      'ieee_events',
      'acm',
      'dwtc_events',
      'excel_london',
      'javits_center',
      'mccormick_place',
      'messe_frankfurt_venue',
      'india_expo_centre',
      'us_ita',
      'indian_trade_portal',
      'google_search',
      'bing_search',
      'linkedin_search',
    ];
    setSelectedSources(b2bOnly);
  };

  const handleResetDefaults = () => {
    setSelectedSources(DEFAULT_ACTIVE_SOURCES);
    setListingUrls(DEFAULT_LISTING_URLS);
  };

  // Website template handlers
  const handleAddWebsite = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setUrlError(null);
    const trimmed = newUrlInput.trim();
    if (!trimmed) return;

    if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
      setUrlError('URL must begin with http:// or https://');
      return;
    }

    if (listingUrls.includes(trimmed)) {
      setUrlError('This website URL is already in the list.');
      return;
    }

    setListingUrls((prev) => [...prev, trimmed]);
    setNewUrlInput('');
  };

  const handleRemoveWebsite = (indexToRemove: number) => {
    setListingUrls((prev) => prev.filter((_, idx) => idx !== indexToRemove));
  };

  const insertToken = (token: string) => {
    setNewUrlInput((prev) => prev + token);
  };

  const handleTestTicketmaster = () => {
    setTmTestResult(null);
    testTm.mutate(
      { apiKey: ticketmasterApiKey },
      {
        onSuccess: (data) => setTmTestResult(data),
        onError: (err) =>
          setTmTestResult({
            success: false,
            message: err instanceof Error ? err.message : 'Connection test failed',
          }),
      }
    );
  };

  const handleSaveAll = () => {
    setSaveSuccess(false);
    setAuto.mutate(
      {
        listingUrls,
        ticketmasterApiKey: ticketmasterApiKey.trim() || null,
        ticketmasterEnabled,
        sources: selectedSources,
      },
      {
        onSuccess: () => {
          setSaveSuccess(true);
          setTimeout(() => setSaveSuccess(false), 4000);
          if (onSaved) onSaved();
        },
      }
    );
  };

  const activeOperationalCount = useMemo(() => {
    return ALL_OPERATIONAL_IDS.filter((id) => selectedSources.includes(id)).length;
  }, [selectedSources]);

  return (
    <div className="space-y-6">
      {/* 1. CORE STRATEGY PRESETS (PRIMARY TOGGLES) */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="font-display text-sm font-bold text-foreground flex items-center gap-2">
              <Sparkles size={16} className="text-accent" /> Discovery Strategy & Core Toggles
            </h4>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Select key discovery channels. These determine which official sources, search engines, and directories run during discovery.
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <span className="font-mono text-[11px] text-accent font-semibold bg-accent/10 px-2 py-0.5 rounded">
              {activeOperationalCount} / {ALL_OPERATIONAL_IDS.length} Sources Active
            </span>
          </div>
        </div>

        {/* 3 Strategy Preset Cards */}
        <div className="grid gap-3 sm:grid-cols-3">
          {/* Preset A: General Web & Google/Bing Search */}
          <div
            onClick={toggleWebSearch}
            className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
              isWebSearchOn
                ? 'border-accent bg-accent/5 ring-1 ring-accent/30'
                : 'border-foreground/10 bg-card/40 opacity-70 hover:opacity-100'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-accent/10 text-accent">
                  <Search size={15} />
                </div>
                <div>
                  <span className="text-xs font-bold text-foreground block">
                    General Web & Google/Bing
                  </span>
                  <Badge tone="accent">Recommended</Badge>
                </div>
              </div>
              <input
                type="checkbox"
                checked={isWebSearchOn}
                onChange={() => {}}
                className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent mt-1 shrink-0"
              />
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">
              Discovers official event homepages, summit portals, and organizer contact pages worldwide.
            </p>
          </div>

          {/* Preset B: Global Directories & Adapters */}
          <div
            onClick={toggleGlobalAdapters}
            className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
              isGlobalAdaptersOn
                ? 'border-accent bg-accent/5 ring-1 ring-accent/30'
                : 'border-foreground/10 bg-card/40 opacity-70 hover:opacity-100'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-accent/10 text-accent">
                  <Globe size={15} />
                </div>
                <div>
                  <span className="text-xs font-bold text-foreground block">
                    Global Directories & Adapters
                  </span>
                  <Badge tone="good">High Trust B2B</Badge>
                </div>
              </div>
              <input
                type="checkbox"
                checked={isGlobalAdaptersOn}
                onChange={() => {}}
                className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent mt-1 shrink-0"
              />
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">
              dev.events, WikiCFP, venue calendars & trade associations. High-trust structured directories with genuine organizer contacts.
            </p>
          </div>

          {/* Preset C: Consumer Aggregators */}
          <div
            onClick={toggleConsumerAggregators}
            className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
              isConsumerAggregatorsOn
                ? 'border-accent bg-accent/5 ring-1 ring-accent/30'
                : 'border-foreground/10 bg-card/40 opacity-70 hover:opacity-100'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-accent/10 text-accent">
                  <Ticket size={15} />
                </div>
                <div>
                  <span className="text-xs font-bold text-foreground block">
                    Consumer Aggregators
                  </span>
                  <Badge tone="neutral">High Yield</Badge>
                </div>
              </div>
              <input
                type="checkbox"
                checked={isConsumerAggregatorsOn}
                onChange={() => {}}
                className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent mt-1 shrink-0"
              />
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">
              Eventbrite, Meetup, Allevents, 10Times. High volume public listings. Often masks organizer emails for privacy.
            </p>
          </div>
        </div>

        {/* Quick Action Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg border border-foreground/10 bg-muted/20">
          <span className="text-[11px] font-semibold text-muted-foreground">Quick Selection:</span>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleSelectB2BOnly}
              className="px-2.5 py-1 rounded text-[11px] font-semibold bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
            >
              ⭐ B2B Conferences Only (Recommended)
            </button>
            <button
              type="button"
              onClick={handleSelectAllOperational}
              className="px-2.5 py-1 rounded text-[11px] font-semibold border border-foreground/15 hover:bg-muted text-foreground transition-colors"
            >
              Select All Operational ({ALL_OPERATIONAL_IDS.length} Sources)
            </button>
            <button
              type="button"
              onClick={handleResetDefaults}
              className="px-2.5 py-1 rounded text-[11px] font-semibold text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              <RefreshCw size={11} /> Reset to Defaults
            </button>
          </div>
        </div>
      </div>

      {/* 2. SOURCE REGISTRY CATEGORIES (ALL 7 OPERATIONAL CATEGORIES) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-display text-sm font-bold text-foreground flex items-center gap-2">
              <Layers size={16} className="text-accent" /> Source Registry Categories (7 Operational)
            </h4>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Toggle complete categories or expand them to inspect and customize individual source adapters.
            </p>
          </div>
        </div>

        <div className="space-y-2">
          {SOURCE_REGISTRY_CATEGORIES.map((cat) => {
            const Icon = cat.icon;
            const catSourceIds = cat.sources.map((s) => s.id);
            const activeCount = catSourceIds.filter((id) => selectedSources.includes(id)).length;
            const isAllActive = activeCount === cat.sources.length;
            const isSomeActive = activeCount > 0 && !isAllActive;
            const isExpanded = Boolean(expandedCategories[cat.slug]);

            return (
              <div
                key={cat.slug}
                className="rounded-xl border border-foreground/10 bg-card/60 overflow-hidden transition-all"
              >
                {/* Category Header Row */}
                <div className="flex items-center justify-between p-3 sm:px-4 gap-3 bg-card hover:bg-muted/30 transition-colors">
                  <div
                    className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer"
                    onClick={() => toggleCategoryAccordion(cat.slug)}
                  >
                    <div className="p-2 rounded-lg bg-accent/10 text-accent shrink-0">
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-display text-xs font-bold text-foreground">
                          {cat.name}
                        </span>
                        <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-semibold bg-accent/15 text-accent">
                          {activeCount} / {cat.operationalCount} Active
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          ({cat.totalCount} Total in Registry)
                        </span>
                      </div>
                      <p className="text-[11px] text-muted-foreground truncate mt-0.5 max-w-xl">
                        {cat.description}
                      </p>
                    </div>
                  </div>

                  {/* Master Checkbox & Accordion Toggle */}
                  <div className="flex items-center gap-3 shrink-0">
                    <label
                      title={`Toggle all sources in ${cat.name}`}
                      className="flex items-center gap-1.5 text-xs cursor-pointer font-medium text-muted-foreground hover:text-foreground"
                    >
                      <input
                        type="checkbox"
                        checked={isAllActive}
                        ref={(el) => {
                          if (el) el.indeterminate = isSomeActive;
                        }}
                        onChange={() => toggleCategoryMaster(cat)}
                        className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => toggleCategoryAccordion(cat.slug)}
                      className="p-1 text-muted-foreground hover:text-foreground transition-transform"
                      title={isExpanded ? 'Collapse sources' : 'Expand sources'}
                    >
                      {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                  </div>
                </div>

                {/* Expanded Individual Sources Accordion */}
                {isExpanded && (
                  <div className="p-3 sm:p-4 border-t border-foreground/10 bg-background/50 space-y-2">
                    <span className="text-[10px] uppercase font-mono tracking-wider text-muted-foreground block mb-1">
                      Individual Operational Sources ({cat.sources.length}):
                    </span>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {cat.sources.map((src) => {
                        const active = selectedSources.includes(src.id);
                        return (
                          <div
                            key={src.id}
                            onClick={() => toggleSourceId(src.id)}
                            className={`flex items-center justify-between gap-2 p-2.5 rounded-lg border text-xs cursor-pointer transition-all ${
                              active
                                ? 'border-accent/40 bg-accent/5 hover:bg-accent/10'
                                : 'border-foreground/10 bg-card/40 opacity-60 hover:opacity-90'
                            }`}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5">
                                <span className="font-semibold text-foreground truncate">
                                  {src.name}
                                </span>
                                <Badge tone="good">Operational</Badge>
                              </div>
                              <div className="flex items-center gap-2 mt-0.5">
                                <span className="text-[10px] text-accent font-medium truncate">
                                  {src.tag}
                                </span>
                                <span className="text-muted-foreground">•</span>
                                <a
                                  href={src.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="text-[10px] text-muted-foreground hover:text-foreground inline-flex items-center gap-0.5 truncate max-w-[120px]"
                                >
                                  {getDomainFromUrl(src.url)} <ExternalLink size={9} />
                                </a>
                              </div>
                            </div>
                            <input
                              type="checkbox"
                              checked={active}
                              onChange={() => {}}
                              className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent shrink-0"
                            />
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. TICKETMASTER OFFICIAL API CARD */}
      <div className="rounded-xl border border-accent/40 bg-accent/5 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-accent/20 p-2 text-accent mt-0.5">
              <Ticket size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="font-display text-sm font-bold text-foreground">
                  Ticketmaster Discovery API v2
                </h4>
                <Badge tone="accent">Official API</Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed max-w-xl">
                Fetch structured events from Ticketmaster’s global discovery network. Free API key from{' '}
                <a
                  href="https://developer.ticketmaster.com"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-accent hover:underline inline-flex items-center gap-0.5"
                >
                  developer.ticketmaster.com <ExternalLink size={10} />
                </a>
                . Note: Ticketmaster masks organizer emails for privacy.
              </p>
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer shrink-0">
            <span>Enable Ticketmaster</span>
            <input
              type="checkbox"
              checked={ticketmasterEnabled}
              onChange={(e) => setTicketmasterEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent"
            />
          </label>
        </div>

        <div className="mt-4 pt-4 border-t border-accent/20 grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-foreground mb-1">
              Ticketmaster Consumer API Key
            </label>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                placeholder="Enter Ticketmaster API Key (e.g. 7elakhwR...)"
                value={ticketmasterApiKey}
                onChange={(e) => {
                  setTicketmasterApiKey(e.target.value);
                  setTmTestResult(null);
                }}
                className={`${inputClass} pr-10`}
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          <div className="flex items-end">
            <Btn
              type="button"
              variant="secondary"
              size="md"
              loading={testTm.isPending}
              onClick={handleTestTicketmaster}
              className="w-full h-9 text-xs"
            >
              <KeyRound size={13} className="mr-1" /> Test API Key
            </Btn>
          </div>
        </div>

        {tmTestResult && (
          <div className="mt-3">
            <Notice tone={tmTestResult.success ? 'info' : 'danger'}>
              <div className="flex items-center gap-1.5">
                {tmTestResult.success ? (
                  <CheckCircle2 size={13} className="text-green-500 shrink-0" />
                ) : (
                  <XCircle size={13} className="text-red-500 shrink-0" />
                )}
                <span className="text-xs font-semibold">{tmTestResult.message}</span>
              </div>
            </Notice>
          </div>
        )}
      </div>

      {/* 4. WEBSITE LISTING SOURCES & URL TEMPLATES */}
      <div className="rounded-xl border border-foreground/10 bg-card p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h4 className="font-display text-sm font-bold text-foreground flex items-center gap-2">
              <Globe size={15} className="text-accent" /> Custom Website Listing Sources ({listingUrls.length})
            </h4>
            <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">
              Scraping templates for custom listing portals supporting{' '}
              <code className="text-accent font-mono-face text-[11px]">{'{city}'}</code> and{' '}
              <code className="text-accent font-mono-face text-[11px]">{'{country}'}</code> tokens.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setListingUrls(DEFAULT_LISTING_URLS)}
            className="text-[11px] text-muted-foreground hover:text-accent flex items-center gap-1 font-medium"
          >
            <RefreshCw size={11} /> Reset URL templates
          </button>
        </div>

        {/* Existing Website List */}
        <div className="divide-y divide-foreground/10 border border-foreground/10 rounded-lg overflow-hidden bg-background/50 max-h-56 overflow-y-auto">
          {listingUrls.map((url, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between gap-3 px-3 py-2 text-xs hover:bg-muted/30 transition-colors"
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span className="px-1.5 py-0.5 text-[10px] font-mono-face uppercase rounded bg-muted text-muted-foreground shrink-0">
                  {getDomainFromUrl(url)}
                </span>
                <span className="font-mono-face text-[11px] truncate text-foreground/90">
                  {url}
                </span>
              </div>
              <button
                type="button"
                onClick={() => handleRemoveWebsite(idx)}
                className="p-1 text-muted-foreground hover:text-red-500 transition-colors shrink-0"
                title="Remove this source"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
          {listingUrls.length === 0 && (
            <div className="p-4 text-center text-xs text-muted-foreground">
              No custom website templates configured.
            </div>
          )}
        </div>

        {/* Add New Website Form */}
        <form onSubmit={handleAddWebsite} className="mt-4 pt-3 border-t border-foreground/10 space-y-2">
          <label className="block text-xs font-semibold text-foreground">
            Add New Website / URL Template
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              placeholder="e.g. https://insider.in/all-events-in-{city}"
              value={newUrlInput}
              onChange={(e) => {
                setNewUrlInput(e.target.value);
                setUrlError(null);
              }}
              className={`${inputClass} flex-1 min-w-[260px] font-mono-face text-xs`}
            />
            <Btn type="submit" variant="secondary" size="md" className="h-9 text-xs">
              <Plus size={13} className="mr-1" /> Add Website
            </Btn>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-muted-foreground pt-1">
            <span>Insert dynamic token:</span>
            <button
              type="button"
              onClick={() => insertToken('{city}')}
              className="px-2 py-0.5 rounded border border-foreground/15 bg-background font-mono-face text-[10px] font-semibold text-accent hover:border-accent"
            >
              +{'{city}'}
            </button>
            <button
              type="button"
              onClick={() => insertToken('{country}')}
              className="px-2 py-0.5 rounded border border-foreground/15 bg-background font-mono-face text-[10px] font-semibold text-accent hover:border-accent"
            >
              +{'{country}'}
            </button>
          </div>

          {urlError && (
            <span className="font-mono-face text-xs text-red-500 block pt-1">{urlError}</span>
          )}
        </form>
      </div>

      {/* Save Button & Feedback */}
      {showSaveButton && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <Btn
            type="button"
            variant="primary"
            size="md"
            loading={setAuto.isPending}
            onClick={handleSaveAll}
          >
            <CheckCircle2 size={15} className="mr-1.5" /> Save Discovery Sources & Websites
          </Btn>

          {saveSuccess && (
            <span className="font-mono-face text-xs text-green-500 flex items-center gap-1 font-semibold">
              <CheckCircle2 size={13} /> Sources and websites saved successfully!
            </span>
          )}

          {setAuto.isError && (
            <span className="font-mono-face text-xs text-red-500 flex items-center gap-1">
              <XCircle size={13} /> Failed to save: {(setAuto.error as Error)?.message}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
