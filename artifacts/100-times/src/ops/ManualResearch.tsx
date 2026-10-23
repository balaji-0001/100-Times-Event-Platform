// Manual trigger for the discovery automation. Discovery no longer runs on a timer — every run starts
// here, with its scope (and therefore its API cost) chosen explicitly by an admin.
import { useEffect, useState } from 'react';
import { Link } from 'wouter';
import { Check, Layers, Search } from 'lucide-react';
import { useCategories, useRunDiscovery } from './api';
import { GeoChecklistSelector } from './GeoChecklistSelector';
import { Btn, DL, Drawer, ErrorState, Notice, inputClass } from './ui';

const num = (v: string, fallback: number) => { const n = Number(v); return Number.isFinite(n) && n > 0 ? n : fallback; };

const DEFAULT_CATEGORIES = [
  'Construction', 'Energy and Power Generation', 'Finance', 'Healthcare',
  'Manufacturing', 'Mining', 'Oil and Gas', 'Packaging', 'Pharmaceuticals',
  'Telecommunications', 'Textiles', 'Transport and Logistics'
];

export function ManualResearchForm() {
  const run = useRunDiscovery();
  const categoriesQuery = useCategories();
  const allAvailableCategories = categoriesQuery.data?.map((c) => c.name) || DEFAULT_CATEGORIES;

  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>(allAvailableCategories);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [depth, setDepth] = useState('4');
  const [perQuery, setPerQuery] = useState('3');
  const pages = num(depth, 4) * num(perQuery, 3);
  const result = run.data as Record<string, unknown> | undefined;

  useEffect(() => {
    if (categoriesQuery.data && categoriesQuery.data.length > 0) {
      const serverCats = categoriesQuery.data.map((c) => c.name);
      setSelectedCategories((prev) => (prev.length === 0 ? serverCats : prev));
    }
  }, [categoriesQuery.data]);

  const toggleCategory = (cat: string) => {
    if (run.isPending) return;
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const selectAllCategories = () => setSelectedCategories([...allAvailableCategories]);
  const clearCategories = () => setSelectedCategories([]);

  const start = () => run.mutate({
    country: selectedCountries.length ? selectedCountries[0] : undefined,
    countries: selectedCountries.length ? selectedCountries : undefined,
    states: selectedStates.length ? selectedStates : undefined,
    cities: selectedCities.length ? selectedCities : undefined,
    categories: selectedCategories.length > 0 ? selectedCategories : undefined,
    searchDepth: num(depth, 4),
    sourcesPerQuery: num(perQuery, 3),
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
  });

  return (
    <div className="grid gap-3 text-xs">
      <GeoChecklistSelector
        selectedCountries={selectedCountries}
        onCountriesChange={setSelectedCountries}
        selectedStates={selectedStates}
        onStatesChange={setSelectedStates}
        selectedCities={selectedCities}
        onCitiesChange={setSelectedCities}
        disabled={run.isPending}
      />
      <div>
        <div className="flex items-center justify-between">
          <span className="font-semibold text-foreground flex items-center gap-1.5">
            <Layers size={13} className="text-accent" /> Target Sectors
          </span>
          <div className="flex gap-2 text-[10px]">
            <button
              type="button"
              onClick={selectAllCategories}
              className="text-accent hover:underline"
              disabled={run.isPending}
            >
              Select all
            </button>
            <span>•</span>
            <button
              type="button"
              onClick={clearCategories}
              className="text-muted-foreground hover:underline"
              disabled={run.isPending}
            >
              Clear
            </button>
          </div>
        </div>
        <span className="block text-[11px] text-muted-foreground mt-0.5 mb-2">
          Click to toggle which 100 TIMES sectors are discovered
        </span>
        <div className="flex flex-wrap gap-1.5">
          {allAvailableCategories.map((cat) => {
            const active = selectedCategories.includes(cat);
            return (
              <button
                type="button"
                key={cat}
                onClick={() => toggleCategory(cat)}
                disabled={run.isPending}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium border transition-colors ${
                  active
                    ? 'border-accent bg-accent/15 text-accent font-semibold'
                    : 'border-foreground/15 bg-card text-muted-foreground hover:border-foreground/30'
                }`}
              >
                {active && <Check size={11} />}
                {cat}
              </button>
            );
          })}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label>From Date <span className="text-muted-foreground">(optional; event start)</span>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={`${inputClass} mt-1`} disabled={run.isPending} />
        </label>
        <label>To Date <span className="text-muted-foreground">(optional; event end)</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className={`${inputClass} mt-1`} disabled={run.isPending} />
        </label>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label>Search queries<input type="number" min={1} max={200} value={depth} onChange={(e) => setDepth(e.target.value)} className={`${inputClass} mt-1`} disabled={run.isPending} /></label>
        <label>Pages per query<input type="number" min={1} max={20} value={perQuery} onChange={(e) => setPerQuery(e.target.value)} className={`${inputClass} mt-1`} disabled={run.isPending} /></label>
      </div>
      <Notice tone="info">Reads the event-listing sites for each city, then runs <strong>{num(depth, 4)} web searches</strong> and opens up to <strong>{pages} result pages</strong> in a headless browser. No AI and no API costs — searches are spaced out to stay polite, so runs take a few minutes.</Notice>
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
      <Drawer open={open} onClose={() => setOpen(false)} kicker="Organizer Discovery · Automation" title="Run manual research" width="max-w-2xl">
        <p className="mb-4 text-sm text-muted-foreground">Discovery does not run automatically. Choose the scope for this run and start it; results land in New Discoveries when it finishes.</p>
        <ManualResearchForm />
      </Drawer>
    </>
  );
}
