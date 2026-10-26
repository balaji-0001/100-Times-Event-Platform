import { useMemo, useState } from 'react';
import { Link } from 'wouter';
import { ChevronRight, Eye } from 'lucide-react';
import { type AgentRun, useDiscoveredEvents, useDiscoveredOrganizers, useDiscoveryRuns, useOutreachMessages, useOutreachRuns } from './api';
import { buildActivity } from './activity';
import { AdminTable, Badge, Btn, Chips, DL, Drawer, ErrorState, EmptyState, LoadingState, NA, Notice, PageHeader, Panel, Section, cell, cellMuted, cx, fmtDate, fmtDateTime, fmtDuration, fmtTime, parseDate } from './ui';

type Tab = 'discovery' | 'outreach';
const runTone = (s: AgentRun['status']) => (s === 'completed' ? 'good' : s === 'failed' ? 'danger' : 'warn');

export function ActivityPage() {
  const [tab, setTab] = useState<Tab>('discovery');
  const [openRun, setOpenRun] = useState<AgentRun | null>(null);
  const discoveryRuns = useDiscoveryRuns();
  const outreachRuns = useOutreachRuns();
  const events = useDiscoveredEvents();
  const organizers = useDiscoveredOrganizers();
  const messages = useOutreachMessages();

  const runsQuery = tab === 'discovery' ? discoveryRuns : outreachRuns;
  const runs = useMemo(() => [...(runsQuery.data ?? [])].sort((a, b) => b.id - a.id), [runsQuery.data]);
  const feed = useMemo(() => buildActivity({ events: events.data, organizers: organizers.data, messages: messages.data, runs: [] }).filter((a) => a.agent === tab).slice(0, 100), [events.data, organizers.data, messages.data, tab]);

  const s = (r: AgentRun, k: string) => (r.summary?.[k] ?? 0);

  const getRunEvents = (r: AgentRun | null) => {
    if (!r || !events.data) return [];
    const eventIds: number[] = Array.isArray(r.summary?.event_ids) ? (r.summary.event_ids as number[]) : [];
    if (eventIds.length > 0) {
      const set = new Set(eventIds);
      return events.data.filter((e) => set.has(e.id));
    }
    if (!r.startedAt) return [];
    const startMs = new Date(r.startedAt).getTime() - 60000;
    const endMs = (r.completedAt ? new Date(r.completedAt).getTime() : Date.now()) + 60000;
    return events.data.filter((e) => {
      if (!e.discoveredAt) return false;
      const t = new Date(e.discoveredAt).getTime();
      return t >= startMs && t <= endMs;
    });
  };

  const runDiscoveredEvents = useMemo(() => getRunEvents(openRun), [openRun, events.data]);

  if (runsQuery.isLoading) return <LoadingState label="Loading agent runs" />;
  if (runsQuery.isError) return <ErrorState error={runsQuery.error} retry={() => runsQuery.refetch()} />;

  return (
    <div>
      <PageHeader kicker="Agent Activity" title="What the agents did, and when." subtitle="Run history for both agents, plus a record-level feed built from stored timestamps. The agents do not log intermediate steps, so nothing here is inferred." />
      <div className="mt-6"><Chips<Tab> value={tab} onChange={setTab} options={[{ key: 'discovery', label: 'Organizer Discovery', count: discoveryRuns.data?.length }, { key: 'outreach', label: 'Organizer Outreach', count: outreachRuns.data?.length }]} /></div>

      <Panel className="mt-6 p-6">
        <Section title={`${tab === 'discovery' ? 'Discovery' : 'Outreach'} agent runs (${runs.length})`}>
          {runs.length === 0 ? <EmptyState title="No runs recorded." /> : tab === 'discovery' ? (
            <AdminTable columns={['Run', 'Status', 'View Discoveries', 'Discovered', 'New', 'Duplicates', 'Organizers', 'Contacts', 'Needs review', 'Started', 'Duration', 'Error', 'Details']} minWidth={1260}>
              {runs.map((r) => (
                <tr key={r.id} className="cursor-pointer hover:bg-muted/20" onClick={() => setOpenRun(r)}>
                  <td className={cell}><span className="font-mono-face font-bold">#{r.id}</span></td>
                  <td className={cell}><Badge tone={runTone(r.status)}>{r.status}</Badge></td>
                  <td className={cell}>
                    {s(r, 'events_discovered') > 0 ? (
                      <Link
                        href={`/admin/discovery/events?run=${r.id}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Btn
                          size="sm"
                          variant={s(r, 'new_events') > 0 ? 'secondary' : 'ghost'}
                          className={cx(
                            'h-7 text-xs font-semibold whitespace-nowrap',
                            s(r, 'new_events') > 0 && 'border-accent/40 bg-accent/15 text-accent hover:bg-accent/25'
                          )}
                          title={`View events discovered during run #${r.id}`}
                        >
                          <Eye size={12} className="mr-1 text-accent" />
                          View Discoveries{s(r, 'new_events') > 0 ? ` (${s(r, 'new_events')} new)` : ` (${s(r, 'events_discovered')})`}
                        </Btn>
                      </Link>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className={cell}>
                    {s(r, 'events_discovered') > 0 ? (
                      <Link
                        href={`/admin/discovery/events?run=${r.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-medium text-foreground hover:text-accent hover:underline inline-flex items-center gap-1"
                        title={`View events from run #${r.id}`}
                      >
                        {s(r, 'events_discovered')}
                      </Link>
                    ) : (
                      s(r, 'events_discovered')
                    )}
                  </td>
                  <td className={cell}>
                    {s(r, 'new_events') > 0 ? (
                      <Link
                        href={`/admin/discovery/events?run=${r.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-bold text-accent hover:underline inline-flex items-center gap-1"
                        title={`View ${s(r, 'new_events')} new events from run #${r.id}`}
                      >
                        {s(r, 'new_events')}
                      </Link>
                    ) : (
                      s(r, 'new_events')
                    )}
                  </td>
                  <td className={cellMuted}>{s(r, 'duplicate_events')}</td>
                  <td className={cell}>{s(r, 'organizers_found')}<span className="text-muted-foreground"> ({s(r, 'new_organizers')} new)</span></td><td className={cell}>{s(r, 'contacts_found')}</td><td className={cellMuted}>{s(r, 'events_needing_review')}</td>
                  <td className={cellMuted}>{fmtDateTime(r.startedAt)}</td>
                  <td className={cellMuted}>{r.status === 'running' ? 'still running' : fmtDuration(r.startedAt, r.completedAt)}</td>
                  <td className={cell}>{r.error ? <span className="block max-w-[200px] truncate text-red-600" title={r.error}>{r.error}</span> : <span className="text-muted-foreground">—</span>}</td>
                  <td className={cell}>
                    <Btn size="sm" variant="ghost" className="h-7 text-xs" onClick={(e) => { e.stopPropagation(); setOpenRun(r); }}>Details</Btn>
                  </td>
                </tr>
              ))}
            </AdminTable>
          ) : (
            <AdminTable columns={['Run', 'Status', 'Started', 'Completed', 'Duration', 'Considered', 'Emails generated', 'Skipped (duplicate)', 'Skipped (suppressed)', 'Skipped (no organizer)', 'Error', 'Actions']} minWidth={1200}>
              {runs.map((r) => (
                <tr key={r.id} className="cursor-pointer hover:bg-muted/20" onClick={() => setOpenRun(r)}>
                  <td className={cell}><span className="font-mono-face">#{r.id}</span></td>
                  <td className={cell}><Badge tone={runTone(r.status)}>{r.status}</Badge></td>
                  <td className={cellMuted}>{fmtDateTime(r.startedAt)}</td>
                  <td className={cellMuted}>{fmtDateTime(r.completedAt)}</td>
                  <td className={cellMuted}>{r.status === 'running' ? 'still running' : fmtDuration(r.startedAt, r.completedAt)}</td>
                  <td className={cell}>{s(r, 'candidates_considered')}</td><td className={cell}>{s(r, 'drafted')}</td>
                  <td className={cellMuted}>{s(r, 'skipped_duplicate')}</td><td className={cellMuted}>{s(r, 'skipped_suppressed')}</td><td className={cellMuted}>{s(r, 'skipped_no_organizer')}</td>
                  <td className={cell}>{r.error ? <span className="block max-w-[260px] truncate text-red-600" title={r.error}>{r.error}</span> : <span className="text-muted-foreground">—</span>}</td>
                  <td className={cell}><Btn size="sm" onClick={(e) => { e.stopPropagation(); setOpenRun(r); }}>Details</Btn></td>
                </tr>
              ))}
            </AdminTable>
          )}
          {runs.some((r) => r.status === 'running' && Date.now() - (parseDate(r.startedAt)?.getTime() ?? Date.now()) > 2 * 3600 * 1000) && (
            <div className="mt-3"><Notice tone="warn">A run has been marked “running” for more than two hours — it most likely stopped without recording a result (for example, the server restarted mid-run).</Notice></div>
          )}
        </Section>
      </Panel>

      <Panel className="mt-6 p-6">
        <Section title={tab === 'discovery' ? 'Discovery feed — events found' : 'Outreach feed — organizers contacted'}>
          {feed.length === 0 ? <p className="text-sm text-muted-foreground">No records yet.</p> : (
            <ol className="divide-y divide-foreground/10 text-sm">
              {feed.map((a) => (
                <li key={a.id} className="flex items-start gap-4 py-2.5">
                  <span className="w-[7.5rem] shrink-0 font-mono-face text-[10px] leading-5 text-muted-foreground">{fmtDate(a.at)}<br />{fmtTime(a.at)}</span>
                  <div className="min-w-0">{a.href ? <Link href={a.href} className={cx('font-semibold hover:underline', a.tone === 'danger' && 'text-red-700')}>{a.title}</Link> : <p className="font-semibold">{a.title}</p>}{a.detail && <p className="text-xs text-muted-foreground">{a.detail}</p>}</div>
                </li>
              ))}
            </ol>
          )}
        </Section>
      </Panel>

      <Drawer open={Boolean(openRun)} onClose={() => setOpenRun(null)} kicker={openRun ? `${openRun.agentType} run` : ''} title={openRun ? `Run #${openRun.id} — ${openRun.status}` : ''}>
        {openRun && (
          <>
            {openRun.error && <Notice tone="danger"><strong>Error:</strong> {openRun.error}</Notice>}

            {openRun.agentType === 'discovery' && (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-accent/30 bg-accent/10 p-3.5">
                <div>
                  <div className="text-xs font-semibold text-foreground">Discovered Events for Run #{openRun.id}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {s(openRun, 'new_events') || s(openRun, 'events_discovered') || 0} events recorded during this run
                  </div>
                </div>
                <Link href={`/admin/discovery/events?run=${openRun.id}`}>
                  <Btn variant="primary" size="sm">
                    <Eye size={13} className="mr-1.5" /> View in Events Catalog →
                  </Btn>
                </Link>
              </div>
            )}

            <Section title="Timing"><DL rows={[['Started', fmtDateTime(openRun.startedAt)], ['Completed', fmtDateTime(openRun.completedAt)], ['Duration', openRun.status === 'running' ? 'still running' : fmtDuration(openRun.startedAt, openRun.completedAt)]]} /></Section>
            <Section title="Results"><DL rows={Object.entries(openRun.summary ?? {}).map(([k, v]) => [k.replace(/_/g, ' '), String(v)])} /></Section>

            {openRun.agentType === 'discovery' && runDiscoveredEvents.length > 0 && (
              <Section title={`Events Discovered in this Run (${runDiscoveredEvents.length})`}>
                <div className="space-y-2">
                  {runDiscoveredEvents.slice(0, 8).map((ev) => (
                    <div key={ev.id} className="flex items-center justify-between rounded-lg border border-foreground/10 bg-background/50 p-2.5 text-xs">
                      <div className="min-w-0 pr-2">
                        <span className="block truncate font-medium text-foreground">{ev.name}</span>
                        <span className="block text-[11px] text-muted-foreground">
                          {ev.category ?? 'General'} · {ev.city ?? ev.country ?? 'Worldwide'} · {fmtDate(ev.discoveredAt)}
                        </span>
                      </div>
                      <Link href={`/admin/discovery/events?run=${openRun.id}&event=${ev.id}`}>
                        <Btn size="sm" variant="ghost" className="h-6 text-[11px] px-2 text-accent">
                          Inspect <ChevronRight size={11} className="ml-1" />
                        </Btn>
                      </Link>
                    </div>
                  ))}
                  {runDiscoveredEvents.length > 8 && (
                    <div className="pt-1 text-center">
                      <Link href={`/admin/discovery/events?run=${openRun.id}`} className="text-xs font-semibold text-accent hover:underline">
                        View all {runDiscoveredEvents.length} events in Event Catalog →
                      </Link>
                    </div>
                  )}
                </div>
              </Section>
            )}

            <Section title="Configuration used">
              {openRun.configSnapshot ? <pre className="max-h-80 overflow-auto rounded-xl border border-foreground/10 bg-background p-4 font-mono-face text-[11px] leading-relaxed">{JSON.stringify(openRun.configSnapshot, null, 2)}</pre> : <p className="text-sm text-muted-foreground">{NA}</p>}
            </Section>
            <p className="mt-6 text-[11px] text-muted-foreground">Per-step activity inside a run is not recorded by the agent; the records it produced are listed in the feed above and on the discovery/outreach pages.</p>
          </>
        )}
      </Drawer>
    </div>
  );
}
