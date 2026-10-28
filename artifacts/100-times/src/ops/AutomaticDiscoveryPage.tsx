import { type ReactNode, useMemo, useState } from 'react';
import { Link } from 'wouter';
import { ArrowRight, Clock, Pencil, Power } from 'lucide-react';
import {
  type AgentRun,
  type DiscoveryAutoStatus,
  type DiscoveryCatalog,
  discoveryRunTrigger,
  runCount,
  useDiscoveryAutoStatus,
  useDiscoveryCatalog,
  useDiscoveryRuns,
  useSetDiscoveryAuto,
} from './api';
import { Breadcrumbs } from './OpsLayout';
import { AdminTable, Badge, Btn, EmptyState, ErrorState, LoadingState, Notice, PageHeader, Panel, Section, Switch, cell, cellMuted, cx, fmtDateTime, fmtDuration } from './ui';

const runTone = (s: AgentRun['status']) => (s === 'completed' ? 'good' : s === 'failed' ? 'danger' : 'warn');
const dash = (v: number | null) => (v === null ? '—' : v);

/** "A, B, C +4 more" — every name is from the saved settings. */
function NameList({ names, max = 8, empty }: { names: string[]; max?: number; empty: ReactNode }) {
  if (names.length === 0) return <span className="text-muted-foreground">{empty}</span>;
  return <span>{names.slice(0, max).join(', ')}{names.length > max && <span className="text-muted-foreground"> +{names.length - max} more</span>}</span>;
}

function SummaryRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground sm:pt-0.5">{label}</dt>
      <dd className="break-words text-sm">{children}</dd>
    </div>
  );
}

/** Read-only summary of the saved configuration, worded from the saved values only. */
function SavedConfigSummary({ a, catalog }: { a: DiscoveryAutoStatus; catalog?: DiscoveryCatalog }) {
  const countries = a.countries && a.countries.length ? a.countries : a.country ? [a.country] : [];
  const noPlace = countries.length === 0 && (a.states ?? []).length === 0 && (a.cities ?? []).length === 0;
  const sources = a.sources ?? [];
  const web = sources.includes('web');
  const directories = sources.includes('global_adapters');
  const aggregators = sources.includes('consumer_aggregators') || sources.includes('event_platforms');
  const catalogIds = new Set((catalog?.sources ?? []).map((s) => s.id));
  const namedSources = sources.filter((id) => catalogIds.has(id));
  const providerNames = a.searchProviders == null
    ? null
    : a.searchProviders.map((id) => catalog?.providers.find((p) => p.id === id)?.name ?? id);
  const rules = [
    a.rejectPastEvents && 'past events',
    a.rejectUnparseableDates && 'unclear dates',
    a.rejectMissingLocation && 'no location',
    a.rejectMissingTicketUrl && 'no ticket link',
    a.rejectNoOrganizer && 'no organizer',
    a.requireOrganizerEmail && 'no organizer e-mail',
    a.requireOrganizerPhone && 'no organizer phone',
    a.requireOrganizerWebsite && 'no organizer website',
    a.rejectUnmatchedCategory && 'unmatched sector',
  ].filter((r): r is string => Boolean(r));

  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-[max-content_1fr]">
      <SummaryRow label="Countries">
        {noPlace ? <span className="text-muted-foreground">None saved — the server's default target places are used</span> : <NameList names={countries} empty="Any (states / cities below)" />}
      </SummaryRow>
      {!noPlace && <SummaryRow label="States"><NameList names={a.states ?? []} empty="Whole countries / ticked cities" /></SummaryRow>}
      {!noPlace && <SummaryRow label="Cities"><NameList names={a.cities ?? []} empty="Whole countries / states" /></SummaryRow>}
      <SummaryRow label="Sectors"><NameList names={a.categories ?? []} max={6} empty="None saved — every platform sector" /></SummaryRow>
      <SummaryRow label="Channels">
        <span className="flex flex-wrap gap-1.5">
          <Badge tone={web ? 'good' : 'neutral'}>Web search {web ? 'on' : 'off'}</Badge>
          <Badge tone={directories ? 'good' : 'neutral'}>Directories {directories ? 'on' : 'off'}</Badge>
          <Badge tone={aggregators ? 'good' : 'neutral'}>Aggregators {aggregators ? 'on' : 'off'}</Badge>
          <Badge tone={a.ticketmasterEnabled ? 'good' : 'neutral'}>Ticketmaster {a.ticketmasterEnabled ? (a.ticketmasterApiKeySet ? 'on' : 'on · no key') : 'off'}</Badge>
        </span>
      </SummaryRow>
      {web && (
        <SummaryRow label="Search providers">
          {providerNames === null ? 'Every configured provider (free ones first)' : <NameList names={providerNames} empty="None selected" />}
        </SummaryRow>
      )}
      <SummaryRow label="Sources ticked">{catalog ? `${namedSources.length} catalogued source${namedSources.length === 1 ? '' : 's'}` : '—'}{` · ${(a.listingUrls ?? []).length} listing website${(a.listingUrls ?? []).length === 1 ? '' : 's'}`}</SummaryRow>
      <SummaryRow label="Rejects events with">{rules.length ? rules.join(', ') : <span className="text-muted-foreground">No rejection rules on</span>}</SummaryRow>
      <SummaryRow label="Per run">
        {a.eventsPerRun ?? '—'} events examined · stops at {a.targetValidEvents ?? '—'} verified · {a.searchDepth ?? 'server default'} search queries
      </SummaryRow>
      <SummaryRow label="Daily cap">{a.dailyLimit != null ? `${a.dailyLimit} new events per day` : 'Server default'}</SummaryRow>
      <SummaryRow label="Rejected events">{a.keepRejectedEvents ? 'Kept for review (All events → Rejected)' :'Off-sector and no-e-mail rejections are not stored; other rejections are'}</SummaryRow>
    </dl>
  );
}

