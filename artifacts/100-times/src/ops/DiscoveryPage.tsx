import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useSearch } from 'wouter';
import { RotateCcw } from 'lucide-react';
import { type DiscoveredEvent, messagesForEvent, organizerById, useDiscoveredEvents, useDiscoveredOrganizers, useOutreachMessages } from './api';
import { AdminTable, Badge, Btn, ConfidenceBar, ErrorState, EmptyState, LoadingState, NA, PageHeader, Pager, SearchBox, SelectFilter, StatCard, cell, cellMuted, fmtDate, useDebounce, usePagination, verificationTone } from './ui';
import { EventDrawer, sourceTypeLabel } from './EventDrawer';
import { ManualResearchButton } from './ManualResearch';

const ALL = '__all__';
const uniq = (vals: Array<string | null | undefined>) => Array.from(new Set(vals.filter((v): v is string => Boolean(v)))).sort();

export function DiscoveryPage({ mode }: { mode: 'new' | 'events' }) {
  const events = useDiscoveredEvents();
  const organizers = useDiscoveredOrganizers();
  const messages = useOutreachMessages();
  const [, setLocation] = useLocation();
  const search = useSearch();
  const selectedId = Number(new URLSearchParams(search).get('event')) || null;

  const [q, setQ] = useState(''); const term = useDebounce(q.trim().toLowerCase());
  // Dashboard stat cards deep-link here with ?verification=… / ?format=… so the list opens already filtered.
  const initial = new URLSearchParams(search);
  const fromUrl = (key: string, allowed: string[]) => { const v = initial.get(key); return v && allowed.includes(v) ? v : ALL; };
  const [state, setState] = useState(ALL); const [city, setCity] = useState(ALL); const [category, setCategory] = useState(ALL);
  const [verification, setVerification] = useState(() => fromUrl('verification', ['VERIFIED', 'NEEDS_REVIEW', 'UNVERIFIED', 'REJECTED'])); const [minConfidence, setMinConfidence] = useState('0');
  const [organizerFilter, setOrganizerFilter] = useState(ALL); const [format, setFormat] = useState(() => fromUrl('format', ['online', 'offline', 'hybrid', 'unspecified']));
  const [discoveredFrom, setDiscoveredFrom] = useState(''); const [discoveredTo, setDiscoveredTo] = useState('');
  const [eventFrom, setEventFrom] = useState(''); const [eventTo, setEventTo] = useState('');

  const all = events.data ?? [];
  const rows = useMemo(() => {
    let list = [...all].sort((a, b) => (b.discoveredAt ?? '').localeCompare(a.discoveredAt ?? ''));
    if (mode === 'new') return list;
    if (state !== ALL) list = list.filter((e) => e.state === state);
    if (city !== ALL) list = list.filter((e) => e.city === city);
    if (category !== ALL) list = list.filter((e) => e.category === category);
    if (verification !== ALL) list = list.filter((e) => e.verificationStatus === verification);
    if (organizerFilter !== ALL) list = list.filter((e) => (organizerFilter === 'found' ? e.organizerStatus === 'FOUND' : e.organizerStatus !== 'FOUND'));
    if (format !== ALL) list = list.filter((e) => (format === 'unspecified' ? !e.eventFormat : e.eventFormat === format));
    const minC = Number(minConfidence) || 0; if (minC > 0) list = list.filter((e) => e.confidenceScore >= minC);
    if (discoveredFrom) list = list.filter((e) => (e.discoveredAt ?? '') >= discoveredFrom);
    if (discoveredTo) list = list.filter((e) => (e.discoveredAt ?? '').slice(0, 10) <= discoveredTo);
    if (eventFrom) list = list.filter((e) => e.eventDate && e.eventDate >= eventFrom);
    if (eventTo) list = list.filter((e) => e.eventDate && e.eventDate <= eventTo);
    if (term) list = list.filter((e) => [e.name, e.city, e.state, e.category, e.subcategory, e.venue, organizerById(organizers.data, e.organizerId)?.name, organizerById(organizers.data, e.organizerId)?.email].some((v) => v?.toLowerCase().includes(term)));
    return list;
  }, [all, mode, state, city, category, verification, organizerFilter, format, minConfidence, discoveredFrom, discoveredTo, eventFrom, eventTo, term, organizers.data]);

  const pager = usePagination(rows, mode === 'new' ? 20 : 25);
  const selected = selectedId ? all.find((e) => e.id === selectedId) ?? null : null;
  const openEvent = (e: DiscoveredEvent) => setLocation(`${mode === 'new' ? '/admin/discovery' : '/admin/discovery/events'}?event=${e.id}`);
  const closeEvent = () => setLocation(mode === 'new' ? '/admin/discovery' : '/admin/discovery/events');
  useEffect(() => { if (selectedId && events.isSuccess && !selected) closeEvent(); }, [selectedId, events.isSuccess, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  if (events.isLoading || organizers.isLoading) return <LoadingState label="Loading discovered events" />;
  if (events.isError) return <ErrorState error={events.error} retry={() => events.refetch()} />;

  const org = organizers.data ?? [];
  const newEvents = all.filter((e) => e.discoveryStatus === 'NEW').length;
  const contacts = org.reduce((n, o) => n + o.contacts.length, 0);
  const needsReview = all.filter((e) => e.verificationStatus === 'NEEDS_REVIEW').length;

  const resetFilters = () => { setQ(''); setState(ALL); setCity(ALL); setCategory(ALL); setVerification(ALL); setMinConfidence('0'); setOrganizerFilter(ALL); setFormat(ALL); setDiscoveredFrom(''); setDiscoveredTo(''); setEventFrom(''); setEventTo(''); };
  const dateInput = 'rounded-lg border border-foreground/15 bg-background px-2 py-1.5 text-xs text-foreground outline-none focus:border-accent';

  return (
    <div>
      <PageHeader
        kicker={mode === 'new' ? 'Organizer Discovery · Agent 1' : 'Organizer Discovery · Events found'}
        title={mode === 'new' ? 'Organizer Discovery' : 'Events Found'}
        subtitle={mode === 'new' ? 'Discover events across India and extract verified organizer information.' : `Every event Agent 1 has discovered — ${all.length} so far — with the organizer, source and verification data behind each one.`}
        actions={mode === 'new' && <ManualResearchButton />}
      />

      {mode === 'new' && (
        <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="New events" value={newEvents} sub={`${all.length} discovered in total`} href="/admin/discovery/events" />
          <StatCard label="New organizers" value={org.length} href="/admin/discovery/organizers" />
          <StatCard label="Contacts found" value={contacts} sub={`${org.filter((o) => o.email).length} organizers with email`} href="/admin/discovery/contacts" />
          <StatCard label="Needs review" value={needsReview} tone={needsReview ? 'warn' : 'good'} href="/admin/discovery/events?verification=NEEDS_REVIEW" />
        </div>
      )}

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl font-bold">{mode === 'new' ? 'Recently discovered' : `${rows.length} event${rows.length === 1 ? '' : 's'}`}</h2>
        {mode === 'new' ? <Link href="/admin/discovery/events" className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">All events with filters →</Link> : <SearchBox value={q} onChange={setQ} placeholder="Search event, organizer, city, category…" />}
      </div>

      {mode === 'events' && (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-foreground/10 bg-card px-4 py-3">
          <SelectFilter label="State" value={state} onChange={setState} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((e) => e.state)).map((v) => ({ value: v, label: v }))]} />
          <SelectFilter label="City" value={city} onChange={setCity} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((e) => e.city)).map((v) => ({ value: v, label: v }))]} />
          <SelectFilter label="Category" value={category} onChange={setCategory} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((e) => e.category)).map((v) => ({ value: v, label: v }))]} />
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
            <AdminTable columns={['Event', 'Organizer', 'Category', 'Date', 'City', 'State', 'Format & venue', 'Organizer email', 'Organizer phone', 'Source', 'Status', 'Discovered', '']} minWidth={1520}>
              {pager.slice.map((e) => {
                const o = organizerById(org, e.organizerId);
                const venueRelevant = e.eventFormat === 'offline' || e.eventFormat === 'hybrid';
                return (
                  <tr key={e.id} className="cursor-pointer hover:bg-muted/20" onClick={() => openEvent(e)}>
                    <td className={cell}><span className="block max-w-[260px] truncate font-semibold" title={e.name ?? ''}>{e.name ?? NA}</span></td>
                    <td className={cell}>{o ? <Link href={`/admin/discovery/organizers/${o.id}`} onClick={(ev) => ev.stopPropagation()} className="block max-w-[200px] truncate text-accent hover:underline" title={o.name}>{o.name}</Link> : <span className="text-muted-foreground">{e.organizerStatus === 'NOT_FOUND' ? 'Not found' : NA}</span>}</td>
                    <td className={cellMuted}><span className="block max-w-[160px] truncate" title={e.category ?? ''}>{e.category ?? NA}</span></td>
                    <td className={cellMuted}><span className="block max-w-[140px] truncate">{e.date ?? NA}</span></td>
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
