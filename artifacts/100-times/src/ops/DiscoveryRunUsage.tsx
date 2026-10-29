import { Fragment, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Badge, StatCard, cx, fmtDateTime } from './ui';

// One discovery run's usage, as stored in agent_runs.summary.usage (see
// backend run_usage.py). Runs saved before tracking existed have
// `tracked: false`: their queries and AI usage were never recorded.

export type CostBasis =
  | 'reported_by_provider' | 'configured_price' | 'list_price' | 'no_fee' | 'failed_not_billed' | 'no_tokens' | 'unknown' | 'not_used';

export interface RunSearchProvider {
  id: string;
  name: string;
  used: boolean;
  calls: number;
  successes: number;
  failures: number;
  rate_limited: number;
  results: number;
  cost_usd: number | null;
  cost_basis: CostBasis;
}

export interface RunAIModel {
  model: string;
  provider: string | null;
  calls: number;
  failed_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  used_by: Record<string, number>;
  cost_usd: number | null;
  cost_basis: CostBasis;
}

export interface DiscoveryRunUsage {
  runId: number;
  status: string;
  startedAt: string | null;
  completedAt: string | null;
  tracked: boolean;
  validEvents: number;
  queries: { attempted: number; with_results: number; no_results: number; served_from_cache: number; no_provider: number } | null;
  provider_calls: { attempted: number; succeeded: number; failed: number; rate_limited: number };
  search_providers: RunSearchProvider[];
  ai_models: RunAIModel[] | null;
  ai_totals: { calls: number; failed_calls: number; prompt_tokens: number; completion_tokens: number; total_tokens: number } | null;
  costs: { search_usd: number; search_complete: boolean; ai_usd: number | null; ai_complete: boolean; total_usd: number; total_complete: boolean };
}

export interface DiscoveryRunsUsage {
  latest: DiscoveryRunUsage | null;
  history: DiscoveryRunUsage[];
}

const NOT_RECORDED = 'Not recorded';

