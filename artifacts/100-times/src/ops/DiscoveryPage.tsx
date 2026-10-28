import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useSearch } from 'wouter';
import { Compass, Download, FileText, RotateCcw, Square, X } from 'lucide-react';
import { runsByEventId, useActiveDiscoveryRun, useDiscoveryRunEvents, useDiscoveryRuns, useStopDiscoveryRun } from './api';
import { ALL_WORLD_COUNTRIES, getReferenceStatesForCountry, getReferenceCitiesForState, getReferenceCitiesForCountry } from '@/lib/countries';
import { type DiscoveredEvent, messagesForEvent, organizerById, PLATFORM_CATEGORIES, useCategories, useDiscoveredEvents, useDiscoveredOrganizers, useDiscoveryStats, useDownloadDiscoveredEvents, useOutreachMessages } from './api';
import { AdminTable, Badge, Btn, Chips, ConfidenceBar, ErrorState, EmptyState, LoadingState, NA, Notice, PageHeader, Pager, SearchBox, SelectFilter, StatCard, cell, cellMuted, fmtDate, fmtDateTime, useDebounce, usePagination, verificationTone } from './ui';
import { EventDrawer, rejectionReason, sourceTypeLabel } from './EventDrawer';
import { RunScopeHeaderBadges } from './RunScopeDisplay';

const ALL = '__all__';
const uniq = (vals: Array<string | null | undefined>) => Array.from(new Set(vals.filter((v): v is string => Boolean(v)))).sort();
const VERIFICATION_VALUES = ['VERIFIED', 'NEEDS_REVIEW', 'UNVERIFIED', 'REJECTED'] as const;
const FORMAT_VALUES = ['online', 'offline', 'hybrid', 'unspecified'] as const;
const linkButton = 'button-press inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1 text-[11px] font-bold transition-colors';

