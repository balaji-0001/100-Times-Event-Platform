// Guided manual discovery run: six short steps, then a review and Start.
// Every choice lives in one state object mirrored to sessionStorage, so leaving
// the page or moving between steps never resets it ("Start over" clears it).
// Owner rules: sectors and places start EMPTY (nothing copied from the Automatic
// settings); a run needs >= 1 sector and >= 1 country or an explicit Worldwide;
// dates default to "upcoming" from the recommended config; organizer e-mail is
// required by default. The backend has no include-keyword or event-type filter,
// so only exclusions (keywords, domains) are offered.

import { type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useSearch } from 'wouter';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Building2,
  CalendarX,
  Check,
  ChevronDown,
  ChevronUp,
  FilterX,
  Globe,
  History,
  Layers,
  MapPin,
  Phone,
  Play,
  RotateCcw,
  Tag,
} from 'lucide-react';
import {
  type AgentRun,
  type DiscoveryAutoStatus,
  type DiscoveryCatalog,
  type DiscoveryRunPayload,
  type RecommendedConfig,
  apiErrorStatus,
  keys,
  useActiveDiscoveryRun,
  useCategories,
  useDiscoveryAutoStatus,
  useDiscoveryCatalog,
  useDiscoveryRun,
  useRecommendedConfig,
  useRunDiscovery,
} from './api';
import { buildDiscoveryLocations, buildRegionCities } from '@/lib/countries';
import { GeoChecklistSelector } from './GeoChecklistSelector';
import { DiscoverySourcesManager, type DiscoverySourcesState } from './DiscoverySourcesManager';
import { FilterRuleRow } from './ManualResearch';
import { RunProgress, linkButton } from './RunProgress';
import { Badge, Btn, ErrorState, Kicker, LoadingState, Notice, PageHeader, Panel, cx, inputClass } from './ui';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'ops.discover.wizard.v1';
const WATCH_KEY = 'ops.discover.watchRun.v1';

// Channel switches inside `sources` (same tokens as the backend catalog / DiscoverySourcesManager).
const WEB = 'web';
const DIRECTORIES = 'global_adapters';
const AGGREGATORS = 'consumer_aggregators';
// The backend raises the first wave of searches so every sector x country pair gets one, up to this many.
const COVERAGE_CAP = 60;

const STEPS = [
  { title: 'What are you looking for?', short: 'Sectors' },
  { title: 'Where should we search?', short: 'Places' },
  { title: 'When?', short: 'Dates' },
  { title: 'Discovery strategy', short: 'Strategy' },
  { title: 'Goals', short: 'Goals' },
  { title: 'Review & start', short: 'Review' },
] as const;
const LAST = STEPS.length - 1;

const RULE_FLAGS = [
  'rejectNoOrganizer',
  'fallbackToOtherSector',
  'rejectUnmatchedCategory',
  'requireOrganizerPhone',
  'requireOrganizerWebsite',
  'rejectPastEvents',
  'rejectUnparseableDates',
  'rejectMissingLocation',
  'rejectMissingTicketUrl',
] as const;
type RuleFlag = (typeof RULE_FLAGS)[number];
const RULE_NUMBERS = ['minTitleLength', 'minDescriptionLength', 'minConfidenceScore'] as const;
type RuleNumber = (typeof RULE_NUMBERS)[number];

type Rules = Record<RuleFlag, boolean> & Record<RuleNumber, string> & { blacklistedKeywords: string; excludedDomains: string };

/** The manual-research defaults, used where the saved Automatic settings have no value. */
const MANUAL_RULE_DEFAULTS: Rules = {
  rejectNoOrganizer: true,
  fallbackToOtherSector: false,
  rejectUnmatchedCategory: true,
  requireOrganizerPhone: false,
  requireOrganizerWebsite: false,
  rejectPastEvents: true,
  rejectUnparseableDates: true,
  rejectMissingLocation: false,
  rejectMissingTicketUrl: false,
  minTitleLength: '8',
  minDescriptionLength: '20',
  minConfidenceScore: '20',
  blacklistedKeywords: '',
  excludedDomains: '',
};

const SNAKE: Record<RuleFlag | RuleNumber | 'blacklistedKeywords' | 'excludedDomains', string> = {
  rejectNoOrganizer: 'reject_no_organizer',
  fallbackToOtherSector: 'fallback_to_other_sector',
  rejectUnmatchedCategory: 'reject_unmatched_category',
  requireOrganizerPhone: 'require_organizer_phone',
  requireOrganizerWebsite: 'require_organizer_website',
  rejectPastEvents: 'reject_past_events',
  rejectUnparseableDates: 'reject_unparseable_dates',
  rejectMissingLocation: 'reject_missing_location',
  rejectMissingTicketUrl: 'reject_missing_ticket_url',
  minTitleLength: 'min_title_length',
  minDescriptionLength: 'min_description_length',
  minConfidenceScore: 'min_confidence_score',
  blacklistedKeywords: 'blacklisted_keywords',
  excludedDomains: 'excluded_domains',
};

type LimitKey = 'eventsPerRun' | 'searchDepth' | 'sourcesPerQuery';
// Same defaults ManualResearch used for blank run-size fields; ranges are the API's limits.
const LIMITS: Record<LimitKey, { def: number; min: number; max: number; snake: string }> = {
  eventsPerRun: { def: 250, min: 1, max: 1000, snake: 'events_per_run' },
  searchDepth: { def: 12, min: 1, max: 200, snake: 'search_depth' },
  sourcesPerQuery: { def: 5, min: 1, max: 20, snake: 'sources_per_query' },
};
const TARGET_RANGE = { min: 1, max: 1000 };

// ---------------------------------------------------------------------------
// Wizard state
// ---------------------------------------------------------------------------

interface AdvancedSources {
  sources: string[];
  /** null = every configured provider. */
  searchProviders: string[] | null;
  listingUrls: string[];
  ticketmasterEnabled: boolean;
}

interface WizardState {
  version: 1;
  step: number;
  /** Highest step reached; steps up to it are clickable. */
  visited: number;
  /** Steps where Next was pressed with something missing (their errors are shown). */
  attempted: number[];
  sectors: string[];
  geoMode: 'worldwide' | 'countries' | null;
  countries: string[];
  states: string[];
  cities: string[];
  dateMode: 'upcoming' | 'custom';
  dateFrom: string;
  dateTo: string;
  strategy: 'recommended' | 'advanced';
  /** Filled by the Advanced source controls; null until they have loaded once. */
  advanced: AdvancedSources | null;
  /** '' = the recommended goal. */
  targetValidEvents: string;
  /** null = the recommended default. */
  requireOrganizerEmail: boolean | null;
  keepRejectedEvents: boolean | null;
  /** Only the rules the admin changed (or a re-run copied); the rest come from defaults. */
  rules: Partial<Rules>;
  /** '' / missing = default. */
  limits: Partial<Record<LimitKey, string>>;
  open: { keywords: boolean; goals: boolean };
  prefilledFrom: number | null;
}

const initialState = (): WizardState => ({
  version: 1,
  step: 0,
  visited: 0,
  attempted: [],
  sectors: [],
  geoMode: null,
  countries: [],
  states: [],
  cities: [],
  dateMode: 'upcoming',
  dateFrom: '',
  dateTo: '',
  strategy: 'recommended',
  advanced: null,
  targetValidEvents: '',
  requireOrganizerEmail: null,
  keepRejectedEvents: null,
  rules: {},
  limits: {},
  open: { keywords: false, goals: false },
  prefilledFrom: null,
});

const strings = (v: unknown): string[] =>
  Array.isArray(v) ? Array.from(new Set(v.filter((x): x is string => typeof x === 'string' && x.trim() !== '').map((x) => x.trim()))) : [];

function loadState(): WizardState {
  const base = initialState();
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return base;
    const saved = JSON.parse(raw) as Partial<WizardState> | null;
    if (!saved || saved.version !== 1) return base;
    return {
      ...base,
      ...saved,
      sectors: strings(saved.sectors),
      countries: strings(saved.countries),
      states: strings(saved.states),
      cities: strings(saved.cities),
      attempted: Array.isArray(saved.attempted) ? saved.attempted.filter((n) => typeof n === 'number') : [],
      step: Math.min(LAST, Math.max(0, Number(saved.step) || 0)),
      visited: Math.min(LAST, Math.max(0, Number(saved.visited) || 0)),
      rules: saved.rules && typeof saved.rules === 'object' ? saved.rules : {},
      limits: saved.limits && typeof saved.limits === 'object' ? saved.limits : {},
      open: { ...base.open, ...(saved.open ?? {}) },
    };
  } catch {
    return base;
  }
}

