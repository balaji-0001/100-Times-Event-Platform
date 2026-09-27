import { useState } from 'react';
import { Play } from 'lucide-react';
import { useMe, useOutreachStats, useProcessFollowups, useRunOutreachBatch } from './api';
import { Badge, Btn, DL, ErrorState, Notice, PageHeader, Panel, Section, inputClass } from './ui';
import { ManualResearchForm } from './ManualResearch';

export function SettingsPage() {
  const me = useMe();
  const stats = useOutreachStats();
  const runBatch = useRunOutreachBatch();
  const followups = useProcessFollowups();
  const [maxCandidates, setMaxCandidates] = useState('10');

  return (
    <div>
      <PageHeader kicker="Settings" title="Console settings and agent controls" subtitle="Agent configuration lives in the server environment (.env). Agents run only when triggered from this console." />

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Panel className="p-6">
          <Section title="Signed in as"><DL rows={[['Name', me.data?.name ?? '—'], ['Email', me.data?.email ?? '—'], ['Role', me.data?.role ?? '—']]} /></Section>
          <Section title="Email delivery">
            <DL rows={[['Provider', stats.data ? <Badge tone={stats.data.emailProviderStatus === 'REAL' ? 'good' : 'warn'}>{stats.data.emailProviderStatus === 'REAL' ? 'SMTP configured' : 'Not configured (mock)'}</Badge> : '—']]} />
            {stats.data?.emailProviderStatus === 'NOT_CONFIGURED' && <div className="mt-3"><Notice tone="warn">Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM_EMAIL in the API server's .env to send real emails. Until then, approved emails are logged only.</Notice></div>}
          </Section>
          <Section title="Schedules">
            <p className="text-sm text-muted-foreground">Agent 1's automatic discovery scan has its own on/off switch on the Dashboard — off by default, takes effect immediately either way. Outreach batches are drafted only via “Generate outreach batch”, and every email still waits for approval regardless of that switch.</p>
          </Section>
        </Panel>

        <Panel className="p-6">
          <Section title="Run Organizer Discovery (Agent 1) — manual research">
            <ManualResearchForm />
          </Section>
          <Section title="Run Organizer Outreach (Agent 2)">
            <div className="grid gap-2 text-xs">
              <label>Max organizers to draft for<input type="number" min={1} max={200} value={maxCandidates} onChange={(e) => setMaxCandidates(e.target.value)} className={`${inputClass} mt-1`} /></label>
              <div className="flex flex-wrap gap-2">
                <Btn variant="primary" loading={runBatch.isPending} onClick={() => runBatch.mutate({ maxCandidates: Number(maxCandidates) || undefined })}><Play size={13} /> Generate outreach batch</Btn>
                <Btn loading={followups.isPending} onClick={() => followups.mutate()}>Process follow-ups</Btn>
              </div>
              <p className="text-[11px] text-muted-foreground">Drafts land in Outreach → Pending. Nothing is sent until approved.</p>
              {runBatch.isError && <ErrorState error={runBatch.error} title="Batch failed" />}
              {runBatch.isSuccess && <Notice tone="info"><pre className="whitespace-pre-wrap font-mono-face text-[11px]">{JSON.stringify(runBatch.data, null, 2)}</pre></Notice>}
              {followups.isSuccess && <Notice tone="info"><pre className="whitespace-pre-wrap font-mono-face text-[11px]">{JSON.stringify(followups.data, null, 2)}</pre></Notice>}
            </div>
          </Section>
        </Panel>
      </div>
    </div>
  );
}
