// Live (or final) progress of one discovery run, stage by stage. Every number is
// read from the run's stored summary (`summary`, `summary.timings`,
// `summary.sources`) — a counter an older run never recorded shows "—".

import { useEffect, useRef, useState } from 'react';
import { Link } from 'wouter';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Check, Circle, FileText, Loader2, Minus, Square, X } from 'lucide-react';
import { type AgentRun, keys, useDiscoveryRun, useDiscoveryRunEvents, useStopDiscoveryRun } from './api';
import { Badge, Btn, Kicker, Notice, cx, parseDate } from './ui';

export const DASH = '—';

export type StageStatus = 'pending' | 'running' | 'completed' | 'stopped' | 'failed';

const STATUS_LABEL: Record<StageStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  stopped: 'Stopped',
  failed: 'Failed',
};
const STATUS_TONE: Record<StageStatus, 'neutral' | 'info' | 'good' | 'warn' | 'danger'> = {
  pending: 'neutral',
  running: 'info',
  completed: 'good',
  stopped: 'warn',
  failed: 'danger',
};

export const RUN_STATUS_LABEL: Record<AgentRun['status'], string> = {
  running: 'Running',
  completed: 'Completed',
  stopped: 'Stopped',
  failed: 'Failed',
};
export const runStatusTone = (s: AgentRun['status']) =>
  s === 'completed' ? 'good' : s === 'failed' ? 'danger' : s === 'running' ? 'info' : 'warn';

/** A real count, or null when the run never recorded it. */
export const count = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
export const showCount = (v: number | null) => (v === null ? DASH : v.toLocaleString('en-IN'));

/** Plain-language reason a run ended (`summary.stop_reason`). */
export function stopReasonText(run: AgentRun): string | null {
  const reason = run.summary?.stop_reason;
  if (typeof reason !== 'string' || !reason) return null;
  const target = count(run.configSnapshot?.target_valid_events);
  const maxSeconds = count(run.configSnapshot?.max_run_seconds);
  switch (reason) {
    case 'target_reached':
      return target !== null ? `Reached the goal of ${target} verified events.` : 'Reached the goal.';
    case 'sources_exhausted':
      return 'Used every planned search and source — nothing left to try.';
    case 'time_budget':
      return maxSeconds !== null ? `Hit the ${Math.round(maxSeconds / 60)}-minute time limit.` : 'Hit the time limit.';
    case 'candidate_ceiling':
      return "Reached the run's candidate or daily limit.";
    case 'cancelled':
      return 'Stopped by an admin.';
    default:
      return reason.replace(/_/g, ' ');
  }
}

