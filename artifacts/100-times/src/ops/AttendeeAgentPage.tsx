// Admin view of the Attendee Agent. Every number is a live count from
// GET /api/attendee/admin/overview — attendee preferences, saves, confirmed
// registrations, assistant questions and notifications actually sent.

import { Play } from 'lucide-react';
import {
  useAttendeeAdminOverview, useRunAttendeeNotifications, useSetAttendeeNotificationsAuto,
} from '@/attendee/api';
import { errorText } from '@/attendee/components';
import { AdminTable, Badge, Btn, ErrorState, LoadingState, Notice, PageHeader, Panel, StatCard, Switch, cell, cellMuted, fmtDateTime } from './ui';

const KIND_LABEL: Record<string, string> = {
  reminder: 'Event reminders',
  deadline: 'Deadline alerts',
  change: 'Event change notices',
  new_matches: 'New-match digests',
};

export function AttendeeAgentPage() {
  const q = useAttendeeAdminOverview();
  const setAuto = useSetAttendeeNotificationsAuto();
  const run = useRunAttendeeNotifications();

  if (q.isLoading) return <LoadingState label="Loading Attendee Agent" />;
  if (q.isError || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const d = q.data;
  const runResult = run.data as { usersConsidered?: number; reminder?: number; deadline?: number; change?: number; new_matches?: number; errors?: string[] } | undefined;

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Agents / Attendee"
        title="Attendee Agent"
        subtitle="Personalised discovery for signed-in attendees: preferences, Match My Events, the event assistant, favourites, registration tracking and consent-based notifications — all over verified events only."
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Recommendable events" value={d.catalog.total} sub={`${d.catalog.discovered} verified discovered · ${d.catalog.platform} Trust-approved platform`} />
        <StatCard label="Attendees with preferences" value={d.attendees.withPreferences} sub={`${d.attendees.notificationConsent} gave notification consent`} />
        <StatCard label="Assistant questions" value={d.assistant.questionsAsked} />
        <StatCard label="Event detail views" value={d.engagement.eventViews} />
        <StatCard label="Saved events" value={d.engagement.savedPlatform + d.engagement.savedDiscovered} sub={`${d.engagement.savedDiscovered} external · ${d.engagement.savedPlatform} platform`} />
        <StatCard label="Registration pages opened" value={d.engagement.registrationPagesOpened} sub="Opening a page is not counted as registering" />
        <StatCard label="External registrations" value={d.engagement.externalRegistrationsConfirmed} sub="Confirmed by the attendee themselves" tone="good" />
        <StatCard label="Platform registrations" value={d.engagement.platformRegistrations} sub="Confirmed or waitlisted on 100 TIMES" tone="good" />
      </div>

      <Panel className="space-y-4 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-xl font-bold">Notifications</h2>
            <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
              Reminders, registration deadlines, event changes and new matches — only for attendees who switched consent on, and only the kinds each of them chose.
              Each notice is sent at most once.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs font-semibold">
              <Switch checked={d.notifications.autoEnabled} disabled={setAuto.isPending} onChange={(v) => setAuto.mutate(v)} />
              Run automatically (hourly)
            </label>
            <Btn variant="primary" size="sm" loading={run.isPending} onClick={() => run.mutate()}><Play size={12} /> Run now</Btn>
          </div>
        </div>
        {d.notifications.emailDelivery.status !== 'REAL' && (
          <Notice tone="warn">SMTP is not configured — attendees who asked for email get in-app notifications only, recorded as "not_configured".</Notice>
        )}
        {(setAuto.error || run.error) && <Notice tone="danger">{errorText(setAuto.error || run.error)}</Notice>}
        {runResult && (
          <Notice tone={runResult.errors?.length ? 'danger' : 'good'}>
            Swept {runResult.usersConsidered ?? 0} consenting attendee(s): {runResult.reminder ?? 0} reminders, {runResult.deadline ?? 0} deadline alerts,
            {' '}{runResult.change ?? 0} change notices, {runResult.new_matches ?? 0} new-match digests.
            {runResult.errors?.length ? ` Errors: ${runResult.errors.join('; ')}` : ''}
          </Notice>
        )}
        <div className="grid gap-3 sm:grid-cols-4">
          {Object.entries(KIND_LABEL).map(([kind, label]) => (
            <div key={kind} className="rounded-xl border border-foreground/10 p-4">
              <p className="font-mono-face text-[10px] uppercase text-muted-foreground">{label}</p>
              <p className="mt-1 font-display text-2xl font-bold">{d.notifications.sentByKind[kind] ?? 0}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Email: {Object.keys(d.notifications.emailByStatus).length
            ? Object.entries(d.notifications.emailByStatus).map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`).join(' · ')
            : 'none yet'}
          {' · '}Last sweep: {d.notifications.lastSweep.at ? `${fmtDateTime(d.notifications.lastSweep.at)} (${d.notifications.lastSweep.result})` : 'never run'}
        </p>
      </Panel>

      <section>
        <h2 className="mb-3 font-display text-xl font-bold">Recent assistant questions</h2>
        {d.assistant.recent.length ? (
          <AdminTable columns={['Question', 'Result', 'Place', 'Sector', 'Type', 'Asked']} minWidth={800}>
            {d.assistant.recent.map((r) => (
              <tr key={r.id}>
                <td className={cell}>{r.question}</td>
                <td className={cell}><Badge tone={r.status === 'ANSWERED' ? 'good' : 'warn'}>{r.status === 'ANSWERED' ? 'Answered' : 'No results'}</Badge></td>
                <td className={cellMuted}>{r.location ?? '—'}</td>
                <td className={cellMuted}>{r.sector ?? '—'}</td>
                <td className={cellMuted}>{r.eventType ?? '—'}</td>
                <td className={cellMuted}>{fmtDateTime(r.createdAt)}</td>
              </tr>
            ))}
          </AdminTable>
        ) : (
          <Notice tone="info">No attendee has asked the assistant anything yet.</Notice>
        )}
      </section>
    </div>
  );
}
