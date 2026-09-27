// Manual trigger for Agent 1. Discovery no longer runs on a timer — every run starts
// here, with its scope (and therefore its API cost) chosen explicitly by an admin.
import { useState } from 'react';
import { Link } from 'wouter';
import { Search } from 'lucide-react';
import { useRunDiscovery } from './api';
import { Btn, DL, Drawer, ErrorState, Notice, inputClass } from './ui';

const list = (v: string) => v.split(',').map((s) => s.trim()).filter(Boolean);
const num = (v: string, fallback: number) => { const n = Number(v); return Number.isFinite(n) && n > 0 ? n : fallback; };

export function ManualResearchForm() {
  const run = useRunDiscovery();
  const [cities, setCities] = useState('');
  const [categories, setCategories] = useState('');
  const [depth, setDepth] = useState('4');
  const [perQuery, setPerQuery] = useState('3');
  const pages = num(depth, 4) * num(perQuery, 3);
  const result = run.data as Record<string, unknown> | undefined;

  const start = () => run.mutate({
    cities: list(cities).length ? list(cities) : undefined,
    categories: list(categories).length ? list(categories) : undefined,
    searchDepth: num(depth, 4),
    sourcesPerQuery: num(perQuery, 3),
  });

  return (
    <div className="grid gap-3 text-xs">
      <label>Cities <span className="text-muted-foreground">(comma-separated; blank = configured default list)</span>
        <input value={cities} onChange={(e) => setCities(e.target.value)} className={`${inputClass} mt-1`} placeholder="Pune, Mumbai" disabled={run.isPending} />
      </label>
      <label>Categories <span className="text-muted-foreground">(comma-separated; blank = default list)</span>
        <input value={categories} onChange={(e) => setCategories(e.target.value)} className={`${inputClass} mt-1`} placeholder="Technology, Startup" disabled={run.isPending} />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label>Search queries<input type="number" min={1} max={200} value={depth} onChange={(e) => setDepth(e.target.value)} className={`${inputClass} mt-1`} disabled={run.isPending} /></label>
        <label>Pages per query<input type="number" min={1} max={20} value={perQuery} onChange={(e) => setPerQuery(e.target.value)} className={`${inputClass} mt-1`} disabled={run.isPending} /></label>
      </div>
      <Notice tone="info">Up to <strong>{pages} pages</strong> will be fetched and read by the AI model, plus {num(depth, 4)} web searches. Every one is a real API call — keep this small while testing. Runs take a few minutes.</Notice>
      <div className="flex items-center gap-2">
        <Btn variant="primary" loading={run.isPending} onClick={start}><Search size={13} /> {run.isPending ? 'Researching…' : 'Run manual research'}</Btn>
        {run.isPending && <span className="text-[11px] text-muted-foreground">Leave this open until it finishes.</span>}
      </div>
      {run.isError && <ErrorState error={run.error} title="Research run failed" />}
      {result && (
        <div className="rounded-xl border border-foreground/10 bg-background p-4">
          <DL rows={[
            ['Run', String(result.runId ?? '—')],
            ['Status', String(result.status ?? '—')],
            ['Events discovered', String(result.events_discovered ?? 0)],
            ['New events', String(result.new_events ?? 0)],
            ['Duplicates skipped', String(result.duplicate_events ?? 0)],
            ['Organizers found', `${result.organizers_found ?? 0} (${result.new_organizers ?? 0} new)`],
            ['Contacts found', String(result.contacts_found ?? 0)],
            ['Needs review', String(result.events_needing_review ?? 0)],
          ]} />
          <div className="mt-3 flex gap-3 font-mono-face text-[10px] uppercase tracking-wider">
            <Link href="/admin/discovery" className="text-accent hover:underline">See discoveries →</Link>
            <Link href="/admin/activity" className="text-accent hover:underline">Run details →</Link>
          </div>
        </div>
      )}
    </div>
  );
}

export function ManualResearchButton({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Btn variant="primary" size={size} onClick={() => setOpen(true)}><Search size={size === 'sm' ? 11 : 13} /> Run manual research</Btn>
      <Drawer open={open} onClose={() => setOpen(false)} kicker="Organizer Discovery · Agent 1" title="Run manual research" width="max-w-xl">
        <p className="mb-4 text-sm text-muted-foreground">Discovery does not run automatically. Choose the scope for this run and start it; results land in New Discoveries when it finishes.</p>
        <ManualResearchForm />
      </Drawer>
    </>
  );
}
