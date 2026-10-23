import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useSearch } from 'wouter';
import { Download, RotateCcw } from 'lucide-react';
import { ALL_WORLD_COUNTRIES, getReferenceStatesForCountry, getReferenceCitiesForState, getReferenceCitiesForCountry } from '@/lib/countries';
import { type DiscoveredEvent, messagesForEvent, organizerById, PLATFORM_CATEGORIES, useCategories, useDiscoveredEvents, useDiscoveredOrganizers, useDiscoveryStats, useDownloadDiscoveredEvents, useOutreachMessages } from './api';
import { AdminTable, Badge, Btn, ConfidenceBar, ErrorState, EmptyState, LoadingState, NA, PageHeader, Pager, SearchBox, SelectFilter, StatCard, cell, cellMuted, fmtDate, useDebounce, usePagination, verificationTone } from './ui';
import { EventDrawer, sourceTypeLabel } from './EventDrawer';
import { ManualResearchButton } from './ManualResearch';

const ALL = '__all__';
const uniq = (vals: Array<string | null | undefined>) => Array.from(new Set(vals.filter((v): v is string => Boolean(v)))).sort();

export function DiscoveryPage({ mode }: { mode: 'new' | 'events' }) {
  const events = useDiscoveredEvents();
  const organizers = useDiscoveredOrganizers();
  const messages = useOutreachMessages();
  const discoveryStats = useDiscoveryStats();
  const download = useDownloadDiscoveredEvents();
  const [, setLocation] = useLocation();
  const search = useSearch();
  const selectedId = Number(new URLSearchParams(search).get('event')) || null;

  const [q, setQ] = useState(''); const term = useDebounce(q.trim().toLowerCase());
  // Dashboard stat cards deep-link here with ?verification=… / ?format=… so the list opens already filtered.
  const initial = new URLSearchParams(search);
  const fromUrl = (key: string, allowed: string[]) => { const v = initial.get(key); return v && allowed.includes(v) ? v : ALL; };
  const [country, setCountry] = useState(ALL); const [state, setState] = useState(ALL); const [city, setCity] = useState(ALL); const [category, setCategory] = useState(ALL);
  const [verification, setVerification] = useState(() => fromUrl('verification', ['VERIFIED', 'NEEDS_REVIEW', 'UNVERIFIED', 'REJECTED'])); const [minConfidence, setMinConfidence] = useState('0');
  const [organizerFilter, setOrganizerFilter] = useState(ALL); const [format, setFormat] = useState(() => fromUrl('format', ['online', 'offline', 'hybrid', 'unspecified']));
  const [discoveredFrom, setDiscoveredFrom] = useState(''); const [discoveredTo, setDiscoveredTo] = useState('');
  const [eventFrom, setEventFrom] = useState(''); const [eventTo, setEventTo] = useState('');

  const all = events.data ?? [];

  // Filter events by country first for cascading dropdowns and table rows
  const countryFilteredEvents = useMemo(() => {
    if (country === ALL) return all;
    const cLow = country.toLowerCase();
    return all.filter((e) => {
      const itemCountry = (e.country || 'India').toLowerCase();
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

  const rows = useMemo(() => {
    let list = country !== ALL ? [...countryFilteredEvents] : [...all];
    list = list.filter((e) => e.organizerStatus === 'FOUND' && Boolean(e.organizerId));
    list.sort((a, b) => (b.discoveredAt ?? '').localeCompare(a.discoveredAt ?? ''));
    if (mode === 'new') return list.filter((e) => e.verificationStatus !== 'REJECTED');
    if (state !== ALL) list = list.filter((e) => e.state === state);
    if (city !== ALL) list = list.filter((e) => e.city === city);
    if (category !== ALL) list = list.filter((e) => e.category === category);
    if (verification === ALL) list = list.filter((e) => e.verificationStatus !== 'REJECTED');
    else list = list.filter((e) => e.verificationStatus === verification);
    if (organizerFilter !== ALL) list = list.filter((e) => (organizerFilter === 'found' ? e.organizerStatus === 'FOUND' : e.organizerStatus !== 'FOUND'));
    if (format !== ALL) list = list.filter((e) => (format === 'unspecified' ? !e.eventFormat : e.eventFormat === format));
    const minC = Number(minConfidence) || 0; if (minC > 0) list = list.filter((e) => e.confidenceScore >= minC);
    if (discoveredFrom) list = list.filter((e) => (e.discoveredAt ?? '') >= discoveredFrom);
    if (discoveredTo) list = list.filter((e) => (e.discoveredAt ?? '').slice(0, 10) <= discoveredTo);
    if (eventFrom) list = list.filter((e) => e.eventDate && e.eventDate >= eventFrom);
    if (eventTo) list = list.filter((e) => e.eventDate && e.eventDate <= eventTo);
    if (term) list = list.filter((e) => [e.name, e.city, e.state, e.category, e.subcategory, e.venue, organizerById(organizers.data, e.organizerId)?.name, organizerById(organizers.data, e.organizerId)?.email].some((v) => v?.toLowerCase().includes(term)));
    return list;
  }, [all, countryFilteredEvents, country, mode, state, city, category, verification, organizerFilter, format, minConfidence, discoveredFrom, discoveredTo, eventFrom, eventTo, term, organizers.data]);

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
  const selected = selectedId ? all.find((e) => e.id === selectedId) ?? null : null;
  const openEvent = (e: DiscoveredEvent) => setLocation(`${mode === 'new' ? '/admin/discovery' : '/admin/discovery/events'}?event=${e.id}`);
  const closeEvent = () => setLocation(mode === 'new' ? '/admin/discovery' : '/admin/discovery/events');
  useEffect(() => { if (selectedId && events.isSuccess && !selected) closeEvent(); }, [selectedId, events.isSuccess, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  if (events.isLoading || organizers.isLoading) return <LoadingState label="Loading discovered events" />;
  if (events.isError) return <ErrorState error={events.error} retry={() => events.refetch()} />;

  const org = organizers.data ?? [];
  // Real DB totals, not derived from the 200-row-capped `all`/`org` lists above
  // (those are for the browsing table), so these keep growing correctly past that cap.
  const ds = discoveryStats.data;

  const resetFilters = () => { setQ(''); setCountry(ALL); setState(ALL); setCity(ALL); setCategory(ALL); setVerification(ALL); setMinConfidence('0'); setOrganizerFilter(ALL); setFormat(ALL); setDiscoveredFrom(''); setDiscoveredTo(''); setEventFrom(''); setEventTo(''); };
  const dateInput = 'rounded-lg border border-foreground/15 bg-background px-2 py-1.5 text-xs text-foreground outline-none focus:border-accent';

  return (
    <div>
      <PageHeader
        kicker={mode === 'new' ? 'Organizer Discovery · Automation' : 'Organizer Discovery · Events found'}
        title={mode === 'new' ? 'Organizer Discovery' : 'Events Found'}
        subtitle={mode === 'new' ? 'Discover events across India and extract verified organizer information.' : `Every event the discovery automation has found — ${ds?.eventsTotal ?? all.length} so far — with the organizer, source and verification data behind each one.`}
        actions={mode === 'new' ? <ManualResearchButton /> : (
          <div className="flex flex-col items-end gap-1">
            <Btn variant="primary" loading={download.isPending} disabled={!!eventFrom && !!eventTo && eventFrom > eventTo} onClick={() => download.mutate({ from: eventFrom, to: eventTo })}>
              <Download size={13} /> Download Excel
            </Btn>
            <span className="text-[10px] text-muted-foreground">{eventFrom || eventTo ? `Event date ${eventFrom ? fmtDate(eventFrom) : '…'} – ${eventTo ? fmtDate(eventTo) : '…'}` : 'All events · set an event date range below to narrow it'}</span>
            {download.isError && <span className="text-[10px] text-red-600 dark:text-red-400">Download failed — {download.error instanceof Error ? download.error.message : 'try again'}</span>}
          </div>
        )}
      />

      {mode === 'new' && (
        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="New events" value={ds?.newEventsTotal ?? 0} sub={`${ds?.eventsTotal ?? 0} discovered in total`} href="/admin/discovery/events" />
          <StatCard label="Organizers found" value={ds?.organizersTotal ?? 0} href="/admin/discovery/organizers" />
          <StatCard label="Contacts found" value={ds?.contactsTotal ?? 0} sub={`${ds?.organizersWithEmailTotal ?? 0} organizers with email`} href="/admin/discovery/contacts" />
          <StatCard label="Needs review" value={ds?.needsReviewTotal ?? 0} tone={ds?.needsReviewTotal ? 'warn' : 'good'} href="/admin/discovery/events?verification=NEEDS_REVIEW" />
        </div>
      )}

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl font-bold">{mode === 'new' ? 'Recently discovered' : `${rows.length} event${rows.length === 1 ? '' : 's'}`}</h2>
        {mode === 'new' ? <Link href="/admin/discovery/events" className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">All events with filters →</Link> : <SearchBox value={q} onChange={setQ} placeholder="Search event, organizer, city, sector…" />}
      </div>

      {mode === 'events' && (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-foreground/10 bg-card px-4 py-3">
          <SelectFilter label="Country" value={country} onChange={handleCountryChange} options={countryOptions} />
          <SelectFilter label="State" value={state} onChange={handleStateChange} options={stateOptions} />
          <SelectFilter label="City" value={city} onChange={setCity} options={cityOptions} />
          <SelectFilter label="Sector" value={category} onChange={setCategory} options={[{ value: ALL, label: 'All' }, ...categoryOptions.map((v) => ({ value: v, label: v }))]} />
          <SelectFilter label="Verification" value={verification} onChange={setVerification} options={[{ value: ALL, label: 'All' }, { value: 'VERIFIED', label: 'Verified' }, { value: 'NEEDS_REVIEW', label: 'Needs review' }, { value: 'UNVERIFIED', label: 'Unverified' }, { value: 'REJECTED', label: 'Rejected' }]} />
          <SelectFilter label="Organizer" value={organizerFilter} onChange={setOrganizerFilter} options={[{ value: ALL, label: 'All' }, { value: 'found', label: 'Found' }, { value: 'missing', label: 'Not found' }]} />
          <SelectFilter label="Format" value={format} onChange={setFormat} options={[{ value: ALL, label: 'All' }, { value: 'online', label: 'Online' }, { value: 'offline', label: 'Offline' }, { value: 'hybrid', label: 'Hybrid' }, { value: 'unspecified', label: 'Not specified' }]} />
          <SelectFilter label="Min confidence" value={minConfidence} onChange={setMinConfidence} options={['0', '50', '60', '70', '80', '90'].map((v) => ({ value: v, label: v === '0' ? 'Any' : `${v}+` }))} />
          <label className="flex items-center gap-2 text-[11px] text-muted-foreground"><span className="font-mono-face uppercase tracking-wider">Discovered</span><input type="date" value={discoveredFrom} onChange={(e) => setDiscoveredFrom(e.target.value)} className={dateInput} /><span>–</span><input type="date" value={discoveredTo} onChange={(e) => setDiscoveredTo(e.target.value)} className={dateInput} /></label>
          <label className="flex items-center gap-2 text-[11px] text-muted-foreground"><span className="font-mono-face uppercase tracking-wider">Event date</span><input type="date" value={eventFrom} onChange={(e) => setEventFrom(e.target.value)} className={dateInput} /><span>–</span><input type="date" value={eventTo} onChange={(e) => setEventTo(e.target.value)} className={dateInput} /></label>
          <Btn variant="ghost" size="sm" onClick={resetFilters}><RotateCcw size={11} /> Reset</Btn>
        </div>
      )}

      <div className="mt-4">
        {rows.length === 0 ? <EmptyState title={all.length === 0 ? 'No events discovered yet.' : 'No events match these filters.'} body={all.length === 0 ? 'Use “Run manual research” to start finding events.' : undefined} /> : (
          <>
            <AdminTable columns={['Event', 'Organizer', 'Sector', 'Date', 'Country', 'City', 'State', 'Format & venue', 'Organizer email', 'Organizer phone', 'Source', 'Status', 'Discovered', '']} minWidth={1600}>
              {pager.slice.map((e) => {
                const o = organizerById(org, e.organizerId);
                const venueRelevant = e.eventFormat === 'offline' || e.eventFormat === 'hybrid';
                return (
                  <tr key={e.id} className="cursor-pointer hover:bg-muted/20" onClick={() => openEvent(e)}>
                    <td className={cell}><span className="block max-w-[260px] truncate font-semibold" title={e.name ?? ''}>{e.name ?? NA}</span></td>
                    <td className={cell}>{o ? <Link href={`/admin/discovery/organizers/${o.id}`} onClick={(ev) => ev.stopPropagation()} className="block max-w-[200px] truncate text-accent hover:underline" title={o.name}>{o.name}</Link> : <span className="text-muted-foreground">{e.organizerStatus === 'NOT_FOUND' ? 'Not found' : NA}</span>}</td>
                    <td className={cellMuted}><span className="block max-w-[160px] truncate" title={e.category ?? ''}>{e.category ?? NA}</span></td>
                    <td className={cellMuted}><span className="block max-w-[140px] truncate">{e.date ?? NA}</span></td>
                    <td className={cellMuted}>{e.country ?? 'India'}</td>
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
                    <td className={cell}><Badge tone={verificationTone(e.verificationStatus)}>{e.verificationStatus.replace('_', ' ')}</Badge><div className="mt-1.5"><ConfidenceBar value={e.confidenceScore} /></div></td>
                    <td className={cellMuted}>{fmtDate(e.discoveredAt)}</td>
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
