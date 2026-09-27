import { useMemo, useState } from 'react';
import { Link } from 'wouter';
import { RotateCcw } from 'lucide-react';
import { type DiscoveredOrganizer, type OrganizerContact, useDiscoveredOrganizers } from './api';
import { AdminTable, Badge, Btn, ConfidenceBar, ErrorState, EmptyState, ExtLink, LoadingState, NA, PageHeader, Pager, SearchBox, SelectFilter, StatCard, cell, cellMuted, useDebounce, usePagination } from './ui';

const ALL = '__all__';

type Row = { contact: OrganizerContact; organizer: DiscoveredOrganizer };

const TYPE_TONE: Record<string, 'info' | 'good' | 'accent' | 'neutral'> = { email: 'info', phone: 'good', linkedin: 'accent', website: 'neutral' };

/** Every contact channel Agent 1 found, across all organizers — the rows behind the Dashboard's "Contacts found" number. */
export function ContactsPage() {
  const organizers = useDiscoveredOrganizers();
  const [q, setQ] = useState(''); const term = useDebounce(q.trim().toLowerCase());
  const [type, setType] = useState(ALL); const [primary, setPrimary] = useState(ALL);

  const all = useMemo<Row[]>(() => (organizers.data ?? []).flatMap((o) => o.contacts.map((c) => ({ contact: c, organizer: o }))), [organizers.data]);
  const rows = useMemo(() => {
    let list = all;
    if (type !== ALL) list = list.filter((r) => r.contact.contactType === type);
    if (primary !== ALL) list = list.filter((r) => (primary === 'yes' ? r.contact.isPrimary : !r.contact.isPrimary));
    if (term) list = list.filter((r) => [r.contact.value, r.contact.contactType, r.organizer.name, r.organizer.city, r.organizer.state, r.contact.sourceUrl].some((v) => v?.toLowerCase().includes(term)));
    return [...list].sort((a, b) => b.contact.id - a.contact.id);
  }, [all, type, primary, term]);
  const pager = usePagination(rows, 25);

  if (organizers.isLoading) return <LoadingState label="Loading contacts" />;
  if (organizers.isError) return <ErrorState error={organizers.error} retry={() => organizers.refetch()} />;

  const byType: Record<string, number> = {};
  for (const r of all) byType[r.contact.contactType] = (byType[r.contact.contactType] ?? 0) + 1;
  const types = Object.keys(byType).sort();
  const organizersWithContacts = new Set(all.map((r) => r.organizer.id)).size;

  return (
    <div>
      <PageHeader kicker="Organizer Discovery · Contacts" title="Contacts Found" subtitle={`Every contact channel Agent 1 extracted — ${all.length} across ${organizersWithContacts} organizers — with the exact page each one was found on. Nothing here is guessed; every value was read from a public page.`} />

      <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="All contacts" value={all.length} />
        <StatCard label="Emails" value={byType.email ?? 0} />
        <StatCard label="Phones" value={byType.phone ?? 0} />
        <StatCard label="LinkedIn" value={byType.linkedin ?? 0} />
        <StatCard label="Websites" value={byType.website ?? 0} />
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl font-bold">{rows.length} contact{rows.length === 1 ? '' : 's'}</h2>
        <SearchBox value={q} onChange={setQ} placeholder="Search value, organizer, city, source…" />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-foreground/10 bg-card px-4 py-3">
        <SelectFilter label="Type" value={type} onChange={setType} options={[{ value: ALL, label: 'All' }, ...types.map((t) => ({ value: t, label: `${t[0].toUpperCase()}${t.slice(1)} (${byType[t]})` }))]} />
        <SelectFilter label="Primary" value={primary} onChange={setPrimary} options={[{ value: ALL, label: 'All' }, { value: 'yes', label: 'Primary only' }, { value: 'no', label: 'Secondary only' }]} />
        <Btn variant="ghost" size="sm" onClick={() => { setQ(''); setType(ALL); setPrimary(ALL); }}><RotateCcw size={11} /> Reset</Btn>
      </div>

      <div className="mt-4">
        {rows.length === 0 ? <EmptyState title={all.length === 0 ? 'No contacts found yet.' : 'No contacts match these filters.'} body={all.length === 0 ? 'Run discovery to extract organizer contact details.' : undefined} /> : (
          <>
            <AdminTable columns={['Organizer', 'Type', 'Contact', 'Found on', 'Confidence', 'Primary', '']} minWidth={1100}>
              {pager.slice.map(({ contact: c, organizer: o }) => (
                <tr key={c.id} className="hover:bg-muted/20">
                  <td className={cell}>
                    <Link href={`/admin/discovery/organizers/${o.id}`} className="block max-w-[240px] truncate font-semibold text-accent hover:underline" title={o.name}>{o.name}</Link>
                    <span className="block text-[11px] text-muted-foreground">{[o.city, o.state].filter(Boolean).join(', ') || NA}</span>
                  </td>
                  <td className={cell}><Badge tone={TYPE_TONE[c.contactType] ?? 'neutral'}>{c.contactType}</Badge></td>
                  <td className={cell}><span className="block max-w-[300px] break-all">{contactValue(c)}</span></td>
                  <td className={cell}><span className="block max-w-[200px]"><ExtLink href={c.sourceUrl}>{safeHost(c.sourceUrl)}</ExtLink></span></td>
                  <td className={cell}><ConfidenceBar value={c.confidenceScore} /></td>
                  <td className={cellMuted}>{c.isPrimary && <Badge tone="accent">Primary</Badge>}</td>
                  <td className={cell}><Link href={`/admin/discovery/organizers/${o.id}`}><Btn size="sm">View organizer</Btn></Link></td>
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

function contactValue(c: OrganizerContact) {
  const v = c.value;
  if (c.contactType === 'email') return <a href={`mailto:${v}`} className="text-accent hover:underline">{v}</a>;
  if (c.contactType === 'phone') return <a href={`tel:${v.replace(/\s+/g, '')}`} className="text-accent hover:underline">{v}</a>;
  if (/^https?:\/\//i.test(v)) return <ExtLink href={v}>{v.replace(/^https?:\/\/(www\.)?/i, '')}</ExtLink>;
  return v;
}

function safeHost(url?: string | null) { try { return url ? new URL(url).host.replace(/^www\./, '') : undefined; } catch { return url ?? undefined; } }
