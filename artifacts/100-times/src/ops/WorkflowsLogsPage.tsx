import { useQuery } from '@tanstack/react-query';
import { customFetch } from '@workspace/api-client-react';
import { Workflow, ShieldCheck, CheckCircle2 } from 'lucide-react';
import { Badge, Kicker, LoadingState } from './ui';

interface WorkflowDef {
  id: string;
  file: string;
  name: string;
  webhook: string;
  trigger: string;
  description: string;
}

interface AutomationRunItem {
  id: number;
  workflowId: string;
  workflowName: string;
  idempotencyKey: string;
  triggerEvent: string;
  entityType?: string | null;
  entityId?: number | null;
  status: string;
  startedAt: string;
}

interface AuditLogItem {
  id: number;
  actor: string;
  action: string;
  entity: string;
  entityId?: string | null;
  result: string;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export function WorkflowsLogsPage({ mode = 'workflows' }: { mode?: 'workflows' | 'audit' }) {
  const wfQuery = useQuery({
    queryKey: ['ops', 'n8n-workflows'],
    queryFn: () => customFetch<WorkflowDef[]>('/api/webhooks/n8n/workflows'),
  });

  const runsQuery = useQuery({
    queryKey: ['ops', 'automation-runs'],
    queryFn: () => customFetch<AutomationRunItem[]>('/api/admin/automation-runs'),
  });

  const auditQuery = useQuery({
    queryKey: ['ops', 'audit-logs'],
    queryFn: () => customFetch<AuditLogItem[]>('/api/admin/audit-logs?limit=100'),
  });

  if (wfQuery.isLoading || runsQuery.isLoading || auditQuery.isLoading) {
    return <LoadingState label="Loading n8n workflows & audit trail" />;
  }

  const workflows = wfQuery.data ?? [];
  const runs = runsQuery.data ?? [];
  const audits = auditQuery.data ?? [];

  return (
    <div className="space-y-8">
      <div>
        <Kicker>{mode === 'audit' ? 'Security & Compliance' : 'n8n Automation Architecture'}</Kicker>
        <h1 className="mt-2 font-display text-3xl font-extrabold tracking-tight">
          {mode === 'audit' ? 'System & Security Audit Logs' : 'n8n Workflows & Idempotent Executions'}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {mode === 'audit'
            ? 'Immutable audit trail across organizer signup, event lifecycle, Trust Agent decisions, registrations, and notifications.'
            : 'All 8 reusable n8n workflows exported in /n8n/workflows/ with HMAC secret verification and idempotency keys.'}
        </p>
      </div>

      {mode === 'workflows' && (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {workflows.map((wf) => (
              <div key={wf.id} className="rounded-2xl border border-foreground/10 bg-card p-5 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-2 font-display text-base font-bold">
                    <Workflow size={16} className="text-accent" /> {wf.name}
                  </span>
                  <Badge tone="good">ACTIVE</Badge>
                </div>
                <p className="text-xs text-muted-foreground">{wf.description}</p>
                <div className="flex flex-wrap items-center justify-between gap-2 pt-2 font-mono-face text-[11px] text-muted-foreground">
                  <span>File: /n8n/workflows/{wf.file}</span>
                  <span className="text-accent">POST {wf.webhook}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-2xl border border-foreground/10 bg-card p-6 space-y-4">
            <h2 className="font-display text-lg font-bold">Recent Idempotent Workflow Runs ({runs.length})</h2>
            <div className="space-y-2">
              {runs.map((r) => (
                <div
                  key={r.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-foreground/10 bg-background p-3 text-xs"
                >
                  <div>
                    <span className="font-semibold">{r.workflowName}</span> ·{' '}
                    <span className="font-mono-face text-[11px] text-muted-foreground">{r.idempotencyKey}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={r.status === 'COMPLETED' ? 'good' : 'warn'}>{r.status}</Badge>
                    <span className="font-mono-face text-[10px] text-muted-foreground">
                      {new Date(r.startedAt).toLocaleString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="rounded-2xl border border-foreground/10 bg-card p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-bold flex items-center gap-2">
            <ShieldCheck size={18} className="text-accent" /> Platform Audit Trail ({audits.length})
          </h2>
          <span className="inline-flex items-center gap-1 font-mono-face text-[11px] text-emerald-400">
            <CheckCircle2 size={12} /> Secret Redaction Active
          </span>
        </div>
        <div className="space-y-2">
          {audits.map((log) => (
            <div
              key={log.id}
              className="flex flex-col justify-between gap-2 rounded-xl border border-foreground/10 bg-background p-3 text-xs sm:flex-row sm:items-center"
            >
              <div>
                <span className="rounded bg-muted px-2 py-0.5 font-mono-face text-[10px] font-bold">
                  {log.action}
                </span>{' '}
                <strong className="ml-1">{log.entity}</strong> #{log.entityId ?? 'N/A'} · by{' '}
                <span className="text-accent">{log.actor}</span>
              </div>
              <div className="flex items-center gap-3 font-mono-face text-[10px] text-muted-foreground">
                <span>{log.result}</span>
                <span>{new Date(log.createdAt).toLocaleString()}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
