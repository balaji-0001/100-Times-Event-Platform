import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'wouter';
import { useQueryClient } from '@tanstack/react-query';
import { Check, ChevronDown, ChevronUp, Clock, Save, Undo2 } from 'lucide-react';
import {
  type DiscoveryAutoStatus,
  type DiscoveryAutoUpdate,
  runScopedKeys,
  useCategories,
  useDiscoveryAutoStatus,
  useSetDiscoveryAuto,
} from './api';
import { buildDiscoveryLocations, buildRegionCities } from '@/lib/countries';
import { GeoChecklistSelector } from './GeoChecklistSelector';
import { type DiscoverySourcesState, DiscoverySourcesManager } from './DiscoverySourcesManager';
import { Breadcrumbs } from './OpsLayout';
import { Badge, Btn, ErrorState, LoadingState, Notice, PageHeader, Panel, Switch, cx, fmtTime, inputClass } from './ui';

// ---------------------------------------------------------------------------
// The ONE place the saved discovery configuration is edited. Automatic discovery
// runs with exactly these values (the server reads them on every scheduled run).
// Saves go through PATCH /api/discovery/auto with the same field names the old
// settings drawer used; only fields the admin actually changed are sent, so a
// save never rewrites values nobody touched.
// ---------------------------------------------------------------------------

/** Shown when /api/categories can't be read — the same list the old settings drawer used. */
const FALLBACK_SECTORS = [
  'Construction', 'Energy and Power Generation', 'Finance', 'Healthcare', 'Manufacturing', 'Mining', 'Oil and Gas',
  'Packaging', 'Pharmaceuticals', 'Telecommunications', 'Textiles', 'Transport and Logistics', 'Other',
];

const BOOL_KEYS = [
  'fallbackToOtherSector', 'rejectUnmatchedCategory',
  'rejectPastEvents', 'rejectUnparseableDates', 'rejectMissingLocation', 'rejectMissingTicketUrl',
  'rejectNoOrganizer', 'requireOrganizerEmail', 'requireOrganizerPhone', 'requireOrganizerWebsite', 'keepRejectedEvents',
] as const;
type BoolKey = (typeof BOOL_KEYS)[number];

const NUM_FIELDS = {
  eventsPerRun: { min: 1, max: 500 },
  targetValidEvents: { min: 1, max: 500 },
  searchDepth: { min: 1, max: 200 },
  dailyLimit: { min: 1, max: 2000 },
  minTitleLength: { min: 0, max: 50 },
  minDescriptionLength: { min: 0, max: 200 },
  minConfidenceScore: { min: 0, max: 100 },
} as const;
type NumKey = keyof typeof NUM_FIELDS;
const NUM_KEYS = Object.keys(NUM_FIELDS) as NumKey[];

type Draft = {
  countries: string[];
  states: string[];
  cities: string[];
  categories: string[];
  blacklistedKeywords: string;
  excludedDomains: string;
} & Record<BoolKey, boolean> & Record<NumKey, string>;

type SectionId = 'geography' | 'sectors' | 'sources' | 'rules' | 'organizer' | 'limits';
const SECTIONS: Array<{ id: SectionId; label: string }> = [
  { id: 'geography', label: 'Geography' },
  { id: 'sectors', label: 'Sectors' },
  { id: 'sources', label: 'Sources & providers' },
  { id: 'rules', label: 'Validation & rejection rules' },
  { id: 'organizer', label: 'Organizer research' },
  { id: 'limits', label: 'Execution limits' },
];
const SECTION_OF: Record<BoolKey | NumKey | 'blacklistedKeywords' | 'excludedDomains', SectionId> = {
  fallbackToOtherSector: 'sectors', rejectUnmatchedCategory: 'sectors',
  rejectPastEvents: 'rules', rejectUnparseableDates: 'rules', rejectMissingLocation: 'rules', rejectMissingTicketUrl: 'rules',
  minTitleLength: 'rules', minDescriptionLength: 'rules', minConfidenceScore: 'rules', blacklistedKeywords: 'rules', excludedDomains: 'rules',
  rejectNoOrganizer: 'organizer', requireOrganizerEmail: 'organizer', requireOrganizerPhone: 'organizer', requireOrganizerWebsite: 'organizer', keepRejectedEvents: 'organizer',
  eventsPerRun: 'limits', targetValidEvents: 'limits', searchDepth: 'limits', dailyLimit: 'limits',
};

