import { useMemo, useState } from 'react';
import { Link, useLocation, useSearch } from 'wouter';
import { Eye, FileText } from 'lucide-react';
import { type AgentRun, discoveryRunTrigger, runCount, useDiscoveredEvents, useDiscoveredOrganizers, useDiscoveryRuns, useOutreachMessages, useOutreachRuns } from './api';
import { buildActivity } from './activity';
import { RunScopeSummaryLine } from './RunScopeDisplay';
import { Breadcrumbs } from './OpsLayout';
import { AdminTable, Badge, Btn, Chips, DL, Drawer, ErrorState, EmptyState, LoadingState, NA, Notice, PageHeader, Panel, Section, cell, cellMuted, cx, fmtDate, fmtDateTime, fmtDuration, fmtTime, parseDate } from './ui';

type Tab = 'discovery' | 'outreach';
type TriggerFilter = 'all' | 'manual' | 'automatic';
const runTone = (s: AgentRun['status']) => (s === 'completed' ? 'good' : s === 'failed' ? 'danger' : 'warn');
const dash = (v: number | null) => (v === null ? '—' : v);
const TRIGGER_LABEL = { manual: 'Manual', automatic: 'Automatic' } as const;

/** A summary value as text; nested objects are shown as JSON instead of "[object Object]". */
const summaryText = (v: unknown) => (v === null || v === undefined ? NA : typeof v === 'object' ? JSON.stringify(v) : String(v));

/**
 * Run history & reports (/admin/discover/runs; /admin/activity redirects here).
 * Discovery runs open their full report at /admin/discover/runs/:id; outreach runs
 * (which have no report page) keep the details drawer.
 */