function AutomaticRunsTable({ runs }: { runs: AgentRun[] }) {
  return (
    <AdminTable columns={['Run', 'Status', 'Started', 'Duration', 'Verified', 'New events', 'Needs review', 'Error', '']} minWidth={900}>
      {runs.map((r) => {
        const fresh = runCount(r, 'new_events');
        return (
          <tr key={r.id} className="hover:bg-muted/20">
            <td className={cell}><Link href={`/admin/discover/runs/${r.id}`} className="font-mono-face font-bold text-accent hover:underline">#{r.id}</Link></td>
            <td className={cell}><Badge tone={runTone(r.status)}>{r.status}</Badge></td>
            <td className={cellMuted}>{fmtDateTime(r.startedAt)}</td>
            <td className={cellMuted}>{r.status === 'running' ? 'still running' : fmtDuration(r.startedAt, r.completedAt)}</td>
            <td className={cell}>{dash(runCount(r, 'verified_events'))}</td>
            <td className={cell}>{dash(fresh)}</td>
            <td className={cellMuted}>{dash(runCount(r, 'events_needing_review'))}</td>
            <td className={cell}>{r.error ? <span className="block max-w-[220px] truncate text-red-600 dark:text-red-300" title={r.error}>{r.error}</span> : <span className="text-muted-foreground">—</span>}</td>
            <td className={cell}>
              <div className="flex items-center gap-2 whitespace-nowrap">
                <Link href={`/admin/discover/runs/${r.id}`} className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">Report</Link>
                {fresh !== null && fresh > 0 && (
                  <Link href={`/admin/discovery/events?run=${r.id}`} className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">View {fresh} new event{fresh === 1 ? '' : 's'}</Link>
                )}
              </div>
            </td>
          </tr>
        );
      })}
    </AdminTable>
  );
}