const numStr = (v?: number | null) => (typeof v === 'number' && Number.isFinite(v) ? String(v) : '');
const parseKeywords = (s: string) => s.split(',').map((k) => k.trim()).filter(Boolean);
const parseDomains = (s: string) => s.split(',').map((d) => d.trim().replace(/^https?:\/\//i, '').replace(/\/.*$/, '')).filter(Boolean);
const sameSet = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join('\u0000') === [...b].sort().join('\u0000');

/** The form's view of the saved settings. Defaults only apply when the API omits a field (it normally returns every one). */
function draftFromServer(a: DiscoveryAutoStatus): Draft {
  return {
    countries: a.countries && a.countries.length > 0 ? a.countries : a.country ? [a.country] : [],
    states: a.states ?? [],
    cities: a.cities ?? [],
    categories: a.categories ?? [],
    fallbackToOtherSector: a.fallbackToOtherSector ?? true,
    rejectUnmatchedCategory: a.rejectUnmatchedCategory ?? false,
    rejectPastEvents: a.rejectPastEvents ?? true,
    rejectUnparseableDates: a.rejectUnparseableDates ?? true,
    rejectMissingLocation: a.rejectMissingLocation ?? false,
    rejectMissingTicketUrl: a.rejectMissingTicketUrl ?? false,
    rejectNoOrganizer: a.rejectNoOrganizer ?? true,
    requireOrganizerEmail: a.requireOrganizerEmail ?? true,
    requireOrganizerPhone: a.requireOrganizerPhone ?? false,
    requireOrganizerWebsite: a.requireOrganizerWebsite ?? false,
    keepRejectedEvents: a.keepRejectedEvents ?? true,
    eventsPerRun: numStr(a.eventsPerRun),
    targetValidEvents: numStr(a.targetValidEvents),
    // null = never saved: the server uses its own default, so the field stays empty rather than showing a guess.
    searchDepth: numStr(a.searchDepth),
    dailyLimit: numStr(a.dailyLimit),
    minTitleLength: numStr(a.minTitleLength),
    minDescriptionLength: numStr(a.minDescriptionLength),
    minConfidenceScore: numStr(a.minConfidenceScore),
    blacklistedKeywords: (a.blacklistedKeywords ?? []).join(', '),
    excludedDomains: (a.excludedDomains ?? []).join(', '),
  };
}

/** The sources-related part of the saved settings, to notice when it changes on the server. */
const serverSourcesSignature = (a: DiscoveryAutoStatus) =>
  JSON.stringify([a.sources ?? [], a.searchProviders ?? null, a.listingUrls ?? [], Boolean(a.ticketmasterEnabled), Boolean(a.ticketmasterApiKeySet)]);

const sourcesSignature = (s: DiscoverySourcesState) =>
  JSON.stringify([[...s.sources].sort(), s.searchProviders === null ? null : [...s.searchProviders].sort(), [...s.listingUrls].sort(), s.ticketmasterEnabled, s.ticketmasterApiKey]);

function numberError(key: NumKey, value: string, saved: string): string | null {
  const v = value.trim();
  if (v === '') return saved.trim() === '' ? null : 'Enter a number — a saved value can’t be cleared.';
  const n = Number(v);
  const { min, max } = NUM_FIELDS[key];
  if (!Number.isInteger(n)) return 'Whole numbers only.';
  if (n < min || n > max) return `Must be between ${min} and ${max}.`;
  return null;
}

/** Warn before leaving with unsaved edits: browser reload/close, and in-app links (capture phase, before wouter's handler). */
function useUnsavedChangesGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const message = 'You have unsaved changes to the discovery configuration. Leave without saving?';
    const onBeforeUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = message; return message; };
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const anchor = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null;
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
      const url = new URL(anchor.href, window.location.href);
      if (url.origin !== window.location.origin || url.pathname === window.location.pathname) return;
      if (!window.confirm(message)) { e.preventDefault(); e.stopPropagation(); }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    document.addEventListener('click', onClick, true);
    return () => { window.removeEventListener('beforeunload', onBeforeUnload); document.removeEventListener('click', onClick, true); };
  }, [dirty]);
}

// ---------------------------------------------------------------------------
// Small presentational pieces
// ---------------------------------------------------------------------------

