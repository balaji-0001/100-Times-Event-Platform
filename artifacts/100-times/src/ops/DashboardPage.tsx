import { useState } from 'react';
import { Link } from 'wouter';
import { ArrowRight, CalendarSearch, Mail, MapPin } from 'lucide-react';
import { useDiscoveredEvents, useDiscoveredOrganizers, useDiscoveryRuns, useDiscoveryStats, useOutreachMessages, useOutreachRuns, useOutreachStats, useDiscoveryAutoStatus, useSetDiscoveryAuto, useOutreachAutoStatus, useSetOutreachAuto } from './api';
import { buildActivity } from './activity';
import { Badge, ErrorState, Kicker, LoadingState, Notice, PageHeader, Panel, StatCard, Switch, cx, fmtDate, fmtTime, parseDate } from './ui';
import { ManualResearchButton } from './ManualResearch';
import { DiscoverySettingsButton } from './DiscoverySettingsModal';
import { OutreachSettingsButton } from './OutreachSettingsModal';

function AutoDiscoveryToggle() {
  const auto = useDiscoveryAutoStatus();
  const setAuto = useSetDiscoveryAuto();
  const enabled = auto.data?.enabled ?? false;
  const interval = auto.data?.intervalMinutes;
  const country = auto.data?.country;
  const categories = auto.data?.categories || [];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-2 rounded-full border border-foreground/15 bg-background px-3 py-1.5">
        <Switch checked={enabled} disabled={auto.isLoading || setAuto.isPending} onChange={(next) => setAuto.mutate(next)} label="Automatic discovery" />
        <span className="text-[11px]">
          <span className="font-bold">Automatic discovery {enabled ? 'on' : 'off'}</span>
          <span className="block text-muted-foreground">
            {enabled
              ? `Runs every ${interval ?? '—'} min${country ? ` · Target: ${country}` : ' · Worldwide'}${categories.length ? ` (${categories.length} sectors)` : ''}`
              : `Off — configure settings before turning on or use “Run manual research”`}
          </span>
        </span>
      </div>
      <DiscoverySettingsButton size="sm" />
    </div>
  );
}

function AutoOutreachToggle() {
  const auto = useOutreachAutoStatus();
  const setAuto = useSetOutreachAuto();
  const enabled = auto.data?.enabled ?? false;
  const draftInterval = auto.data?.draftIntervalMinutes;
  const followupInterval = auto.data?.followupIntervalMinutes;
  const country = auto.data?.country;
  const categories = auto.data?.categories || [];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-2 rounded-full border border-foreground/15 bg-background px-3 py-1.5">
        <Switch checked={enabled} disabled={auto.isLoading || setAuto.isPending} onChange={(next) => setAuto.mutate(next)} label="Automatic outreach drafting" />
        <span className="text-[11px]">
          <span className="font-bold">Automatic drafting {enabled ? 'on' : 'off'}</span>
          <span className="block text-muted-foreground">
            {enabled
              ? `Drafts every ${draftInterval ?? '—'} min${categories.length ? ` · ${categories.length} sectors` : ' · All sectors'} — waits for approval`
              : 'Off — configure settings before turning on or use “Generate outreach batch”'}
          </span>
        </span>
      </div>
      <OutreachSettingsButton size="sm" />
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
  const [dismissedRunIds, setDismissedRunIds] = useState<number[]>([]);

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
  // Only surface a failure banner for something that actually just happened — picking the
  // highest-id failed run across all history kept resurfacing a month-old, long-superseded
  // failure forever, even after dozens of later runs succeeded.
  const RECENT_FAILURE_WINDOW_MS = 24 * 60 * 60 * 1000;
  const recentFailures = runs.filter((r) => r.status === 'failed' && Date.now() - (parseDate(r.startedAt)?.getTime() ?? 0) < RECENT_FAILURE_WINDOW_MS);
  const latestFailed = recentFailures.sort((a, b) => b.id - a.id).find((r) => !dismissedRunIds.includes(r.id));
  const activity = buildActivity({ events: ev, organizers: org, messages: msg, runs }).slice(0, 25);

  return (
    <div>
      <PageHeader kicker="100Times Operations" title="Discover event organizers and grow the 100Times event network." subtitle="The discovery automation finds events and the organizers behind them — automatic scanning is off by default, flip the switch below to let it run on its own. Agent 2 invites those organizers to list on 100Times — every email is approved by a person before it is sent." />

      {(stats.data?.emailProviderStatus === 'NOT_CONFIGURED' || latestFailed) && (
        <div className="mt-6 space-y-2">
          {stats.data?.emailProviderStatus === 'NOT_CONFIGURED' && <Notice tone="warn"><strong>Email sending is in mock mode.</strong> SMTP is not configured, so approved emails are logged but not delivered to anyone.</Notice>}
          {latestFailed && (
            <Notice tone="danger">
              <div className="flex items-center justify-between gap-3 w-full">
                <div>
                  <strong>Latest {latestFailed.agentType} run #{latestFailed.id} failed:</strong> {latestFailed.error ?? 'no error recorded'} <Link href="/admin/activity" className="underline">View runs</Link>
                </div>
                <button
                  type="button"
                  onClick={() => setDismissedRunIds((prev) => [...prev, latestFailed.id])}
                  className="text-xs text-muted-foreground hover:text-foreground font-bold px-1.5 py-0.5 rounded hover:bg-foreground/10 shrink-0"
                  title="Dismiss error notice"
                >
                  ✕
                </button>
              </div>
            </Notice>
          )}
        </div>
      )}

      <div className="mt-8 grid gap-6 xl:grid-cols-2">
        <Panel className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2"><CalendarSearch size={16} className="text-accent" /><Kicker>Organizer Discovery — Automation</Kicker></div>
            <div className="flex items-center gap-3">
              <ManualResearchButton size="sm" />
              <Link href="/admin/discovery" className="inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">View discoveries <ArrowRight size={11} /></Link>
            </div>
          </div>
          <div className="mt-4"><AutoDiscoveryToggle /></div>
          <div className="mt-5 grid grid-cols-2 gap-3 2xl:grid-cols-4">
            <StatCard label="Events discovered" value={ds?.eventsTotal ?? 0} href="/admin/discovery/events" />
            <StatCard label="Organizers found" value={ds?.organizersTotal ?? 0} href="/admin/discovery/organizers" />
            <StatCard label="Contacts found" value={ds?.contactsTotal ?? 0} sub={`${ds?.organizersWithEmailTotal ?? 0} with email`} href="/admin/discovery/contacts" />
            <StatCard label="Needs review" value={ds?.needsReviewTotal ?? 0} tone={ds?.needsReviewTotal ? 'warn' : 'good'} href="/admin/discovery/events?verification=NEEDS_REVIEW" />
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
          <Link href="/admin/activity" className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">Full activity log →</Link>
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