export function usd(n: number) {
  if (n === 0) return '$0';
  return n < 1 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`; // discovery costs are usually fractions of a cent
}

/** A total that may include costs nobody reported or priced. */
function costText(amount: number | null, complete: boolean, anythingUsed: boolean) {
  if (amount === null) return NOT_RECORDED;
  if (!anythingUsed) return '$0';
  if (complete) return usd(amount);
  return amount > 0 ? `${usd(amount)} + unknown` : 'Unknown';
}

/** Search + AI. For a run saved before AI tracking, says so instead of "Unknown". */
function totalText(run: DiscoveryRunUsage) {
  const c = run.costs;
  const anySearch = usedProviders(run).length > 0;
  if (c.ai_usd === null) return `${costText(c.search_usd, c.search_complete, anySearch)} + AI not recorded`;
  return costText(c.total_usd, c.total_complete, anySearch || (run.ai_models?.length ?? 0) > 0);
}

const BASIS_LABEL: Record<CostBasis, string> = {
  reported_by_provider: 'reported by provider',
  configured_price: 'at configured price',
  list_price: 'at list price',
  no_fee: 'no per-search fee',
  failed_not_billed: "failed requests aren't billed",
  no_tokens: 'no tokens used',
  unknown: 'no price set',
  not_used: '',
};

function CostCell({ cost, basis }: { cost: number | null; basis: CostBasis }) {
  if (basis === 'not_used') return <span className="text-muted-foreground">Not used</span>;
  return (
    <span className="flex flex-col items-end leading-tight">
      <span className={cx('font-mono font-semibold', cost === null ? 'text-amber-700 dark:text-amber-300' : 'text-foreground')}>
        {cost === null ? 'Unknown' : usd(cost)}
      </span>
      <span className="text-[10px] text-muted-foreground">{BASIS_LABEL[basis]}</span>
    </span>
  );
}

const th = 'px-3 py-2 text-right font-mono-face text-[10px] font-medium uppercase tracking-wider text-muted-foreground';
const td = 'px-3 py-2 text-right tabular-nums';

/** Per-provider and per-model detail of one run. */
export function RunBreakdown({ run }: { run: DiscoveryRunUsage }) {
  const providers = [...run.search_providers].sort((a, b) => Number(b.used) - Number(a.used) || b.calls - a.calls);
  return (
    <div className="grid min-w-0 gap-4">
      <div className="min-w-0 overflow-x-auto rounded-xl border border-foreground/10 bg-card">
        <table className="w-full min-w-[560px] text-xs">
          <thead className="border-b border-foreground/10">
            <tr>
              <th className={cx(th, 'text-left')}>Search provider</th>
              <th className={th}>Attempted</th>
              <th className={th}>Succeeded</th>
              <th className={th}>Failed</th>
              <th className={th}>Results</th>
              <th className={th}>Cost</th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.id} className={cx('border-b border-foreground/5 last:border-0', !p.used && 'opacity-60')} data-testid={`run-provider-${p.id}`}>
                <td className="px-3 py-2 text-left font-semibold">{p.name}</td>
                <td className={td}>{p.calls}</td>
                <td className={td}>{p.successes}</td>
                <td className={td}>{p.failures}{p.rate_limited > 0 && <span className="text-muted-foreground"> ({p.rate_limited} rate-limited)</span>}</td>
                <td className={td}>{p.results}</td>
                <td className={td}><CostCell cost={p.cost_usd} basis={p.cost_basis} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="min-w-0 overflow-x-auto rounded-xl border border-foreground/10 bg-card">
        {run.ai_models === null ? (
          <p className="p-4 text-xs text-muted-foreground">AI model usage was not recorded for this run (it ran before per-run tracking was added).</p>
        ) : run.ai_models.length === 0 ? (
          <p className="p-4 text-xs text-muted-foreground">No AI model was called in this run.</p>
        ) : (
          <table className="w-full min-w-[560px] text-xs">
            <thead className="border-b border-foreground/10">
              <tr>
                <th className={cx(th, 'text-left')}>AI model</th>
                <th className={th}>Calls</th>
                <th className={th}>Prompt</th>
                <th className={th}>Completion</th>
                <th className={th}>Total tokens</th>
                <th className={th}>Cost</th>
              </tr>
            </thead>
            <tbody>
              {run.ai_models.map((m) => (
                <tr key={m.model} className="border-b border-foreground/5 last:border-0" data-testid={`run-model-${m.model}`}>
                  <td className="px-3 py-2 text-left">
                    <span className="font-semibold">{m.model}</span>
                    <span className="block text-[10px] text-muted-foreground">via {Object.keys(m.used_by).join(', ') || m.provider}</span>
                  </td>
                  <td className={td}>{m.calls}{m.failed_calls > 0 && <span className="text-muted-foreground"> ({m.failed_calls} failed)</span>}</td>
                  <td className={td}>{m.prompt_tokens.toLocaleString()}</td>
                  <td className={td}>{m.completion_tokens.toLocaleString()}</td>
                  <td className={cx(td, 'font-semibold')}>{m.total_tokens.toLocaleString()}</td>
                  <td className={td}><CostCell cost={m.cost_usd} basis={m.cost_basis} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function usedProviders(run: DiscoveryRunUsage) {
  return run.search_providers.filter((p) => p.used);
}

export function LatestRunUsage({ run }: { run: DiscoveryRunUsage }) {
  const q = run.queries;
  const ai = run.ai_totals;
  const c = run.costs;
  const anySearch = usedProviders(run).length > 0;
  const anyAI = (run.ai_models?.length ?? 0) > 0;
  return (
    <div className="space-y-4" data-testid="section-latest-run-usage">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-base font-bold">Latest discovery run · #{run.runId}</h2>
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          {fmtDateTime(run.startedAt)}
          <Badge tone={run.status === 'completed' ? 'good' : run.status === 'running' ? 'info' : 'warn'}>{run.status}</Badge>
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Search queries"
          value={q ? q.attempted.toLocaleString() : '—'}
          sub={
            q
              ? `${q.with_results} with results · ${q.served_from_cache} from cache · ${q.no_results} no results${q.no_provider ? ` · ${q.no_provider} not sent (no provider available)` : ''}`
              : NOT_RECORDED
          }
        />
        <StatCard
          label="Provider requests"
          value={run.provider_calls.attempted.toLocaleString()}
          sub={`${run.provider_calls.succeeded} succeeded · ${run.provider_calls.failed} failed${run.provider_calls.rate_limited ? ` (${run.provider_calls.rate_limited} rate-limited)` : ''}`}
        />
        <StatCard
          label="AI model calls"
          value={ai ? ai.calls.toLocaleString() : '—'}
          sub={ai ? `${ai.total_tokens.toLocaleString()} tokens (${ai.prompt_tokens.toLocaleString()} prompt · ${ai.completion_tokens.toLocaleString()} completion)` : NOT_RECORDED}
        />
        <StatCard label="Valid events" value={run.validEvents.toLocaleString()} sub="verified in this run" tone="good" />
        <StatCard label="Search cost" value={costText(c.search_usd, c.search_complete, anySearch)} tone={c.search_complete ? 'accent' : 'warn'} />
        <StatCard label="AI cost" value={costText(c.ai_usd, c.ai_complete || !anyAI, anyAI)} tone={c.ai_complete || !anyAI ? 'accent' : 'warn'} />
        <StatCard label="Total estimated cost" value={totalText(run)} tone={c.total_complete ? 'accent' : 'warn'} />
      </div>
      <RunBreakdown run={run} />
    </div>
  );
}

export function RunUsageHistory({ runs }: { runs: DiscoveryRunUsage[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="space-y-3" data-testid="section-run-usage-history">
      <div>
        <h2 className="font-display text-base font-bold">Discovery usage history</h2>
        <p className="mt-1 text-xs text-muted-foreground">Each run's own usage, newest first. Select a run to see its providers and models.</p>
      </div>
      <div className="min-w-0 overflow-x-auto rounded-2xl border border-foreground/10 bg-card">
        <table className="w-full min-w-[980px] text-xs">
          <thead className="border-b border-foreground/10">
            <tr>
              <th className={cx(th, 'text-left')}>Run</th>
              <th className={cx(th, 'text-left')}>Date / time</th>
              <th className={th}>Queries</th>
              <th className={cx(th, 'text-left')}>Providers used</th>
              <th className={th}>Model calls</th>
              <th className={th}>Tokens</th>
              <th className={th}>AI cost</th>
              <th className={th}>Search cost</th>
              <th className={th}>Total cost</th>
              <th className={th}>Valid events</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => {
              const used = usedProviders(run);
              const anyAI = (run.ai_models?.length ?? 0) > 0;
              const isOpen = open === run.runId;
              return (
                <Fragment key={run.runId}>
                  <tr
                    className={cx('cursor-pointer border-b border-foreground/5 hover:bg-muted/40', isOpen && 'bg-muted/40')}
                    onClick={() => setOpen(isOpen ? null : run.runId)}
                    data-testid={`row-run-usage-${run.runId}`}
                  >
                    <td className="px-3 py-2 text-left font-semibold">
                      <button
                        type="button"
                        className="flex items-center gap-1 outline-none focus-visible:text-accent"
                        aria-expanded={isOpen}
                        aria-label={`Show usage details for run ${run.runId}`}
                        onClick={(e) => { e.stopPropagation(); setOpen(isOpen ? null : run.runId); }}
                      >
                        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}#{run.runId}
                      </button>
                    </td>
                    <td className="px-3 py-2 text-left text-muted-foreground">{fmtDateTime(run.startedAt)}</td>
                    <td className={td}>{run.queries ? run.queries.attempted : <span className="text-muted-foreground" title="Not recorded: the run predates per-run tracking">—</span>}</td>
                    <td className="px-3 py-2 text-left">{used.length ? used.map((p) => `${p.name} (${p.calls})`).join(', ') : <span className="text-muted-foreground">None</span>}</td>
                    <td className={td}>{run.ai_totals ? run.ai_totals.calls : '—'}</td>
                    <td className={td}>{run.ai_totals ? run.ai_totals.total_tokens.toLocaleString() : '—'}</td>
                    <td className={td}>{costText(run.costs.ai_usd, run.costs.ai_complete || !anyAI, anyAI)}</td>
                    <td className={td}>{costText(run.costs.search_usd, run.costs.search_complete, used.length > 0)}</td>
                    <td className={cx(td, 'font-semibold')}>{totalText(run)}</td>
                    <td className={td}>{run.validEvents}</td>
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-foreground/10 bg-muted/20">
                      <td colSpan={10} className="p-3">
                        {!run.tracked && (
                          <p className="mb-3 text-xs text-muted-foreground">
                            This run ran before per-run tracking was added: only its search-provider requests and the costs providers reported were saved.
                          </p>
                        )}
                        <RunBreakdown run={run} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