function ConfigSection({ id, title, description, changed, children }: { id: SectionId; title: string; description: ReactNode; changed?: boolean; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-40">
      <Panel className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-foreground/10 pb-4">
          <div>
            <h2 className="font-display text-lg font-bold">{title}</h2>
            <p className="mt-1 max-w-3xl text-xs text-muted-foreground">{description}</p>
          </div>
          {changed && <Badge tone="warn">Unsaved changes</Badge>}
        </div>
        <div className="mt-5 grid min-w-0 grid-cols-1 gap-4">{children}</div>
      </Panel>
    </section>
  );
}

function RuleRow({ title, description, checked, onChange, disabled }: { title: string; description: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-foreground/10 bg-background/60 p-3">
      <div className="min-w-0">
        <p className="text-xs font-semibold">{title}</p>
        <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{description}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2 pt-0.5">
        <span className="font-mono-face text-[10px] uppercase text-muted-foreground">{checked ? 'On' : 'Off'}</span>
        <Switch checked={checked} onChange={onChange} disabled={disabled} label={title} />
      </div>
    </div>
  );
}

function NumberField({ label, hint, value, onChange, error, placeholder, disabled, min, max }: { label: string; hint: string; value: string; onChange: (v: string) => void; error: string | null; placeholder?: string; disabled?: boolean; min: number; max: number }) {
  return (
    <label className="block text-xs">
      <span className="font-semibold">{label}</span>
      <input type="number" inputMode="numeric" min={min} max={max} value={value} placeholder={placeholder} disabled={disabled} onChange={(e) => onChange(e.target.value)}
        className={cx(inputClass, 'mt-1', error && 'border-red-500/60 focus:border-red-500')} aria-invalid={Boolean(error)} />
      <span className={cx('mt-1 block text-[10px]', error ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground')}>{error ?? hint}</span>
    </label>
  );
}

function Advanced({ forceOpen, children }: { forceOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const shown = open || Boolean(forceOpen);
  return (
    <div className="rounded-xl border border-dashed border-foreground/15">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={shown} className="flex w-full items-center justify-between px-3 py-2.5 text-left text-xs font-semibold text-muted-foreground hover:text-foreground">
        <span>Advanced{forceOpen && !open ? ' — has changes or errors' : ''}</span>
        {shown ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {shown && <div className="grid min-w-0 grid-cols-1 gap-3 border-t border-dashed border-foreground/15 p-3">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function DiscoveryConfigPage() {
  const auto = useDiscoveryAutoStatus();
  const setAuto = useSetDiscoveryAuto();
  const categoriesQuery = useCategories();
  const qc = useQueryClient();

  const [draft, setDraft] = useState<Draft | null>(null);
  const [baseline, setBaseline] = useState<Draft | null>(null);
  // Sources & providers live in DiscoverySourcesManager; it reports its state through onChange.
  // Its first report after (re)loading from the server is the baseline for "changed?".
  const [sources, setSources] = useState<DiscoverySourcesState | null>(null);
  const [sourcesBaseline, setSourcesBaseline] = useState<DiscoverySourcesState | null>(null);
  const sourcesBaselineRef = useRef<DiscoverySourcesState | null>(null);
  const [sourcesKey, setSourcesKey] = useState(0);
  const appliedSignature = useRef<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [serverChanged, setServerChanged] = useState(false);
  // True from "Save" until the saved values have been re-read from the server.
  const [reloading, setReloading] = useState(false);
  const reloadingRef = useRef(false);

  const applyServer = useCallback((a: DiscoveryAutoStatus) => {
    const d = draftFromServer(a);
    setDraft(d);
    setBaseline(d);
    appliedSignature.current = JSON.stringify(d) + serverSourcesSignature(a);
    sourcesBaselineRef.current = null;
    setSources(null);
    setSourcesBaseline(null);
    setSourcesKey((k) => k + 1); // remount: the sources manager re-reads the saved values
    setServerChanged(false);
  }, []);

  const handleSourcesChange = useCallback((s: DiscoverySourcesState) => {
    setSources(s);
    if (!sourcesBaselineRef.current) {
      sourcesBaselineRef.current = s;
      setSourcesBaseline(s);
    }
  }, []);

  const allSectors = useMemo(() => {
    const fromApi = categoriesQuery.data?.map((c) => c.name) ?? [];
    const base = fromApi.length > 0 ? fromApi : FALLBACK_SECTORS;
    // Keep saved sectors that are no longer in the list visible, so they can be unticked.
    return Array.from(new Set([...base, ...(baseline?.categories ?? [])]));
  }, [categoriesQuery.data, baseline?.categories]);

  // ---- what changed, and the PATCH body for exactly those fields ----------
  const sourcesChanged = Boolean(sources && sourcesBaseline && sourcesSignature(sources) !== sourcesSignature(sourcesBaseline));
  const { payload, changedSections } = useMemo(() => {
    const p: DiscoveryAutoUpdate = {};
    const changed = new Set<SectionId>();
    if (!draft || !baseline) return { payload: p, changedSections: changed };
    if (!sameSet(draft.countries, baseline.countries) || !sameSet(draft.states, baseline.states) || !sameSet(draft.cities, baseline.cities)) {
      changed.add('geography');
      Object.assign(p, {
        country: draft.countries.length ? draft.countries[0] : null,
        countries: draft.countries,
        locations: buildDiscoveryLocations(draft.countries, draft.states, draft.cities),
        regionCities: buildRegionCities(draft.countries, draft.states, draft.cities),
        states: draft.states,
        cities: draft.cities,
      });
    }
    if (!sameSet(draft.categories, baseline.categories)) {
      changed.add('sectors');
      // As before: saving with no sector ticked stores every sector.
      p.categories = draft.categories.length ? draft.categories : allSectors;
    }
    const out = p as Record<string, unknown>;
    for (const k of BOOL_KEYS) if (draft[k] !== baseline[k]) { out[k] = draft[k]; changed.add(SECTION_OF[k]); }
    for (const k of NUM_KEYS) {
      const v = draft[k].trim();
      if (v !== baseline[k].trim() && v !== '') { out[k] = Number(v); changed.add(SECTION_OF[k]); }
      else if (v !== baseline[k].trim()) changed.add(SECTION_OF[k]); // cleared: flagged as an error below
    }
    if (parseKeywords(draft.blacklistedKeywords).join('\u0000') !== parseKeywords(baseline.blacklistedKeywords).join('\u0000')) {
      p.blacklistedKeywords = parseKeywords(draft.blacklistedKeywords); changed.add('rules');
    }
    if (parseDomains(draft.excludedDomains).join('\u0000') !== parseDomains(baseline.excludedDomains).join('\u0000')) {
      p.excludedDomains = parseDomains(draft.excludedDomains); changed.add('rules');
    }
    if (sources && sourcesChanged) {
      changed.add('sources');
      // Same keys DiscoverySourcesManager's own save sends.
      p.listingUrls = sources.listingUrls;
      p.ticketmasterEnabled = sources.ticketmasterEnabled;
      p.sources = sources.sources.length ? sources.sources : ['web'];
      if (sources.ticketmasterApiKey) p.ticketmasterApiKey = sources.ticketmasterApiKey;
      if (sources.searchProviders === null) p.resetSearchProviders = true;
      else p.searchProviders = sources.searchProviders;
    }
    return { payload: p, changedSections: changed };
  }, [draft, baseline, sources, sourcesChanged, allSectors]);

  const errors = useMemo(() => {
    const e: Partial<Record<NumKey, string>> = {};
    if (!draft || !baseline) return e;
    for (const k of NUM_KEYS) { const msg = numberError(k, draft[k], baseline[k]); if (msg) e[k] = msg; }
    return e;
  }, [draft, baseline]);
  const errorCount = Object.keys(errors).length;
  const dirty = changedSections.size > 0;
  const saving = setAuto.isPending || reloading;

  useUnsavedChangesGuard(dirty);

  // First load, and later server-side changes (another tab, the run wizard saving sources…):
  // reload silently when nothing is being edited, otherwise say so instead of overwriting edits.
  useEffect(() => {
    if (!auto.data || reloadingRef.current) return; // a save in progress applies the reloaded values itself
    const signature = JSON.stringify(draftFromServer(auto.data)) + serverSourcesSignature(auto.data);
    if (appliedSignature.current === null) { applyServer(auto.data); return; }
    if (signature === appliedSignature.current) return;
    if (!dirty && !saving) applyServer(auto.data);
    else setServerChanged(true);
  }, [auto.data]); // eslint-disable-line react-hooks/exhaustive-deps

  // Deep links such as /admin/discover/configuration#sources.
  const scrolledToHash = useRef(false);
  useEffect(() => {
    if (!draft || scrolledToHash.current) return;
    scrolledToHash.current = true;
    const id = window.location.hash.replace('#', '');
    if (id) requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }));
  }, [draft]);

  const update = <K extends keyof Draft>(key: K, value: Draft[K]) => { setDraft((d) => (d ? { ...d, [key]: value } : d)); setSavedAt(null); };

  const save = () => {
    if (!dirty || errorCount > 0 || saving) return;
    setSavedAt(null);
    reloadingRef.current = true;
    setReloading(true);
    setAuto.mutate(payload, {
      onSuccess: async (data) => {
        try {
          // Reload from the server rather than trusting the form: what is shown is what is stored.
          const fresh = await auto.refetch();
          applyServer(fresh.data ?? data);
          qc.invalidateQueries({ queryKey: runScopedKeys.catalog });
          setSavedAt(new Date());
        } finally {
          reloadingRef.current = false;
          setReloading(false);
        }
      },
      onError: () => { reloadingRef.current = false; setReloading(false); },
    });
  };

  const discard = () => {
    if (!auto.data) return;
    if (dirty && !window.confirm('Discard all unsaved changes and reload the saved configuration?')) return;
    setAuto.reset();
    setSavedAt(null);
    applyServer(auto.data);
  };

  const goTo = (id: SectionId) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const header = (
    <>
      <Breadcrumbs items={[{ label: 'Discover events', href: '/admin/discover' }, { label: 'Discovery configuration' }]} />
      <PageHeader
        kicker="Discover events"
        title="Discovery configuration"
        subtitle="The saved settings Automatic discovery uses on every scheduled run: where to look, which sectors, which sources, and which events to keep."
        actions={
          <>
            {auto.data && (
              <Link href="/admin/discover/automatic" className="inline-flex items-center gap-2 rounded-full border border-foreground/15 bg-background px-3 py-1.5 text-[11px] font-semibold hover:border-accent hover:text-accent">
                <span className={cx('h-2 w-2 rounded-full', auto.data.enabled ? 'bg-emerald-500' : 'bg-muted-foreground/50')} />
                Automatic discovery {auto.data.enabled ? 'on' : 'off'} →
              </Link>
            )}
          </>
        }
      />
    </>
  );

  if (auto.isLoading || (auto.data && !draft)) return <div>{header}<div className="mt-8"><LoadingState label="Loading the saved discovery configuration" /></div></div>;
  if (auto.isError || !auto.data || !draft || !baseline) {
    return <div>{header}<div className="mt-8"><ErrorState error={auto.error} title="Could not load the saved discovery configuration." retry={() => auto.refetch()} /></div></div>;
  }

  const disabled = saving;
  const interval = auto.data.intervalMinutes;
  const advancedRulesForced = Boolean(errors.minTitleLength || errors.minDescriptionLength || errors.minConfidenceScore
    || draft.minTitleLength !== baseline.minTitleLength || draft.minDescriptionLength !== baseline.minDescriptionLength || draft.minConfidenceScore !== baseline.minConfidenceScore
    || draft.blacklistedKeywords !== baseline.blacklistedKeywords || draft.excludedDomains !== baseline.excludedDomains
    || draft.rejectMissingLocation !== baseline.rejectMissingLocation || draft.rejectMissingTicketUrl !== baseline.rejectMissingTicketUrl);
  const advancedLimitsForced = Boolean(errors.searchDepth || errors.dailyLimit || draft.searchDepth !== baseline.searchDepth || draft.dailyLimit !== baseline.dailyLimit);

  return (
    <div>
      {header}

      <div className="mt-6">
        <Notice tone="info">
          Automatic discovery reads this configuration at the start of every scheduled run, so a saved change applies from the next run.
          A run you start yourself from <Link href="/admin/discover" className="font-semibold underline">Run discovery</Link> uses the choices made in that wizard;
          both go through the same discovery pipeline and the same validation and rejection rules engine.
        </Notice>
      </div>

      {serverChanged && (
        <div className="mt-3">
          <Notice tone="warn">
            The saved configuration was changed somewhere else while you were editing. <strong>Discard changes</strong> to load it, or <strong>Save</strong> to write your changed fields over it.
          </Notice>
        </div>
      )}

      {/* Section navigation */}
      {/* top-[84px]: just below the 72px sticky site header */}
      <div className="sticky top-[84px] z-20 mt-6 overflow-x-auto rounded-2xl border border-foreground/10 bg-card/95 px-2 py-2 backdrop-blur">
        <div className="flex gap-1.5">
          {SECTIONS.map((s) => (
            <button key={s.id} type="button" onClick={() => goTo(s.id)}
              className={cx('inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold transition-colors hover:bg-muted', changedSections.has(s.id) ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground hover:text-foreground')}>
              {changedSections.has(s.id) && <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-label="changed" />}
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 grid min-w-0 grid-cols-1 gap-6">
        {/* 1. Geography */}
        <ConfigSection id="geography" title="Geography" changed={changedSections.has('geography')}
          description="Countries, states and cities automatic runs search. Ticking a whole state covers all of its cities.">
          <GeoChecklistSelector
            selectedCountries={draft.countries}
            onCountriesChange={(v) => update('countries', v)}
            selectedStates={draft.states}
            onStatesChange={(v) => update('states', v)}
            selectedCities={draft.cities}
            onCitiesChange={(v) => update('cities', v)}
            disabled={disabled}
          />
          {draft.countries.length === 0 && draft.states.length === 0 && draft.cities.length === 0 && (
            <Notice tone="warn">No place is selected. With nothing saved here, automatic runs fall back to the default target places set on the server.</Notice>
          )}
        </ConfigSection>

        {/* 2. Sectors */}
        <ConfigSection id="sectors" title="Sectors" changed={changedSections.has('sectors')}
          description="Which 100 TIMES sectors an event must belong to. Events outside them never count toward a run's target.">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold">Target sectors <span className="font-normal text-muted-foreground">({draft.categories.length} of {allSectors.length} selected)</span></span>
              <div className="flex gap-2 text-[11px]">
                <button type="button" disabled={disabled} onClick={() => update('categories', [...allSectors])} className="text-accent hover:underline disabled:opacity-50">Select all</button>
                <span className="text-muted-foreground">·</span>
                <button type="button" disabled={disabled} onClick={() => update('categories', [])} className="text-muted-foreground hover:underline disabled:opacity-50">Clear</button>
              </div>
            </div>
            {categoriesQuery.isError && <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">Could not load the sector list from the platform — showing the standard list.</p>}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {allSectors.map((cat) => {
                const on = draft.categories.includes(cat);
                return (
                  <button key={cat} type="button" disabled={disabled} aria-pressed={on}
                    onClick={() => update('categories', on ? draft.categories.filter((c) => c !== cat) : [...draft.categories, cat])}
                    className={cx('inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors disabled:opacity-50',
                      on ? 'border-accent bg-accent/15 font-semibold text-accent' : 'border-foreground/15 bg-card text-muted-foreground hover:border-foreground/30')}>
                    {on && <Check size={11} />}{cat}
                  </button>
                );
              })}
            </div>
            {draft.categories.length === 0 && (
              <p className="mt-2 text-[11px] text-muted-foreground">No sector ticked. Saving this stores <strong>all {allSectors.length} sectors</strong>, the same as “Select all”.</p>
            )}
          </div>
          <RuleRow title="Keep events that fit no sector under “Other”" disabled={disabled}
            description="Applies only when no sector restricts the run: events matching none of the 100 TIMES sectors are kept under “Other” instead of being dropped."
            checked={draft.fallbackToOtherSector} onChange={(v) => update('fallbackToOtherSector', v)} />
          {(!draft.fallbackToOtherSector || draft.rejectUnmatchedCategory !== baseline.rejectUnmatchedCategory) && (
            <RuleRow title="Reject events whose sector can't be matched" disabled={disabled}
              description="Rejects an event outright when its industry doesn't match any 100 TIMES sector."
              checked={draft.rejectUnmatchedCategory} onChange={(v) => update('rejectUnmatchedCategory', v)} />
          )}
        </ConfigSection>

        {/* 3. Sources & providers */}
        <ConfigSection id="sources" title="Sources & providers" changed={changedSections.has('sources')}
          description="Web-search providers, directories, aggregators, listing websites and the Ticketmaster key. Statuses come from real runs and checks. Changes here are saved with the Save bar at the bottom; “Check ticked sources” only tests the sources and doesn't change the configuration.">
          <DiscoverySourcesManager key={sourcesKey} showSaveButton={false} onChange={handleSourcesChange} />
          <p className="text-[11px] text-muted-foreground">
            Whether a source may run at all is set in the <Link href="/admin/settings?tab=registry" className="text-accent hover:underline">source registry</Link> (Providers &amp; API keys).
          </p>
        </ConfigSection>

        {/* 4. Validation & rejection rules */}
        <ConfigSection id="rules" title="Validation & rejection rules" changed={changedSections.has('rules')}
          description="Events that break an enabled rule are rejected with the reason recorded. Rejected events can be reviewed and restored under All events → Rejected.">
          <RuleRow title="Reject past events" disabled={disabled} description="Rejects events whose date has already passed." checked={draft.rejectPastEvents} onChange={(v) => update('rejectPastEvents', v)} />
          <RuleRow title="Reject unclear dates" disabled={disabled} description="Rejects events whose date can't be read as a calendar date (for example “Coming soon” or “Late 2026”)." checked={draft.rejectUnparseableDates} onChange={(v) => update('rejectUnparseableDates', v)} />
          <Advanced forceOpen={advancedRulesForced}>
            <RuleRow title="Reject in-person events without a location" disabled={disabled} description="Rejects offline or hybrid events that have neither a venue nor a city." checked={draft.rejectMissingLocation} onChange={(v) => update('rejectMissingLocation', v)} />
            <RuleRow title="Require a ticket or registration link" disabled={disabled} description="Rejects events without a ticket, booking or registration URL." checked={draft.rejectMissingTicketUrl} onChange={(v) => update('rejectMissingTicketUrl', v)} />
            <div className="grid gap-3 sm:grid-cols-3">
              <NumberField label="Minimum title length" hint="Characters (0–50)" value={draft.minTitleLength} onChange={(v) => update('minTitleLength', v)} error={errors.minTitleLength ?? null} disabled={disabled} min={0} max={50} />
              <NumberField label="Minimum description length" hint="Characters (0–200)" value={draft.minDescriptionLength} onChange={(v) => update('minDescriptionLength', v)} error={errors.minDescriptionLength ?? null} disabled={disabled} min={0} max={200} />
              <NumberField label="Minimum confidence score" hint="0–100; lower-scoring extractions are rejected" value={draft.minConfidenceScore} onChange={(v) => update('minConfidenceScore', v)} error={errors.minConfidenceScore ?? null} disabled={disabled} min={0} max={100} />
            </div>
            <label className="block text-xs">
              <span className="font-semibold">Blocked keywords</span>
              <textarea rows={2} value={draft.blacklistedKeywords} disabled={disabled} onChange={(e) => update('blacklistedKeywords', e.target.value)} placeholder="e.g. airdrop, crypto giveaway, casino" className={cx(inputClass, 'mt-1')} />
              <span className="mt-1 block text-[10px] text-muted-foreground">Comma-separated. An event with any of these in its title or description is rejected.</span>
            </label>
            <label className="block text-xs">
              <span className="font-semibold">Excluded websites</span>
              <textarea rows={2} value={draft.excludedDomains} disabled={disabled} onChange={(e) => update('excludedDomains', e.target.value)} placeholder="e.g. spam-listings.com, bit.ly" className={cx(inputClass, 'mt-1')} />
              <span className="mt-1 block text-[10px] text-muted-foreground">Comma-separated domains (https:// and paths are stripped on save). Never used as a source or ticket link.</span>
            </label>
          </Advanced>
        </ConfigSection>

        {/* 5. Organizer research */}
        <ConfigSection id="organizer" title="Organizer research" changed={changedSections.has('organizer')}
          description="What the run must find about an event's organizer before the event is accepted.">
          <RuleRow title="Reject events with no organizer" disabled={disabled} description="Rejects pages where no organizer or company could be identified." checked={draft.rejectNoOrganizer} onChange={(v) => update('rejectNoOrganizer', v)} />
          <RuleRow title="Require a public organizer e-mail" disabled={disabled} description="Rejects events when no valid organizer e-mail is found on public pages. Without one, an event can't be used for outreach." checked={draft.requireOrganizerEmail} onChange={(v) => update('requireOrganizerEmail', v)} />
          <RuleRow title="Require an organizer phone number" disabled={disabled} description="Rejects events when no official organizer phone number is found." checked={draft.requireOrganizerPhone} onChange={(v) => update('requireOrganizerPhone', v)} />
          <RuleRow title="Require an organizer website" disabled={disabled} description="Rejects events when the organizer has no official website." checked={draft.requireOrganizerWebsite} onChange={(v) => update('requireOrganizerWebsite', v)} />
          <RuleRow title="Keep rejected events for review" disabled={disabled}
            description="Also saves events turned down for being outside your sectors or having no organizer e-mail (other rejections are always saved), so they can be reviewed and restored under All events → Rejected. They never count toward a run's target."
            checked={draft.keepRejectedEvents} onChange={(v) => update('keepRejectedEvents', v)} />
        </ConfigSection>

        {/* 6. Execution limits */}
        <ConfigSection id="limits" title="Execution limits" changed={changedSections.has('limits')}
          description="How much one automatic run does, and how often runs happen.">
          <div className="grid gap-3 sm:grid-cols-2">
            <NumberField label="Events to examine per run" hint="Most candidate events one run looks at (1–500)" value={draft.eventsPerRun} onChange={(v) => update('eventsPerRun', v)} error={errors.eventsPerRun ?? null} disabled={disabled} min={1} max={500} />
            <NumberField label="Verified events to find" hint="The run stops once this many are verified (1–500)" value={draft.targetValidEvents} onChange={(v) => update('targetValidEvents', v)} error={errors.targetValidEvents ?? null} disabled={disabled} min={1} max={500} />
          </div>
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-foreground/10 bg-background/60 p-3 text-xs">
            <Clock size={14} className="text-accent" />
            <span><span className="font-semibold">Run interval:</span> {typeof interval === 'number' ? `every ${interval} minutes` : '—'}</span>
            <span className="text-[11px] text-muted-foreground">Set on the server (DISCOVERY_SCAN_INTERVAL_MINUTES); it can't be changed from the admin console.</span>
          </div>
          <Advanced forceOpen={advancedLimitsForced}>
            <div className="grid gap-3 sm:grid-cols-2">
              <NumberField label="Search queries per run" hint={baseline.searchDepth ? 'Search depth (1–200)' : 'Not saved — the server default is used. Enter a number to set it (1–200).'} placeholder="Server default" value={draft.searchDepth} onChange={(v) => update('searchDepth', v)} error={errors.searchDepth ?? null} disabled={disabled} min={1} max={200} />
              <NumberField label="New events per day" hint={baseline.dailyLimit ? 'Daily cap across all runs (1–2000)' : 'Not saved — the server default is used. Enter a number to set it (1–2000).'} placeholder="Server default" value={draft.dailyLimit} onChange={(v) => update('dailyLimit', v)} error={errors.dailyLimit ?? null} disabled={disabled} min={1} max={2000} />
            </div>
          </Advanced>
        </ConfigSection>
      </div>

      {/* Save bar */}
      <div className="sticky bottom-4 z-20 mt-8">
        <Panel className={cx('flex flex-wrap items-center justify-between gap-3 p-4 shadow-xl', dirty && 'border-amber-500/40')}>
          <div className="min-w-0 text-xs" role="status" aria-live="polite">
            {saving ? (
              <span className="font-semibold">Saving…</span>
            ) : setAuto.isError ? (
              <span className="text-red-700 dark:text-red-300"><strong>Not saved.</strong> {setAuto.error instanceof Error ? setAuto.error.message : 'The server rejected the change.'} Your edits are still here.</span>
            ) : dirty ? (
              <span><strong>Unsaved changes</strong> in {SECTIONS.filter((s) => changedSections.has(s.id)).map((s) => s.label).join(', ')}.{errorCount > 0 && <span className="ml-1 text-red-700 dark:text-red-300">Fix {errorCount} field{errorCount === 1 ? '' : 's'} before saving.</span>}</span>
            ) : savedAt ? (
              <span className="text-emerald-700 dark:text-emerald-300"><strong>Saved.</strong> Reloaded from the server at {fmtTime(savedAt.toISOString())} — this is what the next automatic run uses.</span>
            ) : (
              <span className="text-muted-foreground">No unsaved changes. Showing the configuration stored on the server.</span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Btn variant="ghost" onClick={discard} disabled={!dirty || saving}><Undo2 size={13} /> Discard changes</Btn>
            <Btn variant="primary" onClick={save} loading={saving} disabled={!dirty || errorCount > 0}><Save size={13} /> Save configuration</Btn>
          </div>
        </Panel>
      </div>
    </div>
  );
}
