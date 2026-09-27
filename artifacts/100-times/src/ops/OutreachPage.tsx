import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useParams, useSearch } from 'wouter';
import { Play, RotateCcw } from 'lucide-react';
import { type OutreachMessage, OUTREACH_STATUSES, OUTREACH_TABS, type OutreachTabKey, STATUS_LABEL, useDiscoveredOrganizers, useOutreachMessages, useOutreachStats, useProcessFollowups, useRunOutreachBatch } from './api';
import { AdminTable, Btn, ErrorState, EmptyState, LoadingState, NA, Notice, PageHeader, Pager, SearchBox, SelectFilter, StatCard, StatusBadge, cell, cellMuted, cx, fmtDateTime, useDebounce, usePagination } from './ui';
import { OutreachDrawer } from './OutreachDrawer';

const ALL = '__all__';
const uniq = (vals: Array<string | null | undefined>) => Array.from(new Set(vals.filter((v): v is string => Boolean(v)))).sort();

export function OutreachPage() {
  const params = useParams<{ tab?: string }>();
  const tab = (OUTREACH_TABS.some((t) => t.key === params.tab) ? params.tab : 'all') as OutreachTabKey;
  const [, setLocation] = useLocation();
  const search = useSearch();
  const selectedId = Number(new URLSearchParams(search).get('message')) || null;

  const messages = useOutreachMessages();
  const organizers = useDiscoveredOrganizers();
  const stats = useOutreachStats();
  const runBatch = useRunOutreachBatch();
  const followups = useProcessFollowups();

  const [q, setQ] = useState(''); const term = useDebounce(q.trim().toLowerCase());
  const [status, setStatus] = useState(ALL); const [city, setCity] = useState(ALL); const [state, setState] = useState(ALL); const [event, setEvent] = useState(ALL); const [organizer, setOrganizer] = useState(ALL);
  const [sentFrom, setSentFrom] = useState(''); const [sentTo, setSentTo] = useState('');

  const all = messages.data ?? [];
  const tabDef = OUTREACH_TABS.find((t) => t.key === tab)!;
  const rows = useMemo(() => {
    let list = [...all].sort((a, b) => (b.sentAt ?? b.createdAt).localeCompare(a.sentAt ?? a.createdAt));
    if (tabDef.statuses) list = list.filter((m) => (tabDef.statuses as readonly string[]).includes(m.status));
    if (status !== ALL) list = list.filter((m) => m.status === status);
    if (city !== ALL) list = list.filter((m) => m.event.city === city);
    if (state !== ALL) list = list.filter((m) => m.event.state === state);
    if (event !== ALL) list = list.filter((m) => String(m.event.id) === event);
    if (organizer !== ALL) list = list.filter((m) => String(m.organizer?.id) === organizer);
    if (sentFrom) list = list.filter((m) => (m.sentAt ?? '') >= sentFrom);
    if (sentTo) list = list.filter((m) => (m.sentAt ?? '').slice(0, 10) <= sentTo && m.sentAt);
    if (term) list = list.filter((m) => [m.organizer?.name, m.event.name, m.recipient, m.subject, m.event.city].some((v) => v?.toLowerCase().includes(term)));
    return list;
  }, [all, tabDef, status, city, state, event, organizer, sentFrom, sentTo, term]);
  const pager = usePagination(rows, 25);
  const counts = useMemo(() => Object.fromEntries(OUTREACH_TABS.map((t) => [t.key, t.statuses ? all.filter((m) => (t.statuses as readonly string[]).includes(m.status)).length : all.length])), [all]);

  const selected = selectedId ? all.find((m) => m.id === selectedId) ?? null : null;
  const base = `/admin/outreach/${tab}`;
  const openMessage = (m: OutreachMessage) => setLocation(`${base}?message=${m.id}`);
  const closeMessage = () => setLocation(base);
  useEffect(() => { if (selectedId && messages.isSuccess && !selected) closeMessage(); }, [selectedId, messages.isSuccess, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  if (messages.isLoading) return <LoadingState label="Loading outreach records" />;
  if (messages.isError) return <ErrorState error={messages.error} retry={() => messages.refetch()} />;

  const org = organizers.data ?? [];
  const contactedIds = new Set(all.filter((m) => m.organizer?.id).map((m) => m.organizer!.id));
  const ready = org.filter((o) => o.email && !o.blocked && !contactedIds.has(o.id)).length;
  const sent = all.filter((m) => m.sentAt).length;
  const delivered = all.filter((m) => ['DELIVERED', 'REPLIED', 'FOLLOW_UP_DUE', 'COMPLETED'].includes(m.status)).length;
  const replies = all.filter((m) => m.responseAt).length;
  const followUps = all.filter((m) => m.status === 'FOLLOW_UP_DUE').length;
  const dateInput = 'rounded-lg border border-foreground/15 bg-background px-2 py-1.5 text-xs text-foreground outline-none focus:border-accent';

  return (
    <div>
      <PageHeader kicker="Organizer Outreach · Agent 2" title="Organizer Outreach" subtitle="Promote 100Times to event organizers and invite them to list their events. Every email is generated per organizer and sent only after an admin approves it."
        actions={<>
          <Btn loading={followups.isPending} onClick={() => followups.mutate()}>Process follow-ups</Btn>
          <Btn variant="primary" loading={runBatch.isPending} onClick={() => runBatch.mutate({})}><Play size={13} /> Generate outreach batch</Btn>
        </>} />
      {runBatch.isError && <div className="mt-4"><ErrorState error={runBatch.error} title="Outreach batch failed" /></div>}
      {runBatch.isSuccess && <div className="mt-4"><Notice tone="info">Batch finished: {JSON.stringify(runBatch.data)}</Notice></div>}
      {followups.isSuccess && <div className="mt-4"><Notice tone="info">Follow-up sweep: {JSON.stringify(followups.data)}</Notice></div>}
      {stats.data?.emailProviderStatus === 'NOT_CONFIGURED' && <div className="mt-4"><Notice tone="warn"><strong>Email provider: mock.</strong> SMTP is not configured, so “Send” hands the message to a mock provider and no real email reaches the organizer. Statuses below reflect that.</Notice></div>}

      <div className="mt-8 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Total organizers" value={org.length} />
        <StatCard label="Ready for outreach" value={ready} sub="with email, not yet contacted" />
        <StatCard label="Emails sent" value={sent} />
        <StatCard label="Delivered" value={delivered} tone="good" />
        <StatCard label="Replies" value={replies} />
        <StatCard label="Follow-ups" value={followUps} tone={followUps ? 'warn' : 'accent'} />
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {OUTREACH_TABS.map((t) => (
            <Link key={t.key} href={`/admin/outreach/${t.key}`} className={cx('rounded-full px-3 py-1 font-mono-face text-[11px] transition-colors', tab === t.key ? 'bg-accent font-bold text-accent-foreground' : 'border border-foreground/15 text-muted-foreground hover:text-foreground')}>{t.label}<span className="ml-1.5 opacity-70">{counts[t.key]}</span></Link>
          ))}
        </div>
        <SearchBox value={q} onChange={setQ} placeholder="Search organizer, event, email, subject…" />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-foreground/10 bg-card px-4 py-3">
        <SelectFilter label="Status" value={status} onChange={setStatus} options={[{ value: ALL, label: 'All' }, ...OUTREACH_STATUSES.map((s) => ({ value: s, label: STATUS_LABEL[s] }))]} />
        <SelectFilter label="Organizer" value={organizer} onChange={setOrganizer} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((m) => (m.organizer ? `${m.organizer.id}` : null))).map((id) => ({ value: id, label: all.find((m) => String(m.organizer?.id) === id)?.organizer?.name ?? id }))]} />
        <SelectFilter label="Event" value={event} onChange={setEvent} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((m) => `${m.event.id}`)).map((id) => ({ value: id, label: all.find((m) => String(m.event.id) === id)?.event.name ?? id }))]} />
        <SelectFilter label="City" value={city} onChange={setCity} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((m) => m.event.city)).map((v) => ({ value: v, label: v }))]} />
        <SelectFilter label="State" value={state} onChange={setState} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((m) => m.event.state)).map((v) => ({ value: v, label: v }))]} />
        <label className="flex items-center gap-2 text-[11px] text-muted-foreground"><span className="font-mono-face uppercase tracking-wider">Sent</span><input type="date" value={sentFrom} onChange={(e) => setSentFrom(e.target.value)} className={dateInput} /><span>–</span><input type="date" value={sentTo} onChange={(e) => setSentTo(e.target.value)} className={dateInput} /></label>
        <Btn variant="ghost" size="sm" onClick={() => { setQ(''); setStatus(ALL); setCity(ALL); setState(ALL); setEvent(ALL); setOrganizer(ALL); setSentFrom(''); setSentTo(''); }}><RotateCcw size={11} /> Reset</Btn>
      </div>

      <div className="mt-4">
        {rows.length === 0 ? <EmptyState title={all.length === 0 ? 'Agent 2 has not generated any outreach yet.' : `No ${tab === 'all' ? '' : tabDef.label.toLowerCase() + ' '}records match.`} body={all.length === 0 ? 'Generate a batch to draft emails for organizers with a verified email address.' : undefined} /> : (
          <>
            <AdminTable columns={['Organizer', 'Event', 'Recipient', 'Subject', 'Sent at', 'Status', '']} minWidth={1100}>
              {pager.slice.map((m) => (
                <tr key={m.id} className="cursor-pointer hover:bg-muted/20" onClick={() => openMessage(m)}>
                  <td className={cell}>{m.organizer ? <Link href={`/admin/discovery/organizers/${m.organizer.id}`} onClick={(e) => e.stopPropagation()} className="block max-w-[220px] truncate font-semibold text-accent hover:underline" title={m.organizer.name}>{m.organizer.name}</Link> : <span className="text-muted-foreground">{NA}</span>}</td>
                  <td className={cell}><span className="block max-w-[240px] truncate" title={m.event.name ?? ''}>{m.event.name ?? NA}</span><span className="text-muted-foreground">{[m.event.city, m.event.date].filter(Boolean).join(' · ')}</span></td>
                  <td className={cell}><span className="block max-w-[220px] truncate">{m.recipient ?? NA}</span></td>
                  <td className={cell}><span className="block max-w-[280px] truncate" title={m.subject ?? ''}>{m.subject ?? <span className="text-muted-foreground">Not generated</span>}</span></td>
                  <td className={cellMuted}>{m.sentAt ? fmtDateTime(m.sentAt) : '—'}</td>
                  <td className={cell}><StatusBadge status={m.status} />{m.failureReason && <span className="mt-1 block max-w-[200px] truncate text-[10px] text-red-600" title={m.failureReason}>{m.failureReason}</span>}</td>
                  <td className={cell}><Btn size="sm" onClick={(e) => { e.stopPropagation(); openMessage(m); }}>View</Btn></td>
                </tr>
              ))}
            </AdminTable>
            <Pager {...pager} />
          </>
        )}
      </div>

      <OutreachDrawer message={selected} onClose={closeMessage} />
    </div>
  );
}