function saveState(state: WizardState) {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable: the wizard still works for this visit */
  }
}

/** A number kept in sessionStorage (the run this page is following). */
function useSessionNumber(key: string): [number | null, (v: number | null) => void] {
  const [value, setValue] = useState<number | null>(() => {
    try {
      const n = Number(window.sessionStorage.getItem(key));
      return Number.isInteger(n) && n > 0 ? n : null;
    } catch {
      return null;
    }
  });
  const set = useCallback(
    (v: number | null) => {
      setValue(v);
      try {
        if (v === null) window.sessionStorage.removeItem(key);
        else window.sessionStorage.setItem(key, String(v));
      } catch {
        /* ignore */
      }
    },
    [key],
  );
  return [value, set];
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

const pad = (n: number) => String(n).padStart(2, '0');
const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const dayFmt = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
/** "2026-10-27" -> "27 Oct 2026", read as a local calendar day. */
function fmtDay(iso: string | null | undefined): string {
  const m = iso ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null;
  return m ? dayFmt.format(new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))) : '—';
}
function windowLabel(days: number): string {
  const months = Math.round(days / 30.4);
  return days >= 28 ? `next ${months} month${months === 1 ? '' : 's'}` : `next ${days} day${days === 1 ? '' : 's'}`;
}

/** A whole number written in a field, or NaN. */
const wholeNumber = (v: string) => (/^\s*\d+\s*$/.test(v) ? Number(v.trim()) : NaN);
const splitList = (v: string) =>
  v
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
const cleanDomains = (v: string) =>
  splitList(v)
    .map((d) => d.replace(/^https?:\/\//i, '').replace(/\/.*$/, ''))
    .filter(Boolean);
const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function rulesFromAuto(a?: DiscoveryAutoStatus): Partial<Rules> {
  if (!a) return {};
  const out: Partial<Rules> = {};
  for (const k of RULE_FLAGS) if (typeof a[k] === 'boolean') out[k] = a[k] as boolean;
  for (const k of RULE_NUMBERS) if (typeof a[k] === 'number') out[k] = String(a[k]);
  if (Array.isArray(a.blacklistedKeywords)) out.blacklistedKeywords = a.blacklistedKeywords.join(', ');
  if (Array.isArray(a.excludedDomains)) out.excludedDomains = a.excludedDomains.join(', ');
  return out;
}

const hasChannel = (a: AdvancedSources) =>
  a.sources.some((id) => id !== 'ticketmaster' && id !== 'ticketmaster_api') || a.ticketmasterEnabled;

/** Directory / aggregator sources a custom selection would read (a source only runs while its channel is on). */
function advancedSourceCount(a: AdvancedSources, catalog?: DiscoveryCatalog): number | null {
  if (!catalog) return null;
  const dirOn = a.sources.includes(DIRECTORIES);
  const aggOn = a.sources.includes(AGGREGATORS);
  return catalog.sources.filter(
    (s) => a.sources.includes(s.id) && ((s.channel === 'directories' && dirOn) || (s.channel === 'aggregators' && aggOn)),
  ).length;
}

/** Re-run: map a run's stored config (snake_case) back onto the wizard. Anything not mappable stays default. */
function stateFromSnapshot(run: AgentRun, rec?: RecommendedConfig): WizardState {
  const c: Record<string, unknown> = run.configSnapshot ?? {};
  const st = initialState();
  const bool = (v: unknown) => (typeof v === 'boolean' ? v : undefined);
  const int = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? String(Math.round(v)) : undefined);
  const locations = Array.isArray(c.locations) ? (c.locations as Array<Record<string, unknown>>).filter((l) => l && typeof l === 'object') : [];

  st.sectors = strings(c.categories);
  let countries = strings(c.countries);
  if (!countries.length && typeof c.country === 'string' && c.country.trim() && c.country.trim().toLowerCase() !== 'worldwide') countries = [c.country.trim()];
  if (!countries.length) countries = strings(locations.map((l) => l.country));
  let cities = strings(c.cities);
  if (!cities.length) cities = strings(locations.map((l) => l.city));
  let states = strings(c.states);
  if (!states.length) states = strings(locations.filter((l) => !l.city).map((l) => l.state));
  st.countries = countries;
  st.states = states;
  st.cities = cities;
  // No country but cities/states: keep them and ask for a country rather than silently going worldwide.
  st.geoMode = countries.length || cities.length || states.length ? 'countries' : 'worldwide';

  if (typeof c.date_from === 'string' || typeof c.date_to === 'string') {
    st.dateMode = 'custom';
    st.dateFrom = typeof c.date_from === 'string' ? c.date_from.slice(0, 10) : '';
    st.dateTo = typeof c.date_to === 'string' ? c.date_to.slice(0, 10) : '';
  }

  const sources = strings(c.sources);
  const providers = Array.isArray(c.search_providers) ? strings(c.search_providers) : null;
  if (sources.length) {
    if (rec && providers === null && sameSet(sources, rec.sources)) st.strategy = 'recommended';
    else {
      st.strategy = 'advanced';
      st.advanced = {
        sources,
        searchProviders: providers,
        listingUrls: strings(c.listing_urls),
        ticketmasterEnabled: bool(c.ticketmaster_enabled) ?? false,
      };
    }
  }

  st.targetValidEvents = int(c.target_valid_events) ?? '';
  st.requireOrganizerEmail = bool(c.require_organizer_email) ?? null;
  st.keepRejectedEvents = bool(c.keep_rejected_events) ?? null;
  const rules: Partial<Rules> = {};
  for (const k of RULE_FLAGS) {
    const v = bool(c[SNAKE[k]]);
    if (v !== undefined) rules[k] = v;
  }
  for (const k of RULE_NUMBERS) {
    const v = int(c[SNAKE[k]]);
    if (v !== undefined) rules[k] = v;
  }
  if (Array.isArray(c.blacklisted_keywords)) rules.blacklistedKeywords = strings(c.blacklisted_keywords).join(', ');
  if (Array.isArray(c.excluded_domains)) rules.excludedDomains = strings(c.excluded_domains).join(', ');
  st.rules = rules;
  for (const k of Object.keys(LIMITS) as LimitKey[]) {
    const v = int(c[LIMITS[k].snake]);
    if (v !== undefined) st.limits[k] = v;
  }
  st.open = { keywords: Boolean(rules.blacklistedKeywords), goals: false };
  st.step = LAST;
  st.visited = LAST;
  st.prefilledFrom = run.id;
  return st;
}

// ---------------------------------------------------------------------------
// Small presentational pieces
// ---------------------------------------------------------------------------

function FieldError({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="mt-1.5 flex items-start gap-1 text-[11px] font-medium text-red-600 dark:text-red-400">
      <AlertTriangle size={12} className="mt-0.5 shrink-0" /> {children}
    </p>
  );
}

function Help({ id, children }: { id?: string; children: ReactNode }) {
  return <p id={id} className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{children}</p>;
}

function ChoiceCard({
  name,
  checked,
  onSelect,
  title,
  children,
  disabled,
}: {
  name: string;
  checked: boolean;
  onSelect: () => void;
  title: ReactNode;
  children?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label
      className={cx(
        'flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors focus-within:ring-2 focus-within:ring-accent/50',
        checked ? 'border-accent bg-accent/5' : 'border-foreground/10 bg-background/60 hover:border-foreground/25',
        disabled && 'cursor-not-allowed opacity-60',
      )}
    >
      <input type="radio" name={name} checked={checked} onChange={onSelect} disabled={disabled} className="mt-0.5 h-4 w-4 shrink-0 accent-accent" />
      <span className="min-w-0">
        <span className="block text-sm font-bold">{title}</span>
        {children && <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">{children}</span>}
      </span>
    </label>
  );
}

function Expander({ open, onToggle, title, summary, children }: { open: boolean; onToggle: () => void; title: string; summary?: ReactNode; children: ReactNode }) {
  const id = useId();
  return (
    <div className="rounded-xl border border-foreground/10 bg-background/40">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
      >
        <span className="min-w-0">
          <span className="text-xs font-bold">{title}</span>
          {summary && <span className="ml-2 text-[11px] text-muted-foreground">{summary}</span>}
        </span>
        {open ? <ChevronUp size={15} className="shrink-0" /> : <ChevronDown size={15} className="shrink-0" />}
      </button>
      {open && (
        <div id={id} className="border-t border-foreground/10 p-4">
          {children}
        </div>
      )}
    </div>
  );
}

function NumberField({
  label,
  value,
  placeholder,
  onChange,
  help,
  error,
  min,
  max,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (v: string) => void;
  help?: ReactNode;
  error?: string;
  min: number;
  max: number;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="text-[11px] font-semibold">
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={cx(help ? `${id}-help` : null, error ? `${id}-err` : null) || undefined}
        className={cx(inputClass, 'mt-1', error && 'border-red-500/60')}
      />
      {help && <Help id={`${id}-help`}>{help}</Help>}
      {error && <FieldError id={`${id}-err`}>{error}</FieldError>}
    </div>
  );
}

function TextAreaField({ label, value, onChange, placeholder, help }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; help?: ReactNode }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="text-[11px] font-semibold">
        {label}
      </label>
      <textarea
        id={id}
        rows={2}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-describedby={help ? `${id}-help` : undefined}
        className={cx(inputClass, 'mt-1')}
      />
      {help && <Help id={`${id}-help`}>{help}</Help>}
    </div>
  );
}

