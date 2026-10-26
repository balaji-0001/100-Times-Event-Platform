import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  ExternalLink,
  Eye,
  EyeOff,
  Facebook,
  Globe,
  Instagram,
  KeyRound,
  Linkedin,
  MessageCircle,
  Plus,
  Radio,
  RefreshCw,
  Send,
  Ticket,
  Trash2,
  Twitter,
  XCircle,
} from 'lucide-react';
import { useDiscoveryAutoStatus, useSetDiscoveryAuto, useTestTicketmaster } from './api';
import { Badge, Btn, Notice, Panel, Section, inputClass } from './ui';

const DEFAULT_LISTING_URLS = [
  'https://allevents.in/{city}',
  'https://www.eventbrite.com/d/{country}--{city}/events/',
  'https://www.eventbrite.com/d/{city}/events/',
  'https://www.meetup.com/find/?location={city}&source=EVENTS',
  'https://10times.com/{city}',
  'https://www.skillboxes.com/events',
];

interface SourceChannel {
  id: string;
  name: string;
  description: string;
  icon: any;
  badge?: string;
}

const AVAILABLE_CHANNELS: SourceChannel[] = [
  {
    id: 'ticketmaster',
    name: 'Ticketmaster Discovery API v2',
    description: 'Official API for live concerts, expos, business summits, and theater worldwide.',
    icon: Ticket,
    badge: 'API Official',
  },
  {
    id: 'event_platforms',
    name: 'Ticketing & Event Portals',
    description: 'Eventbrite, Meetup, Allevents, 10times, Lu.ma, and Townscript public listings.',
    icon: Ticket,
    badge: 'High Yield',
  },
  {
    id: 'web',
    name: 'Web & Industry Portals',
    description: 'Conference directories, trade associations, industry councils, and sector publications.',
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
    id: 'twitter',
    name: 'Twitter / X',
    description: 'Official conference handles, event announcement hashtags, and summit threads.',
    icon: Twitter,
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
];

function getDomainFromUrl(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl.replace(/\{city\}|\{country\}/g, 'city'));
    return parsed.hostname.replace(/^www\./, '');
  } catch {
    return 'custom';
  }
}

export function DiscoverySourcesManager({
  onSaved,
  compact = false,
}: {
  onSaved?: () => void;
  compact?: boolean;
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

  // Channel toggles state
  const [selectedChannels, setSelectedChannels] = useState<string[]>([
    'ticketmaster',
    'event_platforms',
    'web',
    'linkedin',
    'facebook',
    'instagram',
    'twitter',
    'telegram',
    'reddit',
  ]);

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
        setSelectedChannels(auto.data.sources);
      }
    }
  }, [auto.data]);

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

  const handleResetDefaults = () => {
    setListingUrls(DEFAULT_LISTING_URLS);
  };

  const insertToken = (token: string) => {
    setNewUrlInput((prev) => prev + token);
  };

  const toggleChannel = (channelId: string) => {
    setSelectedChannels((prev) =>
      prev.includes(channelId) ? prev.filter((c) => c !== channelId) : [...prev, channelId]
    );
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
        sources: selectedChannels,
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

  return (
    <div className="space-y-6">
      {/* 1. Ticketmaster API Integration Card */}
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
                Fetch official, structured events from Ticketmaster’s global discovery network.
                Requires a free Consumer Key from{' '}
                <a
                  href="https://developer.ticketmaster.com"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-accent hover:underline inline-flex items-center gap-0.5"
                >
                  developer.ticketmaster.com <ExternalLink size={10} />
                </a>
                .
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

      {/* 2. Web Listing Sources & Custom Websites */}
      <div className="rounded-xl border border-foreground/10 bg-card p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h4 className="font-display text-sm font-bold text-foreground flex items-center gap-2">
              <Globe size={15} className="text-accent" /> Website Listing Sources ({listingUrls.length})
            </h4>
            <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">
              Websites from which the agent scrapes live events. Templates support{' '}
              <code className="text-accent font-mono-face text-[11px]">{'{city}'}</code> and{' '}
              <code className="text-accent font-mono-face text-[11px]">{'{country}'}</code> tokens.
            </p>
          </div>
          <button
            type="button"
            onClick={handleResetDefaults}
            className="text-[11px] text-muted-foreground hover:text-accent flex items-center gap-1 font-medium"
          >
            <RefreshCw size={11} /> Reset to defaults
          </button>
        </div>

        {/* Existing Website List */}
        <div className="divide-y divide-foreground/10 border border-foreground/10 rounded-lg overflow-hidden bg-background/50 max-h-64 overflow-y-auto">
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
              No website sources configured. Add a website template below.
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
              placeholder="e.g. https://insider.in/all-events-in-{city} or https://myevents.com/events"
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

          {/* Quick Token Helpers */}
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

      {/* 3. Multi-Channel Sources (Social, Web, Ticketing) */}
      <div className="rounded-xl border border-foreground/10 bg-card p-4 sm:p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h4 className="font-display text-sm font-bold text-foreground flex items-center gap-2">
              <Radio size={15} className="text-accent" /> Discovery Channels & Platforms
            </h4>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Select which categories of sources the Discovery Agent queries during automated and manual sweeps.
            </p>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          {AVAILABLE_CHANNELS.map((ch) => {
            const active = selectedChannels.includes(ch.id);
            const Icon = ch.icon;
            return (
              <div
                key={ch.id}
                onClick={() => toggleChannel(ch.id)}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                  active
                    ? 'border-accent/40 bg-accent/5 hover:bg-accent/10'
                    : 'border-foreground/10 bg-background/50 hover:bg-background opacity-60'
                }`}
              >
                <div className="p-1.5 rounded-md bg-accent/10 text-accent mt-0.5 shrink-0">
                  <Icon size={14} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-semibold text-foreground">{ch.name}</span>
                    {ch.badge && (
                      <span className="px-1 py-0.2 text-[9px] uppercase font-bold rounded bg-accent/15 text-accent">
                        {ch.badge}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">
                    {ch.description}
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={active}
                  onChange={() => {}}
                  className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent mt-1 shrink-0"
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* Save Button & Feedback */}
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
    </div>
  );
}
