import { useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Activity,
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
import {
  CatalogProvider,
  CatalogSource,
  CatalogCheckResult,
  RunSourceReport,
  runScopedKeys,
  useCheckDiscoveryCatalog,
  useDiscoveryAutoStatus,
  useDiscoveryCatalog,
  useDiscoveryRuns,
  useSetDiscoveryAuto,
  useTestTicketmaster,
} from './api';
import { Link } from 'wouter';
import { Badge, Btn, Notice, inputClass, parseDate } from './ui';

// Channel switches stored in `sources` (the backend's catalog.py uses the same tokens).
const WEB = 'web';
const DIRECTORIES = 'global_adapters';
const AGGREGATORS = 'consumer_aggregators';
const LEGACY_AGGREGATORS = 'event_platforms';

function timeAgo(iso: string | null | undefined): string {
  // parseDate reads the API's zone-less timestamps as UTC (new Date() would read them as local time).
  const at = parseDate(iso);
  if (!at) return '';
  const seconds = Math.max(0, (Date.now() - at.getTime()) / 1000);
  if (seconds < 90) return 'just now';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

function hostOf(rawUrl: string): string {
  try {
    return new URL(rawUrl.replace(/\{city\}|\{country\}/g, 'city')).hostname.replace(/^www\./, '');
  } catch {
    return 'custom';
  }
}

/** Real status of a source, from its last run or probe — never a fixed label. */
function SourceStatusBadge({ source, disabledByAdmin }: { source: CatalogSource; disabledByAdmin: boolean }) {
  if (disabledByAdmin) return <Badge tone="neutral">Disabled in registry</Badge>;
  const { status, checked_at } = source.health;
  const when = timeAgo(checked_at);
  switch (status) {
    case 'ok':
      return <Badge tone="good">Working{when ? ` · ${when}` : ''}</Badge>;
    case 'no_events':
      return <Badge tone="warn">Reads, no events{when ? ` · ${when}` : ''}</Badge>;
    case 'failed':
      return <Badge tone="danger">Failing{when ? ` · ${when}` : ''}</Badge>;
    case 'not_implemented':
      return <Badge tone="neutral">No client</Badge>;
    case 'not_configured':
      return <Badge tone="warn">Needs key</Badge>;
    default:
      return <Badge tone="neutral">Untested</Badge>;
  }
}

function providerState(p: CatalogProvider): { label: string; tone: 'good' | 'warn' | 'danger' | 'neutral'; title: string } {
  if (!p.configured) return { label: p.unavailable_reason?.startsWith('Unavailable') ? 'retired' : 'needs key', tone: 'neutral', title: p.unavailable_reason ?? '' };
  if (p.cooling_down_seconds > 0) return { label: 'paused', tone: 'danger', title: p.cooldown_reason ?? 'Failing — retried later' };
  if (p.last_call.status && p.last_call.status !== 'SUCCESS') return { label: 'failing', tone: 'danger', title: p.last_call.error ?? p.last_call.status };
  const role = p.tier === 'free' ? 'free · first' : p.tier === 'last_resort' ? 'last resort' : 'paid · top-up';
  const last = p.last_call.status ? `Last call ${timeAgo(p.last_call.at)}: ${p.last_call.results ?? 0} results` : 'Not called yet';
  return { label: role, tone: 'good', title: last };
}

export interface DiscoverySourcesState {
  listingUrls: string[];
  /** A NEW Ticketmaster key typed here; empty = keep the saved one (never sent back to the browser). */
  ticketmasterApiKey: string;
  ticketmasterEnabled: boolean;
  sources: string[];
  /** Web-search providers runs may call; null = every configured provider. */
  searchProviders: string[] | null;
}

export function DiscoverySourcesManager({
  onSaved,
  onChange,
  showSaveButton = true,
}: {
  onSaved?: () => void;
  onChange?: (state: DiscoverySourcesState) => void;
  /** Kept for callers; the layout no longer differs. */
  compact?: boolean;
  showSaveButton?: boolean;
}) {
  const auto = useDiscoveryAutoStatus();
  const catalog = useDiscoveryCatalog();
  const runs = useDiscoveryRuns();
  const setAuto = useSetDiscoveryAuto();
  const testTm = useTestTicketmaster();
  const check = useCheckDiscoveryCatalog();
  const qc = useQueryClient();

  const [listingUrls, setListingUrls] = useState<string[]>([]);
  const [newUrlInput, setNewUrlInput] = useState('');
  const [urlError, setUrlError] = useState<string | null>(null);
  const [ticketmasterEnabled, setTicketmasterEnabled] = useState(false);
  const [newTmKey, setNewTmKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [tmTestResult, setTmTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [providers, setProviders] = useState<string[] | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [checkResult, setCheckResult] = useState<CatalogCheckResult | null>(null);
  const [loaded, setLoaded] = useState(false);

  const sourcesById = useMemo(() => new Map((catalog.data?.sources ?? []).map((s) => [s.id, s])), [catalog.data]);
  const idsOf = (channel: CatalogSource['channel']) => (catalog.data?.sources ?? []).filter((s) => s.channel === channel).map((s) => s.id);
  const aggregatorHosts = useMemo(
    () => new Set((catalog.data?.sources ?? []).filter((s) => s.channel === 'aggregators').map((s) => hostOf(s.url).split('.').slice(-2).join('.'))),
    [catalog.data],
  );

  // Load the saved selection ONCE (needs the catalog to expand a bare channel
  // switch into the sources it runs, so what is ticked == what runs).
  const loadedFromServer = useRef(false);
  useEffect(() => {
    if (loadedFromServer.current || !auto.data || !catalog.data) return;
    loadedFromServer.current = true;
    const cat = catalog.data;
    let sel = auto.data.sources && auto.data.sources.length > 0 ? [...auto.data.sources] : [...cat.default_sources];
    if (sel.includes(LEGACY_AGGREGATORS) && !sel.includes(AGGREGATORS)) sel.push(AGGREGATORS);
    for (const [token, channel] of [[DIRECTORIES, 'directories'], [AGGREGATORS, 'aggregators']] as const) {
      const ids = cat.sources.filter((s) => s.channel === channel).map((s) => s.id);
      if (sel.includes(token) && !ids.some((id) => sel.includes(id))) {
        sel = [...sel, ...cat.sources.filter((s) => s.channel === channel && s.default_selected).map((s) => s.id)];
      }
    }
    setSelected(Array.from(new Set(sel.filter((id) => id !== LEGACY_AGGREGATORS))));
    setProviders(auto.data.searchProviders ?? null);
    setListingUrls(auto.data.listingUrls && auto.data.listingUrls.length > 0 ? auto.data.listingUrls : cat.default_listing_urls);
    setTicketmasterEnabled(Boolean(auto.data.ticketmasterEnabled));
    setLoaded(true);
  }, [auto.data, catalog.data]);

  useEffect(() => {
    if (onChange && loaded) {
      onChange({ listingUrls, ticketmasterApiKey: newTmKey.trim(), ticketmasterEnabled, sources: selected, searchProviders: providers });
    }
  }, [listingUrls, newTmKey, ticketmasterEnabled, selected, providers, onChange, loaded]);

  const webOn = selected.includes(WEB);
  const directoriesOn = selected.includes(DIRECTORIES);
  const aggregatorsOn = selected.includes(AGGREGATORS);
  const allProviders = catalog.data?.providers ?? [];
  const providerOn = (id: string) => (providers === null ? Boolean(allProviders.find((p) => p.id === id)?.configured) : providers.includes(id));

  const toggleChannel = (token: string, channel: 'directories' | 'aggregators' | null) => {
    setSelected((prev) => {
      if (prev.includes(token)) return prev.filter((id) => id !== token);
      const next = [...prev, token];
      if (channel) {
        const ids = idsOf(channel);
        if (!ids.some((id) => prev.includes(id))) {
          next.push(...(catalog.data?.sources ?? []).filter((s) => s.channel === channel && s.default_selected).map((s) => s.id));
        }
      }
      return Array.from(new Set(next));
    });
  };

  const toggleSource = (src: CatalogSource) => {
    const token = src.channel === 'directories' ? DIRECTORIES : src.channel === 'aggregators' ? AGGREGATORS : null;
    setSelected((prev) => {
      if (prev.includes(src.id)) {
        const next = prev.filter((id) => id !== src.id);
        // Nothing left ticked in the channel: switch it off, so "none ticked" really runs none.
        if (token && !idsOf(src.channel).some((id) => next.includes(id))) return next.filter((id) => id !== token);
        return next;
      }
      return Array.from(new Set([...prev, src.id, ...(token ? [token] : [])]));
    });
  };

  const toggleProvider = (id: string) => {
    setProviders((prev) => {
      const current = prev ?? allProviders.filter((p) => p.configured).map((p) => p.id);
      return current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
    });
  };

  // --- Counts from the catalog (setup) and the latest run (execution) -------
  const customSites = listingUrls.filter((u) => !aggregatorHosts.has(hostOf(u).split('.').slice(-2).join('.')));
  const counts = useMemo(() => {
    const rows: { configured: boolean; available: boolean }[] = [];
    if (webOn) {
      for (const p of allProviders) {
        if (providerOn(p.id)) rows.push({ configured: p.configured, available: p.configured && p.cooling_down_seconds === 0 });
      }
    }
    for (const id of selected) {
      const s = sourcesById.get(id);
      if (!s || (s.channel === 'directories' && !directoriesOn) || (s.channel === 'aggregators' && !aggregatorsOn) || s.channel === 'apis') continue;
      const configured = s.implemented && s.configured;
      rows.push({ configured, available: configured && s.enabled_by_admin && s.health.status !== 'failed' });
    }
    if (ticketmasterEnabled) {
      const tm = sourcesById.get('ticketmaster_api');
      rows.push({ configured: Boolean(auto.data?.ticketmasterApiKeySet || newTmKey), available: Boolean(auto.data?.ticketmasterApiKeySet || newTmKey) && tm?.health.status !== 'failed' });
    }
    customSites.forEach(() => rows.push({ configured: true, available: true }));
    return { selected: rows.length, configured: rows.filter((r) => r.configured).length, available: rows.filter((r) => r.available).length };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, providers, webOn, directoriesOn, aggregatorsOn, ticketmasterEnabled, catalog.data, auto.data, newTmKey, listingUrls]);

  const lastRun = (runs.data ?? []).find((r) => r.summary?.sources?.counts);
  const lastReport = lastRun?.summary?.sources as RunSourceReport | undefined;

  const handleCheck = (withProviders: boolean) => {
    setCheckResult(null);
    const sourceIds = selected.filter((id) => sourcesById.has(id));
    const providerIds = withProviders ? allProviders.filter((p) => p.configured && providerOn(p.id)).map((p) => p.id) : [];
    check.mutate({ sourceIds, providerIds }, { onSuccess: (data) => setCheckResult(data) });
  };

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

  const handleTestTicketmaster = () => {
    setTmTestResult(null);
    testTm.mutate(newTmKey.trim() ? { apiKey: newTmKey.trim() } : undefined, {
      onSuccess: (data) => setTmTestResult(data),
      onError: (err) => setTmTestResult({ success: false, message: err instanceof Error ? err.message : 'Connection test failed' }),
    });
  };

  const handleSaveAll = () => {
    setSaveSuccess(false);
    setAuto.mutate(
      {
        listingUrls,
        ticketmasterEnabled,
        sources: selected,
        ...(newTmKey.trim() ? { ticketmasterApiKey: newTmKey.trim() } : {}),
        ...(providers === null ? { resetSearchProviders: true } : { searchProviders: providers }),
      },
      {
        onSuccess: () => {
          setNewTmKey('');
          // A saved/removed Ticketmaster key changes that source's catalog status ("Needs key").
          qc.invalidateQueries({ queryKey: runScopedKeys.catalog });
          setSaveSuccess(true);
          setTimeout(() => setSaveSuccess(false), 4000);
          if (onSaved) onSaved();
        },
      },
    );
  };

  // An error with no data at all is shown as an error (before, it read "Loading…" forever);
  // a failed background refresh keeps showing the last good catalog.
  if (!catalog.data) {
    if (catalog.isError) return <Notice tone="danger">Could not load the discovery source registry: {(catalog.error as Error)?.message}</Notice>;
    return <p className="text-xs text-muted-foreground">Loading discovery sources…</p>;
  }
  if (!loaded) {
    if (auto.isError) return <Notice tone="danger">Could not load the saved discovery settings: {(auto.error as Error)?.message}</Notice>;
    return <p className="text-xs text-muted-foreground">Loading discovery sources…</p>;
  }

  const cat = catalog.data;
  const groups: { key: string; title: string; channel: CatalogSource['channel']; sources: CatalogSource[] }[] = [];
  for (const s of cat.sources) {
    const title = s.channel === 'aggregators' ? 'Consumer Aggregators' : s.channel === 'apis' ? 'Event Platform APIs' : s.category;
    let group = groups.find((g) => g.title === title);
    if (!group) groups.push((group = { key: `${s.channel}:${title}`, title, channel: s.channel, sources: [] }));
    group.sources.push(s);
  }
  const channelOn = (channel: CatalogSource['channel']) => (channel === 'directories' ? directoriesOn : channel === 'aggregators' ? aggregatorsOn : true);
  const readyIn = (channel: 'directories' | 'aggregators') =>
    cat.sources.filter((s) => s.channel === channel && selected.includes(s.id) && s.health.status === 'ok').length;
  const pickedIn = (channel: 'directories' | 'aggregators') => cat.sources.filter((s) => s.channel === channel && selected.includes(s.id)).length;

  return (
    <div className="space-y-6">
      {/* 1. STRATEGY TOGGLES */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h4 className="font-display text-sm font-bold text-foreground flex items-center gap-2">
              <Sparkles size={16} className="text-accent" /> Discovery Strategy & Core Toggles
            </h4>
            <p className="mt-0.5 text-xs text-muted-foreground">
              What runs is exactly what is ticked here. Status comes from real runs and checks, not labels.
            </p>
          </div>
          <div className="text-right text-[11px] font-mono" title="Selected = ticked in enabled channels · Configured = settings/credentials present · Available = configured and not currently failing">
            <span className="rounded bg-accent/10 px-2 py-0.5 font-semibold text-accent">
              {counts.selected} selected · {counts.configured} configured · {counts.available} available
            </span>
            {lastReport && lastRun && (
              <p className="mt-1 text-muted-foreground" title="From the most recent run's execution record">
                <Link href={`/admin/discover/runs/${lastRun.id}`} className="text-accent hover:underline">Last run #{lastRun.id}</Link> ({timeAgo(lastRun.completedAt ?? lastRun.startedAt)}): {lastReport.counts.executed} executed ·{' '}
                {lastReport.counts.successful} ok · {lastReport.counts.returned_candidates} candidates · {lastReport.counts.failed} failed ·{' '}
                {lastReport.counts.skipped} skipped
              </p>
            )}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          {/* A. General Web Search */}
          <div className={`p-3.5 rounded-xl border transition-all ${webOn ? 'border-accent bg-accent/5 ring-1 ring-accent/30' : 'border-foreground/10 bg-card/40 opacity-80'}`}>
            <label className="flex items-start justify-between gap-2 cursor-pointer">
              <span className="flex items-center gap-2">
                <span className="p-1.5 rounded-lg bg-accent/10 text-accent"><Search size={15} /></span>
                <span className="text-xs font-bold text-foreground">General Web Search</span>
              </span>
              <input type="checkbox" checked={webOn} onChange={() => toggleChannel(WEB, null)} className="h-4 w-4 mt-1 shrink-0 rounded border-foreground/20 text-accent focus:ring-accent" />
            </label>
            <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">
              Free providers first, then paid ones one at a time while results are short (max {cat.paid_search_budget_per_run} paid calls per run).
            </p>
            <div className="mt-2 flex flex-wrap gap-1">
              {allProviders.map((p) => {
                const on = providerOn(p.id);
                const st = providerState(p);
                return (
                  <button
                    key={p.id}
                    type="button"
                    title={`${p.full_name}\n${st.title}${p.setup_env.length ? `\nNeeds: ${p.setup_env.join(', ')}` : ''}`}
                    onClick={() => toggleProvider(p.id)}
                    className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-semibold border transition-colors ${
                      !on
                        ? 'border-foreground/10 text-muted-foreground line-through opacity-60'
                        : st.tone === 'good'
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                          : st.tone === 'danger'
                            ? 'border-red-500/30 bg-red-500/10 text-red-600'
                            : 'border-foreground/15 bg-muted text-muted-foreground'
                    }`}
                  >
                    {on ? '✓ ' : ''}
                    {p.name} · {st.label}
                  </button>
                );
              })}
            </div>
            {cat.web_options.map((opt) => (
              <label key={opt.id} className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer" title={opt.description}>
                <input
                  type="checkbox"
                  checked={selected.includes(opt.id)}
                  onChange={() => setSelected((prev) => (prev.includes(opt.id) ? prev.filter((x) => x !== opt.id) : [...prev, opt.id]))}
                  className="h-3.5 w-3.5 rounded border-foreground/20 text-accent"
                />
                {opt.name}
              </label>
            ))}
          </div>

          {/* B / C. Directories & Aggregators */}
          {(
            [
              { token: DIRECTORIES, channel: 'directories', title: 'Global Directories & Adapters', icon: Globe },
              { token: AGGREGATORS, channel: 'aggregators', title: 'Consumer Aggregators', icon: Ticket },
            ] as const
          ).map(({ token, channel, title, icon: Icon }) => {
            const on = selected.includes(token);
            const info = cat.channels.find((c) => c.id === channel);
            return (
              <div key={token} className={`p-3.5 rounded-xl border transition-all ${on ? 'border-accent bg-accent/5 ring-1 ring-accent/30' : 'border-foreground/10 bg-card/40 opacity-80'}`}>
                <label className="flex items-start justify-between gap-2 cursor-pointer">
                  <span className="flex items-center gap-2">
                    <span className="p-1.5 rounded-lg bg-accent/10 text-accent"><Icon size={15} /></span>
                    <span className="text-xs font-bold text-foreground">{title}</span>
                  </span>
                  <input type="checkbox" checked={on} onChange={() => toggleChannel(token, channel)} className="h-4 w-4 mt-1 shrink-0 rounded border-foreground/20 text-accent focus:ring-accent" />
                </label>
                <p className="mt-2 text-[11px] text-muted-foreground leading-relaxed">{info?.description}</p>
                <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                  {pickedIn(channel)} ticked · {readyIn(channel)} working in their last run/check
                </p>
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg border border-foreground/10 bg-muted/20">
          <span className="text-[11px] font-semibold text-muted-foreground">Quick selection:</span>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setSelected(Array.from(new Set([...cat.default_sources.filter((id) => sourcesById.get(id)?.channel !== 'aggregators' && id !== AGGREGATORS)])))}
              className="px-2.5 py-1 rounded text-[11px] font-semibold bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
            >
              B2B only (no consumer aggregators)
            </button>
            <button
              type="button"
              onClick={() => setSelected([WEB, DIRECTORIES, AGGREGATORS, ...cat.sources.filter((s) => s.health.status === 'ok').map((s) => s.id)])}
              className="px-2.5 py-1 rounded text-[11px] font-semibold border border-foreground/15 hover:bg-muted text-foreground transition-colors"
              title="Only sources whose last run or check returned events"
            >
              Working sources only
            </button>
            <button
              type="button"
              onClick={() => {
                setSelected(cat.default_sources);
                setProviders(null);
                setListingUrls(cat.default_listing_urls);
              }}
              className="px-2.5 py-1 rounded text-[11px] font-semibold text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              <RefreshCw size={11} /> Reset to defaults
            </button>
            <Btn type="button" size="sm" variant="secondary" loading={check.isPending} onClick={() => handleCheck(false)} title="Reads every ticked source's events page now (free)">
              <Activity size={12} className="mr-1" /> Check ticked sources
            </Btn>
            <Btn
              type="button"
              size="sm"
              variant="ghost"
              loading={check.isPending}
              onClick={() => handleCheck(true)}
              title="Also runs one real search per ticked provider — paid providers bill for it (Exa ≈ $0.007, Google 1 grounded request)"
            >
              + test providers
            </Btn>
          </div>
        </div>

        {check.isError && <Notice tone="danger">Check failed: {(check.error as Error)?.message}</Notice>}
        {checkResult && (
          <Notice tone={checkResult.sources.some((s) => !s.ok) ? 'warn' : 'good'}>
            Checked {checkResult.sources.length} sources: {checkResult.sources.filter((s) => s.ok && s.events > 0).length} returned events,{' '}
            {checkResult.sources.filter((s) => s.ok && s.events === 0).length} read but listed none, {checkResult.sources.filter((s) => !s.ok).length} failed.
            {checkResult.providers.length > 0 && (
              <> Providers: {checkResult.providers.map((p) => `${p.id} ${p.status === 'ok' ? `ok (${p.results})` : `${p.status}${p.error ? `: ${p.error.slice(0, 80)}` : ''}`}`).join(' · ')}.</>
            )}
          </Notice>
        )}
      </div>

      {/* 2. EVERY SOURCE, WITH ITS REAL STATUS */}
      <div className="space-y-3">
        <div>
          <h4 className="font-display text-sm font-bold text-foreground flex items-center gap-2">
            <Layers size={16} className="text-accent" /> Sources ({cat.sources.filter((s) => s.implemented).length} with a working client, {cat.sources.length} catalogued)
          </h4>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Ticking a source turns its channel on; unticking the last one turns the channel off. Hover a status for its last error.
          </p>
        </div>

        <div className="space-y-2">
          {groups.map((group) => {
            const ids = group.sources.filter((s) => s.implemented && s.enabled_by_admin).map((s) => s.id);
            const active = ids.filter((id) => selected.includes(id)).length;
            const working = group.sources.filter((s) => s.health.status === 'ok').length;
            const isExpanded = Boolean(expanded[group.key]);
            const on = channelOn(group.channel);
            return (
              <div key={group.key} className="rounded-xl border border-foreground/10 bg-card/60 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setExpanded((prev) => ({ ...prev, [group.key]: !prev[group.key] }))}
                  className="flex w-full items-center justify-between gap-3 p-3 sm:px-4 bg-card hover:bg-muted/30 transition-colors text-left"
                >
                  <span className="min-w-0">
                    <span className="font-display text-xs font-bold text-foreground">{group.title}</span>{' '}
                    <span className="px-1.5 rounded text-[10px] font-mono font-semibold bg-accent/15 text-accent">
                      {group.channel === 'apis' ? `${group.sources.length} listed` : `${active} / ${ids.length} ticked`}
                    </span>{' '}
                    <span className="text-[10px] text-muted-foreground">{working} working</span>
                    {!on && <span className="ml-1 text-[10px] text-amber-600">· channel off — none of these run</span>}
                  </span>
                  {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>

                {isExpanded && (
                  <div className="p-3 sm:p-4 border-t border-foreground/10 bg-background/50 grid gap-2 sm:grid-cols-2">
                    {group.sources.map((src) => {
                      const selectable = src.implemented && src.enabled_by_admin && src.channel !== 'apis';
                      const ticked = selected.includes(src.id);
                      return (
                        <div
                          key={src.id}
                          className={`flex items-start justify-between gap-2 p-2.5 rounded-lg border text-xs transition-all ${
                            ticked && on && selectable ? 'border-accent/40 bg-accent/5' : 'border-foreground/10 bg-card/40'
                          } ${selectable ? '' : 'opacity-70'}`}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-semibold text-foreground truncate">{src.name}</span>
                              <span title={src.health.detail ?? undefined}>
                                <SourceStatusBadge source={src} disabledByAdmin={!src.enabled_by_admin} />
                              </span>
                            </div>
                            <a
                              href={src.events_page && !src.events_page.includes('{') ? src.events_page : src.url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-0.5 inline-flex items-center gap-0.5 text-[10px] text-muted-foreground hover:text-foreground truncate max-w-full"
                            >
                              {src.events_page ?? src.url} <ExternalLink size={9} />
                            </a>
                            {src.health.status === 'failed' && src.health.detail && (
                              <p className="mt-0.5 text-[10px] text-red-600 line-clamp-2">{src.health.detail}</p>
                            )}
                            {src.health.status === 'not_implemented' && src.health.detail && (
                              <p className="mt-0.5 text-[10px] text-muted-foreground line-clamp-2">{src.health.detail}</p>
                            )}
                          </div>
                          {src.channel !== 'apis' && (
                            <input
                              type="checkbox"
                              checked={ticked}
                              disabled={!selectable}
                              onChange={() => toggleSource(src)}
                              title={selectable ? undefined : 'Cannot run: see its status'}
                              className="h-4 w-4 mt-0.5 shrink-0 rounded border-foreground/20 text-accent focus:ring-accent disabled:opacity-40"
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. TICKETMASTER */}
      <div className="rounded-xl border border-accent/40 bg-accent/5 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-accent/20 p-2 text-accent mt-0.5"><Ticket size={20} /></div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="font-display text-sm font-bold text-foreground">Ticketmaster Discovery API v2</h4>
                {auto.data?.ticketmasterApiKeySet ? (
                  <Badge tone="good">Key saved {auto.data.ticketmasterApiKeyHint ?? ''}</Badge>
                ) : (
                  <Badge tone="warn">No key</Badge>
                )}
                {sourcesById.get('ticketmaster_api') && <SourceStatusBadge source={sourcesById.get('ticketmaster_api')!} disabledByAdmin={false} />}
              </div>
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed max-w-xl">
                Free key from{' '}
                <a href="https://developer.ticketmaster.com" target="_blank" rel="noreferrer" className="font-medium text-accent hover:underline inline-flex items-center gap-0.5">
                  developer.ticketmaster.com <ExternalLink size={10} />
                </a>
                . The key is stored on the server and never shown again. Ticketmaster hides organiser emails.
              </p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer shrink-0">
            <span>Enable Ticketmaster</span>
            <input type="checkbox" checked={ticketmasterEnabled} onChange={(e) => setTicketmasterEnabled(e.target.checked)} className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent" />
          </label>
        </div>
        <div className="mt-4 pt-4 border-t border-accent/20 grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-foreground mb-1">{auto.data?.ticketmasterApiKeySet ? 'Replace API key' : 'API key'}</label>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                placeholder={auto.data?.ticketmasterApiKeySet ? 'Leave empty to keep the saved key' : 'Enter Ticketmaster API key'}
                value={newTmKey}
                autoComplete="off"
                onChange={(e) => {
                  setNewTmKey(e.target.value);
                  setTmTestResult(null);
                }}
                className={`${inputClass} pr-10`}
              />
              <button type="button" onClick={() => setShowApiKey(!showApiKey)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
          <div className="flex items-end">
            <Btn type="button" variant="secondary" size="md" loading={testTm.isPending} onClick={handleTestTicketmaster} className="w-full h-9 text-xs">
              <KeyRound size={13} className="mr-1" /> Test {newTmKey.trim() ? 'new' : 'saved'} key
            </Btn>
          </div>
        </div>
        {tmTestResult && (
          <div className="mt-3">
            <Notice tone={tmTestResult.success ? 'info' : 'danger'}>
              <span className="flex items-center gap-1.5 text-xs font-semibold">
                {tmTestResult.success ? <CheckCircle2 size={13} className="text-green-500 shrink-0" /> : <XCircle size={13} className="text-red-500 shrink-0" />}
                {tmTestResult.message}
              </span>
            </Notice>
          </div>
        )}
      </div>

      {/* 4. WEBSITES */}
      <div className="rounded-xl border border-foreground/10 bg-card p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <div>
            <h4 className="font-display text-sm font-bold text-foreground flex items-center gap-2">
              <Globe size={15} className="text-accent" /> Website Listing Pages ({listingUrls.length})
            </h4>
            <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">
              Aggregator pages here run when that aggregator is ticked; any other site you add always runs. Supports{' '}
              <code className="text-accent font-mono-face text-[11px]">{'{city}'}</code> and <code className="text-accent font-mono-face text-[11px]">{'{country}'}</code>.
            </p>
          </div>
          <button type="button" onClick={() => setListingUrls(cat.default_listing_urls)} className="text-[11px] text-muted-foreground hover:text-accent flex items-center gap-1 font-medium">
            <RefreshCw size={11} /> Reset URL templates
          </button>
        </div>
        <div className="divide-y divide-foreground/10 border border-foreground/10 rounded-lg overflow-hidden bg-background/50 max-h-56 overflow-y-auto">
          {listingUrls.map((url, idx) => (
            <div key={url} className="flex items-center justify-between gap-3 px-3 py-2 text-xs hover:bg-muted/30 transition-colors">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span className="px-1.5 py-0.5 text-[10px] font-mono-face uppercase rounded bg-muted text-muted-foreground shrink-0">{hostOf(url)}</span>
                <span className="font-mono-face text-[11px] truncate text-foreground/90">{url}</span>
                {customSites.includes(url) && <Badge tone="info">always runs</Badge>}
              </div>
              <button type="button" onClick={() => setListingUrls((prev) => prev.filter((_, i) => i !== idx))} className="p-1 text-muted-foreground hover:text-red-500 transition-colors shrink-0" title="Remove">
                <Trash2 size={13} />
              </button>
            </div>
          ))}
          {listingUrls.length === 0 && <div className="p-4 text-center text-xs text-muted-foreground">No website templates configured.</div>}
        </div>
        <form onSubmit={handleAddWebsite} className="mt-4 pt-3 border-t border-foreground/10 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              placeholder="e.g. https://insider.in/all-events-in-{city}"
              value={newUrlInput}
              onChange={(e) => {
                setNewUrlInput(e.target.value);
                setUrlError(null);
              }}
              className={`${inputClass} flex-1 min-w-[220px] font-mono-face text-xs`}
            />
            <Btn type="submit" variant="secondary" size="md" className="h-9 text-xs">
              <Plus size={13} className="mr-1" /> Add Website
            </Btn>
          </div>
          {urlError && <span className="font-mono-face text-xs text-red-500 block pt-1">{urlError}</span>}
        </form>
      </div>

      {showSaveButton && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <Btn type="button" variant="primary" size="md" loading={setAuto.isPending} onClick={handleSaveAll}>
            <CheckCircle2 size={15} className="mr-1.5" /> Save Discovery Sources & Websites
          </Btn>
          {saveSuccess && (
            <span className="font-mono-face text-xs text-green-500 flex items-center gap-1 font-semibold">
              <CheckCircle2 size={13} /> Saved
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