export function ActivityPage() {
  const search = useSearch();
  const [, setLocation] = useLocation();
  const params = new URLSearchParams(search);
  const tab: Tab = params.get('agent') === 'outreach' ? 'outreach' : 'discovery';
  const triggerParam = params.get('trigger');
  const trigger: TriggerFilter = triggerParam === 'manual' || triggerParam === 'automatic' ? triggerParam : 'all';
  const setParams = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(search);
    for (const [k, v] of Object.entries(next)) { if (v === null) p.delete(k); else p.set(k, v); }
    const qs = p.toString();
    setLocation(`/admin/discover/runs${qs ? `?${qs}` : ''}`, { replace: true });
  };

  const [openRun, setOpenRun] = useState<AgentRun | null>(null);
  const discoveryRuns = useDiscoveryRuns();
  const outreachRuns = useOutreachRuns();
  const events = useDiscoveredEvents();
  const organizers = useDiscoveredOrganizers();
  const messages = useOutreachMessages();

  const runsQuery = tab === 'discovery' ? discoveryRuns : outreachRuns;
  const allRuns = useMemo(() => [...(runsQuery.data ?? [])].sort((a, b) => b.id - a.id), [runsQuery.data]);
  const triggerCounts = useMemo(() => {
    const d = discoveryRuns.data ?? [];
    return { all: d.length, manual: d.filter((r) => discoveryRunTrigger(r) === 'manual').length, automatic: d.filter((r) => discoveryRunTrigger(r) === 'automatic').length };
  }, [discoveryRuns.data]);
  const runs = tab === 'discovery' && trigger !== 'all' ? allRuns.filter((r) => discoveryRunTrigger(r) === trigger) : allRuns;
  const feed = useMemo(() => buildActivity({ events: events.data, organizers: organizers.data, messages: messages.data, runs: [] }).filter((a) => a.agent === tab).slice(0, 100), [events.data, organizers.data, messages.data, tab]);

  const s = (r: AgentRun, k: string) => runCount(r, k);

  const header = (
    <>
      <Breadcrumbs items={[{ label: 'Discover events', href: '/admin/discover' }, { label: 'Run history & reports' }]} />
      <PageHeader
        kicker="Discover events"
        title="Run history & reports"
        subtitle="Every discovery run — started by an admin or by automatic discovery — with its results and a full report. Outreach batches are listed on their own tab."
        actions={<Link href="/admin/discover" className="button-press inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground">Run discovery</Link>}
      />
    </>
  );

  return (
    <div>
      {header}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <Chips<Tab> value={tab} onChange={(t) => setParams({ agent: t === 'outreach' ? 'outreach' : null, trigger: null })} options={[{ key: 'discovery', label: 'Discovery runs', count: discoveryRuns.data?.length }, { key: 'outreach', label: 'Outreach batches', count: outreachRuns.data?.length }]} />
        {tab === 'discovery' && (
          <Chips<TriggerFilter> value={trigger} onChange={(t) => setParams({ trigger: t === 'all' ? null : t })} options={[
            { key: 'all', label: 'All', count: discoveryRuns.data ? triggerCounts.all : undefined },
            { key: 'manual', label: 'Manual', count: discoveryRuns.data ? triggerCounts.manual : undefined },
            { key: 'automatic', label: 'Automatic', count: discoveryRuns.data ? triggerCounts.automatic : undefined },
          ]} />
        )}
      </div>

      {runsQuery.isLoading ? <div className="mt-6"><LoadingState label="Loading runs" /></div> : runsQuery.isError ? <div className="mt-6"><ErrorState error={runsQuery.error} retry={() => runsQuery.refetch()} /></div> : (
        <Panel className="mt-6 p-6">
          <Section title={`${tab === 'discovery' ? `${trigger === 'all' ? 'Discovery' : TRIGGER_LABEL[trigger]} runs` : 'Outreach batches'} (${runs.length})`}>
            {runs.length === 0 ? (
              <EmptyState title={tab === 'discovery' && trigger !== 'all' ? `No ${trigger} runs recorded.` : 'No runs recorded.'} body={tab === 'discovery' ? 'Start one from Run discovery, or switch on Automatic discovery.' : undefined} />
            ) : tab === 'discovery' ? (
              <AdminTable columns={['Run', 'Status', 'Started by', 'Scope (country · city · sectors)', 'Started', 'Duration', 'Verified', 'New', 'Needs review', 'Rejected', 'Organizers', 'Error', '']} minWidth={1380}>
                {runs.map((r) => {
                  const fresh = s(r, 'new_events');
                  const trig = discoveryRunTrigger(r);
                  const organizersFound = s(r, 'organizers_found');
                  const newOrganizers = s(r, 'new_organizers');
                  return (
                    <tr key={r.id} className="cursor-pointer hover:bg-muted/20" onClick={() => setLocation(`/admin/discover/runs/${r.id}`)}>
                      <td className={cell}><Link href={`/admin/discover/runs/${r.id}`} onClick={(e) => e.stopPropagation()} className="font-mono-face font-bold text-accent hover:underline">#{r.id}</Link></td>
                      <td className={cell}><Badge tone={runTone(r.status)}>{r.status}</Badge></td>
                      <td className={cellMuted}>{trig ? TRIGGER_LABEL[trig] : '—'}</td>
                      <td className={cell} style={{ minWidth: 180, maxWidth: 260 }}><RunScopeSummaryLine run={r} /></td>
                      <td className={cellMuted}>{fmtDateTime(r.startedAt)}</td>
                      <td className={cellMuted}>{r.status === 'running' ? 'still running' : fmtDuration(r.startedAt, r.completedAt)}</td>
                      <td className={cell}>{dash(s(r, 'verified_events'))}</td>
                      <td className={cell}>{fresh !== null && fresh > 0 ? <span className="font-bold text-accent">{fresh}</span> : dash(fresh)}</td>
                      <td className={cellMuted}>{dash(s(r, 'events_needing_review'))}</td>
                      <td className={cellMuted}>{dash(s(r, 'rejected_events'))}</td>
                      <td className={cell}>{dash(organizersFound)}{newOrganizers !== null && <span className="text-muted-foreground"> ({newOrganizers} new)</span>}</td>
                      <td className={cell}>{r.error ? <span className="block max-w-[200px] truncate text-red-600 dark:text-red-300" title={r.error}>{r.error}</span> : <span className="text-muted-foreground">—</span>}</td>
                      <td className={cell}>
                        <div className="flex items-center gap-1.5 whitespace-nowrap">
                          <Link href={`/admin/discover/runs/${r.id}`} onClick={(e) => e.stopPropagation()} className="button-press inline-flex items-center gap-1 rounded-full border border-foreground/15 bg-background px-3 py-1 text-[11px] font-bold hover:border-accent hover:text-accent">
                            <FileText size={12} /> Report
                          </Link>
                          {fresh !== null && fresh > 0 && (
                            <Link href={`/admin/discovery/events?run=${r.id}`} onClick={(e) => e.stopPropagation()} title={`Open the events run #${r.id} added`}
                              className="button-press inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-[11px] font-bold text-accent hover:bg-accent/20">
                              <Eye size={12} /> View {fresh} new event{fresh === 1 ? '' : 's'}
                            </Link>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
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
                    <td className={cell}>{dash(s(r, 'candidates_considered'))}</td><td className={cell}>{dash(s(r, 'drafted'))}</td>
                    <td className={cellMuted}>{dash(s(r, 'skipped_duplicate'))}</td><td className={cellMuted}>{dash(s(r, 'skipped_suppressed'))}</td><td className={cellMuted}>{dash(s(r, 'skipped_no_organizer'))}</td>
                    <td className={cell}>{r.error ? <span className="block max-w-[260px] truncate text-red-600 dark:text-red-300" title={r.error}>{r.error}</span> : <span className="text-muted-foreground">—</span>}</td>
                    <td className={cell}><Btn size="sm" onClick={(e) => { e.stopPropagation(); setOpenRun(r); }}>Details</Btn></td>
                  </tr>
                ))}
              </AdminTable>
            )}
            {runs.some((r) => r.status === 'running' && Date.now() - (parseDate(r.startedAt)?.getTime() ?? Date.now()) > 2 * 3600 * 1000) && (
              <div className="mt-3"><Notice tone="warn">A run has been marked “running” for more than two hours — it most likely stopped without recording a result (for example, the server restarted mid-run).</Notice></div>
            )}
            {tab === 'discovery' && <p className="mt-3 text-[11px] text-muted-foreground">Shows the latest 100 runs. “Started by” is read from each run's stored configuration; runs recorded before that was stored show “—”.</p>}
          </Section>
        </Panel>
      )}

      <Panel className="mt-6 p-6">
        <Section title={tab === 'discovery' ? 'Discovery feed — events found' : 'Outreach feed — organizers contacted'}>
          {feed.length === 0 ? <p className="text-sm text-muted-foreground">No records yet.</p> : (
            <ol className="divide-y divide-foreground/10 text-sm">
              {feed.map((a) => (
                <li key={a.id} className="flex items-start gap-4 py-2.5">
                  <span className="w-[7.5rem] shrink-0 font-mono-face text-[10px] leading-5 text-muted-foreground">{fmtDate(a.at)}<br />{fmtTime(a.at)}</span>
                  <div className="min-w-0">{a.href ? <Link href={a.href} className={cx('font-semibold hover:underline', a.tone === 'danger' && 'text-red-700 dark:text-red-300')}>{a.title}</Link> : <p className="font-semibold">{a.title}</p>}{a.detail && <p className="text-xs text-muted-foreground">{a.detail}</p>}</div>
                </li>
              ))}
            </ol>
          )}
        </Section>
      </Panel>

      {/* Outreach batches only — discovery runs have a full report page. */}
      <Drawer open={Boolean(openRun)} onClose={() => setOpenRun(null)} kicker={openRun ? 'Outreach batch' : ''} title={openRun ? `Run #${openRun.id} — ${openRun.status}` : ''}>
        {openRun && (
          <>
            {openRun.error && <Notice tone="danger"><strong>Error:</strong> {openRun.error}</Notice>}
            <Section title="Timing"><DL rows={[['Started', fmtDateTime(openRun.startedAt)], ['Completed', fmtDateTime(openRun.completedAt)], ['Duration', openRun.status === 'running' ? 'still running' : fmtDuration(openRun.startedAt, openRun.completedAt)]]} /></Section>
            <Section title="Results"><DL rows={Object.entries(openRun.summary ?? {}).map(([k, v]) => [k.replace(/_/g, ' '), summaryText(v)])} /></Section>
            <Section title="Configuration used">
              {openRun.configSnapshot ? <pre className="max-h-80 overflow-auto rounded-xl border border-foreground/10 bg-background p-4 font-mono-face text-[11px] leading-relaxed">{JSON.stringify(openRun.configSnapshot, null, 2)}</pre> : <p className="text-sm text-muted-foreground">{NA}</p>}
            </Section>
            <div className="mt-6 flex flex-wrap gap-2">
              <Link href="/admin/outreach/pending" className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">Pending outreach →</Link>
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
}