function SwitchRow({ title, description, checked, onChange, badge }: { title: string; description: string; checked: boolean; onChange: (v: boolean) => void; badge?: string }) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-foreground/10 bg-background/60 p-3.5">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-sm font-bold">
          <span id={`${id}-label`}>{title}</span>
          {badge && <Badge tone="accent">{badge}</Badge>}
        </p>
        <p id={`${id}-desc`} className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
          {description}
        </p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-desc`}
        onClick={() => onChange(!checked)}
        className={cx(
          'button-press relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          checked ? 'border-accent bg-accent' : 'border-foreground/20 bg-muted',
        )}
      >
        <span className={cx('inline-block h-3.5 w-3.5 transform rounded-full bg-background shadow transition-transform', checked ? 'translate-x-4' : 'translate-x-0.5')} />
      </button>
    </div>
  );
}

function StepIndicator({ step, visited, done, onGo }: { step: number; visited: number; done: (i: number) => boolean; onGo: (i: number) => void }) {
  return (
    <nav aria-label="Run setup steps">
      <p className="text-[11px] text-muted-foreground sm:hidden">
        Step {step + 1} of {STEPS.length} · {STEPS[step].short}
      </p>
      <ol className="mt-2 flex flex-wrap gap-1.5 sm:mt-0">
        {STEPS.map((s, i) => {
          const current = i === step;
          const reachable = i <= visited;
          const complete = reachable && !current && done(i);
          return (
            <li key={s.short}>
              <button
                type="button"
                onClick={() => onGo(i)}
                disabled={!reachable}
                aria-current={current ? 'step' : undefined}
                aria-label={`Step ${i + 1}: ${s.title}${complete ? ' (done)' : ''}${!reachable ? ' (not reached yet)' : ''}`}
                className={cx(
                  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:cursor-not-allowed',
                  current
                    ? 'border-accent bg-accent text-accent-foreground'
                    : reachable
                      ? 'border-foreground/15 bg-background hover:border-accent hover:text-accent'
                      : 'border-foreground/10 text-muted-foreground opacity-60',
                )}
              >
                <span
                  className={cx(
                    'grid h-4 w-4 place-items-center rounded-full font-mono-face text-[9px]',
                    current ? 'bg-accent-foreground/20' : complete ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300' : 'bg-muted',
                  )}
                  aria-hidden="true"
                >
                  {complete ? <Check size={10} /> : i + 1}
                </span>
                {s.short}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/**
 * The existing source / provider / website controls (DiscoverySourcesManager), started from
 * the wizard's own selection instead of the saved Automatic settings. The manager reads its
 * starting point from the `discoveryAuto` query, so it gets a private query cache seeded with
 * the wizard's values (real saved settings for everything else, e.g. whether a Ticketmaster
 * key exists). Its save button is hidden: changes here apply to this run only.
 */
function AdvancedSourcesEditor({ seed, onChange }: { seed: AdvancedSources; onChange: (s: DiscoverySourcesState) => void }) {
  const auto = useDiscoveryAutoStatus();
  const catalog = useDiscoveryCatalog();
  const seedRef = useRef(seed);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);
  const [sandbox, setSandbox] = useState<QueryClient | null>(null);

  useEffect(() => {
    if (sandbox || !auto.data) return;
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false, refetchOnWindowFocus: false } } });
    const s = seedRef.current;
    client.setQueryData<DiscoveryAutoStatus>(keys.discoveryAuto, {
      ...auto.data,
      sources: s.sources,
      searchProviders: s.searchProviders,
      listingUrls: s.listingUrls,
      ticketmasterEnabled: s.ticketmasterEnabled,
    });
    if (catalog.data) client.setQueryData(['discoveryCatalog'], catalog.data);
    setSandbox(client);
  }, [auto.data, catalog.data, sandbox]);
  useEffect(() => () => sandbox?.clear(), [sandbox]);

  const handleChange = useCallback((s: DiscoverySourcesState) => onChangeRef.current(s), []);

  if (auto.isError) return <ErrorState error={auto.error} retry={() => auto.refetch()} title="Could not load the source settings." />;
  if (!sandbox) return <p className="text-xs text-muted-foreground">Loading discovery sources…</p>;
  return (
    <QueryClientProvider client={sandbox}>
      <DiscoverySourcesManager showSaveButton={false} onChange={handleChange} />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface WizardError {
  step: number;
  field: string;
  message: string;
}

export function RunWizardPage() {
  const search = useSearch();
  const [, navigate] = useLocation();
  const fromParam = Number(new URLSearchParams(search).get('from'));
  const fromId = Number.isInteger(fromParam) && fromParam > 0 ? fromParam : null;

  const categories = useCategories();
  const recommended = useRecommendedConfig();
  const auto = useDiscoveryAutoStatus();
  const catalog = useDiscoveryCatalog();
  const activeQ = useActiveDiscoveryRun();
  const startRun = useRunDiscovery();
  const fromRun = useDiscoveryRun(fromId);

  const [state, setState] = useState<WizardState>(loadState);
  const [tmKey, setTmKey] = useState(''); // a newly typed Ticketmaster key: used for this run, never stored
  const [confirmReset, setConfirmReset] = useState(false);
  const [startNote, setStartNote] = useState<string | null>(null);
  const [watchId, setWatchId] = useSessionNumber(WATCH_KEY);
  const sectorsLabelId = useId();

  useEffect(() => saveState(state), [state]);

  const update = useCallback((patch: Partial<WizardState> | ((prev: WizardState) => Partial<WizardState>)) => {
    setState((prev) => ({ ...prev, ...(typeof patch === 'function' ? patch(prev) : patch) }));
  }, []);
  const setRule = <K extends keyof Rules>(k: K, v: Rules[K]) => update((prev) => ({ rules: { ...prev.rules, [k]: v } }));
  const setLimit = (k: LimitKey, v: string) => update((prev) => ({ limits: { ...prev.limits, [k]: v } }));

  // --- Re-run: pre-fill once from /admin/discover?from=<id> ----------------
  // Waits for the recommended config only to tell "recommended" from custom sources; a failed first try doesn't hold it up.
  const recSettled = !recommended.isLoading || recommended.failureCount > 0;
  useEffect(() => {
    if (!fromId || !fromRun.data || state.prefilledFrom === fromId || !recSettled) return;
    setState(stateFromSnapshot(fromRun.data, recommended.data));
    setTmKey('');
  }, [fromId, fromRun.data, recSettled, recommended.data, state.prefilledFrom]);

  // --- The run this page follows (active, or the one started here) ---------
  const activeRun = activeQ.data?.active ? activeQ.data.run : null;
  useEffect(() => {
    if (activeRun && activeRun.id !== watchId) setWatchId(activeRun.id);
  }, [activeRun, watchId, setWatchId]);
  const watched = useDiscoveryRun(watchId);
  useEffect(() => {
    if (watched.isError && apiErrorStatus(watched.error) === 404) setWatchId(null);
  }, [watched.isError, watched.error, setWatchId]);
  const panelRun = activeRun ?? (watched.data && watched.data.id === watchId ? watched.data : null);

  // --- Effective values (defaults resolved; nothing invented) --------------
  const rec = recommended.data;
  const rules: Rules = useMemo(() => ({ ...MANUAL_RULE_DEFAULTS, ...rulesFromAuto(auto.data), ...state.rules }), [auto.data, state.rules]);
  const requireEmail = state.requireOrganizerEmail ?? rec?.requireOrganizerEmail ?? true;
  const keepRejected = state.keepRejectedEvents ?? rec?.keepRejectedEvents ?? true;
  const targetText = state.targetValidEvents.trim();
  const target = targetText ? wholeNumber(targetText) : rec?.targetValidEvents ?? null;
  const limitValue = (k: LimitKey) => {
    const raw = (state.limits[k] ?? '').trim();
    return raw ? wholeNumber(raw) : LIMITS[k].def;
  };
  const dateFrom = state.dateMode === 'upcoming' ? rec?.dateFrom ?? null : state.dateFrom || null;
  const dateTo = state.dateMode === 'upcoming' ? rec?.dateTo ?? null : state.dateTo || null;
  const sectorOptions = useMemo(() => {
    const names = (categories.data ?? []).map((c) => c.name);
    return Array.from(new Set([...names, ...state.sectors])); // a chosen sector never disappears from view
  }, [categories.data, state.sectors]);
  const allSectorsChosen = (categories.data?.length ?? 0) > 0 && (categories.data ?? []).every((c) => state.sectors.includes(c.name));
  const worldwide = state.geoMode === 'worldwide';
  const advancedSeed: AdvancedSources = state.advanced ?? {
    sources: rec?.sources ?? [],
    searchProviders: rec?.searchProviders ?? null,
    listingUrls: [], // empty -> the editor starts from the default website list
    ticketmasterEnabled: false,
  };

  // --- Validation -----------------------------------------------------------
  const errors: WizardError[] = useMemo(() => {
    const out: WizardError[] = [];
    const add = (step: number, field: string, message: string) => out.push({ step, field, message });
    if (state.sectors.length === 0) add(0, 'sectors', 'Choose at least one sector.');

    if (state.geoMode === null) add(1, 'geo', 'Choose Worldwide, or pick the countries to search.');
    else if (state.geoMode === 'countries' && state.countries.length === 0) add(1, 'geo', 'Pick at least one country, or choose Worldwide.');

    if (state.dateMode === 'upcoming') {
      if (!rec) add(2, 'dates', recommended.isError ? 'The upcoming date range could not be loaded — choose custom dates instead.' : 'Loading the upcoming date range…');
    } else {
      const today = todayISO();
      if (!state.dateFrom) add(2, 'dateFrom', 'Choose a start date.');
      if (!state.dateTo) add(2, 'dateTo', 'Choose an end date.');
      else if (state.dateTo < today) add(2, 'dateTo', 'The end date is in the past — events must end on or after today.');
      if (state.dateFrom && state.dateTo && state.dateFrom > state.dateTo) add(2, 'dateFrom', 'The start date is after the end date.');
    }

    if (rec?.blocker) add(3, 'strategy', rec.blocker);
    else if (state.strategy === 'recommended' && !rec) {
      add(3, 'strategy', recommended.isError ? 'The recommended settings could not be loaded — try again or choose Advanced.' : 'Loading the recommended settings…');
    } else if (state.strategy === 'advanced') {
      if (!state.advanced) add(3, 'strategy', 'Open the Advanced source settings once so they can load.');
      else if (!hasChannel(state.advanced)) add(3, 'strategy', 'Turn on at least one source: web search, directories, aggregators or Ticketmaster.');
    }

    if (target === null) add(4, 'target', 'Enter how many valid events to find.');
    else if (!Number.isInteger(target) || target < TARGET_RANGE.min || target > TARGET_RANGE.max) add(4, 'target', `Enter a whole number from ${TARGET_RANGE.min} to ${TARGET_RANGE.max}.`);
    for (const k of Object.keys(LIMITS) as LimitKey[]) {
      const v = limitValue(k);
      if (!Number.isInteger(v) || v < LIMITS[k].min || v > LIMITS[k].max) add(4, k, `Enter a whole number from ${LIMITS[k].min} to ${LIMITS[k].max}.`);
    }
    for (const k of RULE_NUMBERS) {
      const v = wholeNumber(rules[k]);
      const max = k === 'minConfidenceScore' ? 100 : 1000;
      if (!Number.isInteger(v) || v < 0 || v > max) add(4, k, `Enter a whole number from 0 to ${max}.`);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, rec, recommended.isError, target, rules]);

  const errorsFor = (step: number) => errors.filter((e) => e.step === step);
  const fieldError = (field: string) => {
    const e = errors.find((x) => x.field === field);
    return e && (state.attempted.includes(e.step) || state.step === LAST) ? e.message : undefined;
  };
  const stepDone = (i: number) => i === LAST || errorsFor(i).length === 0;

  // --- Navigation -----------------------------------------------------------
  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [state.step]);

  const go = (i: number) => {
    if (i < 0 || i > LAST || i > state.visited) return;
    update({ step: i });
  };
  const next = () => {
    const step = state.step;
    if (errorsFor(step).length > 0) {
      update((prev) => ({ attempted: prev.attempted.includes(step) ? prev.attempted : [...prev.attempted, step] }));
      return;
    }
    update((prev) => ({ step: step + 1, visited: Math.max(prev.visited, step + 1) }));
  };
  const back = () => update((prev) => ({ step: Math.max(0, prev.step - 1) }));

  const startOver = () => {
    setState(initialState());
    setTmKey('');
    setConfirmReset(false);
    setStartNote(null);
    startRun.reset();
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    if (fromId) navigate('/admin/discover', { replace: true });
  };

  const onAdvancedChange = useCallback(
    (s: DiscoverySourcesState) => {
      setTmKey(s.ticketmasterApiKey);
      setState((prev) => {
        const next: AdvancedSources = { sources: s.sources, searchProviders: s.searchProviders, listingUrls: s.listingUrls, ticketmasterEnabled: s.ticketmasterEnabled };
        const cur = prev.advanced;
        if (
          cur &&
          cur.ticketmasterEnabled === next.ticketmasterEnabled &&
          sameSet(cur.sources, next.sources) &&
          sameSet(cur.listingUrls, next.listingUrls) &&
          (cur.searchProviders === null ? next.searchProviders === null : next.searchProviders !== null && sameSet(cur.searchProviders, next.searchProviders))
        )
          return prev;
        return { ...prev, advanced: next };
      });
    },
    [],
  );

  // --- Payload (the same shape ManualResearch sends) ------------------------
  const buildPayload = (): DiscoveryRunPayload => {
    const adv = state.strategy === 'advanced' ? state.advanced : null;
    const geo = worldwide
      ? { countries: undefined, country: undefined, locations: [], regionCities: {}, states: undefined, cities: undefined }
      : {
          country: state.countries[0],
          countries: state.countries,
          locations: buildDiscoveryLocations(state.countries, state.states, state.cities),
          regionCities: buildRegionCities(state.countries, state.states, state.cities),
          states: state.states.length ? state.states : undefined,
          cities: state.cities.length ? state.cities : undefined,
        };
    return {
      ...geo,
      categories: state.sectors,
      sources: adv ? adv.sources : rec?.sources ?? [WEB],
      searchProviders: adv ? adv.searchProviders ?? undefined : rec?.searchProviders ?? undefined,
      listingUrls: adv && adv.listingUrls.length ? adv.listingUrls : undefined,
      ticketmasterEnabled: adv ? adv.ticketmasterEnabled : undefined,
      ticketmasterApiKey: adv && tmKey.trim() ? tmKey.trim() : undefined,
      eventsPerRun: limitValue('eventsPerRun'),
      targetValidEvents: target ?? undefined,
      searchDepth: limitValue('searchDepth'),
      sourcesPerQuery: limitValue('sourcesPerQuery'),
      dateFrom: dateFrom ?? undefined,
      dateTo: dateTo ?? undefined,
      requireOrganizerEmail: requireEmail,
      keepRejectedEvents: keepRejected,
      rejectNoOrganizer: rules.rejectNoOrganizer,
      fallbackToOtherSector: rules.fallbackToOtherSector,
      rejectUnmatchedCategory: rules.rejectUnmatchedCategory,
      requireOrganizerPhone: rules.requireOrganizerPhone,
      requireOrganizerWebsite: rules.requireOrganizerWebsite,
      rejectPastEvents: rules.rejectPastEvents,
      rejectUnparseableDates: rules.rejectUnparseableDates,
      rejectMissingLocation: rules.rejectMissingLocation,
      rejectMissingTicketUrl: rules.rejectMissingTicketUrl,
      minTitleLength: wholeNumber(rules.minTitleLength),
      minDescriptionLength: wholeNumber(rules.minDescriptionLength),
      minConfidenceScore: wholeNumber(rules.minConfidenceScore),
      blacklistedKeywords: splitList(rules.blacklistedKeywords),
      excludedDomains: cleanDomains(rules.excludedDomains),
    };
  };

  const canStart = errors.length === 0 && !activeRun && !startRun.isPending;
  const start = () => {
    if (!canStart) return;
    setStartNote(null);
    startRun.mutate(buildPayload(), {
      onSuccess: (res) => {
        const id = typeof res.runId === 'number' ? res.runId : null;
        if (id) setWatchId(id);
        // The server answers with the run already going when one was running (it never runs two at once).
        if ((res as { alreadyRunning?: boolean }).alreadyRunning) setStartNote(String(res.message ?? 'A discovery run is already in progress.'));
        const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
      },
    });
  };

  // --- Scope estimate (clearly labelled as one) -----------------------------
  const advProviders = state.strategy === 'advanced' ? state.advanced?.searchProviders ?? null : null;
  // Web search runs when its channel is on and at least one provider may be called (null = all configured).
  const webOn =
    state.strategy === 'advanced'
      ? Boolean(state.advanced?.sources.includes(WEB)) && (advProviders === null || advProviders.length > 0)
      : Boolean(rec?.channels.web.available);
  const places = worldwide ? 1 : state.countries.length;
  const depth = limitValue('searchDepth');
  const firstWave = webOn && Number.isInteger(depth) ? Math.max(depth, Math.min(state.sectors.length * Math.max(places, 1), COVERAGE_CAP)) : 0;
  const sourceCount =
    state.strategy === 'advanced'
      ? state.advanced
        ? advancedSourceCount(state.advanced, catalog.data)
        : null
      : rec
        ? rec.channels.directories.sources + rec.channels.aggregators.sources
        : null;
  const providerNames = advProviders
    ? advProviders.map((id) => catalog.data?.providers.find((p) => p.id === id)?.name ?? id)
    : rec?.channels.web.providers ?? [];

  // --- Render ---------------------------------------------------------------
  if (categories.isLoading) return <LoadingState label="Loading discovery settings" />;

  const step = state.step;
  const stepErrors = state.attempted.includes(step) ? errorsFor(step) : [];
  const notices = rec?.notices ?? [];

  return (
    <div className="page-enter">
      <PageHeader
        kicker="Discover events"
        title="Run discovery"
        subtitle="Answer a few short questions, check the summary, then start. Nothing is pre-selected — you choose the sectors and places for every run."
        actions={
          <>
            <Link href="/admin/discover/runs" className={linkButton('secondary')}>
              <History size={13} /> Run history
            </Link>
            {confirmReset ? (
              <span className="inline-flex flex-wrap items-center gap-2 rounded-full border border-foreground/15 bg-card px-3 py-1 text-[11px]" role="group" aria-label="Confirm start over">
                Clear every choice?
                <Btn size="sm" variant="danger" onClick={startOver}>
                  Yes, start over
                </Btn>
                <Btn size="sm" variant="ghost" onClick={() => setConfirmReset(false)}>
                  Cancel
                </Btn>
              </span>
            ) : (
              <Btn onClick={() => setConfirmReset(true)}>
                <RotateCcw size={13} /> Start over
              </Btn>
            )}
          </>
        }
      />

      {fromId && fromRun.isError && (
        <div className="mt-6">
          <Notice tone="warn">
            {apiErrorStatus(fromRun.error) === 404 ? `Run #${fromId} was not found` : `Run #${fromId} could not be loaded`}, so nothing was pre-filled.
          </Notice>
        </div>
      )}
      {fromId && fromRun.isLoading && <p className="mt-6 text-xs text-muted-foreground">Loading the settings of run #{fromId}…</p>}
      {state.prefilledFrom && (
        <div className="mt-6">
          <Notice tone="info">
            Pre-filled from{' '}
            <Link href={`/admin/discover/runs/${state.prefilledFrom}`} className="font-semibold text-accent hover:underline">
              run #{state.prefilledFrom}
            </Link>
            . Check each step — anything that run did not record keeps its default.
          </Notice>
        </div>
      )}

      {panelRun && (
        <div className="mt-6">
          <RunProgress key={panelRun.id} run={panelRun} live onDismiss={panelRun.status === 'running' ? undefined : () => setWatchId(null)} />
        </div>
      )}
      {startNote && (
        <div className="mt-3">
          <Notice tone="warn">{startNote} No new run was started.</Notice>
        </div>
      )}
      {activeRun && (
        <div className="mt-3">
          <Notice tone="info">
            Run #{activeRun.id} is still going. The server runs one discovery at a time, so you can set up the next run now and start it once this one
            finishes (or after you stop it).
          </Notice>
        </div>
      )}

      <Panel className="mt-6 p-5 sm:p-6">
        <StepIndicator step={step} visited={state.visited} done={stepDone} onGo={go} />

        <div className="mt-6">
          <Kicker className="text-muted-foreground">
            Step {step + 1} of {STEPS.length}
          </Kicker>
          <h2 ref={headingRef} tabIndex={-1} className="mt-1 font-display text-2xl font-extrabold tracking-[-.04em] outline-none">
            {STEPS[step].title}
          </h2>
        </div>

        {stepErrors.length > 0 && (
          <div className="mt-4" role="alert">
            <Notice tone="danger">
              {stepErrors.length === 1 ? stepErrors[0].message : (
                <ul className="list-disc pl-4">
                  {stepErrors.map((e) => (
                    <li key={e.field}>{e.message}</li>
                  ))}
                </ul>
              )}
            </Notice>
          </div>
        )}

        <div className="mt-5">
          {/* ---------------- Step 1: sectors ---------------- */}
          {step === 0 && (
            <div className="grid gap-5">
              <div role="group" aria-labelledby={sectorsLabelId}>
                <div className="flex flex-wrap items-end justify-between gap-2">
                  <h3 id={sectorsLabelId} className="text-sm font-bold">Target sectors</h3>
                  <div className="flex gap-3 text-[11px]">
                    <button type="button" className="font-semibold text-accent hover:underline disabled:opacity-50" disabled={!sectorOptions.length} onClick={() => update({ sectors: [...sectorOptions] })}>
                      Select all
                    </button>
                    <button type="button" className="text-muted-foreground hover:underline disabled:opacity-50" disabled={!state.sectors.length} onClick={() => update({ sectors: [] })}>
                      Clear
                    </button>
                  </div>
                </div>
                <Help>Pick at least one. Events outside these sectors are not counted toward your goal.</Help>
                {categories.isError ? (
                  <div className="mt-3">
                    <ErrorState error={categories.error} retry={() => categories.refetch()} title="Could not load the sector list." />
                  </div>
                ) : (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {sectorOptions.map((name) => {
                      const on = state.sectors.includes(name);
                      return (
                        <button
                          type="button"
                          key={name}
                          aria-pressed={on}
                          onClick={() => update((prev) => ({ sectors: on ? prev.sectors.filter((s) => s !== name) : [...prev.sectors, name] }))}
                          className={cx(
                            'inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60',
                            on ? 'border-accent bg-accent/15 font-semibold text-accent' : 'border-foreground/15 bg-card text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                          )}
                        >
                          {on && <Check size={12} aria-hidden="true" />}
                          {name}
                        </button>
                      );
                    })}
                  </div>
                )}
                <p className="mt-2 text-[11px] text-muted-foreground" aria-live="polite">
                  {state.sectors.length ? `${plural(state.sectors.length, 'sector')} selected` : 'No sector selected yet'}
                </p>
                {fieldError('sectors') && <FieldError>{fieldError('sectors')}</FieldError>}
              </div>

              <Expander
                open={state.open.keywords}
                onToggle={() => update((prev) => ({ open: { ...prev.open, keywords: !prev.open.keywords } }))}
                title="Advanced"
                summary={splitList(rules.blacklistedKeywords).length ? `${plural(splitList(rules.blacklistedKeywords).length, 'excluded word')}` : 'Exclude words'}
              >
                <TextAreaField
                  label="Exclude events containing…"
                  value={rules.blacklistedKeywords}
                  onChange={(v) => setRule('blacklistedKeywords', v)}
                  placeholder="e.g. webinar, crypto giveaway, casino"
                  help="Separate with commas. An event whose title or description contains any of these is rejected. Starts from the words saved in the Automatic settings."
                />
              </Expander>
            </div>
          )}

          {/* ---------------- Step 2: places ---------------- */}
          {step === 1 && (
            <div className="grid gap-4">
              <fieldset className="grid gap-2 sm:grid-cols-2">
                <legend className="sr-only">Where to search</legend>
                <ChoiceCard name="geo" checked={state.geoMode === 'worldwide'} onSelect={() => update({ geoMode: 'worldwide' })} title={<span className="inline-flex items-center gap-1.5"><Globe size={14} className="text-accent" /> Worldwide</span>}>
                  Search every country. No place filter is applied.
                </ChoiceCard>
                <ChoiceCard name="geo" checked={state.geoMode === 'countries'} onSelect={() => update({ geoMode: 'countries' })} title={<span className="inline-flex items-center gap-1.5"><MapPin size={14} className="text-accent" /> Specific countries</span>}>
                  Pick countries, and optionally narrow to states or cities.
                </ChoiceCard>
              </fieldset>
              {fieldError('geo') && <FieldError>{fieldError('geo')}</FieldError>}
              {state.geoMode === 'countries' && (
                <div>
                  <Help>A country with no state or city ticked means the whole country. Events outside the places you pick are rejected.</Help>
                  <div className="mt-3">
                    <GeoChecklistSelector
                      selectedCountries={state.countries}
                      onCountriesChange={(countries) => update({ countries })}
                      selectedStates={state.states}
                      onStatesChange={(states) => update({ states })}
                      selectedCities={state.cities}
                      onCitiesChange={(cities) => update({ cities })}
                      emptyMeansWorldwide={false}
                    />
                  </div>
                </div>
              )}
              {state.geoMode === 'worldwide' && (state.countries.length > 0 || state.cities.length > 0) && (
                <Help>Your country and city picks are kept, but not used while Worldwide is selected.</Help>
              )}
            </div>
          )}

          {/* ---------------- Step 3: dates ---------------- */}
          {step === 2 && (
            <div className="grid gap-4">
              <fieldset className="grid gap-2 sm:grid-cols-2">
                <legend className="sr-only">Event dates</legend>
                <ChoiceCard
                  name="dates"
                  checked={state.dateMode === 'upcoming'}
                  onSelect={() => update({ dateMode: 'upcoming' })}
                  title={rec ? `Upcoming (${windowLabel(rec.upcomingWindowDays)})` : 'Upcoming'}
                >
                  {rec ? `Events from ${fmtDay(rec.dateFrom)} to ${fmtDay(rec.dateTo)}.` : recommended.isError ? 'The upcoming range could not be loaded.' : 'Loading the upcoming range…'}
                </ChoiceCard>
                <ChoiceCard name="dates" checked={state.dateMode === 'custom'} onSelect={() => update({ dateMode: 'custom' })} title="Custom dates">
                  Only events that take place between two dates you choose.
                </ChoiceCard>
              </fieldset>
              {state.dateMode === 'upcoming' && fieldError('dates') && <FieldError>{fieldError('dates')}</FieldError>}
              {state.dateMode === 'custom' && <CustomDates state={state} update={update} fieldError={fieldError} />}
            </div>
          )}

          {/* ---------------- Step 4: strategy ---------------- */}
          {step === 3 && (
            <div className="grid gap-4">
              {rec?.blocker && (
                <Notice tone="danger">
                  <strong>Discovery can't run right now.</strong> {rec.blocker}
                </Notice>
              )}
              <fieldset className="grid gap-2">
                <legend className="sr-only">Discovery strategy</legend>
                <ChoiceCard name="strategy" checked={state.strategy === 'recommended'} onSelect={() => update({ strategy: 'recommended' })} title="Recommended (automatic)">
                  The system picks the sources that are set up and working right now.
                </ChoiceCard>
                {state.strategy === 'recommended' && <RecommendedSummary recommended={recommended} />}
                <ChoiceCard name="strategy" checked={state.strategy === 'advanced'} onSelect={() => update({ strategy: 'advanced' })} title="Advanced (choose sources yourself)">
                  Pick channels, individual sources, search providers and listing websites for this run. Nothing here changes the saved settings.
                </ChoiceCard>
              </fieldset>
              {fieldError('strategy') && !rec?.blocker && <FieldError>{fieldError('strategy')}</FieldError>}
              {state.strategy === 'advanced' && (
                <div className="rounded-xl border border-foreground/10 bg-background/40 p-4">
                  <AdvancedSourcesEditor seed={advancedSeed} onChange={onAdvancedChange} />
                </div>
              )}
              {state.strategy === 'advanced' && notices.length > 0 && <RecommendedNotices notices={notices} />}
            </div>
          )}

          {/* ---------------- Step 5: goals ---------------- */}
          {step === 4 && (
            <div className="grid gap-4">
              <div className="max-w-xs">
                <NumberField
                  label="Valid events to find"
                  value={state.targetValidEvents}
                  placeholder={rec ? String(rec.targetValidEvents) : undefined}
                  onChange={(v) => update({ targetValidEvents: v })}
                  min={TARGET_RANGE.min}
                  max={TARGET_RANGE.max}
                  error={fieldError('target')}
                  help={
                    <>
                      The run stops once this many verified events are saved{rec ? `, after ${rec.maxRunMinutes} minutes,` : ','} or when the sources run out.
                      {rec && !targetText && ` Leave blank for the recommended ${rec.targetValidEvents}.`}
                    </>
                  }
                />
              </div>
              <SwitchRow
                title="Require a public organizer e-mail"
                badge="Recommended"
                description="Only events with a public organizer e-mail count as valid — outreach needs one."
                checked={requireEmail}
                onChange={(v) => update({ requireOrganizerEmail: v })}
              />
              <SwitchRow
                title="Keep rejected events for review"
                badge="Recommended"
                description="Saves rejected events with the reason, so you can review and restore them later. They never count toward the goal."
                checked={keepRejected}
                onChange={(v) => update({ keepRejectedEvents: v })}
              />
              <Expander
                open={state.open.goals}
                onToggle={() => update((prev) => ({ open: { ...prev.open, goals: !prev.open.goals } }))}
                title="Advanced"
                summary="Rejection rules and run limits"
              >
                <GoalsAdvanced rules={rules} setRule={setRule} limits={state.limits} setLimit={setLimit} fieldError={fieldError} target={target} allSectorsChosen={allSectorsChosen} />
              </Expander>
            </div>
          )}

          {/* ---------------- Step 6: review ---------------- */}
          {step === LAST && (
            <div className="grid gap-5">
              <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[max-content_1fr]">
                <ReviewRow label="Sectors" onEdit={() => go(0)} empty={!state.sectors.length}>
                  {state.sectors.length ? state.sectors.join(', ') : 'None chosen'}
                </ReviewRow>
                <ReviewRow label="Places" onEdit={() => go(1)} empty={!state.geoMode || (!worldwide && !state.countries.length)}>
                  {worldwide
                    ? 'Worldwide'
                    : state.countries.length
                      ? [
                          state.countries.join(', '),
                          state.states.length ? plural(state.states.length, 'state') : null,
                          state.cities.length ? plural(state.cities.length, 'city', 'cities') : null,
                        ]
                          .filter(Boolean)
                          .join(' · ')
                      : 'Not chosen'}
                </ReviewRow>
                <ReviewRow label="Dates" onEdit={() => go(2)} empty={!dateFrom || !dateTo}>
                  {dateFrom && dateTo
                    ? `${state.dateMode === 'upcoming' ? 'Upcoming: ' : ''}${fmtDay(dateFrom)} → ${fmtDay(dateTo)}`
                    : 'Not set'}
                </ReviewRow>
                <ReviewRow label="Strategy" onEdit={() => go(3)}>
                  {state.strategy === 'recommended' ? (
                    rec ? (
                      <>
                        Recommended — {rec.channels.web.available ? `web search via ${rec.channels.web.providers.join(', ')}` : 'no web search'}, {plural(rec.channels.directories.sources, 'directory', 'directories')},{' '}
                        {plural(rec.channels.aggregators.sources, 'aggregator')}
                      </>
                    ) : (
                      'Recommended'
                    )
                  ) : state.advanced ? (
                    <>
                      Advanced — {webOn ? `web search${providerNames.length ? ` via ${providerNames.join(', ')}` : ' (every configured provider)'}` : state.advanced.sources.includes(WEB) ? 'web search on, but no provider ticked' : 'no web search'}
                      {sourceCount !== null && `, ${plural(sourceCount, 'directory/aggregator source')}`}
                      {state.advanced.ticketmasterEnabled && ', Ticketmaster'}
                      {state.advanced.listingUrls.length > 0 && `, ${plural(state.advanced.listingUrls.length, 'listing website')}`}
                    </>
                  ) : (
                    'Advanced — not loaded yet'
                  )}
                </ReviewRow>
                <ReviewRow label="Goals" onEdit={() => go(4)}>
                  {target !== null && Number.isInteger(target) ? `${target} verified events` : 'Not set'} · organizer e-mail {requireEmail ? 'required' : 'not required'} · rejected events{' '}
                  {keepRejected ? 'kept for review' : 'discarded'}
                </ReviewRow>
                <ReviewRow label="Exclusions" onEdit={() => go(0)}>
                  {[
                    splitList(rules.blacklistedKeywords).length ? `words: ${splitList(rules.blacklistedKeywords).join(', ')}` : null,
                    cleanDomains(rules.excludedDomains).length ? `sites: ${cleanDomains(rules.excludedDomains).join(', ')}` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ') || 'None'}
                </ReviewRow>
                <ReviewRow label="Rules" onEdit={() => go(4)}>
                  {activeRuleNames(rules, allSectorsChosen)}
                </ReviewRow>
              </dl>

              <div className="rounded-xl border border-dashed border-foreground/20 bg-muted/20 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-xs font-bold">Estimated scope</p>
                  <Badge tone="neutral">Estimate</Badge>
                </div>
                <p className="mt-1.5 text-sm">
                  {plural(state.sectors.length, 'sector')} × {worldwide ? 'worldwide' : plural(state.countries.length, 'country', 'countries')} →{' '}
                  {webOn ? <>about <strong>{firstWave}</strong> first-wave searches</> : <>no web searches</>}
                  {'; '}
                  {sourceCount !== null ? <><strong>{sourceCount}</strong> directory/aggregator sources</> : 'directory/aggregator sources: —'}.
                </p>
                <Help>
                  Worked out from your choices before the run starts. More searches run only if the first wave falls short of the goal, and directories that don't
                  cover your countries are skipped. The run report shows what really ran.
                </Help>
              </div>

              {notices.length > 0 && <RecommendedNotices notices={notices} />}

              {errors.length > 0 && (
                <div role="alert">
                  <Notice tone="danger">
                    <p className="font-semibold">Fix {errors.length === 1 ? 'this' : 'these'} before starting:</p>
                    <ul className="mt-1 space-y-1">
                      {errors.map((e) => (
                        <li key={`${e.step}-${e.field}`} className="flex flex-wrap items-baseline gap-x-2">
                          <span>{e.message}</span>
                          <button type="button" onClick={() => go(e.step)} className="font-semibold underline underline-offset-2">
                            Go to {STEPS[e.step].short}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </Notice>
                </div>
              )}
              {activeRun && (
                <Notice tone="warn">Run #{activeRun.id} is still going — the server runs one discovery at a time. Start this one when it finishes, or stop it above.</Notice>
              )}
              {startRun.isError && <Notice tone="danger">The run could not be started: {(startRun.error as Error)?.message}</Notice>}

              <div className="flex flex-wrap items-center gap-3">
                <Btn variant="primary" onClick={start} disabled={!canStart} loading={startRun.isPending}>
                  <Play size={13} /> {startRun.isPending ? 'Starting…' : 'Start discovery run'}
                </Btn>
                <span className="text-[11px] text-muted-foreground">The run works on the server; you can leave this page while it runs.</span>
              </div>
            </div>
          )}
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-foreground/10 pt-4">
          <Btn onClick={back} disabled={step === 0}>
            <ArrowLeft size={13} /> Back
          </Btn>
          {step < LAST && (
            <Btn variant="primary" onClick={next}>
              Next: {STEPS[step + 1].short} <ArrowRight size={13} />
            </Btn>
          )}
        </div>
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step pieces
// ---------------------------------------------------------------------------

function CustomDates({
  state,
  update,
  fieldError,
}: {
  state: WizardState;
  update: (patch: Partial<WizardState>) => void;
  fieldError: (field: string) => string | undefined;
}) {
  const fromId = useId();
  const toId = useId();
  const fromErr = fieldError('dateFrom');
  const toErr = fieldError('dateTo');
  return (
    <div className="grid max-w-md gap-3 sm:grid-cols-2">
      <div>
        <label htmlFor={fromId} className="text-[11px] font-semibold">
          From
        </label>
        <input
          id={fromId}
          type="date"
          value={state.dateFrom}
          max={state.dateTo || undefined}
          onChange={(e) => update({ dateFrom: e.target.value })}
          aria-invalid={Boolean(fromErr)}
          aria-describedby={fromErr ? `${fromId}-err` : undefined}
          className={cx(inputClass, 'mt-1', fromErr && 'border-red-500/60')}
        />
        {fromErr && <FieldError id={`${fromId}-err`}>{fromErr}</FieldError>}
      </div>
      <div>
        <label htmlFor={toId} className="text-[11px] font-semibold">
          To
        </label>
        <input
          id={toId}
          type="date"
          value={state.dateTo}
          min={todayISO()}
          onChange={(e) => update({ dateTo: e.target.value })}
          aria-invalid={Boolean(toErr)}
          aria-describedby={toErr ? `${toId}-err` : undefined}
          className={cx(inputClass, 'mt-1', toErr && 'border-red-500/60')}
        />
        {toErr && <FieldError id={`${toId}-err`}>{toErr}</FieldError>}
      </div>
      <p className="text-[11px] text-muted-foreground sm:col-span-2">The end date can't be in the past.</p>
    </div>
  );
}

function RecommendedNotices({ notices }: { notices: RecommendedConfig['notices'] }) {
  return (
    <div className="grid gap-2">
      {notices.map((n, i) => (
        <Notice key={i} tone={n.level === 'warning' ? 'warn' : 'info'}>
          {n.message}
          {n.action && <span className="mt-1 block font-semibold">What to do: {n.action}</span>}
        </Notice>
      ))}
    </div>
  );
}

function RecommendedSummary({ recommended }: { recommended: ReturnType<typeof useRecommendedConfig> }) {
  if (recommended.isLoading) return <p className="px-1 text-xs text-muted-foreground">Checking which sources are available…</p>;
  if (recommended.isError || !recommended.data)
    return <ErrorState error={recommended.error} retry={() => recommended.refetch()} title="Could not load the recommended settings." />;
  const r = recommended.data;
  const rows: Array<{ label: string; on: boolean; detail: string }> = [
    { label: 'Web search', on: r.channels.web.available, detail: r.channels.web.available ? `via ${r.channels.web.providers.join(', ')}` : 'no search provider is usable' },
    { label: 'Directories', on: r.channels.directories.available, detail: r.channels.directories.available ? plural(r.channels.directories.sources, 'source') : 'none working' },
    { label: 'Aggregators', on: r.channels.aggregators.available, detail: r.channels.aggregators.available ? plural(r.channels.aggregators.sources, 'source') : 'none working' },
    { label: 'Event listing pages', on: (r.listingUrls?.length ?? 0) > 0, detail: r.listingUrls?.length ? `${plural(r.listingUrls.length, 'default page')} read directly` : 'none set' },
    { label: 'Ticketmaster', on: Boolean(r.ticketmaster?.available), detail: r.ticketmaster?.available ? 'API key set — included' : 'no API key — skipped' },
  ];
  return (
    <div className="ml-0 grid gap-3 rounded-xl border border-foreground/10 bg-background/40 p-4 sm:ml-7">
      <ul className="grid gap-2 sm:grid-cols-3">
        {rows.map((row) => (
          <li key={row.label} className="rounded-lg border border-foreground/10 bg-card p-3">
            <p className="flex items-center gap-1.5 text-xs font-bold">
              <span className={cx('h-2 w-2 rounded-full', row.on ? 'bg-emerald-500' : 'bg-muted-foreground/40')} aria-hidden="true" />
              {row.label}
              <span className="sr-only">{row.on ? '(usable)' : '(not usable)'}</span>
            </p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{row.detail}</p>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-muted-foreground">
        Runs for at most {r.maxRunMinutes} minutes{r.paidSearchBudget !== null ? `, with up to ${r.paidSearchBudget} paid searches` : ''}. Free search providers are asked first.
      </p>
      {r.notices.length > 0 && <RecommendedNotices notices={r.notices} />}
    </div>
  );
}

function GoalsAdvanced({
  rules,
  setRule,
  limits,
  setLimit,
  fieldError,
  target,
  allSectorsChosen,
}: {
  rules: Rules;
  setRule: <K extends keyof Rules>(k: K, v: Rules[K]) => void;
  limits: Partial<Record<LimitKey, string>>;
  setLimit: (k: LimitKey, v: string) => void;
  fieldError: (field: string) => string | undefined;
  target: number | null;
  allSectorsChosen: boolean;
}) {
  const eventsPerRun = limits.eventsPerRun?.trim() ? wholeNumber(limits.eventsPerRun) : LIMITS.eventsPerRun.def;
  // The server raises the cap to at least 10x the goal and never below 500 when a goal is set.
  const effectiveCap = Number.isInteger(eventsPerRun) && target !== null && Number.isInteger(target) ? Math.max(eventsPerRun, target * 10, 500) : null;
  return (
    <div className="grid gap-5">
      <p className="text-[11px] text-muted-foreground">These start from the saved Automatic settings. Changes apply to this run only.</p>

      <div className="grid gap-2">
        <Kicker className="text-muted-foreground">Organizer</Kicker>
        <FilterRuleRow icon={Building2} title="Reject events with no organizer" description="Skip events where no organizer could be identified." checked={rules.rejectNoOrganizer} onChange={(v) => setRule('rejectNoOrganizer', v)} />
        <FilterRuleRow icon={Phone} title="Require an organizer phone number" description="Skip events without an official phone number." checked={rules.requireOrganizerPhone} onChange={(v) => setRule('requireOrganizerPhone', v)} />
        <FilterRuleRow icon={Globe} title="Require an organizer website" description="Skip events whose organizer has no official website." checked={rules.requireOrganizerWebsite} onChange={(v) => setRule('requireOrganizerWebsite', v)} />
      </div>

      <div className="grid gap-2">
        <Kicker className="text-muted-foreground">Dates, place and links</Kicker>
        <FilterRuleRow icon={CalendarX} title="Reject past events" description="Skip events whose start date has already passed." checked={rules.rejectPastEvents} onChange={(v) => setRule('rejectPastEvents', v)} />
        <FilterRuleRow icon={AlertTriangle} title="Reject unclear dates" description="Skip events whose date can't be read as a calendar date." checked={rules.rejectUnparseableDates} onChange={(v) => setRule('rejectUnparseableDates', v)} />
        <FilterRuleRow icon={MapPin} title="Reject in-person events with no location" description="Skip in-person or hybrid events that list neither a venue nor a city." checked={rules.rejectMissingLocation} onChange={(v) => setRule('rejectMissingLocation', v)} />
        <FilterRuleRow icon={Tag} title="Require a ticket or registration link" description="Skip events without a registration or ticket URL." checked={rules.rejectMissingTicketUrl} onChange={(v) => setRule('rejectMissingTicketUrl', v)} />
      </div>

      <div className="grid gap-2">
        <Kicker className="text-muted-foreground">Sectors</Kicker>
        {allSectorsChosen ? (
          <>
            <FilterRuleRow icon={Layers} title="File unmatched events under 'Other'" description="With every sector chosen, events that fit none of them are kept as 'Other' instead of being turned down." checked={rules.fallbackToOtherSector} onChange={(v) => setRule('fallbackToOtherSector', v)} />
            {!rules.fallbackToOtherSector && (
              <FilterRuleRow icon={FilterX} title="Reject events outside the 100 TIMES sectors" description="Turn down events whose sector doesn't match any 100 TIMES sector." checked={rules.rejectUnmatchedCategory} onChange={(v) => setRule('rejectUnmatchedCategory', v)} />
            )}
          </>
        ) : (
          <p className="rounded-lg border border-foreground/10 bg-card/60 p-3 text-[11px] text-muted-foreground">
            Events outside the sectors you chose are always turned down (kept for review if that option is on).
          </p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <NumberField label="Minimum title length" value={rules.minTitleLength} onChange={(v) => setRule('minTitleLength', v)} min={0} max={1000} error={fieldError('minTitleLength')} help="Characters." />
        <NumberField label="Minimum description length" value={rules.minDescriptionLength} onChange={(v) => setRule('minDescriptionLength', v)} min={0} max={1000} error={fieldError('minDescriptionLength')} help="Characters." />
        <NumberField label="Minimum confidence" value={rules.minConfidenceScore} onChange={(v) => setRule('minConfidenceScore', v)} min={0} max={100} error={fieldError('minConfidenceScore')} help="0–100. Events scored lower are rejected." />
      </div>

      <TextAreaField
        label="Never use pages from these websites"
        value={rules.excludedDomains}
        onChange={(v) => setRule('excludedDomains', v)}
        placeholder="e.g. spam-listings.com, bit.ly"
        help="Separate with commas. Events found on these domains are rejected."
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <NumberField
          label="Events per run"
          value={limits.eventsPerRun ?? ''}
          placeholder={String(LIMITS.eventsPerRun.def)}
          onChange={(v) => setLimit('eventsPerRun', v)}
          min={LIMITS.eventsPerRun.min}
          max={LIMITS.eventsPerRun.max}
          error={fieldError('eventsPerRun')}
          help={effectiveCap !== null ? `Most candidates the run looks at. The server raises this to at least 10× the goal (minimum 500): ${effectiveCap} for this run.` : 'Most candidates the run looks at.'}
        />
        <NumberField
          label="Search queries"
          value={limits.searchDepth ?? ''}
          placeholder={String(LIMITS.searchDepth.def)}
          onChange={(v) => setLimit('searchDepth', v)}
          min={LIMITS.searchDepth.min}
          max={LIMITS.searchDepth.max}
          error={fieldError('searchDepth')}
          help={`Searches in the first wave — raised so each sector × country pair gets one (up to ${COVERAGE_CAP}).`}
        />
        <NumberField
          label="Pages per query"
          value={limits.sourcesPerQuery ?? ''}
          placeholder={String(LIMITS.sourcesPerQuery.def)}
          onChange={(v) => setLimit('sourcesPerQuery', v)}
          min={LIMITS.sourcesPerQuery.min}
          max={LIMITS.sourcesPerQuery.max}
          error={fieldError('sourcesPerQuery')}
          help="Result links opened from each search."
        />
      </div>
    </div>
  );
}

const RULE_NAMES: Record<RuleFlag, string> = {
  rejectNoOrganizer: 'no organizer',
  requireOrganizerPhone: 'no organizer phone',
  requireOrganizerWebsite: 'no organizer website',
  rejectPastEvents: 'past events',
  rejectUnparseableDates: 'unclear dates',
  rejectMissingLocation: 'no location',
  rejectMissingTicketUrl: 'no ticket link',
  rejectUnmatchedCategory: 'outside 100 TIMES sectors',
  fallbackToOtherSector: "unmatched filed as 'Other'",
};

/** "Rejects: past events, unclear dates, …" for the review. */
function activeRuleNames(rules: Rules, allSectorsChosen: boolean): string {
  const shown: RuleFlag[] = ['rejectNoOrganizer', 'requireOrganizerPhone', 'requireOrganizerWebsite', 'rejectPastEvents', 'rejectUnparseableDates', 'rejectMissingLocation', 'rejectMissingTicketUrl'];
  if (allSectorsChosen) shown.push(rules.fallbackToOtherSector ? 'fallbackToOtherSector' : 'rejectUnmatchedCategory');
  const names = shown.filter((k) => rules[k]).map((k) => RULE_NAMES[k]);
  return names.length ? `Rejects: ${names.join(', ')}` : 'No extra rejection rules';
}

function ReviewRow({ label, children, onEdit, empty }: { label: string; children: ReactNode; onEdit: () => void; empty?: boolean }) {
  return (
    <div className="contents">
      <dt className="font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground sm:pt-0.5">{label}</dt>
      <dd className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className={cx('min-w-0 break-words', empty && 'text-red-600 dark:text-red-400')}>{children}</span>
        <button type="button" onClick={onEdit} className="text-[11px] font-semibold text-accent hover:underline" aria-label={`Change ${label.toLowerCase()}`}>
          Change
        </button>
      </dd>
    </div>
  );
}