export function DiscoveryPage({ mode }: { mode: 'new' | 'events' }) {
  const events = useDiscoveredEvents();
  const organizers = useDiscoveredOrganizers();
  const messages = useOutreachMessages();
  const discoveryStats = useDiscoveryStats();
  const download = useDownloadDiscoveredEvents();
  const activeRun = useActiveDiscoveryRun();
  const stopRun = useStopDiscoveryRun();
  const [, setLocation] = useLocation();
  const search = useSearch();
  const basePath = mode === 'new' ? '/admin/discovery' : '/admin/discovery/events';
  const params = useMemo(() => new URLSearchParams(search), [search]);
  const selectedId = Number(params.get('event')) || null;
  const runParam = params.get('run');
  const runId = runParam ? Number(runParam) || null : null;
  const discoveryRuns = useDiscoveryRuns();
  const runEvents = useDiscoveryRunEvents(runId, Boolean(runId && activeRun.data?.active && activeRun.data.run?.id === runId));
  const targetRun = useMemo(() => {
    if (!runId || !discoveryRuns.data) return null;
    return discoveryRuns.data.find((r) => r.id === runId) ?? null;
  }, [runId, discoveryRuns.data]);
  // Which run(s) stored each event, from the runs' own summary.event_ids (latest 100 runs).
  const runIndex = useMemo(() => runsByEventId(discoveryRuns.data), [discoveryRuns.data]);

  /** Change some query params and keep the rest (status tab, format, run filter, open event). */
  const navigate = (changes: Record<string, string | null>, replace = false) => {
    const p = new URLSearchParams(search);
    for (const [k, v] of Object.entries(changes)) { if (v === null) p.delete(k); else p.set(k, v); }
    const qs = p.toString();
    setLocation(`${basePath}${qs ? `?${qs}` : ''}`, { replace });
  };
  const fromUrl = <T extends string>(key: string, allowed: readonly T[]) => { const v = params.get(key); return v && (allowed as readonly string[]).includes(v) ? v : ALL; };

  // The status tab and format live in the URL (?verification=, ?format=), so dashboard links,
  // reloads and the back button all land on the same filtered list.
  const verification = fromUrl('verification', VERIFICATION_VALUES);
  const format = fromUrl('format', FORMAT_VALUES);
  const setVerification = (v: string) => navigate({ verification: v === ALL ? null : v }, true);
  const setFormat = (v: string) => navigate({ format: v === ALL ? null : v }, true);

  const [q, setQ] = useState(''); const term = useDebounce(q.trim().toLowerCase());
  const [country, setCountry] = useState(ALL); const [state, setState] = useState(ALL); const [city, setCity] = useState(ALL); const [category, setCategory] = useState(ALL);
  const [minConfidence, setMinConfidence] = useState('0');
  const [organizerFilter, setOrganizerFilter] = useState(ALL);
  const [discoveredFrom, setDiscoveredFrom] = useState(''); const [discoveredTo, setDiscoveredTo] = useState('');
  const [eventFrom, setEventFrom] = useState(''); const [eventTo, setEventTo] = useState('');

  const all = events.data ?? [];

  // Filter events by country first for cascading dropdowns and table rows
  const countryFilteredEvents = useMemo(() => {
    if (country === ALL) return all;
    const cLow = country.toLowerCase();
    return all.filter((e) => {
      // Events with no recorded country never match a specific country filter.
      const itemCountry = (e.country || '').toLowerCase();
      const itemCity = (e.city || '').toLowerCase();
      if (cLow === 'dubai') {
        return itemCountry === 'dubai' || itemCountry === 'united arab emirates' || itemCity.includes('dubai');
      }
      if (cLow === 'united arab emirates' || cLow === 'uae') {
        return itemCountry === 'united arab emirates' || itemCountry === 'dubai' || itemCity.includes('dubai');
      }
      return itemCountry === cLow;
    });
  }, [all, country]);

  // Hierarchical States: Only states that belong to the selected country
  const stateOptions = useMemo(() => {
    const fromEvents = countryFilteredEvents.map((e) => e.state).filter((s): s is string => Boolean(s));
    const fromRef = country !== ALL ? getReferenceStatesForCountry(country) : [];
    const combined = uniq([...fromRef, ...fromEvents]).sort();
    return [{ value: ALL, label: 'All' }, ...combined.map((v) => ({ value: v, label: v }))];
  }, [countryFilteredEvents, country]);

  // Hierarchical Cities: Only cities that belong to the selected state and country
  const cityOptions = useMemo(() => {
    const list = state !== ALL ? countryFilteredEvents.filter((e) => e.state === state) : countryFilteredEvents;
    const fromEvents = list.map((e) => e.city).filter((c): c is string => Boolean(c));
    const fromRef = country !== ALL
      ? (state !== ALL ? getReferenceCitiesForState(country, state) : getReferenceCitiesForCountry(country))
      : [];
    const combined = uniq([...fromRef, ...fromEvents]).sort();
    return [{ value: ALL, label: 'All' }, ...combined.map((v) => ({ value: v, label: v }))];
  }, [countryFilteredEvents, country, state]);

  const handleCountryChange = (nextCountry: string) => {
    setCountry(nextCountry);
    setState(ALL);
    setCity(ALL);
  };

  const handleStateChange = (nextState: string) => {
    setState(nextState);
    setCity(ALL);
  };

  // Every filter except the status tab — the tabs' counts are computed from this list.
  const baseRows = useMemo(() => {
    let list: DiscoveredEvent[] = [];
    if (runId && runEvents.data && runEvents.data.length > 0) {
      list = [...runEvents.data];
    } else if (runId && targetRun) {
      const eventIds = Array.isArray(targetRun.summary?.event_ids) ? (targetRun.summary.event_ids as number[]) : [];
      if (eventIds.length > 0) {
        const idSet = new Set(eventIds);
        list = all.filter((e) => idSet.has(e.id));
      } else if (targetRun.startedAt) {
        const s = new Date(targetRun.startedAt).getTime() - 60000;
        const c = (targetRun.completedAt ? new Date(targetRun.completedAt).getTime() : Date.now()) + 60000;
        list = all.filter((e) => {
          if (!e.discoveredAt) return false;
          const t = new Date(e.discoveredAt).getTime();
          return t >= s && t <= c;
        });
      }
    } else if (!runId) {
      list = country !== ALL ? [...countryFilteredEvents] : [...all];
    }
    // A run's "View new events" shows only what that run added — its new
    // events (the run table's "New" column) — not the rejected rows it kept for review.
    if (runId) list = list.filter((e) => e.verificationStatus !== 'REJECTED');

    list.sort((a, b) => (b.discoveredAt ?? '').localeCompare(a.discoveredAt ?? ''));

    if (mode === 'new') list = list.filter((e) => e.verificationStatus !== 'REJECTED');
    if (runId && country !== ALL) { const ids = new Set(countryFilteredEvents.map((e) => e.id)); list = list.filter((e) => ids.has(e.id)); }
    if (state !== ALL) list = list.filter((e) => e.state === state);
    if (city !== ALL) list = list.filter((e) => e.city === city);
    if (category !== ALL) list = list.filter((e) => e.category === category);
    if (organizerFilter !== ALL) list = list.filter((e) => (organizerFilter === 'found' ? e.organizerStatus === 'FOUND' : e.organizerStatus !== 'FOUND'));
    if (format !== ALL) list = list.filter((e) => (format === 'unspecified' ? !e.eventFormat : e.eventFormat === format));
    const minC = Number(minConfidence) || 0; if (minC > 0) list = list.filter((e) => e.confidenceScore >= minC);
    if (discoveredFrom) list = list.filter((e) => (e.discoveredAt ?? '') >= discoveredFrom);
    if (discoveredTo) list = list.filter((e) => (e.discoveredAt ?? '').slice(0, 10) <= discoveredTo);
    if (eventFrom) list = list.filter((e) => e.eventDate && e.eventDate >= eventFrom);
    if (eventTo) list = list.filter((e) => e.eventDate && e.eventDate <= eventTo);
    if (term) list = list.filter((e) => [e.name, e.city, e.state, e.category, e.subcategory, e.venue, organizerById(organizers.data, e.organizerId)?.name, organizerById(organizers.data, e.organizerId)?.email].some((v) => v?.toLowerCase().includes(term)));
    return list;
  }, [all, countryFilteredEvents, country, mode, state, city, category, organizerFilter, format, minConfidence, discoveredFrom, discoveredTo, eventFrom, eventTo, term, organizers.data, runId, runEvents.data, targetRun]);

  const statusCounts = useMemo(() => {
    const c: Record<string, number> = { VERIFIED: 0, NEEDS_REVIEW: 0, UNVERIFIED: 0, REJECTED: 0 };
    for (const e of baseRows) c[e.verificationStatus] = (c[e.verificationStatus] ?? 0) + 1;
    return c;
  }, [baseRows]);
  const rows = useMemo(() => (verification === ALL ? baseRows : baseRows.filter((e) => e.verificationStatus === verification)), [baseRows, verification]);

  const categoriesQuery = useCategories();
  const categoryOptions = useMemo(() => {
    const fromApi = categoriesQuery.data?.map((c) => c.name) ?? [];
    const base = fromApi.length > 0 ? fromApi : Array.from(PLATFORM_CATEGORIES);
    return uniq([...base, ...all.map((e) => e.category)]);
  }, [categoriesQuery.data, all]);

  const countryOptions = useMemo(() => {
    const discoveredCountries = new Set(all.map((e) => e.country).filter((c): c is string => Boolean(c)));
    if (all.some((e) => (e.city || '').toLowerCase().includes('dubai') || (e.country || '').toLowerCase().includes('dubai'))) {
      discoveredCountries.add('Dubai');
    }
    const allList = Array.from(new Set([...ALL_WORLD_COUNTRIES, ...discoveredCountries])).sort();
    return [{ value: ALL, label: 'All' }, ...allList.map((c) => ({ value: c, label: discoveredCountries.has(c) ? `${c} •` : c }))];
  }, [all]);

  const pager = usePagination(rows, mode === 'new' ? 20 : 25);
  const { setPage } = pager;
  // A different filter or tab starts again at page 1; opening/closing an event (?event=) keeps the page.
  useEffect(() => { setPage(1); }, [setPage, verification, format, term, country, state, city, category, organizerFilter, minConfidence, discoveredFrom, discoveredTo, eventFrom, eventTo, runId]);

  const selected = selectedId ? all.find((e) => e.id === selectedId) ?? null : null;
  const openEvent = (e: DiscoveredEvent) => navigate({ event: String(e.id) });
  const closeEvent = () => navigate({ event: null });
  useEffect(() => { if (selectedId && events.isSuccess && !selected) navigate({ event: null }, true); }, [selectedId, events.isSuccess, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  if (events.isLoading || organizers.isLoading) return <LoadingState label="Loading discovered events" />;
  if (events.isError) return <ErrorState error={events.error} retry={() => events.refetch()} />;

  const org = organizers.data ?? [];
  // Real DB totals, not derived from the capped `all`/`org` lists above
  // (those are for the browsing table), so these keep growing correctly past that cap.
  const ds = discoveryStats.data;

  const resetFilters = () => {
    setQ('');
    setCountry(ALL);
    setState(ALL);
    setCity(ALL);
    setCategory(ALL);
    setMinConfidence('0');
    setOrganizerFilter(ALL);
    setDiscoveredFrom('');
    setDiscoveredTo('');
    setEventFrom('');
    setEventTo('');
    navigate({ verification: null, format: null, run: null }, true);
  };
  const dateInput = 'rounded-lg border border-foreground/15 bg-background px-2 py-1.5 text-xs text-foreground outline-none focus:border-accent';

  const statusTabs: Array<{ key: string; label: string; count?: number }> = [
    { key: ALL, label: 'All', count: baseRows.length },
    { key: 'VERIFIED', label: 'Verified', count: statusCounts.VERIFIED },
    { key: 'NEEDS_REVIEW', label: 'Needs review', count: statusCounts.NEEDS_REVIEW },
    { key: 'REJECTED', label: 'Rejected', count: statusCounts.REJECTED },
    // Older rows can still be UNVERIFIED; keep them reachable without a fifth tab when there are none.
    ...(statusCounts.UNVERIFIED > 0 || verification === 'UNVERIFIED' ? [{ key: 'UNVERIFIED', label: 'Unverified', count: statusCounts.UNVERIFIED }] : []),
  ];
  const listCapped = Boolean(ds && ds.eventsTotal > all.length);

  return (
    <div>
      <PageHeader
        kicker="Event management"
        title={mode === 'new' ? 'New discoveries' : 'All events'}
        subtitle={mode === 'new'
          ? 'The latest events found by discovery runs, newest first. Rejected events are left out here — find them under All events → Rejected.'
          : `Every event discovery has found — ${ds?.eventsTotal ?? '—'} so far — with the organizer, source, run and verification data behind each one.`}
        actions={mode === 'new' ? (
          <Link href="/admin/discover" className={`${linkButton} bg-accent px-4 py-2 text-xs text-accent-foreground hover:bg-primary hover:text-primary-foreground`}><Compass size={13} /> Run discovery</Link>
        ) : (
          <div className="flex flex-col items-end gap-1">
            <Btn variant="primary" loading={download.isPending} disabled={!!eventFrom && !!eventTo && eventFrom > eventTo} onClick={() => download.mutate({ from: eventFrom, to: eventTo })}>
              <Download size={13} /> Download Excel
            </Btn>
            <span className="text-[10px] text-muted-foreground">{eventFrom || eventTo ? `Event date ${eventFrom ? fmtDate(eventFrom) : '…'} – ${eventTo ? fmtDate(eventTo) : '…'}` : 'All events · set an event date range below to narrow it'}</span>
            {download.isError && <span className="text-[10px] text-red-600 dark:text-red-400">Download failed — {download.error instanceof Error ? download.error.message : 'try again'}</span>}
          </div>
        )}
      />

      {activeRun.data?.active && activeRun.data.run && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent/40 bg-accent/10 px-4 py-3 shadow-sm">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent"></span>
            </span>
            <span className="text-xs font-semibold text-foreground">Discovery run #{activeRun.data.run.id} is running:</span>
            <span className="text-xs text-muted-foreground">
              <strong>{activeRun.data.run.summary?.verified_events ?? '—'} verified</strong> · {activeRun.data.run.summary?.events_needing_review ?? '—'} held for review · {activeRun.data.run.summary?.events_discovered ?? '—'} candidates explored
            </span>
            <Link href={`/admin/discover/runs/${activeRun.data.run.id}`} className="text-xs font-semibold text-accent underline">Progress & report</Link>
            {runId !== activeRun.data.run.id && <Link href={`/admin/discovery/events?run=${activeRun.data.run.id}`} className="text-xs font-semibold text-accent underline">Watch its events live</Link>}
          </div>
          <div className="flex items-center gap-2">
            {stopRun.isError && <span className="text-[11px] text-red-600 dark:text-red-300">Couldn't stop: {stopRun.error instanceof Error ? stopRun.error.message : 'unknown error'}</span>}
            <Btn variant="danger" size="sm" loading={stopRun.isPending} onClick={() => stopRun.mutate(activeRun.data.run!.id)}>
              <Square size={11} className="fill-current" /> Stop run
            </Btn>
          </div>
        </div>
      )}

      {runId && (
        <div className="mt-4 flex flex-col gap-2 rounded-xl border border-accent/40 bg-accent/10 px-4 py-3 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2.5">
              <Badge tone="accent">Run #{runId}</Badge>
              <span className="text-xs font-semibold text-foreground">
                Showing the {baseRows.length} new event{baseRows.length === 1 ? '' : 's'} found by run #{runId}
              </span>
              {targetRun && (
                <span className="text-xs text-muted-foreground">
                  ({fmtDateTime(targetRun.startedAt)} · status: {targetRun.status})
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Link href={`/admin/discover/runs/${runId}`} className={`${linkButton} border border-foreground/15 bg-background hover:border-accent hover:text-accent`}><FileText size={12} /> Run #{runId} report</Link>
              <Link href="/admin/discover/runs" className={`${linkButton} text-muted-foreground hover:bg-muted hover:text-foreground`}>All runs</Link>
              <Btn variant="secondary" size="sm" onClick={() => navigate({ run: null }, true)}>
                <X size={12} /> Clear run filter
              </Btn>
            </div>
          </div>
          {targetRun && (
            <div className="pt-2 border-t border-accent/20 flex items-center gap-2">
              <span className="text-[10px] uppercase font-mono text-muted-foreground font-semibold">Scope:</span>
              <RunScopeHeaderBadges run={targetRun} />
            </div>
          )}
          {runEvents.isError && <p className="text-[11px] text-red-600 dark:text-red-300">Could not load this run's event list from the server; showing what the loaded events say instead.</p>}
        </div>
      )}

      {mode === 'new' && (
        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-5">
          <StatCard label="New events" value={ds?.newEventsTotal ?? '—'} sub={`${ds?.eventsTotal ?? '—'} discovered in total`} href="/admin/discovery/events" />
          <StatCard label="Organizers found" value={ds?.organizersTotal ?? '—'} href="/admin/discovery/organizers" />
          <StatCard label="Contacts found" value={ds?.contactsTotal ?? '—'} sub={`${ds?.organizersWithEmailTotal ?? '—'} organizers with email`} href="/admin/discovery/contacts" />
          <StatCard label="Needs review" value={ds?.needsReviewTotal ?? '—'} tone={ds?.needsReviewTotal ? 'warn' : 'good'} href="/admin/discovery/events?verification=NEEDS_REVIEW" />
          <StatCard label="Rejected" value={ds?.rejectedTotal ?? '—'} sub="Open to restore or approve" href="/admin/discovery/events?verification=REJECTED" />
        </div>
      )}

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl font-bold">{mode === 'new' ? 'Recently discovered' : `${rows.length} event${rows.length === 1 ? '' : 's'}`}</h2>
        {mode === 'new' ? <Link href="/admin/discovery/events" className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">All events with filters →</Link> : <SearchBox value={q} onChange={setQ} placeholder="Search event, organizer, city, sector…" />}
      </div>

      {mode === 'events' && (
        <>
          <div className="mt-3" aria-label="Verification status">
            <Chips<string> value={verification} onChange={setVerification} options={statusTabs} />
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-foreground/10 bg-card px-4 py-3">
            <SelectFilter label="Country" value={country} onChange={handleCountryChange} options={countryOptions} />
            <SelectFilter label="State" value={state} onChange={handleStateChange} options={stateOptions} />
            <SelectFilter label="City" value={city} onChange={setCity} options={cityOptions} />
            <SelectFilter label="Sector" value={category} onChange={setCategory} options={[{ value: ALL, label: 'All' }, ...categoryOptions.map((v) => ({ value: v, label: v }))]} />
            <SelectFilter label="Organizer" value={organizerFilter} onChange={setOrganizerFilter} options={[{ value: ALL, label: 'All' }, { value: 'found', label: 'Found' }, { value: 'missing', label: 'Not found' }]} />
            <SelectFilter label="Format" value={format} onChange={setFormat} options={[{ value: ALL, label: 'All' }, { value: 'online', label: 'Online' }, { value: 'offline', label: 'Offline' }, { value: 'hybrid', label: 'Hybrid' }, { value: 'unspecified', label: 'Not specified' }]} />
            <SelectFilter label="Min confidence" value={minConfidence} onChange={setMinConfidence} options={['0', '50', '60', '70', '80', '90'].map((v) => ({ value: v, label: v === '0' ? 'Any' : `${v}+` }))} />
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground"><span className="font-mono-face uppercase tracking-wider">Discovered</span><input type="date" aria-label="Discovered from" value={discoveredFrom} onChange={(e) => setDiscoveredFrom(e.target.value)} className={dateInput} /><span>–</span><input type="date" aria-label="Discovered to" value={discoveredTo} onChange={(e) => setDiscoveredTo(e.target.value)} className={dateInput} /></div>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground"><span className="font-mono-face uppercase tracking-wider">Event date</span><input type="date" aria-label="Event date from" value={eventFrom} onChange={(e) => setEventFrom(e.target.value)} className={dateInput} /><span>–</span><input type="date" aria-label="Event date to" value={eventTo} onChange={(e) => setEventTo(e.target.value)} className={dateInput} /></div>
            <Btn variant="ghost" size="sm" onClick={resetFilters}><RotateCcw size={11} /> Reset</Btn>
          </div>
          {listCapped && (
            <div className="mt-3"><Notice tone="info">The list and tab counts cover the {all.length} events loaded here; {ds?.eventsTotal} exist in total. Use the Excel download for everything.</Notice></div>
          )}
        </>
      )}

      <div className="mt-4">
        {rows.length === 0 ? (
          <>
            <EmptyState
              title={all.length === 0 ? 'No events discovered yet.' : runId && (runEvents.isLoading || discoveryRuns.isLoading) ? 'Loading this run’s events…' : 'No events match these filters.'}
              body={all.length === 0 ? 'Start a run from Run discovery, or switch on Automatic discovery.' : undefined}
            />
            {all.length === 0 && (
              <div className="mt-3 flex justify-center gap-2">
                <Link href="/admin/discover" className={`${linkButton} bg-accent px-4 py-2 text-xs text-accent-foreground hover:bg-primary hover:text-primary-foreground`}>Run discovery</Link>
                <Link href="/admin/discover/automatic" className={`${linkButton} border border-foreground/15 bg-background px-4 py-2 text-xs hover:border-accent hover:text-accent`}>Automatic discovery</Link>
              </div>
            )}
          </>
        ) : (
          <>
            <AdminTable columns={['Event', 'Organizer', 'Sector', 'Date', 'Country', 'City', 'State', 'Format & venue', 'Organizer email', 'Organizer phone', 'Source', 'Status', 'Discovered', 'Found by', '']} minWidth={1700}>
              {pager.slice.map((e) => {
                const o = organizerById(org, e.organizerId);
                const venueRelevant = e.eventFormat === 'offline' || e.eventFormat === 'hybrid';
                const foundBy = runIndex.get(e.id)?.[0];
                return (
                  <tr key={e.id} className="cursor-pointer hover:bg-muted/20" onClick={() => openEvent(e)}>
                    <td className={cell}><span className="block max-w-[260px] truncate font-semibold" title={e.name ?? ''}>{e.name ?? NA}</span></td>
                    <td className={cell}>{o ? <Link href={`/admin/discovery/organizers/${o.id}`} onClick={(ev) => ev.stopPropagation()} className="block max-w-[200px] truncate text-accent hover:underline" title={o.name}>{o.name}</Link> : <span className="text-muted-foreground">{e.organizerStatus === 'NOT_FOUND' ? 'Not found' : NA}</span>}</td>
                    <td className={cellMuted}><span className="block max-w-[160px] truncate" title={e.category ?? ''}>{e.category ?? NA}</span></td>
                    <td className={cellMuted}><span className="block max-w-[140px] truncate">{e.date ?? NA}</span></td>
                    <td className={cellMuted}>{e.country ?? NA}</td>
                    <td className={cell}>{e.city ?? <span className="text-muted-foreground">{NA}</span>}</td>
                    <td className={cellMuted}>{e.state ?? NA}</td>
                    <td className={cell}>
                      {e.eventFormat ? <Badge tone={e.eventFormat === 'online' ? 'info' : e.eventFormat === 'hybrid' ? 'accent' : 'neutral'}>{e.eventFormat}</Badge> : <span className="text-muted-foreground">Not specified</span>}
                      {venueRelevant && (e.venue
                        ? <span className="mt-1 block max-w-[180px] truncate text-muted-foreground" title={e.venue}>{e.venue}</span>
                        : <span className="mt-1 block text-amber-600 dark:text-amber-400">No venue</span>)}
                    </td>
                    <td className={cell}>{o?.email ? <span className="block max-w-[200px] truncate">{o.email}</span> : <span className="text-muted-foreground">{NA}</span>}</td>
                    <td className={cellMuted}>{o?.phone ?? NA}</td>
                    <td className={cellMuted}><span className="block max-w-[160px] truncate" title={e.sourceUrl ?? ''}>{e.sourceWebsite ?? NA}</span>{e.sources[0] && <span className="block text-[10px]">{sourceTypeLabel(e.sources[0].sourceType)}</span>}</td>
                    <td className={cell}><Badge tone={verificationTone(e.verificationStatus)}>{e.verificationStatus.replace('_', ' ')}</Badge>{rejectionReason(e) && <span className="mt-1 block max-w-[160px] truncate text-[10px] text-muted-foreground" title={rejectionReason(e) ?? ''}>{rejectionReason(e)}</span>}<div className="mt-1.5"><ConfidenceBar value={e.confidenceScore} /></div></td>
                    <td className={cellMuted}>{fmtDate(e.discoveredAt)}</td>
                    <td className={cell}>{foundBy ? <Link href={`/admin/discover/runs/${foundBy}`} onClick={(ev) => ev.stopPropagation()} className="font-mono-face text-accent hover:underline" title={`Open run #${foundBy}'s report`}>#{foundBy}</Link> : <span className="text-muted-foreground" title="Not listed by any of the latest 100 runs">—</span>}</td>
                    <td className={cell}><Btn size="sm" onClick={(ev) => { ev.stopPropagation(); openEvent(e); }}>View details</Btn></td>
                  </tr>
                );
              })}
            </AdminTable>
            <Pager {...pager} />
          </>
        )}
      </div>

      <EventDrawer event={selected} organizer={organizerById(org, selected?.organizerId)} messages={selected ? messagesForEvent(messages.data, selected.id) : []} onClose={closeEvent} />
    </div>
  );
}