export function fmtElapsed(ms: number | null): string {
  if (ms === null || ms < 0) return DASH;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/** Wall-clock length of a run; a running one is measured up to `now`. */
export function runElapsedMs(run: AgentRun, now: number): number | null {
  const start = parseDate(run.startedAt);
  if (!start) return null;
  if (run.status === 'running') return now - start.getTime();
  const end = parseDate(run.completedAt);
  return end ? end.getTime() - start.getTime() : null;
}

/** A stopped run whose worker has not yet written its final summary (it finishes the step in hand first). */
function awaitingFinalSummary(run: AgentRun): boolean {
  if (run.status !== 'stopped' || run.summary?.stop_reason) return false;
  const end = parseDate(run.completedAt);
  return Boolean(end && Date.now() - end.getTime() < 120_000);
}

export const isRunLive = (run: AgentRun) => run.status === 'running' || awaitingFinalSummary(run);

interface Metric {
  label: string;
  value: number | null;
  /** Shown as "value of N" when known. */
  of?: number | null;
}

interface Stage {
  key: 'plan' | 'collect' | 'read' | 'screen' | 'organizer' | 'decide';
  name: string;
  description: string;
  metrics: Metric[];
  note?: string | null;
  /** The run recorded work in this stage. */
  active: boolean;
}

const positive = (...values: Array<number | null>) => values.some((v) => v !== null && v > 0);

function scopeNote(scope: Record<string, any> | undefined): string | null {
  if (!scope || typeof scope !== 'object' || Object.keys(scope).length === 0) return null;
  const parts: string[] = [];
  if (scope.worldwide) parts.push('Worldwide');
  else if (Array.isArray(scope.countries)) parts.push(`${scope.countries.length} countr${scope.countries.length === 1 ? 'y' : 'ies'}`);
  if (typeof scope.cities === 'number' && scope.cities > 0) parts.push(`${scope.cities} cit${scope.cities === 1 ? 'y' : 'ies'}`);
  if (Array.isArray(scope.sectors)) parts.push(`${scope.sectors.length} sector${scope.sectors.length === 1 ? '' : 's'}`);
  return parts.length ? `Scope: ${parts.join(' · ')}` : null;
}

export function buildStages(run: AgentRun): Stage[] {
  const s = run.summary ?? {};
  const t: Record<string, unknown> = s.timings && typeof s.timings === 'object' ? s.timings : {};
  const src = s.sources?.counts && typeof s.sources.counts === 'object' ? s.sources.counts : null;
  const target = count(run.configSnapshot?.target_valid_events);

  const plannedQueries = count(t.planned_queries);
  const plannedReads = count(t.planned_source_reads);
  const searches = count(t.searches);
  const searchResults = count(t.search_results);
  const executed = count(src?.executed);
  const succeeded = count(src?.successful);
  const failedSources = count(src?.failed);
  const pagesRead = count(t.pages_read);
  const screened = count(t.screened);
  const passed = count(t.passed_screening);
  const duplicates = count(s.duplicate_events);
  const lookups = count(t.organizer_lookups);
  const organizers = count(s.organizers_found);
  const verified = count(s.verified_events);
  const review = count(s.events_needing_review);
  const rejected = count(s.rejected_events);
  const saved = count(s.new_events);

  const stages: Stage[] = [
    {
      key: 'plan',
      name: 'Plan',
      description: 'Turn your choices into searches and source pages to read.',
      metrics: [
        { label: 'Searches planned', value: plannedQueries },
        { label: 'Source pages planned', value: plannedReads },
      ],
      note: scopeNote(s.scope),
      active: plannedQueries !== null || plannedReads !== null,
    },
    {
      key: 'collect',
      name: 'Collect',
      description: 'Run the searches and read directories and listing sites.',
      metrics: [
        { label: 'Searches run', value: searches, of: plannedQueries },
        { label: 'Search results', value: searchResults },
        { label: 'Sources executed', value: executed },
        { label: 'Succeeded', value: succeeded },
        { label: 'Failed', value: failedSources },
      ],
      active: positive(searches, searchResults, executed),
    },
    {
      key: 'read',
      name: 'Read pages',
      description: 'Open result pages and pull out event details.',
      metrics: [{ label: 'Pages read', value: pagesRead }],
      active: positive(pagesRead),
    },
    {
      key: 'screen',
      name: 'Screen',
      description: 'Check sector, place, dates and duplicates.',
      metrics: [
        { label: 'Screened', value: screened },
        { label: 'Passed', value: passed },
        { label: 'Duplicates skipped', value: duplicates },
      ],
      active: positive(screened),
    },
    {
      key: 'organizer',
      name: 'Find organizer',
      description: 'Look up who runs each event and a public contact.',
      metrics: [
        { label: 'Organizer checks', value: lookups, of: passed },
        { label: 'Organizers found', value: organizers },
      ],
      active: positive(lookups),
    },
    {
      key: 'decide',
      name: 'Decide & save',
      description: 'Apply your rules and save each event.',
      metrics: [
        { label: 'Verified', value: verified, of: target },
        { label: 'Needs review', value: review },
        { label: 'Rejected', value: rejected },
        { label: 'New events saved', value: saved },
      ],
      active: positive(verified, review, rejected, saved),
    },
  ];
  // Every candidate is planned, collected and screened before it is decided, so later work proves
  // those stages ran even when an older run never stored their own counters (which still show "—").
  // Reading result pages and organizer lookups are not on every path, so they are never inferred.
  const [plan, collect, read, screen, organizer, decide] = stages;
  screen.active ||= organizer.active || decide.active;
  collect.active ||= read.active || screen.active;
  plan.active ||= collect.active;
  return stages;
}

/** Honest per-stage status, derived only from the run's status and recorded activity. */
export function stageStatus(run: AgentRun, stage: Stage): StageStatus {
  switch (run.status) {
    case 'running':
      if (stage.key === 'plan') return stage.active ? 'completed' : 'running';
      return stage.active ? 'running' : 'pending';
    case 'completed':
      return 'completed';
    case 'stopped':
      return stage.active ? 'completed' : 'stopped';
    case 'failed':
      return stage.active ? 'stopped' : 'failed';
    default:
      return 'pending';
  }
}

function StageIcon({ status }: { status: StageStatus }) {
  const base = 'grid h-6 w-6 shrink-0 place-items-center rounded-full border';
  switch (status) {
    case 'completed':
      return <span className={cx(base, 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300')}><Check size={13} /></span>;
    case 'running':
      return <span className={cx(base, 'border-sky-500/40 bg-sky-500/10 text-sky-600 dark:text-sky-300')}><Loader2 size={13} className="motion-safe:animate-spin" /></span>;
    case 'stopped':
      return <span className={cx(base, 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-300')}><Minus size={13} /></span>;
    case 'failed':
      return <span className={cx(base, 'border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-300')}><X size={13} /></span>;
    default:
      return <span className={cx(base, 'border-foreground/15 bg-muted text-muted-foreground')}><Circle size={9} /></span>;
  }
}

/** Re-renders every second while `active`, for a live elapsed-time clock. */
function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

/** Verified events of a live run, shown as each one is saved. */
function LatestVerified({ runId }: { runId: number }) {
  const events = useDiscoveryRunEvents(runId, true);
  const verified = (events.data ?? []).filter((e) => e.verificationStatus === 'VERIFIED');
  if (!verified.length) return null;
  return (
    <div className="mt-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3">
      <p className="text-[11px] font-semibold">Verified so far ({verified.length})</p>
      <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto pr-1 text-[11px]">
        {verified.slice(0, 20).map((e) => (
          <li key={e.id} className="flex justify-between gap-2">
            <Link href={`/admin/discovery/events?event=${e.id}`} className="truncate font-medium hover:text-accent hover:underline">
              {e.name ?? `Event #${e.id}`}
            </Link>
            <span className="shrink-0 text-muted-foreground">{[e.eventDate ?? e.date, e.country].filter(Boolean).join(' · ')}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RunProgress({
  run: initialRun,
  live,
  showReportLink = true,
  onDismiss,
  className,
}: {
  run: AgentRun;
  /** Keep the run fresh (polls while it is running). */
  live: boolean;
  /** Hide the "View report" link when already on the report. */
  showReportLink?: boolean;
  /** Offered once the run has finished (e.g. to clear it from the wizard). */
  onDismiss?: () => void;
  className?: string;
}) {
  const qc = useQueryClient();
  // Poll while the newest copy we have (the cache, else the prop) says the run is still going.
  const cached = qc.getQueryData<AgentRun>(['ops', 'discovery-run', initialRun.id]);
  const polled = useDiscoveryRun(initialRun.id, live && isRunLive(cached ?? initialRun));
  const run = polled.data && polled.data.id === initialRun.id ? polled.data : initialRun;
  const stop = useStopDiscoveryRun();
  // Ticks the elapsed clock, and re-evaluates the "awaiting final summary" window so polling ends.
  const now = useNow(isRunLive(run));

  // When the run finishes, refresh the lists that show its results.
  const prevStatus = useRef(run.status);
  useEffect(() => {
    if (prevStatus.current === 'running' && run.status !== 'running') {
      qc.invalidateQueries({ queryKey: keys.events });
      qc.invalidateQueries({ queryKey: keys.organizers });
      qc.invalidateQueries({ queryKey: keys.discoveryRuns });
      qc.invalidateQueries({ queryKey: keys.discoveryStats });
      qc.invalidateQueries({ queryKey: keys.discoveryActiveRun });
      qc.invalidateQueries({ queryKey: ['discoveryRunEvents'] });
    }
    prevStatus.current = run.status;
  }, [run.status, qc]);

  const stages = buildStages(run);
  const s = run.summary ?? {};
  const target = count(run.configSnapshot?.target_valid_events);
  const verified = count(s.verified_events);
  const newEvents = count(s.new_events);
  const shortfall = count(s.target_shortfall);
  const reason = stopReasonText(run);
  const running = run.status === 'running';
  const finished = !running;
  const pct = target && verified !== null ? Math.min(100, Math.round((verified / target) * 100)) : null;

  return (
    <section
      aria-label={`Discovery run ${run.id} progress`}
      className={cx('rounded-2xl border bg-card p-5', running ? 'border-accent/40' : 'border-foreground/10', className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Kicker>{running ? 'Run in progress' : 'Run finished'}</Kicker>
          <h2 className="mt-1 flex flex-wrap items-center gap-2 font-display text-xl font-bold">
            {running && (
              <span className="relative flex h-2.5 w-2.5" aria-hidden="true">
                <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-60 motion-safe:animate-ping" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-accent" />
              </span>
            )}
            Run #{run.id}
            <Badge tone={runStatusTone(run.status)}>{RUN_STATUS_LABEL[run.status] ?? run.status}</Badge>
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {running ? 'Elapsed' : 'Took'} <span className="font-mono-face text-foreground">{fmtElapsed(runElapsedMs(run, now))}</span>
            {reason && <> · {reason}</>}
            {finished && shortfall !== null && shortfall > 0 && <> · {shortfall} short of the goal</>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {running && (
            <Btn
              variant="danger"
              size="sm"
              loading={stop.isPending}
              onClick={() =>
                stop.mutate(run.id, { onSuccess: () => qc.invalidateQueries({ queryKey: ['ops', 'discovery-run', run.id] }) })
              }
            >
              <Square size={11} className="fill-current" /> Stop run
            </Btn>
          )}
          {finished && onDismiss && (
            <Btn variant="ghost" size="sm" onClick={onDismiss} aria-label={`Hide run ${run.id}`}>
              <X size={12} /> Hide
            </Btn>
          )}
        </div>
      </div>

      {running && (
        <p className="mt-3 text-[11px] text-muted-foreground">
          This run keeps going on the server if you leave this page — come back any time to see where it is. Stopping keeps everything found so far.
        </p>
      )}
      {stop.isError && <div className="mt-3"><Notice tone="danger">Could not stop the run: {(stop.error as Error)?.message}</Notice></div>}
      {run.status === 'stopped' && awaitingFinalSummary(run) && (
        <div className="mt-3"><Notice tone="info">Stopping — the run is finishing the step in hand and writing its final counts.</Notice></div>
      )}
      {run.status === 'failed' && (
        <div className="mt-3"><Notice tone="danger">This run failed{run.error ? `: ${run.error}` : '. No error message was recorded.'}</Notice></div>
      )}
      {run.status !== 'failed' && run.error && (
        <div className="mt-3"><Notice tone="warn">{run.error}</Notice></div>
      )}

      {target !== null && (
        <div className="mt-4">
          <div className="flex items-center justify-between text-[11px]">
            <span className="font-semibold">Goal: {target} verified events</span>
            <span className="font-mono-face text-muted-foreground">{showCount(verified)} / {target}</span>
          </div>
          <div
            className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label="Verified events toward the goal"
            aria-valuemin={0}
            aria-valuemax={target}
            aria-valuenow={verified ?? undefined}
          >
            <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${pct ?? 0}%` }} />
          </div>
        </div>
      )}

      <ol className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {stages.map((stage, i) => {
          const status = stageStatus(run, stage);
          return (
            <li
              key={stage.key}
              className={cx(
                'rounded-xl border p-3',
                status === 'running' ? 'border-sky-500/30 bg-sky-500/5' : 'border-foreground/10 bg-background/60',
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2">
                  <StageIcon status={status} />
                  <div className="min-w-0">
                    <p className="text-xs font-bold">
                      <span className="text-muted-foreground">{i + 1}.</span> {stage.name}
                    </p>
                    <p className="text-[10px] leading-snug text-muted-foreground">{stage.description}</p>
                  </div>
                </div>
                <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>
              </div>
              <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
                {stage.metrics.map((m) => (
                  <div key={m.label} className="min-w-0">
                    <dt className="truncate font-mono-face text-[9px] uppercase tracking-wider text-muted-foreground">{m.label}</dt>
                    <dd className="font-mono-face font-bold">
                      {showCount(m.value)}
                      {m.of !== undefined && m.of !== null && m.value !== null && (
                        <span className="font-normal text-muted-foreground"> of {showCount(m.of)}</span>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
              {stage.note && <p className="mt-2 text-[10px] text-muted-foreground">{stage.note}</p>}
            </li>
          );
        })}
      </ol>

      {running && <LatestVerified runId={run.id} />}

      {finished && (
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-foreground/10 pt-4">
          {showReportLink && (
            <Link href={`/admin/discover/runs/${run.id}`} className={linkButton('secondary')}>
              <FileText size={13} /> View report
            </Link>
          )}
          <Link href={`/admin/discovery/events?run=${run.id}`} className={linkButton('primary')}>
            View {newEvents !== null ? `${newEvents} ` : ''}new event{newEvents === 1 ? '' : 's'} <ArrowRight size={13} />
          </Link>
        </div>
      )}
    </section>
  );
}

/** The Btn look for a wouter Link (an <a> must not wrap a <button>). */
export function linkButton(variant: 'primary' | 'secondary' = 'secondary', size: 'sm' | 'md' = 'md') {
  return cx(
    'button-press inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background',
    size === 'sm' ? 'px-3 py-1 text-[11px]' : 'px-4 py-2 text-xs',
    variant === 'primary'
      ? 'bg-accent text-accent-foreground hover:bg-primary hover:text-primary-foreground'
      : 'border border-foreground/15 bg-background hover:border-accent hover:text-accent',
  );
}
