import { useId, useState } from 'react';
import { ChevronDown, ChevronUp, Layers } from 'lucide-react';
import type { RunSourceReport, RunSourceRow } from './api';
import { Badge } from './ui';

const CHANNEL_LABEL: Record<string, string> = {
  web: 'Web search',
  directories: 'Directories',
  aggregators: 'Aggregators',
  custom: 'Your websites',
  apis: 'APIs',
};

const SKIP_LABEL: Record<string, string> = {
  not_needed: 'free results were enough',
  paid_budget_exhausted: 'paid search budget used up',
  cooling_down: 'paused after repeated failures',
  not_configured: 'not configured',
  retired: 'API retired',
  served_from_cache: 'answered from cache',
};

function statusBadge(row: RunSourceRow) {
  if (row.status === 'failed') return <Badge tone="danger">Failed</Badge>;
  if (row.status === 'skipped') return <Badge tone="neutral">Skipped</Badge>;
  if (row.status === 'pending') return <Badge tone="info">Running</Badge>;
  if (!row.candidates && !row.results) return <Badge tone="warn">Ran · 0 results</Badge>;
  return <Badge tone="good">OK</Badge>;
}

function detail(row: RunSourceRow): string {
  if (row.status === 'skipped') {
    const reasons = Object.entries(row.skipped_reasons ?? {});
    if (reasons.length) return reasons.map(([k, n]) => `${SKIP_LABEL[k] ?? k} ×${n}`).join(', ');
    return row.reason ?? '';
  }
  const parts: string[] = [];
  if (row.kind === 'search_provider') {
    if (typeof row.calls === 'number') parts.push(`${row.calls} call${row.calls === 1 ? '' : 's'}`);
    if (row.results) parts.push(`${row.results} results`);
    if (row.zero_result_calls) parts.push(`${row.zero_result_calls} empty`);
    const organizer = row.purposes?.organizer_lookup;
    if (organizer) parts.push(`${organizer} for organizer lookups`);
    if (row.cost_usd != null) parts.push(`$${row.cost_usd.toFixed(3)}`);
  } else {
    if (typeof row.jobs === 'number') parts.push(`${row.jobs} read${row.jobs === 1 ? '' : 's'}${row.jobs_failed ? ` (${row.jobs_failed} failed)` : ''}`);
  }
  if (row.errors?.length && row.status === 'failed') parts.push(row.errors[0]);
  return parts.join(' · ');
}

/** A run's per-source execution record (`summary.sources`): what was selected,
 * configured, executed, what each source returned and why anything was skipped. */
/** A counter from the report, or "—" when this (older) run did not record it. */
const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : '—');

export function RunSourcesReport({ report, defaultOpen = false }: { report?: RunSourceReport | null; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  if (!report || !report.counts) return null;
  const c = report.counts;
  const rows = Array.isArray(report.sources) ? report.sources : [];
  return (
    <div className="mt-3 rounded-lg border border-foreground/10 bg-card/60 p-3 text-[11px]">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={panelId} className="flex w-full flex-wrap items-center justify-between gap-2 text-left">
        <span className="flex items-center gap-1.5 font-semibold text-foreground">
          <Layers size={13} className="text-accent" /> Sources
        </span>
        <span className="flex flex-wrap items-center gap-x-2 font-mono text-[10px] text-muted-foreground">
          {n(c.selected)} selected · {n(c.configured)} configured · {n(c.executed)} executed · {n(c.successful)} ok · {n(c.returned_candidates)} candidates ·{' '}
          <span className={c.failed ? 'text-red-600' : ''}>{n(c.failed)} failed</span> · {n(c.skipped)} skipped
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>
      {open && (
        <div id={panelId} className="mt-2 max-h-80 overflow-auto">
          <table className="w-full text-[10px]">
            <thead className="text-left font-mono uppercase text-muted-foreground">
              <tr>
                <th className="py-1 pr-2">Source</th>
                <th className="py-1 pr-2">Status</th>
                <th className="py-1 pr-2 text-right" title="Candidate events it produced">Cand.</th>
                <th className="py-1 pr-2 text-right">Verified</th>
                <th className="py-1 pr-2 text-right" title="Held for review">Review</th>
                <th className="py-1 pr-2 text-right" title="Outside the selected sectors">Off-sector</th>
                <th className="py-1 pr-2 text-right">Dupes</th>
                <th className="py-1">Detail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-foreground/5 align-top">
                  <td className="py-1 pr-2">
                    <span className="font-semibold text-foreground">{row.name}</span>
                    <span className="block text-muted-foreground">{CHANNEL_LABEL[row.channel] ?? row.channel}</span>
                  </td>
                  <td className="py-1 pr-2">{statusBadge(row)}</td>
                  <td className="py-1 pr-2 text-right font-mono">{n(row.candidates)}</td>
                  <td className="py-1 pr-2 text-right font-mono font-semibold">{n(row.verified)}</td>
                  <td className="py-1 pr-2 text-right font-mono">{n(row.needs_review)}</td>
                  <td className="py-1 pr-2 text-right font-mono">{n(row.off_sector)}</td>
                  <td className="py-1 pr-2 text-right font-mono">{n(row.duplicates)}</td>
                  <td className={`py-1 ${row.status === 'failed' ? 'text-red-600' : 'text-muted-foreground'}`}>{detail(row)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
