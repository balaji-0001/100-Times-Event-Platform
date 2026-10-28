// Report for one discovery run (/admin/discover/runs/:id): what it was asked to
// do, how each stage went, what every source returned and the search calls it
// made. All values come from the stored run; missing counters show "—".

import { useState } from 'react';
import { Link, useParams } from 'wouter';
import { ArrowLeft, ArrowRight, RotateCcw, Search } from 'lucide-react';
import { type AgentRun, type RunSourceReport, apiErrorStatus, useDiscoveryRunReport } from './api';
import { RunScopeDisplay } from './RunScopeDisplay';
import { RunSourcesReport } from './RunSourcesReport';
import { DASH, RUN_STATUS_LABEL, RunProgress, count, fmtElapsed, isRunLive, linkButton, runElapsedMs, runStatusTone, showCount, stopReasonText } from './RunProgress';
import { Badge, Btn, EmptyState, ErrorState, ExtLink, LoadingState, PageHeader, Panel, Section, StatCard, cx, fmtDateTime } from './ui';

interface SearchLogEntry {
  provider_id?: string;
  provider_name?: string;
  query?: string;
  status?: string;
  result_count?: number;
  latency_ms?: number;
  error?: string | null;
  purpose?: string;
  timestamp?: string;
}

const PURPOSE_LABEL: Record<string, string> = {
  discovery: 'Event search',
  organizer_lookup: 'Organizer lookup',
};

