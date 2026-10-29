import { useState } from 'react';
import { Link } from 'wouter';
import { AlertTriangle, ArrowRight, CalendarSearch, CheckCircle2, Compass, FileText, Mail, MapPin, SlidersHorizontal } from 'lucide-react';
import { type AgentRun, discoveryRunTrigger, runCount, useDiscoveredEvents, useDiscoveredOrganizers, useDiscoveryCatalog, useDiscoveryRuns, useDiscoveryStats, useOutreachMessages, useOutreachRuns, useOutreachStats, useDiscoveryAutoStatus, useOutreachAutoStatus, useSetOutreachAuto } from './api';
import { buildActivity } from './activity';
import { Badge, ErrorState, Kicker, LoadingState, PageHeader, Panel, StatCard, Switch, cx, fmtDate, fmtDateTime, fmtTime, parseDate } from './ui';
import { OutreachSettingsButton } from './OutreachSettingsModal';

const pill = 'button-press inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-[11px] font-bold transition-colors';
const runTone = (s: AgentRun['status']) => (s === 'completed' ? 'good' : s === 'failed' ? 'danger' : 'warn');

/** Automatic discovery's real state, linking to the one page where it is switched on or off. */
function AutoDiscoveryStatus() {
  const auto = useDiscoveryAutoStatus();
  const enabled = auto.data?.enabled;
  const countries = auto.data ? (auto.data.countries?.length ? auto.data.countries : auto.data.country ? [auto.data.country] : []) : [];
  const sectors = auto.data?.categories ?? [];
  return (
    <Link href="/admin/discover/automatic" className="flex flex-wrap items-center gap-2 rounded-full border border-foreground/15 bg-background px-3 py-1.5 text-[11px] hover:border-accent">
      <span className={cx('h-2 w-2 rounded-full', enabled ? 'bg-emerald-500' : 'bg-muted-foreground/50')} />
      <span>
        <span className="font-bold">Automatic discovery {auto.isLoading ? '…' : auto.isError ? 'status unavailable' : enabled ? 'on' : 'off'}</span>
        <span className="block text-muted-foreground">
          {auto.data
            ? enabled
              ? `Every ${auto.data.intervalMinutes ?? '—'} min · ${countries.length ? `${countries.length} countr${countries.length === 1 ? 'y' : 'ies'}` : 'server default places'} · ${sectors.length ? `${sectors.length} sectors` : 'all sectors'}`
              : 'Off — nothing runs on a schedule'
            : '—'}
        </span>
      </span>
      <span className="ml-1 font-mono-face text-[10px] uppercase tracking-wider text-accent">Manage →</span>
    </Link>
  );
}

type Attention = { id: string; tone: 'danger' | 'warn'; text: string; href: string; action: string };

