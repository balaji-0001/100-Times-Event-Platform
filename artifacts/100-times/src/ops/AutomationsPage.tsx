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
import { DiscoverySettingsButton } from './DiscoverySettingsModal';
import { OutreachSettingsButton } from './OutreachSettingsModal';

function latestRun<T extends { startedAt: string; status: string; error?: string | null }>(runs: T[] | undefined) {
  if (!runs || runs.length === 0) return null;
  return [...runs].sort((a, b) => b.startedAt.localeCompare(a.startedAt))[0];
}

function RunStatusLine({ run }: { run: { startedAt: string; status: string; error?: string | null } | null }) {
  if (!run) return <p className="mt-2 text-xs text-muted-foreground">Hasn't run yet.</p>;
  const tone = run.status === 'failed' ? 'danger' : run.status === 'running' ? 'warn' : 'good';
  return (
    <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      Last run <Badge tone={tone}>{run.status}</Badge> {fmtDateTime(run.startedAt)}
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
  toggle?: { enabled: boolean; loading: boolean; onChange: (next: boolean) => void; label: string };
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

  return (
    <div>
      <PageHeader
        kicker="Automations"
        title="Everything that's automated, in one place"
        subtitle="What runs on its own, what's switched off, and when it last ran — nothing hidden, nothing guessed. Turn things on or off below, or ask for something new at the bottom."
      />

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <AutomationCard
          title="Agent 1 — Organizer Discovery"
          description="Discovers worldwide events and verified organizers across all sectors, saving them to 100 TIMES."
          trigger="Every 60 min, when on"
          toggle={{
            enabled: discoveryAuto.data?.enabled ?? false,
            loading: discoveryAuto.isLoading || setDiscoveryAuto.isPending,
            onChange: (next) => setDiscoveryAuto.mutate(next),
            label: 'Automatic discovery',
          }}
        >
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-foreground/10">
            <span className="text-[11px] text-muted-foreground">
              Scope: <strong>{discoveryAuto.data?.country || 'Worldwide'}</strong>
              {discoveryAuto.data?.categories?.length ? ` · ${discoveryAuto.data.categories.length} sectors` : ''}
            </span>
            <DiscoverySettingsButton size="sm" />
          </div>
          {discoveryRuns.isLoading ? <p className="mt-2 text-xs text-muted-foreground">Loading run history…</p> : <RunStatusLine run={lastDiscoveryRun} />}
          <Link href="/admin/discovery" className="mt-3 inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">View discoveries <ArrowRight size={11} /></Link>
        </AutomationCard>

        <AutomationCard
          title="Agent 2 — Outreach Drafting & Follow-ups"
          description="Drafts invitation emails to organizers Agent 1 found, and drafts a follow-up if there's no reply. Drafts only — never sends on its own."
          trigger="Draft every 60 min, follow-ups every 24h, when on"
          toggle={{
            enabled: outreachAuto.data?.enabled ?? false,
            loading: outreachAuto.isLoading || setOutreachAuto.isPending,
            onChange: (next) => setOutreachAuto.mutate(next),
            label: 'Automatic outreach drafting',
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
          {outreachRuns.isLoading ? <p className="mt-2 text-xs text-muted-foreground">Loading run history…</p> : <RunStatusLine run={lastOutreachRun} />}
          <p className="mt-2 text-xs text-muted-foreground">Every draft, timed or manual, waits in <strong>Pending Approval</strong> for a person to send it.</p>
          <Link href="/admin/outreach/pending" className="mt-3 inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">View pending outreach <ArrowRight size={11} /></Link>
        </AutomationCard>

        <AutomationCard
          title="Trust Agent — Verification & Safety"
          description="Checks every event an organizer submits for duplicates, scam language, and missing details, then scores it. High-confidence results publish or reject automatically; uncertain ones wait for a person."
          trigger="Instantly, on every submission"
        >
          <p className="mt-2 text-xs text-muted-foreground">Always on — there's no switch, because nothing runs on a timer here. It fires the moment an organizer submits an event, every time.</p>
          <Link href="/admin/trust-review" className="mt-3 inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">View trust review <ArrowRight size={11} /></Link>
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
