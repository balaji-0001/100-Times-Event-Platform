import { useState } from 'react';
import { Link } from 'wouter';
import { ArrowRight, Sparkles } from 'lucide-react';
import {
  useAutomationRequests, useCreateAutomationRequest,
  useDiscoveryAutoStatus, useSetDiscoveryAuto,
  useOutreachAutoStatus, useSetOutreachAuto,
  useDiscoveryRuns, useOutreachRuns,
} from './api';
import { Badge, Btn, EmptyState, ErrorState, LoadingState, Notice, PageHeader, Panel, Switch, fmtDateTime, inputClass } from './ui';
import { OutreachSettingsButton } from './OutreachSettingsModal';

function latestRun<T extends { startedAt: string; status: string; error?: string | null }>(runs: T[] | undefined) {
  if (!runs || runs.length === 0) return null;
  return [...runs].sort((a, b) => b.startedAt.localeCompare(a.startedAt))[0];
}

const linkClass = 'inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline';

/** Formats a schedule interval that came from the settings endpoint; null when the API didn't give one. */
function fmtInterval(minutes: number | null | undefined) {
  if (typeof minutes !== 'number' || !Number.isFinite(minutes) || minutes <= 0) return null;
  if (minutes >= 60 && minutes % 60 === 0) return `${minutes / 60}h`;
  return `${minutes} min`;
}