/** Problems an admin can act on, each linking to the page where it is fixed. Built only from loaded API data. */
function NeedsAttention({ items, checks, onDismiss }: { items: Attention[]; checks: Array<{ ok: string; known: boolean; unknown: string }>; onDismiss: (id: string) => void }) {
  const known = checks.filter((c) => c.known);
  const unknown = checks.filter((c) => !c.known);
  return (
    <Panel className="mt-6 p-6">
      <div className="flex items-center gap-2"><AlertTriangle size={16} className="text-accent" /><Kicker>Needs attention</Kicker></div>
      {items.length === 0 ? (
        <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          {known.length > 0 && <><CheckCircle2 size={14} className="text-emerald-600" /> Nothing to fix: {known.map((c) => c.ok).join(', ')}.</>}
          {unknown.length > 0 && <span className="text-[11px]">Not checked — {unknown.map((c) => c.unknown).join(', ')}.</span>}
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-foreground/10">
          {items.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5 text-sm">
              <span className="flex min-w-0 items-start gap-2">
                <span className={cx('mt-1.5 h-2 w-2 shrink-0 rounded-full', item.tone === 'danger' ? 'bg-red-500' : 'bg-amber-500')} />
                <span className="min-w-0 break-words">{item.text}</span>
              </span>
              <span className="flex shrink-0 items-center gap-2">
                <Link href={item.href} className={`${pill} border border-foreground/15 bg-background hover:border-accent hover:text-accent`}>{item.action} →</Link>
                {item.id.startsWith('run-') && (
                  <button type="button" onClick={() => onDismiss(item.id)} title="Hide this notice until the page reloads" className="rounded px-1.5 py-0.5 text-xs font-bold text-muted-foreground hover:bg-foreground/10 hover:text-foreground">✕</button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function AutoOutreachToggle() {
  const auto = useOutreachAutoStatus();
  const setAuto = useSetOutreachAuto();
  const enabled = auto.data?.enabled ?? false;
  const draftInterval = auto.data?.draftIntervalMinutes;
  const categories = auto.data?.categories || [];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-2 rounded-full border border-foreground/15 bg-background px-3 py-1.5">
        <Switch checked={enabled} disabled={auto.isLoading || auto.isError || setAuto.isPending} onChange={(next) => setAuto.mutate(next)} label="Automatic outreach drafting" />
        <span className="text-[11px]">
          <span className="font-bold">Automatic drafting {auto.isError ? 'status unavailable' : enabled ? 'on' : 'off'}</span>
          <span className="block text-muted-foreground">
            {enabled
              ? `Drafts every ${draftInterval ?? '—'} min${categories.length ? ` · ${categories.length} sectors` : ' · All sectors'} — waits for approval`
              : 'Off — no drafts are made on a schedule. Check its settings before turning it on.'}
          </span>
        </span>
      </div>
      <OutreachSettingsButton size="sm" />
      {setAuto.isError && <span className="text-[11px] text-red-700 dark:text-red-300">Couldn't change it: {setAuto.error instanceof Error ? setAuto.error.message : 'unknown error'}</span>}
    </div>
  );
}

export function DashboardPage() {
  const events = useDiscoveredEvents();
  const organizers = useDiscoveredOrganizers();
  const messages = useOutreachMessages();
  const stats = useOutreachStats();
  const discoveryStats = useDiscoveryStats();
  const discoveryRuns = useDiscoveryRuns();
  const outreachRuns = useOutreachRuns();
  const catalog = useDiscoveryCatalog();
  const [dismissed, setDismissed] = useState<string[]>([]);

  const loading = events.isLoading || organizers.isLoading || messages.isLoading || discoveryStats.isLoading;
  const error = events.error ?? organizers.error ?? messages.error ?? discoveryStats.error;
  if (loading) return <LoadingState label="Loading operations overview" />;
  if (error) return <ErrorState error={error} retry={() => { events.refetch(); organizers.refetch(); messages.refetch(); discoveryStats.refetch(); }} />;

  // `ev`/`org` are capped at 200 rows (for the browsing tables below) — every
  // headline number here comes from `discoveryStats` (real DB counts) instead,
  // so the overview keeps growing correctly even past that cap.
  const ev = events.data ?? []; const org = organizers.data ?? []; const msg = messages.data ?? [];
  const ds = discoveryStats.data;
  const contactedOrganizers = new Set(msg.filter((m) => m.sentAt).map((m) => m.organizer?.id).filter(Boolean)).size;
  const sent = msg.filter((m) => m.sentAt).length;
  const delivered = msg.filter((m) => ['DELIVERED', 'REPLIED', 'FOLLOW_UP_DUE', 'COMPLETED'].includes(m.status)).length;
  const replies = msg.filter((m) => m.responseAt).length;
  const followUps = msg.filter((m) => m.status === 'FOLLOW_UP_DUE').length;
  const awaiting = msg.filter((m) => m.status === 'PENDING_APPROVAL' || m.status === 'FOLLOW_UP_DUE').length;

  const runs = [...(discoveryRuns.data ?? []), ...(outreachRuns.data ?? [])];
  // Only surface failures that actually just happened — picking the highest-id failed run
  // across all history kept resurfacing a month-old, long-superseded failure forever.
  const RECENT_FAILURE_WINDOW_MS = 24 * 60 * 60 * 1000;
  // A run cut short by a backend restart isn't a failure of the agent: it stays in run
  // history with that reason, but isn't raised here.
  const INTERRUPTED_BY_RESTART = 'Interrupted by a server restart';
  const recentFailures = runs
    .filter((r) => r.status === 'failed' && r.error !== INTERRUPTED_BY_RESTART && Date.now() - (parseDate(r.startedAt)?.getTime() ?? 0) < RECENT_FAILURE_WINDOW_MS)
    .sort((a, b) => b.id - a.id);

  const attention: Attention[] = [];
  if (stats.data?.emailProviderStatus === 'NOT_CONFIGURED') {
    attention.push({ id: 'smtp', tone: 'warn', text: 'E-mail sending is not configured: approved outreach e-mails stay Approved with a “Not sent” reason.', href: '/admin/settings?tab=smtp', action: 'Set up SMTP' });
  }
  for (const r of recentFailures) {
    const id = `run-${r.agentType}-${r.id}`;
    if (dismissed.includes(id)) continue;
    attention.push(r.agentType === 'discovery'
      ? { id, tone: 'danger', text: `Discovery run #${r.id} failed (${fmtDateTime(r.startedAt)}): ${r.error ?? 'no error recorded'}`, href: `/admin/discover/runs/${r.id}`, action: 'Open report' }
      : { id, tone: 'danger', text: `Outreach batch #${r.id} failed (${fmtDateTime(r.startedAt)}): ${r.error ?? 'no error recorded'}`, href: '/admin/discover/runs?agent=outreach', action: 'View batches' });
  }
  // Per-source health is shown on the configuration page, not as a dashboard alert.
  // Last call FAILED / RATE_LIMITED, or paused by the circuit breaker (SKIPPED isn't a failure).
  const failingProviders = (catalog.data?.providers ?? []).filter((p) => p.configured && (p.cooling_down_seconds > 0 || p.last_call.status === 'FAILED' || p.last_call.status === 'RATE_LIMITED'));
  if (failingProviders.length) {
    attention.push({ id: 'providers', tone: 'warn', text: `Search provider${failingProviders.length === 1 ? '' : 's'} failing, rate-limited or paused: ${failingProviders.map((p) => `${p.name}${p.last_call.error ? ` (${p.last_call.error.slice(0, 80)})` : ''}`).join(', ')}.`, href: '/admin/discover/configuration#sources', action: 'Check providers' });
  }

  // Run entries in the activity feed point at the run's report (discovery) or the outreach batch list.
  const activity = buildActivity({ events: ev, organizers: org, messages: msg, runs }).slice(0, 25).map((a) => {
    const m = /^run-(\d+)-/.exec(a.id);
    if (!m) return a;
    return { ...a, href: a.agent === 'discovery' ? `/admin/discover/runs/${m[1]}` : '/admin/discover/runs?agent=outreach' };
  });
  const recentDiscoveryRuns = [...(discoveryRuns.data ?? [])].sort((a, b) => b.id - a.id).slice(0, 5);

  return (
    <div>
      <PageHeader kicker="Overview" title="Discover event organizers and grow the 100Times event network." subtitle="Discovery finds events and the organizers behind them — run it yourself or switch on automatic discovery. Agent 2 invites those organizers to list on 100Times — every e-mail is approved by a person before it is sent." />

      <NeedsAttention
        items={attention}
        checks={[
          { ok: 'no failed runs in the last 24 hours', known: Boolean(discoveryRuns.data && outreachRuns.data), unknown: discoveryRuns.isLoading || outreachRuns.isLoading ? 'loading run history' : 'run history could not be loaded' },
          { ok: 'no failing search providers', known: Boolean(catalog.data), unknown: catalog.isLoading ? 'loading search provider status' : 'search provider status could not be loaded' },
          { ok: 'e-mail sending is configured', known: Boolean(stats.data), unknown: stats.isLoading ? 'loading e-mail status' : 'e-mail status could not be loaded' },
        ]}
        onDismiss={(id) => setDismissed((prev) => [...prev, id])}
      />

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Panel className="p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2"><CalendarSearch size={16} className="text-accent" /><Kicker>Event discovery</Kicker></div>
            <div className="flex flex-wrap items-center gap-2">
              <Link href="/admin/discover" className={`${pill} bg-accent text-accent-foreground hover:bg-primary hover:text-primary-foreground`}><Compass size={12} /> Run discovery</Link>
              <Link href="/admin/discover/configuration" className={`${pill} border border-foreground/15 bg-background hover:border-accent hover:text-accent`}><SlidersHorizontal size={12} /> Configuration</Link>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <AutoDiscoveryStatus />
            <Link href="/admin/discovery" className="inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">New discoveries <ArrowRight size={11} /></Link>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-3 2xl:grid-cols-4">
            <StatCard label="Events discovered" value={ds?.eventsTotal ?? '—'} href="/admin/discovery/events" />
            <StatCard label="Organizers found" value={ds?.organizersTotal ?? '—'} href="/admin/discovery/organizers" />
            <StatCard label="Contacts found" value={ds?.contactsTotal ?? '—'} sub={`${ds?.organizersWithEmailTotal ?? '—'} with email`} href="/admin/discovery/contacts" />
            <StatCard label="Needs review" value={ds?.needsReviewTotal ?? '—'} tone={ds?.needsReviewTotal ? 'warn' : 'good'} href="/admin/discovery/events?verification=NEEDS_REVIEW" />
          </div>
          <div className="mt-6">
            <div className="flex items-center justify-between">
              <p className="font-mono-face text-[10px] uppercase tracking-[.14em] text-muted-foreground">Recent discovery runs</p>
              <Link href="/admin/discover/runs" className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">Run history →</Link>
            </div>
            {discoveryRuns.isLoading ? <p className="mt-2 text-xs text-muted-foreground">Loading runs…</p> : discoveryRuns.isError ? <p className="mt-2 text-xs text-red-600 dark:text-red-300">Could not load runs.</p> : recentDiscoveryRuns.length === 0 ? (
              <p className="mt-2 text-xs text-muted-foreground">No discovery runs yet. <Link href="/admin/discover" className="text-accent hover:underline">Start one</Link>.</p>
            ) : (
              <ul className="mt-2 divide-y divide-foreground/10 rounded-xl border border-foreground/10">
                {recentDiscoveryRuns.map((r) => {
                  const fresh = runCount(r, 'new_events');
                  const trig = discoveryRunTrigger(r);
                  return (
                    <li key={r.id}>
                      <Link href={`/admin/discover/runs/${r.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-xs hover:bg-muted/30">
                        <span className="font-mono-face font-bold text-accent">#{r.id}</span>
                        <Badge tone={runTone(r.status)}>{r.status}</Badge>
                        {trig && <span className="text-muted-foreground">{trig === 'automatic' ? 'Automatic' : 'Manual'}</span>}
                        <span className="text-muted-foreground">{fmtDateTime(r.startedAt)}</span>
                        <span className="ml-auto flex items-center gap-1">{fresh === null ? '—' : `${fresh} new`} <FileText size={11} className="text-accent" /></span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Panel>
        <Panel className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2"><Mail size={16} className="text-accent" /><Kicker>Organizer Outreach — Agent 2</Kicker></div>
            <Link href="/admin/outreach/all" className="inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">View outreach <ArrowRight size={11} /></Link>
          </div>
          <div className="mt-4"><AutoOutreachToggle /></div>
          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-5">
            <StatCard label="Organizers contacted" value={contactedOrganizers} sub={awaiting ? `${awaiting} awaiting approval` : undefined} href={awaiting ? '/admin/outreach/pending' : '/admin/outreach/sent'} />
            <StatCard label="Emails sent" value={sent} href="/admin/outreach/sent" />
            <StatCard label="Delivered" value={delivered} tone="good" href="/admin/outreach/delivered" />
            <StatCard label="Replies" value={replies} tone={replies ? 'good' : 'accent'} href="/admin/outreach/replies" />
            <StatCard label="Follow-ups" value={followUps} tone={followUps ? 'warn' : 'accent'} href="/admin/outreach/follow-ups" />
          </div>
        </Panel>
      </div>

      <Panel className="mt-6 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2"><MapPin size={16} className="text-accent" /><Kicker>Where events are happening</Kicker></div>
          <Link href="/admin/discovery/events" className="inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">All events <ArrowRight size={11} /></Link>
        </div>
        {!ds || ds.eventsTotal === 0 ? <p className="mt-4 text-sm text-muted-foreground">No events discovered yet.</p> : (
          <>
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Online" value={ds.onlineTotal} href="/admin/discovery/events?format=online" />
              <StatCard label="Offline" value={ds.offlineTotal} href="/admin/discovery/events?format=offline" />
              <StatCard label="Hybrid" value={ds.hybridTotal} href="/admin/discovery/events?format=hybrid" />
              <StatCard label="Format not captured" value={ds.formatUnknownTotal} tone={ds.formatUnknownTotal ? 'warn' : 'good'} href="/admin/discovery/events?format=unspecified" />
            </div>
            {(ds.offlineTotal + ds.hybridTotal) > 0 && (
              <p className="mt-4 text-sm text-muted-foreground">
                <span className="font-bold text-foreground">{ds.offlineTotal + ds.hybridTotal - ds.venueMissingTotal} of {ds.offlineTotal + ds.hybridTotal}</span> offline/hybrid events have a venue captured by the discovery automation.
              </p>
            )}
            {ds.venueMissingTotal > 0 && (
              <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
                <p className="font-mono-face text-[10px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-300">{ds.venueMissingTotal} offline/hybrid event{ds.venueMissingTotal === 1 ? '' : 's'} missing a venue</p>
                <ul className="mt-2 space-y-1">
                  {ds.venueMissingSample.map((e) => (
                    <li key={e.id} className="truncate text-sm">
                      <Link href={`/admin/discovery/events?event=${e.id}`} className="text-accent hover:underline">{e.name ?? `Event #${e.id}`}</Link>
                      <span className="text-muted-foreground"> — {e.city || 'city unknown'}</span>
                    </li>
                  ))}
                </ul>
                {ds.venueMissingTotal > ds.venueMissingSample.length && <p className="mt-1 text-[11px] text-muted-foreground">+{ds.venueMissingTotal - ds.venueMissingSample.length} more — see <Link href="/admin/discovery/events" className="underline">all events</Link>.</p>}
              </div>
            )}
          </>
        )}
      </Panel>

      <Panel className="mt-6 p-6">
        <div className="flex items-center justify-between">
          <Kicker>Recent activity</Kicker>
          <Link href="/admin/discover/runs" className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">Run history & full feed →</Link>
        </div>
        {activity.length === 0 ? <p className="mt-4 text-sm text-muted-foreground">No agent activity has been recorded yet.</p> : (
          <ol className="mt-4 divide-y divide-foreground/10">
            {activity.map((a) => (
              <li key={a.id} className="flex items-start gap-4 py-3 text-sm">
                <span className="w-[7.5rem] shrink-0 font-mono-face text-[10px] leading-5 text-muted-foreground">{fmtDate(a.at)}<br />{fmtTime(a.at)}</span>
                <Badge tone={a.agent === 'discovery' ? 'info' : 'accent'}>{a.agent === 'discovery' ? 'Discovery' : 'Agent 2'}</Badge>
                <div className="min-w-0 flex-1">
                  {a.href ? <Link href={a.href} className={cx('font-semibold hover:underline', a.tone === 'danger' && 'text-red-700 dark:text-red-300')}>{a.title}</Link> : <span className="font-semibold">{a.title}</span>}
                  {a.detail && <p className="truncate text-xs text-muted-foreground">{a.detail}</p>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </div>
  );
}
