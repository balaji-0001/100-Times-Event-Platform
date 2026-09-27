import { useMemo, useState } from 'react';
import { Link } from 'wouter';
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

  if (runsQuery.isLoading) return <LoadingState label="Loading agent runs" />;
  if (runsQuery.isError) return <ErrorState error={runsQuery.error} retry={() => runsQuery.refetch()} />;

  const s = (r: AgentRun, k: string) => (r.summary?.[k] ?? 0);

  return (
    <div>
      <PageHeader kicker="Agent Activity" title="What the agents did, and when." subtitle="Run history for both agents, plus a record-level feed built from stored timestamps. The agents do not log intermediate steps, so nothing here is inferred." />
      <div className="mt-6"><Chips<Tab> value={tab} onChange={setTab} options={[{ key: 'discovery', label: 'Organizer Discovery', count: discoveryRuns.data?.length }, { key: 'outreach', label: 'Organizer Outreach', count: outreachRuns.data?.length }]} /></div>

      <Panel className="mt-6 p-6">
        <Section title={`${tab === 'discovery' ? 'Discovery' : 'Outreach'} agent runs (${runs.length})`}>
          {runs.length === 0 ? <EmptyState title="No runs recorded." /> : tab === 'discovery' ? (
            <AdminTable columns={['Run', 'Status', 'Started', 'Completed', 'Duration', 'Discovered', 'New', 'Duplicates', 'Organizers', 'Contacts', 'Needs review', 'Error', '']} minWidth={1300}>
              {runs.map((r) => (
                <tr key={r.id} className="cursor-pointer hover:bg-muted/20" onClick={() => setOpenRun(r)}>
                  <td className={cell}><span className="font-mono-face">#{r.id}</span></td>
                  <td className={cell}><Badge tone={runTone(r.status)}>{r.status}</Badge></td>
                  <td className={cellMuted}>{fmtDateTime(r.startedAt)}</td>
                  <td className={cellMuted}>{fmtDateTime(r.completedAt)}</td>
                  <td className={cellMuted}>{r.status === 'running' ? 'still running' : fmtDuration(r.startedAt, r.completedAt)}</td>
                  <td className={cell}>{s(r, 'events_discovered')}</td><td className={cell}>{s(r, 'new_events')}</td><td className={cellMuted}>{s(r, 'duplicate_events')}</td>
                  <td className={cell}>{s(r, 'organizers_found')}<span className="text-muted-foreground"> ({s(r, 'new_organizers')} new)</span></td><td className={cell}>{s(r, 'contacts_found')}</td><td className={cellMuted}>{s(r, 'events_needing_review')}</td>
                  <td className={cell}>{r.error ? <span className="block max-w-[260px] truncate text-red-600" title={r.error}>{r.error}</span> : <span className="text-muted-foreground">—</span>}</td>
                  <td className={cell}><Btn size="sm" onClick={(e) => { e.stopPropagation(); setOpenRun(r); }}>Details</Btn></td>
                </tr>
              ))}
            </AdminTable>
          ) : (
            <AdminTable columns={['Run', 'Status', 'Started', 'Completed', 'Duration', 'Considered', 'Emails generated', 'Skipped (duplicate)', 'Skipped (suppressed)', 'Skipped (no organizer)', 'Error', '']} minWidth={1200}>
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
            <Section title="Timing"><DL rows={[['Started', fmtDateTime(openRun.startedAt)], ['Completed', fmtDateTime(openRun.completedAt)], ['Duration', openRun.status === 'running' ? 'still running' : fmtDuration(openRun.startedAt, openRun.completedAt)]]} /></Section>
            <Section title="Results"><DL rows={Object.entries(openRun.summary ?? {}).map(([k, v]) => [k.replace(/_/g, ' '), String(v)])} /></Section>
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