export function AutomaticDiscoveryPage() {
  const auto = useDiscoveryAutoStatus();
  const setAuto = useSetDiscoveryAuto();
  const runs = useDiscoveryRuns();
  const catalog = useDiscoveryCatalog();
  const [confirmOn, setConfirmOn] = useState(false);
  const [lastChange, setLastChange] = useState<'on' | 'off' | null>(null);

  const automaticRuns = useMemo(
    () => [...(runs.data ?? [])].filter((r) => discoveryRunTrigger(r) === 'automatic').sort((a, b) => b.id - a.id),
    [runs.data],
  );

  const header = (
    <>
      <Breadcrumbs items={[{ label: 'Discover events', href: '/admin/discover' }, { label: 'Automatic discovery' }]} />
      <PageHeader
        kicker="Discover events"
        title="Automatic discovery"
        subtitle="Let discovery run on a schedule with the saved configuration. It is off unless you switch it on, and it stays exactly as you leave it."
        actions={
          <>
            <Link href="/admin/discover" className="button-press inline-flex items-center gap-1.5 rounded-full border border-foreground/15 bg-background px-4 py-2 text-xs font-bold hover:border-accent hover:text-accent">Run discovery now</Link>
            <Link href="/admin/discover/configuration" className="button-press inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"><Pencil size={12} /> Edit configuration</Link>
          </>
        }
      />
    </>
  );

  if (auto.isLoading) return <div>{header}<div className="mt-8"><LoadingState label="Loading automatic discovery status" /></div></div>;
  if (auto.isError || !auto.data) return <div>{header}<div className="mt-8"><ErrorState error={auto.error} title="Could not load automatic discovery status." retry={() => auto.refetch()} /></div></div>;

  const a = auto.data;
  const enabled = a.enabled;
  const interval = typeof a.intervalMinutes === 'number' ? a.intervalMinutes : null;
  const lastAutomatic = automaticRuns[0];

  const turn = (next: boolean) => {
    setLastChange(null);
    setAuto.mutate(next, { onSuccess: (data) => { setConfirmOn(false); setLastChange(data.enabled ? 'on' : 'off'); } });
  };

  return (
    <div>
      {header}

      <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        {/* On / off */}
        <Panel className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono-face text-[10px] uppercase tracking-[.14em] text-muted-foreground">Status</p>
              <p className={cx('mt-2 font-display text-3xl font-extrabold tracking-[-.04em]', enabled ? 'text-emerald-600 dark:text-emerald-300' : 'text-muted-foreground')}>{enabled ? 'On' : 'Off'}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {enabled
                  ? `A discovery run starts every ${interval ?? '—'} minutes with the saved configuration.`
                  : 'Nothing runs on a schedule. Discovery only runs when someone starts it.'}
              </p>
            </div>
            <Switch checked={enabled} disabled={setAuto.isPending} label="Automatic discovery"
              onChange={(next) => { if (next) setConfirmOn(true); else turn(false); }} />
          </div>

          {confirmOn && !enabled && (
            <div className="mt-4 rounded-xl border border-accent/40 bg-accent/5 p-4">
              <p className="text-sm font-semibold">Turn on automatic discovery?</p>
              <p className="mt-1 text-xs text-muted-foreground">
                A run will start every {interval ?? '—'} minutes using the saved configuration summarised on this page, until you switch it off. Each run uses search-provider quota.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Btn variant="primary" size="sm" loading={setAuto.isPending} onClick={() => turn(true)}><Power size={12} /> Turn on</Btn>
                <Btn variant="ghost" size="sm" disabled={setAuto.isPending} onClick={() => setConfirmOn(false)}>Cancel</Btn>
              </div>
            </div>
          )}
          {setAuto.isError && <div className="mt-4"><Notice tone="danger">Could not change automatic discovery: {setAuto.error instanceof Error ? setAuto.error.message : 'unknown error'}. It is still {enabled ? 'on' : 'off'}.</Notice></div>}
          {lastChange && !setAuto.isError && <div className="mt-4"><Notice tone="good">Automatic discovery is now {lastChange}.</Notice></div>}

          <div className="mt-5 grid gap-2 border-t border-foreground/10 pt-4 text-xs">
            <IntervalControl current={interval} />

            <p className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">Last automatic run:</span>
              {runs.isLoading ? 'Loading…' : runs.isError ? <span className="text-red-600 dark:text-red-300">could not load runs</span> : lastAutomatic ? (
                <>
                  <Link href={`/admin/discover/runs/${lastAutomatic.id}`} className="text-accent hover:underline">#{lastAutomatic.id}</Link>
                  <Badge tone={runTone(lastAutomatic.status)}>{lastAutomatic.status}</Badge>
                  <span className="text-muted-foreground">{fmtDateTime(lastAutomatic.startedAt)}</span>
                </>
              ) : <span className="text-muted-foreground">none recorded</span>}
            </p>
          </div>

          <div className="mt-5">
            <Notice tone="info">
              Automatic runs use the same discovery pipeline as a run you start yourself — the same searches, source readers, organizer research,
              validation and rejection rules. The only difference is where the settings come from: an automatic run uses the saved{' '}
              <Link href="/admin/discover/configuration" className="font-semibold underline">Discovery configuration</Link>; a manual run uses what you choose in{' '}
              <Link href="/admin/discover" className="font-semibold underline">Run discovery</Link>. Their results land in the same places and have the same run reports.
            </Notice>
          </div>
        </Panel>

        {/* What it will search */}
        <Panel className="p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-mono-face text-[10px] uppercase tracking-[.14em] text-muted-foreground">What each automatic run uses</p>
              <p className="mt-1 text-xs text-muted-foreground">Read-only summary of the saved configuration.</p>
            </div>
            <Link href="/admin/discover/configuration" className="inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">Edit configuration <ArrowRight size={11} /></Link>
          </div>
          <div className="mt-5">
            <SavedConfigSummary a={a} catalog={catalog.data} />
          </div>
          {catalog.isError && <p className="mt-3 text-[11px] text-muted-foreground">Source names unavailable — the source catalog could not be loaded.</p>}
        </Panel>
      </div>

      <Panel className="mt-6 p-6">
        <Section
          title={`Recent automatic runs${runs.data ? ` (${automaticRuns.length})` : ''}`}
          aside={<Link href="/admin/discover/runs?trigger=automatic" className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">All runs →</Link>}
        >
          {runs.isLoading ? <LoadingState label="Loading runs" /> : runs.isError ? <ErrorState error={runs.error} retry={() => runs.refetch()} /> : automaticRuns.length === 0 ? (
            <EmptyState title="No automatic runs recorded yet." body={enabled ? `The first one starts within ${interval ?? '—'} minutes of switching on.` : 'Switch automatic discovery on to start scheduled runs.'} />
          ) : (
            <AutomaticRunsTable runs={automaticRuns.slice(0, 10)} />
          )}
          <p className="mt-3 text-[11px] text-muted-foreground">Covers the latest 100 discovery runs. A run counts as automatic when its stored configuration says it wasn't started by an admin.</p>
        </Section>
      </Panel>
    </div>
  );
}

const INTERVAL_CHOICES = [60, 120, 240, 360, 720, 1440];

function intervalLabel(minutes: number) {
  return minutes % 60 === 0 ? (minutes === 60 ? 'every hour' : `every ${minutes / 60} hours`) : `every ${minutes} minutes`;
}

/** How often automatic discovery runs — saved with the discovery settings and
 * picked up by the scheduler at its next cycle (no restart needed). */
function IntervalControl({ current }: { current: number | null }) {
  const setAuto = useSetDiscoveryAuto();
  const [value, setValue] = useState<number | null>(null);
  const chosen = value ?? current;
  const options = Array.from(new Set([...INTERVAL_CHOICES, ...(current ? [current] : [])])).sort((a, b) => a - b);
  const dirty = value !== null && value !== current;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Clock size={13} className="text-accent" />
      <label htmlFor="auto-interval" className="font-semibold">Run interval:</label>
      <select
        id="auto-interval"
        value={chosen ?? ''}
        onChange={(e) => setValue(Number(e.target.value))}
        disabled={setAuto.isPending || chosen === null}
        className="rounded-lg border border-foreground/15 bg-background px-2 py-1 text-xs outline-none focus:border-accent"
      >
        {options.map((m) => <option key={m} value={m}>{intervalLabel(m)}</option>)}
      </select>
      {dirty && (
        <Btn size="sm" variant="primary" loading={setAuto.isPending}
          onClick={() => setAuto.mutate({ intervalMinutes: value! }, { onSuccess: () => setValue(null) })}>
          Save interval
        </Btn>
      )}
      {setAuto.isSuccess && !dirty && <span className="text-[11px] text-emerald-600 dark:text-emerald-400">Saved — applies from the next cycle.</span>}
      {setAuto.isError && <span className="text-[11px] text-red-600 dark:text-red-400">Could not save: {setAuto.error instanceof Error ? setAuto.error.message : 'unknown error'}</span>}
    </div>
  );
}