function SearchLog({ entries }: { entries: SearchLogEntry[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? entries : entries.slice(0, 20);
  return (
    <div className="overflow-hidden rounded-2xl border border-foreground/10 bg-card">
      <div className="max-h-[60vh] overflow-auto">
        <table className="w-full min-w-[640px] text-left text-[11px]">
          <thead className="sticky top-0 border-b border-foreground/10 bg-muted/90 font-mono-face text-[10px] uppercase text-muted-foreground backdrop-blur">
            <tr>
              <th className="p-3 font-normal">Provider</th>
              <th className="p-3 font-normal">Query</th>
              <th className="p-3 font-normal">For</th>
              <th className="p-3 font-normal">Result</th>
              <th className="p-3 text-right font-normal">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-foreground/10">
            {shown.map((e, i) => {
              const ok = e.status === 'SUCCESS';
              return (
                <tr key={i} className="align-top">
                  <td className="p-3 font-semibold">{e.provider_name || e.provider_id || DASH}</td>
                  <td className="max-w-[360px] break-words p-3 font-mono-face text-muted-foreground">
                    {e.query || DASH}
                    {e.error && <span className="mt-0.5 block text-red-600 dark:text-red-400">{e.error}</span>}
                  </td>
                  <td className="whitespace-nowrap p-3 text-muted-foreground">{(e.purpose && PURPOSE_LABEL[e.purpose]) || e.purpose || DASH}</td>
                  <td className="whitespace-nowrap p-3">
                    {ok ? (
                      <Badge tone={e.result_count ? 'good' : 'warn'}>{typeof e.result_count === 'number' ? `${e.result_count} results` : 'OK'}</Badge>
                    ) : (
                      <Badge tone="danger">{(e.status ?? 'unknown').replace(/_/g, ' ').toLowerCase()}</Badge>
                    )}
                  </td>
                  <td className="whitespace-nowrap p-3 text-right font-mono-face text-muted-foreground">
                    {typeof e.latency_ms === 'number' ? `${Math.round(e.latency_ms)} ms` : DASH}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {entries.length > 20 && (
        <div className="border-t border-foreground/10 p-3 text-center">
          <Btn size="sm" variant="ghost" onClick={() => setAll(!all)} aria-expanded={all}>
            {all ? 'Show the first 20' : `Show all ${entries.length} calls`}
          </Btn>
        </div>
      )}
    </div>
  );
}

function ReportHeader({ run }: { run: AgentRun }) {
  const s = run.summary ?? {};
  const target = count(run.configSnapshot?.target_valid_events);
  const shortfall = count(s.target_shortfall);
  const manual = run.configSnapshot?.is_manual;
  return (
    <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="Status"
        value={<Badge tone={runStatusTone(run.status)}>{RUN_STATUS_LABEL[run.status] ?? run.status}</Badge>}
        sub={manual === true ? 'Started by an admin' : manual === false ? 'Automatic run' : undefined}
      />
      <StatCard label="Started" value={<span className="text-base">{fmtDateTime(run.startedAt)}</span>} sub={run.completedAt ? `Finished ${fmtDateTime(run.completedAt)}` : run.status === 'running' ? 'Still running' : 'No finish time recorded'} />
      <StatCard label="Duration" value={<span className="text-lg">{fmtElapsed(runElapsedMs(run, Date.now()))}</span>} sub={stopReasonText(run) ?? (run.status === 'running' ? 'In progress' : run.status === 'failed' ? 'Ended with an error' : 'No stop reason recorded')} />
      <StatCard
        label="Verified vs goal"
        value={
          <span className="text-lg">
            {showCount(count(s.verified_events))}
            {target !== null && <span className="text-muted-foreground"> / {target}</span>}
          </span>
        }
        sub={shortfall !== null ? (shortfall > 0 ? `${shortfall} short of the goal` : 'Goal reached') : target === null ? 'No goal recorded' : DASH}
        tone={shortfall === null ? undefined : shortfall > 0 ? 'warn' : 'good'}
      />
    </div>
  );
}

export function RunReportPage() {
  const { id } = useParams<{ id: string }>();
  const runId = Number(id);
  const valid = Number.isInteger(runId) && runId > 0;
  const q = useDiscoveryRunReport(valid ? runId : null);

  const back = (
    <Link href="/admin/discover/runs" className={linkButton('secondary')}>
      <ArrowLeft size={13} /> Back to run history
    </Link>
  );

  if (!valid) {
    return (
      <div className="page-enter">
        <PageHeader kicker="Discover events" title="Run report" actions={back} />
        <div className="mt-6">
          <EmptyState title="That isn't a run number." body="Open a run from the run history." />
        </div>
      </div>
    );
  }
  if (q.isLoading) return <LoadingState label={`Loading run #${runId}`} />;
  if (q.isError || !q.data) {
    const missing = apiErrorStatus(q.error) === 404;
    return (
      <div className="page-enter">
        <PageHeader kicker="Discover events" title={`Run #${runId}`} actions={back} />
        <div className="mt-6">
          {missing ? (
            <EmptyState title={`Run #${runId} doesn't exist.`} body="It may have been removed, or the link is wrong." />
          ) : (
            <ErrorState error={q.error} retry={() => q.refetch()} title="Could not load this run." />
          )}
        </div>
      </div>
    );
  }

  const run = q.data;
  const s = run.summary ?? {};
  const newEvents = count(s.new_events);
  const logs: SearchLogEntry[] = Array.isArray(s.search_provider_logs) ? s.search_provider_logs : [];
  const hasSnapshot = Boolean(run.configSnapshot && Object.keys(run.configSnapshot).length);
  const live = isRunLive(run);

  const actions = (
    <>
      {back}
      {hasSnapshot && (
        <Link href={`/admin/discover?from=${run.id}`} className={linkButton('secondary')}>
          <RotateCcw size={13} /> Run again with these settings
        </Link>
      )}
      <Link href={`/admin/discovery/events?run=${run.id}`} className={linkButton('primary')}>
        View {newEvents !== null ? `${newEvents} ` : ''}new event{newEvents === 1 ? '' : 's'} <ArrowRight size={13} />
      </Link>
    </>
  );

  return (
    <div className="page-enter">
      <PageHeader
        kicker="Discover events · Run report"
        title={`Run #${run.id}`}
        subtitle={live ? 'This run is still going — the numbers below update by themselves.' : 'What this run was asked to do, how each stage went, and what every source returned.'}
        actions={actions}
      />
      {!hasSnapshot && <p className="mt-3 text-[11px] text-muted-foreground">This run has no stored settings, so it can't be re-run from here.</p>}

      <ReportHeader run={run} />

      <Panel className="mt-6 p-5 sm:p-6">
        <Section title="What it searched">
          <RunScopeDisplay run={run} title="Scope" />
        </Section>
      </Panel>

      <div className="mt-6">
        <RunProgress run={run} live={live} showReportLink={false} />
      </div>

      <Panel className="mt-6 p-5 sm:p-6">
        <Section title="Sources">
          {s.sources?.counts ? (
            <RunSourcesReport report={s.sources as RunSourceReport} defaultOpen />
          ) : (
            <p className="text-xs text-muted-foreground">This run did not record a per-source report.</p>
          )}
        </Section>
      </Panel>


      {logs.length > 0 && (
        <Panel className="mt-6 p-5 sm:p-6">
          <Section
            title={`Search calls (${logs.length})`}
            aside={
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <Search size={11} /> {logs.filter((l) => l.status === 'SUCCESS').length} succeeded
              </span>
            }
          >
            <SearchLog entries={logs} />
          </Section>
        </Panel>
      )}

      <div className="mt-8 flex flex-wrap items-center gap-2 border-t border-foreground/10 pt-5">{actions}</div>
    </div>
  );
}