function RunStatusLine({ run, href }: { run: { id: number; startedAt: string; status: string; error?: string | null } | null; href?: string }) {
  if (!run) return <p className="mt-2 text-xs text-muted-foreground">Hasn't run yet.</p>;
  const tone = run.status === 'failed' ? 'danger' : run.status === 'running' ? 'warn' : 'good';
  return (
    <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      Last run {href ? <Link href={href} className="font-mono-face text-accent hover:underline">#{run.id}</Link> : <span className="font-mono-face">#{run.id}</span>} <Badge tone={tone}>{run.status}</Badge> {fmtDateTime(run.startedAt)}
      {run.status === 'failed' && run.error && <span className="text-red-700 dark:text-red-300">— {run.error}</span>}
    </p>
  );
}

/** One automation's card: what it does, in plain language, its live on/off
 * state (if it has a switch — Trust Agent doesn't, it's event-triggered),
 * and when it last actually ran. No invented numbers — every figure here
 * comes straight from a real AgentRun or the live toggle endpoint. */
function AutomationCard({
  title, description, trigger, toggle, children,
}: {
  title: string;
  description: string;
  trigger: string;
  toggle?: { enabled: boolean; loading: boolean; onChange: (next: boolean) => void; label: string; error?: unknown };
  children?: React.ReactNode;
}) {
  return (
    <Panel className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-bold">{title}</h3>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">{description}</p>
        </div>
        <Badge tone="info">{trigger}</Badge>
      </div>
      {toggle && (
        <div className="mt-4 flex items-center gap-3 rounded-full border border-foreground/15 bg-background px-3 py-1.5 w-fit">
          <Switch checked={toggle.enabled} disabled={toggle.loading} onChange={toggle.onChange} label={toggle.label} />
          <span className="text-[11px] font-bold">{toggle.enabled ? 'On' : 'Off'}</span>
        </div>
      )}
      {toggle?.error != null && (
        <p className="mt-2 text-xs text-red-700 dark:text-red-300">Couldn't change it: {toggle.error instanceof Error ? toggle.error.message : 'unknown error'}. It is still {toggle.enabled ? 'on' : 'off'}.</p>
      )}
      {children}
    </Panel>
  );
}

function RequestAutomationForm() {
  const [text, setText] = useState('');
  const create = useCreateAutomationRequest();

  const submit = () => {
    if (text.trim().length < 10) return;
    create.mutate(text.trim(), { onSuccess: () => setText('') });
  };

  return (
    <div className="space-y-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Describe what you want automated, in plain English. Example: “Automatically restrict an organizer after 3 bounced emails.”"
        rows={3}
        className={`${inputClass} resize-y`}
      />
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-muted-foreground">This goes to a developer to build — it doesn't start running by itself.</p>
        <Btn variant="primary" size="sm" loading={create.isPending} disabled={text.trim().length < 10} onClick={submit}>Submit request</Btn>
      </div>
      {create.isError && <ErrorState error={create.error} title="Couldn't submit that" />}
    </div>
  );
}

const STATUS_TONE = { NEW: 'accent', IN_PROGRESS: 'warn', DONE: 'good', DECLINED: 'neutral' } as const;
const STATUS_LABEL = { NEW: 'New', IN_PROGRESS: 'In progress', DONE: 'Done', DECLINED: 'Declined' } as const;

export function AutomationsPage() {
  const discoveryAuto = useDiscoveryAutoStatus();
  const setDiscoveryAuto = useSetDiscoveryAuto();
  const outreachAuto = useOutreachAutoStatus();
  const setOutreachAuto = useSetOutreachAuto();
  const discoveryRuns = useDiscoveryRuns();
  const outreachRuns = useOutreachRuns();
  const requests = useAutomationRequests();

  const lastDiscoveryRun = latestRun(discoveryRuns.data);
  const lastOutreachRun = latestRun(outreachRuns.data);

  const discoveryEvery = fmtInterval(discoveryAuto.data?.intervalMinutes);
  // Saved places only; with none saved the server's default target places are used (not "worldwide").
  const savedCountries = discoveryAuto.data ? (discoveryAuto.data.countries?.length ? discoveryAuto.data.countries : discoveryAuto.data.country ? [discoveryAuto.data.country] : []) : null;
  const discoveryScope = savedCountries === null
    ? null
    : savedCountries.length === 0
      ? ((discoveryAuto.data?.states?.length || discoveryAuto.data?.cities?.length) ? 'Selected states / cities' : 'Server default places')
      : savedCountries.length <= 3 ? savedCountries.join(', ') : `${savedCountries.slice(0, 3).join(', ')} +${savedCountries.length - 3} more`;
  const draftEvery = fmtInterval(outreachAuto.data?.draftIntervalMinutes);
  const followupEvery = fmtInterval(outreachAuto.data?.followupIntervalMinutes);
  const discoveryTrigger = discoveryAuto.isLoading
    ? 'Loading schedule…'
    : discoveryAuto.isError
    ? 'Status unavailable — could not load settings'
    : discoveryEvery ? `Every ${discoveryEvery}, when on` : 'Timed, when on (interval unavailable)';
  const outreachTrigger = outreachAuto.isLoading
    ? 'Loading schedule…'
    : outreachAuto.isError
    ? 'Status unavailable — could not load settings'
    : draftEvery || followupEvery
    ? [draftEvery && `Draft every ${draftEvery}`, followupEvery && `follow-ups every ${followupEvery}`].filter(Boolean).join(', ') + ', when on'
    : 'Timed, when on (interval unavailable)';

  return (
    <div>
      <PageHeader
        kicker="Automations"
        title="Everything that's automated, in one place"
        subtitle="What runs on its own, what's switched off, and when it last ran — nothing hidden, nothing guessed. Turn things on or off below, or ask for something new at the bottom."
      />

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <AutomationCard
          title="Automatic discovery"
          description="Finds events and their organizers on a schedule, using the saved discovery configuration — the same pipeline and rules as a run you start yourself."
          trigger={discoveryTrigger}
          toggle={{
            enabled: discoveryAuto.data?.enabled ?? false,
            loading: discoveryAuto.isLoading || discoveryAuto.isError || setDiscoveryAuto.isPending,
            onChange: (next) => setDiscoveryAuto.mutate(next),
            label: 'Automatic discovery',
            error: setDiscoveryAuto.isError ? setDiscoveryAuto.error : null,
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2 mt-2 pt-2 border-t border-foreground/10">
            <span className="text-[11px] text-muted-foreground">
              Scope: <strong>{discoveryScope ?? '—'}</strong>
              {discoveryAuto.data ? (discoveryAuto.data.categories?.length ? ` · ${discoveryAuto.data.categories.length} sectors` : ' · all sectors') : ''}
            </span>
            <Link href="/admin/discover/configuration" className={linkClass}>Configuration <ArrowRight size={11} /></Link>
          </div>
          {discoveryRuns.isLoading ? <p className="mt-2 text-xs text-muted-foreground">Loading run history…</p> : discoveryRuns.isError ? <p className="mt-2 text-xs text-red-700 dark:text-red-300">Could not load run history.</p> : <RunStatusLine run={lastDiscoveryRun} href={lastDiscoveryRun ? `/admin/discover/runs/${lastDiscoveryRun.id}` : undefined} />}
          <div className="mt-3 flex flex-wrap gap-4">
            <Link href="/admin/discover/automatic" className={linkClass}>Manage automatic discovery <ArrowRight size={11} /></Link>
            <Link href="/admin/discovery" className={linkClass}>New discoveries <ArrowRight size={11} /></Link>
          </div>
        </AutomationCard>

        <AutomationCard
          title="Agent 2 — Outreach Drafting & Follow-ups"
          description="Drafts invitation emails to organizers Agent 1 found, and drafts a follow-up if there's no reply. Drafts only — never sends on its own."
          trigger={outreachTrigger}
          toggle={{
            enabled: outreachAuto.data?.enabled ?? false,
            loading: outreachAuto.isLoading || outreachAuto.isError || setOutreachAuto.isPending,
            onChange: (next) => setOutreachAuto.mutate(next),
            label: 'Automatic outreach drafting',
            error: setOutreachAuto.isError ? setOutreachAuto.error : null,
          }}
        >
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-foreground/10">
            <span className="text-[11px] text-muted-foreground">
              Targeting: <strong>{outreachAuto.data?.categories?.length ? `${outreachAuto.data.categories.length} sectors` : 'All sectors'}</strong>
              {outreachAuto.data?.maxCandidates ? ` · ${outreachAuto.data.maxCandidates}/run` : ''}
              {outreachAuto.data?.dailyLimit ? ` · Cap: ${outreachAuto.data.dailyLimit}/day` : ''}
            </span>
            <OutreachSettingsButton size="sm" />
          </div>
          {outreachRuns.isLoading ? <p className="mt-2 text-xs text-muted-foreground">Loading run history…</p> : outreachRuns.isError ? <p className="mt-2 text-xs text-red-700 dark:text-red-300">Could not load run history.</p> : <RunStatusLine run={lastOutreachRun} href={lastOutreachRun ? '/admin/discover/runs?agent=outreach' : undefined} />}
          <p className="mt-2 text-xs text-muted-foreground">Every draft, timed or manual, waits in <strong>Pending Approval</strong> for a person to send it.</p>
          <Link href="/admin/outreach/pending" className={`mt-3 ${linkClass}`}>View pending outreach <ArrowRight size={11} /></Link>
        </AutomationCard>

        <AutomationCard
          title="Trust Agent — Verification & Safety"
          description="Checks every event an organizer submits for duplicates, scam language, and missing details, then scores it. High-confidence results publish or reject automatically; uncertain ones wait for a person."
          trigger="Instantly, on every submission"
        >
          <p className="mt-2 text-xs text-muted-foreground">Always on — there's no switch, because nothing runs on a timer here. It fires the moment an organizer submits an event, every time.</p>
          <Link href="/admin/trust-review" className={`mt-3 ${linkClass}`}>View trust review <ArrowRight size={11} /></Link>
        </AutomationCard>

        <Panel className="p-6">
          <div className="flex items-center gap-2"><Sparkles size={16} className="text-accent" /><h3 className="font-display text-lg font-bold">What's deliberately manual</h3></div>
          <p className="mt-2 text-sm text-muted-foreground">Two things never run on a timer, by design, no matter what's switched on above:</p>
          <ul className="mt-3 space-y-2 text-sm">
            <li>• <strong>Sending an outreach email.</strong> Drafting can be automatic; sending always needs a person to click Approve, then Send.</li>
            <li>• <strong>Deciding a borderline Trust Review case.</strong> The Trust Agent auto-decides only when it's confident; everything else waits in the review queue.</li>
          </ul>
        </Panel>
      </div>

      <Panel className="mt-6 p-6">
        <h3 className="font-display text-lg font-bold">Request a new automation</h3>
        <p className="mt-1 text-sm text-muted-foreground">Describe what you want automated. This is a request queue a developer reviews, not a self-service builder — nothing here writes or runs new code by itself.</p>
        <div className="mt-4"><RequestAutomationForm /></div>

        <div className="mt-6">
          {requests.isLoading ? <LoadingState label="Loading requests" /> : requests.isError ? <ErrorState error={requests.error} retry={() => requests.refetch()} /> : (requests.data ?? []).length === 0 ? (
            <EmptyState title="No automation requests yet." body="Submitted requests will show up here with their status." />
          ) : (
            <ol className="divide-y divide-foreground/10">
              {(requests.data ?? []).map((r) => (
                <li key={r.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Badge tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Badge>
                    <span className="font-mono-face text-[10px] text-muted-foreground">{fmtDateTime(r.createdAt)} · {r.requestedBy ?? 'unknown'}</span>
                  </div>
                  <p className="mt-2 text-sm">{r.description}</p>
                  {r.note && <Notice tone="info">{r.note}</Notice>}
                </li>
              ))}
            </ol>
          )}
        </div>
      </Panel>
    </div>
  );
}
