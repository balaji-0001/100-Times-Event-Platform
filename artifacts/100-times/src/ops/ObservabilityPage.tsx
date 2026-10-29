import { type ReactNode, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { customFetch } from '@workspace/api-client-react';
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Cpu,
  DollarSign,
  ExternalLink,
  Layers,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { Badge, ErrorState, Kicker, LoadingState, StatCard, cx } from './ui';
import { type DiscoveryRunsUsage, LatestRunUsage, RunUsageHistory } from './DiscoveryRunUsage';

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
// Durations read best in the largest whole unit: 850 ms, 61.1 s, 4.2 min.
const ms = (v: number | null | undefined) => {
  if (!isNum(v)) return '—';
  if (v < 1000) return `${Math.round(v)} ms`;
  if (v < 60_000) return `${(v / 1000).toFixed(1)} s`;
  return `${(v / 60_000).toFixed(1)} min`;
};
const healthTone = (h: string) => (h === 'HEALTHY' ? 'good' : h === 'UNKNOWN' ? 'neutral' : 'warn');

interface OverviewMetrics {
  totalExecutions: number;
  successCount: number;
  failureCount: number;
  successRate: number | null;
  avgLatencyMs: number | null;
  totalTokens: number;
  estimatedCostUsd: number;
  guardrailBlocks: number;
  systemHealth: string;
}

interface AgentTelemetry {
  id: string;
  name: string;
  category: string;
  status: string;
  totalRuns: number;
  successCount: number;
  failureCount: number;
  avgDurationMs: number | null;
  lastExecution: string | null;
  recentError: string | null;
}

interface WorkflowTrace {
  id: number;
  workflowId: string;
  agentName: string;
  status: string;
  durationMs: number | null;
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
  estimatedCost: number | null;
  modelName: string | null;
  errorMessage: string | null;
  createdAt: string;
}

interface ErrorItem {
  type: string;
  source: string;
  workflowId: string;
  message: string;
  severity: string;
  timestamp: string;
}

interface AIUsageData {
  models: Record<
    string,
    {
      calls: number;
      promptTokens: number;
      completionTokens: number;
      totalTokens: number;
      costUsd: number;
      costComplete?: boolean; // false when some calls used a model without a known price
    }
  >;
  searchProviders?: {
    runsCounted: number;
    providers: SearchProviderUsage[];
  };
  discoveryRuns?: DiscoveryRunsUsage;
  currency: string;
  lastUpdated: string;
}

interface SearchProviderUsage {
  id: string;
  name: string;
  isFree: boolean;
  configured: boolean;
  unavailableReason: string | null;
  runs: number;
  calls: number;
  successes: number;
  failures: number;
  rateLimited: number;
  results: number;
  costUsd: number | null; // only what the provider itself reported
  lastUsedAt: string | null;
}

function SearchProviderCard({ p }: { p: SearchProviderUsage }) {
  const row = (label: string, value: ReactNode) => (
    <div className="flex justify-between gap-3 text-muted-foreground">
      <span>{label}</span>
      <span className="font-mono text-foreground">{value}</span>
    </div>
  );
  return (
    <div className={cx('rounded-2xl border border-foreground/10 bg-card p-5 space-y-3', !p.configured && !p.calls && 'opacity-70')} data-testid={`card-search-provider-${p.id}`}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display text-sm font-bold text-foreground">{p.name}</h3>
        <div className="flex shrink-0 gap-1.5">
          <Badge tone={p.isFree ? 'good' : 'neutral'}>{p.isFree ? 'Free' : 'Paid'}</Badge>
          {p.configured ? <Badge tone="good">Set up</Badge> : <Badge tone="warn">Not set up</Badge>}
        </div>
      </div>
      {!p.configured && p.unavailableReason && <p className="text-[11px] text-muted-foreground">{p.unavailableReason}</p>}
      <div className="space-y-1 text-xs">
        {row('Searches:', p.calls.toLocaleString())}
        {row('Succeeded / failed:', `${p.successes.toLocaleString()} / ${p.failures.toLocaleString()}`)}
        {p.rateLimited > 0 && row('Rate-limited:', p.rateLimited.toLocaleString())}
        {row('Results returned:', p.results.toLocaleString())}
        {row('Used in runs:', p.runs.toLocaleString())}
        <div className="mt-2 flex justify-between gap-3 border-t border-foreground/5 pt-2 text-muted-foreground">
          <span className="font-semibold text-foreground">Cost:</span>
          <span className="font-mono font-bold text-accent">
            {p.costUsd !== null ? `$${p.costUsd.toFixed(4)}` : p.isFree ? '$0 (free)' : p.calls ? 'Not reported by provider' : '—'}
          </span>
        </div>
        {p.lastUsedAt && <p className="pt-1 text-[11px] text-muted-foreground">Last used {new Date(p.lastUsedAt).toLocaleString()}</p>}
      </div>
    </div>
  );
}

interface GuardrailLogItem {
  id: number;
  workflowId: string | null;
  agentName: string;
  decision: string;
  reason: string;
  ruleName: string;
  inputSnippet: string | null;
  createdAt: string;
}

export function ObservabilityPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'agents' | 'traces' | 'errors' | 'ai-usage' | 'guardrails'>('overview');
  const [traceSearch, setTraceSearch] = useState('');
  const [traceAgentFilter, setTraceAgentFilter] = useState('ALL');
  const [traceStatusFilter, setTraceStatusFilter] = useState('ALL');

  const overviewQuery = useQuery({
    queryKey: ['admin', 'observability', 'overview'],
    queryFn: () => customFetch<OverviewMetrics>('/api/admin/observability/overview'),
    refetchInterval: 15000,
  });

  const agentsQuery = useQuery({
    queryKey: ['admin', 'observability', 'agents'],
    queryFn: () => customFetch<AgentTelemetry[]>('/api/admin/observability/agents'),
    refetchInterval: 15000,
  });

  const tracesQuery = useQuery({
    queryKey: ['admin', 'observability', 'traces', traceSearch, traceAgentFilter, traceStatusFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (traceSearch) params.set('q', traceSearch);
      if (traceAgentFilter !== 'ALL') params.set('agent', traceAgentFilter);
      if (traceStatusFilter !== 'ALL') params.set('status_filter', traceStatusFilter);
      return customFetch<WorkflowTrace[]>(`/api/admin/observability/traces?${params.toString()}`);
    },
    refetchInterval: 15000,
  });

  const errorsQuery = useQuery({
    queryKey: ['admin', 'observability', 'errors'],
    queryFn: () => customFetch<ErrorItem[]>('/api/admin/observability/errors'),
    refetchInterval: 15000,
  });

  const aiUsageQuery = useQuery({
    queryKey: ['admin', 'observability', 'ai-usage'],
    queryFn: () => customFetch<AIUsageData>('/api/admin/observability/ai-usage'),
    refetchInterval: 30000,
  });

  const guardrailsQuery = useQuery({
    queryKey: ['admin', 'observability', 'guardrails'],
    queryFn: () => customFetch<GuardrailLogItem[]>('/api/admin/observability/guardrails'),
    refetchInterval: 15000,
  });

  const isLoading = overviewQuery.isLoading || agentsQuery.isLoading;
  const overview = overviewQuery.data;
  const agents = agentsQuery.data ?? [];
  const traces = tracesQuery.data ?? [];
  const errors = errorsQuery.data ?? [];
  const aiUsage = aiUsageQuery.data;
  const guardrails = guardrailsQuery.data ?? [];

  if (isLoading) {
    return <LoadingState label="Collecting real-time telemetry, OpenTelemetry traces & agent metrics..." />;
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Kicker>Observability & Reliability Infrastructure</Kicker>
          <h1 className="mt-2 font-display text-3xl font-extrabold tracking-tight">AI & System Observability</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Distributed tracing, Prometheus OpenMetrics, agent execution health, safety guardrails & AI token cost tracking.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {overviewQuery.isError ? (
            <Badge tone="danger">● System: UNKNOWN (telemetry unavailable)</Badge>
          ) : overview?.systemHealth ? (
            <Badge tone={healthTone(overview.systemHealth)}>● System: {overview.systemHealth}</Badge>
          ) : (
            <Badge tone="neutral">● System: UNKNOWN</Badge>
          )}
          <button
            onClick={() => {
              overviewQuery.refetch();
              agentsQuery.refetch();
              tracesQuery.refetch();
              errorsQuery.refetch();
              aiUsageQuery.refetch();
              guardrailsQuery.refetch();
            }}
            className="flex items-center gap-2 rounded-xl border border-foreground/15 bg-card px-3 py-2 text-xs font-semibold hover:border-accent"
          >
            <RefreshCw size={14} className={overviewQuery.isFetching ? 'animate-spin text-accent' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-foreground/10 pb-3">
        {(
          [
            { key: 'overview', label: 'Overview', icon: Activity },
            { key: 'agents', label: `Agent Monitor (${agents.length})`, icon: Bot },
            { key: 'traces', label: `Workflow Traces (${traces.length})`, icon: Layers },
            { key: 'errors', label: `Error Center (${errors.length})`, icon: AlertTriangle },
            { key: 'ai-usage', label: 'AI Usage & Cost', icon: DollarSign },
            { key: 'guardrails', label: `Safety Guardrails (${guardrails.length})`, icon: ShieldCheck },
          ] as const
        ).map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold transition ${
                isActive ? 'bg-accent text-accent-foreground shadow-sm' : 'bg-card text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab: Overview */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {overviewQuery.isError && (
            <ErrorState title="Could not load telemetry overview." error={overviewQuery.error} retry={() => overviewQuery.refetch()} />
          )}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6">
            <StatCard label="Total Workflows" value={overview ? overview.totalExecutions : '—'} sub={overview ? `${overview.successCount} succeeded` : undefined} />
            <StatCard
              label="Success Rate"
              value={isNum(overview?.successRate) ? `${overview.successRate}%` : '—'}
              tone={isNum(overview?.successRate) ? (overview.successRate >= 95 ? 'good' : 'warn') : undefined}
              sub={overview ? `${overview.failureCount} failures recorded` : undefined}
            />
            <StatCard label="Avg Duration" value={ms(overview?.avgLatencyMs)} sub="Agent task execution" />
            <StatCard label="Total AI Tokens" value={isNum(overview?.totalTokens) ? overview.totalTokens.toLocaleString() : '—'} sub="Across all models" />
            <StatCard label="Estimated Cost" value={isNum(overview?.estimatedCostUsd) ? `$${overview.estimatedCostUsd.toFixed(4)}` : '—'} sub="USD cumulative" />
            <StatCard
              label="Guardrail Blocks"
              value={overview ? overview.guardrailBlocks : '—'}
              tone={overview && overview.guardrailBlocks > 0 ? 'warn' : undefined}
              sub="Attacks & bad inputs"
            />
          </div>

          {/* Infrastructure Health & Diagnostics */}
          <div className="rounded-2xl border border-foreground/10 bg-card p-6 space-y-4">
            <h2 className="font-display text-lg font-bold">Telemetry Endpoints & Metrics Scraping</h2>
            <p className="text-xs text-muted-foreground">
              Production-ready health checks and OpenMetrics Prometheus exporters active on the FastAPI service.
            </p>
            <div className="grid gap-4 md:grid-cols-3">
              <a
                href="/api/ready"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-xl border border-foreground/10 bg-background/50 p-4 hover:border-accent"
              >
                <div>
                  <p className="text-sm font-semibold flex items-center gap-2">
                    <CheckCircle2 size={16} className="text-emerald-500" /> Database Readiness Probe
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">GET /api/ready (MySQL connectivity)</p>
                </div>
                <ExternalLink size={14} className="text-muted-foreground" />
              </a>

              <a
                href="/api/metrics"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-xl border border-foreground/10 bg-background/50 p-4 hover:border-accent"
              >
                <div>
                  <p className="text-sm font-semibold flex items-center gap-2">
                    <Zap size={16} className="text-amber-500" /> Prometheus Metrics Exporter
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">GET /api/metrics (OpenMetrics format)</p>
                </div>
                <ExternalLink size={14} className="text-muted-foreground" />
              </a>

              <a
                href="/openapi.json"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-xl border border-foreground/10 bg-background/50 p-4 hover:border-accent"
              >
                <div>
                  <p className="text-sm font-semibold flex items-center gap-2">
                    <Cpu size={16} className="text-sky-500" /> OpenAPI 3.1 Specification
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">GET /openapi.json (API contracts)</p>
                </div>
                <ExternalLink size={14} className="text-muted-foreground" />
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Agent Monitor */}
      {activeTab === 'agents' && agentsQuery.isError && (
        <ErrorState title="Could not load agent telemetry." error={agentsQuery.error} retry={() => agentsQuery.refetch()} />
      )}
      {activeTab === 'agents' && !agentsQuery.isError && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {agents.length === 0 && (
            <p className="text-sm text-muted-foreground">No agent telemetry recorded yet.</p>
          )}
          {agents.map((agent) => (
            <div key={agent.id} className="rounded-2xl border border-foreground/10 bg-card p-5 space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-[11px] font-mono-face uppercase tracking-wider text-muted-foreground">{agent.category}</span>
                  <h3 className="font-display text-base font-bold text-foreground mt-0.5">{agent.name}</h3>
                </div>
                <Badge tone={agent.status === 'ACTIVE' ? 'good' : agent.status === 'DEGRADED' ? 'warn' : 'neutral'}>
                  {agent.status}
                </Badge>
              </div>

              <div className="grid grid-cols-2 gap-3 border-y border-foreground/5 py-3 text-xs">
                <div>
                  <span className="text-muted-foreground">Total Runs</span>
                  <p className="font-semibold text-foreground text-sm mt-0.5">{agent.totalRuns}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Success / Fail</span>
                  <p className="font-semibold text-foreground text-sm mt-0.5">
                    <span className="text-emerald-500">{agent.successCount}</span> /{' '}
                    <span className={agent.failureCount > 0 ? 'text-rose-500' : 'text-muted-foreground'}>{agent.failureCount}</span>
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Avg Latency</span>
                  <p className="font-semibold text-foreground text-sm mt-0.5">{ms(agent.avgDurationMs)}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Last Executed</span>
                  <p className="font-semibold text-foreground text-sm mt-0.5">
                    {agent.lastExecution ? new Date(agent.lastExecution).toLocaleString() : 'Never'}
                  </p>
                </div>
              </div>

              {agent.recentError && (
                <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-xs text-rose-400">
                  <p className="font-semibold">Recent Issue:</p>
                  <p className="mt-0.5 font-mono text-[11px] truncate">{agent.recentError}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Tab: Workflow Traces */}
      {activeTab === 'traces' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={traceSearch}
                onChange={(e) => setTraceSearch(e.target.value)}
                placeholder="Search by workflow ID (e.g. wf-e8a7bc)..."
                className="w-full rounded-xl border border-foreground/15 bg-background pl-9 pr-4 py-2 text-xs outline-none focus:border-accent"
              />
            </div>
            <select
              value={traceAgentFilter}
              onChange={(e) => setTraceAgentFilter(e.target.value)}
              className="rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs outline-none"
            >
              <option value="ALL">All Agents</option>
              <option value="Discovery">Discovery Agent</option>
              <option value="Trust">Trust & Safety Agent</option>
              <option value="Outreach">Outreach Agent</option>
              <option value="Promotions">Social promotion (automation)</option>
            </select>
            <select
              value={traceStatusFilter}
              onChange={(e) => setTraceStatusFilter(e.target.value)}
              className="rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs outline-none"
            >
              <option value="ALL">All Statuses</option>
              <option value="SUCCESS">Success Only</option>
              <option value="FAILED">Failed Only</option>
            </select>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-foreground/10 bg-card">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-foreground/10 bg-muted/30 font-semibold text-muted-foreground">
                <tr>
                  <th className="p-3">Workflow ID</th>
                  <th className="p-3">Agent</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Duration</th>
                  <th className="p-3">Tokens</th>
                  <th className="p-3">Cost</th>
                  <th className="p-3">Model</th>
                  <th className="p-3">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-foreground/5">
                {tracesQuery.isError ? (
                  <tr>
                    <td colSpan={8} className="p-8 text-center text-red-600 dark:text-red-300">
                      Could not load workflow traces: {errMsg(tracesQuery.error)}
                    </td>
                  </tr>
                ) : traces.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-8 text-center text-muted-foreground">
                      No matching workflow traces found.
                    </td>
                  </tr>
                ) : (
                  traces.map((tr) => (
                    <tr key={tr.id} className="hover:bg-muted/20">
                      <td className="p-3 font-mono text-[11px] text-accent font-semibold">{tr.workflowId}</td>
                      <td className="p-3 font-medium">{tr.agentName}</td>
                      <td className="p-3">
                        <Badge tone={tr.status === 'SUCCESS' ? 'good' : 'warn'}>{tr.status}</Badge>
                      </td>
                      <td className="p-3">{ms(tr.durationMs)}</td>
                      <td className="p-3">{isNum(tr.totalTokens) ? tr.totalTokens.toLocaleString() : '—'}</td>
                      <td className="p-3">{isNum(tr.estimatedCost) ? `$${tr.estimatedCost.toFixed(5)}` : '—'}</td>
                      <td className="p-3 font-mono text-[11px] text-muted-foreground">{tr.modelName ?? "—"}</td>
                      <td className="p-3 text-muted-foreground">{new Date(tr.createdAt).toLocaleTimeString()}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Error Center */}
      {activeTab === 'errors' && (
        <div className="space-y-4">
          {errorsQuery.isError ? (
            <ErrorState title="Could not load the error feed." error={errorsQuery.error} retry={() => errorsQuery.refetch()} />
          ) : errors.length === 0 ? (
            <div className="rounded-2xl border border-foreground/10 bg-card p-12 text-center text-muted-foreground">
              <CheckCircle2 size={32} className="mx-auto text-emerald-500 mb-2" />
              <p className="font-semibold text-foreground">Zero Active Failures</p>
              <p className="text-xs mt-1">All agent workflows and integrations are operating normally without uncaught exceptions.</p>
            </div>
          ) : (
            errors.map((err, idx) => (
              <div key={idx} className="rounded-2xl border border-rose-500/20 bg-card p-4 flex items-start gap-4">
                <AlertTriangle size={18} className="text-rose-500 mt-0.5 shrink-0" />
                <div className="flex-1 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-foreground text-xs">{err.source}</span>
                    <span className="text-[11px] text-muted-foreground font-mono">{new Date(err.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <p className="text-xs text-rose-300 font-mono bg-rose-950/20 p-2.5 rounded-lg">{err.message}</p>
                  <p className="text-[11px] text-muted-foreground">Workflow: <span className="font-mono text-foreground">{err.workflowId}</span></p>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab: AI Usage & Cost */}
      {activeTab === 'ai-usage' && (
        <div className="space-y-6">
          {aiUsageQuery.isError && (
            <ErrorState title="Could not load AI usage." error={aiUsageQuery.error} retry={() => aiUsageQuery.refetch()} />
          )}
          {aiUsage?.discoveryRuns?.latest ? (
            <LatestRunUsage run={aiUsage.discoveryRuns.latest} />
          ) : (
            aiUsage && <p className="text-sm text-muted-foreground">No discovery run has recorded usage yet. Start a run and its searches, AI calls and costs appear here.</p>
          )}
          {(aiUsage?.discoveryRuns?.history.length ?? 0) > 0 && <RunUsageHistory runs={aiUsage!.discoveryRuns!.history} />}

          <h2 className="pt-4 font-display text-base font-bold">AI models · all runs</h2>
          {!aiUsageQuery.isError && aiUsage && Object.keys(aiUsage.models ?? {}).length === 0 && (
            <p className="text-sm text-muted-foreground">No AI model usage recorded yet.</p>
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(aiUsage?.models ?? {}).map(([modelName, data]) => (
              <div key={modelName} className="rounded-2xl border border-foreground/10 bg-card p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-display font-bold text-foreground text-sm">{modelName}</h3>
                  <Badge tone="good">{data.calls} calls</Badge>
                </div>
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between text-muted-foreground">
                    <span>Prompt Tokens:</span>
                    <span className="font-mono text-foreground">{data.promptTokens.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>Completion Tokens:</span>
                    <span className="font-mono text-foreground">{data.completionTokens.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>Total Tokens:</span>
                    <span className="font-mono font-bold text-foreground">{data.totalTokens.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-muted-foreground border-t border-foreground/5 pt-2 mt-2">
                    <span className="font-semibold text-foreground">Estimated Cost:</span>
                    <span className="font-mono font-bold text-accent">
                      ${data.costUsd.toFixed(5)}{data.costComplete === false && ' + unknown'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {aiUsage?.searchProviders && (
            <div className="space-y-3 pt-4" data-testid="section-search-provider-usage">
              <div>
                <h2 className="font-display text-base font-bold">Web search providers · all runs</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Searches made by the Discovery Agent, totalled from {aiUsage.searchProviders.runsCounted} discovery run
                  {aiUsage.searchProviders.runsCounted === 1 ? '' : 's'} with a provider report. Cost is shown only where the provider reports it (Exa does; Brave doesn't).
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {aiUsage.searchProviders.providers.map((p) => <SearchProviderCard key={p.id} p={p} />)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab: Safety Guardrails */}
      {activeTab === 'guardrails' && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-foreground/10 bg-card p-5">
            <h2 className="font-display text-base font-bold flex items-center gap-2">
              <ShieldAlert size={16} className="text-accent" /> Active AI Security & Input Defense Rules
            </h2>
            <p className="text-xs text-muted-foreground mt-1">
              Every external scraped web page, prompt injection attempt, SSRF URL, and adversarial payload is intercepted before reaching LLM context.
            </p>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-foreground/10 bg-card">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-foreground/10 bg-muted/30 font-semibold text-muted-foreground">
                <tr>
                  <th className="p-3">Decision</th>
                  <th className="p-3">Rule</th>
                  <th className="p-3">Agent</th>
                  <th className="p-3">Reason / Details</th>
                  <th className="p-3">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-foreground/5">
                {guardrailsQuery.isError ? (
                  <tr>
                    <td colSpan={5} className="p-8 text-center text-red-600 dark:text-red-300">
                      Could not load guardrail logs: {errMsg(guardrailsQuery.error)}
                    </td>
                  </tr>
                ) : guardrails.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-8 text-center text-muted-foreground">
                      No guardrail events recorded.
                    </td>
                  </tr>
                ) : (
                  guardrails.map((g) => (
                    <tr key={g.id} className="hover:bg-muted/20">
                      <td className="p-3">
                        <Badge tone={g.decision === 'ALLOWED' ? 'good' : 'warn'}>{g.decision}</Badge>
                      </td>
                      <td className="p-3 font-mono font-semibold">{g.ruleName}</td>
                      <td className="p-3">{g.agentName}</td>
                      <td className="p-3 text-muted-foreground">{g.reason}</td>
                      <td className="p-3 text-muted-foreground">{new Date(g.createdAt).toLocaleTimeString()}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

