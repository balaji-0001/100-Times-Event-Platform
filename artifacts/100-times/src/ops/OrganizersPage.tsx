import { useMemo, useState } from 'react';
import { Link, useLocation } from 'wouter';
import { RotateCcw } from 'lucide-react';
import { contactStatus, contactSummary, eventsForOrganizer, messagesForOrganizer, useDiscoveredEvents, useDiscoveredOrganizers, useOutreachMessages } from './api';
import { AdminTable, Badge, Btn, ErrorState, EmptyState, ExtLink, LoadingState, NA, PageHeader, Pager, SearchBox, SelectFilter, cell, cellMuted, fmtDate, useDebounce, usePagination } from './ui';

const ALL = '__all__';
const uniq = (vals: Array<string | null | undefined>) => Array.from(new Set(vals.filter((v): v is string => Boolean(v)))).sort();

const CONTACT_TONE: Record<string, 'neutral' | 'warn' | 'good' | 'danger'> = { 'Not contacted': 'neutral', 'Pending approval': 'warn', Contacted: 'good', Replied: 'good', 'Do not contact': 'danger' };

export function OrganizersPage() {
  const organizers = useDiscoveredOrganizers();
  const events = useDiscoveredEvents();
  const messages = useOutreachMessages();
  const [, setLocation] = useLocation();
  const [q, setQ] = useState(''); const term = useDebounce(q.trim().toLowerCase());
  const [state, setState] = useState(ALL); const [status, setStatus] = useState(ALL); const [hasEmail, setHasEmail] = useState(ALL); const [type, setType] = useState(ALL);

  const all = organizers.data ?? [];
  const rows = useMemo(() => {
    let list = all.map((o) => {
      const msgs = messagesForOrganizer(messages.data, o.id);
      return { o, events: eventsForOrganizer(events.data, o.id).length, status: o.blocked ? 'Do not contact' : contactStatus(msgs), last: contactSummary(msgs).lastContact };
    });
    if (state !== ALL) list = list.filter((r) => r.o.state === state);
    if (type !== ALL) list = list.filter((r) => r.o.organizerType === type);
    if (status !== ALL) list = list.filter((r) => r.status === status);
    if (hasEmail !== ALL) list = list.filter((r) => (hasEmail === 'yes' ? Boolean(r.o.email) : !r.o.email));
    if (term) list = list.filter((r) => [r.o.name, r.o.email, r.o.phone, r.o.website, r.o.city, r.o.state].some((v) => v?.toLowerCase().includes(term)));
    return list.sort((a, b) => b.o.id - a.o.id);
  }, [all, events.data, messages.data, state, type, status, hasEmail, term]);
  const pager = usePagination(rows, 25);

  if (organizers.isLoading) return <LoadingState label="Loading organizer database" />;
  if (organizers.isError) return <ErrorState error={organizers.error} retry={() => organizers.refetch()} />;

  return (
    <div>
      <PageHeader kicker="Organizer Discovery · Organizer database" title="All Organizers" subtitle={`${all.length} organizers extracted by Agent 1, with every contact channel found and their outreach status.`} />
      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl font-bold">{rows.length} organizer{rows.length === 1 ? '' : 's'}</h2>
        <SearchBox value={q} onChange={setQ} placeholder="Search name, email, phone, website, city…" />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-foreground/10 bg-card px-4 py-3">
        <SelectFilter label="Contact status" value={status} onChange={setStatus} options={[{ value: ALL, label: 'All' }, ...['Not contacted', 'Pending approval', 'Contacted', 'Replied', 'Do not contact'].map((v) => ({ value: v, label: v }))]} />
        <SelectFilter label="Email" value={hasEmail} onChange={setHasEmail} options={[{ value: ALL, label: 'All' }, { value: 'yes', label: 'Has email' }, { value: 'no', label: 'No email' }]} />
        <SelectFilter label="State" value={state} onChange={setState} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((o) => o.state)).map((v) => ({ value: v, label: v }))]} />
        <SelectFilter label="Type" value={type} onChange={setType} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((o) => o.organizerType)).map((v) => ({ value: v, label: v }))]} />
        <Btn variant="ghost" size="sm" onClick={() => { setQ(''); setState(ALL); setStatus(ALL); setHasEmail(ALL); setType(ALL); }}><RotateCcw size={11} /> Reset</Btn>
      </div>

      <div className="mt-4">
        {rows.length === 0 ? <EmptyState title={all.length === 0 ? 'No organizers discovered yet.' : 'No organizers match these filters.'} /> : (
          <>
            <AdminTable columns={['Organizer', 'Website', 'Email', 'Phone', 'City', 'State', 'Events', 'Contact status', 'Last contacted', '']} minWidth={1200}>
              {pager.slice.map(({ o, events: n, status: st, last }) => (
                <tr key={o.id} className="cursor-pointer hover:bg-muted/20" onClick={() => setLocation(`/admin/discovery/organizers/${o.id}`)}>
                  <td className={cell}><span className="block max-w-[260px] truncate font-semibold" title={o.name}>{o.name}</span>{o.organizerType && <span className="text-[10px] uppercase text-muted-foreground">{o.organizerType}</span>}</td>
                  <td className={cell} onClick={(e) => e.stopPropagation()}><span className="block max-w-[200px] truncate"><ExtLink href={o.website}>{safeHost(o.website)}</ExtLink></span></td>
                  <td className={cell}>{o.email ? <span className="block max-w-[220px] truncate">{o.email}</span> : <span className="text-muted-foreground">{NA}</span>}</td>
                  <td className={cellMuted}>{o.phone ?? NA}</td>
                  <td className={cellMuted}>{o.city ?? NA}</td>
                  <td className={cellMuted}>{o.state ?? NA}</td>
                  <td className={cell}>{n} event{n === 1 ? '' : 's'}</td>
                  <td className={cell}><Badge tone={CONTACT_TONE[st] ?? 'neutral'}>{st}</Badge></td>
                  <td className={cellMuted}>{last ? fmtDate(last) : '—'}</td>
                  <td className={cell}><Link href={`/admin/discovery/organizers/${o.id}`} onClick={(e) => e.stopPropagation()}><Btn size="sm">View</Btn></Link></td>
                </tr>
              ))}
            </AdminTable>
            <Pager {...pager} />
          </>
        )}
      </div>
    </div>
  );
}

function safeHost(url?: string | null) { try { return url ? new URL(url).host.replace(/^www\./, '') : undefined; } catch { return url ?? undefined; } }
