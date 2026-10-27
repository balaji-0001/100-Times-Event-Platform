import { useMemo, useState } from 'react';
import { Globe, MapPin, Layers, Calendar, Target, ChevronDown, ChevronUp } from 'lucide-react';
import { type AgentRun } from './api';

export interface RunScopeDetails {
  countries: string[];
  cities: string[];
  sectors: string[];
  dateFrom?: string;
  dateTo?: string;
  targetValidEvents?: number;
  isWorldwide: boolean;
}

/**
 * Robust extractor that pulls countries, cities, and sectors from either:
 * - `run.configSnapshot` (the saved configuration when the run was initiated)
 * - `run.summary.scope` (the orchestrator's planned/executed scope)
 * - `run.config` (from manual research immediate return)
 */
export function extractRunScope(run?: AgentRun | {
  configSnapshot?: Record<string, any> | null;
  summary?: Record<string, any> | null;
  config?: Record<string, any> | null;
} | null): RunScopeDetails {
  if (!run) {
    return { countries: [], cities: [], sectors: [], isWorldwide: false };
  }

  const cfg: Record<string, any> = run.configSnapshot || (run as any).config || {};
  const summaryScope: Record<string, any> = run.summary?.scope || {};

  // Extract Countries
  let countries: string[] = [];
  if (Array.isArray(summaryScope.countries) && summaryScope.countries.length > 0) {
    countries = summaryScope.countries;
  } else if (Array.isArray(cfg.countries) && cfg.countries.length > 0) {
    countries = cfg.countries;
  } else if (typeof cfg.country === 'string' && cfg.country.trim() && cfg.country.toLowerCase() !== 'worldwide') {
    countries = [cfg.country.trim()];
  }

  // Extract Cities
  let cities: string[] = [];
  if (Array.isArray(summaryScope.cities_list) && summaryScope.cities_list.length > 0) {
    cities = summaryScope.cities_list;
  } else if (Array.isArray(cfg.cities) && cfg.cities.length > 0) {
    cities = cfg.cities;
  } else if (Array.isArray(cfg.locations)) {
    cities = cfg.locations.map((l: any) => l.city).filter(Boolean);
  }

  // Extract Sectors / Categories
  let sectors: string[] = [];
  if (Array.isArray(summaryScope.sectors) && summaryScope.sectors.length > 0) {
    sectors = summaryScope.sectors;
  } else if (Array.isArray(cfg.categories) && cfg.categories.length > 0) {
    sectors = cfg.categories;
  } else if (Array.isArray(cfg.sectors) && cfg.sectors.length > 0) {
    sectors = cfg.sectors;
  }

  const isWorldwide = Boolean(summaryScope.worldwide) || (countries.length === 0 && (!cfg.country || cfg.country === 'Worldwide'));

  return {
    countries: Array.from(new Set(countries)),
    cities: Array.from(new Set(cities)),
    sectors: Array.from(new Set(sectors)),
    dateFrom: cfg.date_from || cfg.dateFrom,
    dateTo: cfg.date_to || cfg.dateTo,
    targetValidEvents: cfg.target_valid_events ?? cfg.targetValidEvents,
    isWorldwide,
  };
}

/**
 * Beautiful full-panel card displaying the starting scope:
 * Which Country, Which City, Which Sectors the run started with.
 */
export function RunScopeDisplay({
  run,
  title = 'Run Scope & Starting Parameters',
  className = '',
}: {
  run?: AgentRun | {
    configSnapshot?: Record<string, any> | null;
    summary?: Record<string, any> | null;
    config?: Record<string, any> | null;
  } | null;
  title?: string;
  className?: string;
}) {
  const [expandedCities, setExpandedCities] = useState(false);
  const [expandedSectors, setExpandedSectors] = useState(false);

  const scope = useMemo(() => extractRunScope(run), [run]);

  if (!run) return null;

  const displayCities = expandedCities ? scope.cities : scope.cities.slice(0, 8);
  const displaySectors = expandedSectors ? scope.sectors : scope.sectors.slice(0, 8);

  return (
    <div className={`rounded-xl border border-foreground/15 bg-card/70 p-3.5 text-xs shadow-sm ${className}`}>
      <div className="flex items-center justify-between border-b border-foreground/10 pb-2 mb-3">
        <span className="font-semibold text-foreground flex items-center gap-1.5 text-xs">
          <Globe size={13} className="text-accent" /> {title}
        </span>
        <span className="text-[10px] text-muted-foreground font-mono">
          Configured when run started
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Countries */}
        <div className="space-y-1.5 rounded-lg border border-foreground/10 bg-background/60 p-2.5">
          <div className="flex items-center gap-1 text-[11px] font-semibold text-foreground">
            <Globe size={12} className="text-accent" />
            <span>Target Countries ({scope.isWorldwide ? 'Worldwide' : scope.countries.length})</span>
          </div>
          <div className="flex flex-wrap gap-1 pt-0.5">
            {scope.isWorldwide ? (
              <span className="inline-flex items-center gap-1 rounded bg-accent/15 px-2 py-0.5 text-[10px] font-medium text-accent">
                🌍 Worldwide (All Countries)
              </span>
            ) : scope.countries.length === 0 ? (
              <span className="text-[11px] text-muted-foreground italic">None specified</span>
            ) : (
              scope.countries.map((c) => (
                <span
                  key={c}
                  className="inline-flex items-center gap-1 rounded bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent border border-accent/20"
                >
                  {c}
                </span>
              ))
            )}
          </div>
        </div>

        {/* Cities */}
        <div className="space-y-1.5 rounded-lg border border-foreground/10 bg-background/60 p-2.5">
          <div className="flex items-center justify-between text-[11px] font-semibold text-foreground">
            <div className="flex items-center gap-1">
              <MapPin size={12} className="text-accent" />
              <span>Target Cities ({scope.cities.length})</span>
            </div>
            {scope.cities.length > 8 && (
              <button
                type="button"
                onClick={() => setExpandedCities(!expandedCities)}
                className="text-[10px] text-accent hover:underline flex items-center gap-0.5"
              >
                {expandedCities ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                {expandedCities ? 'Show less' : `+${scope.cities.length - 8} more`}
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-1 pt-0.5">
            {scope.cities.length === 0 ? (
              <span className="inline-flex items-center gap-1 rounded bg-muted/30 px-2 py-0.5 text-[10px] text-muted-foreground">
                📍 All Cities in Selected Countries
              </span>
            ) : (
              displayCities.map((city) => (
                <span
                  key={city}
                  className="inline-flex items-center gap-0.5 rounded bg-muted/40 px-1.5 py-0.5 text-[10px] font-medium text-foreground border border-foreground/10"
                >
                  {city}
                </span>
              ))
            )}
          </div>
        </div>

        {/* Sectors */}
        <div className="space-y-1.5 rounded-lg border border-foreground/10 bg-background/60 p-2.5">
          <div className="flex items-center justify-between text-[11px] font-semibold text-foreground">
            <div className="flex items-center gap-1">
              <Layers size={12} className="text-accent" />
              <span>Target Sectors ({scope.sectors.length})</span>
            </div>
            {scope.sectors.length > 8 && (
              <button
                type="button"
                onClick={() => setExpandedSectors(!expandedSectors)}
                className="text-[10px] text-accent hover:underline flex items-center gap-0.5"
              >
                {expandedSectors ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                {expandedSectors ? 'Show less' : `+${scope.sectors.length - 8} more`}
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-1 pt-0.5">
            {scope.sectors.length === 0 ? (
              <span className="inline-flex items-center gap-1 rounded bg-muted/30 px-2 py-0.5 text-[10px] text-muted-foreground">
                All 100 TIMES Sectors
              </span>
            ) : (
              displaySectors.map((sector) => (
                <span
                  key={sector}
                  className="inline-flex items-center gap-0.5 rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent border border-accent/20"
                >
                  {sector}
                </span>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Date & Target Row */}
      {(scope.dateFrom || scope.dateTo || typeof scope.targetValidEvents === 'number') && (
        <div className="mt-2.5 pt-2 border-t border-foreground/10 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          {(scope.dateFrom || scope.dateTo) && (
            <div className="flex items-center gap-1">
              <Calendar size={11} className="text-accent" />
              <span>
                Date Filter: <strong>{scope.dateFrom || 'Any'}</strong> → <strong>{scope.dateTo || 'Any'}</strong>
              </span>
            </div>
          )}
          {typeof scope.targetValidEvents === 'number' && (
            <div className="flex items-center gap-1">
              <Target size={11} className="text-accent" />
              <span>
                Target Goal: <strong>{scope.targetValidEvents} verified events</strong>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Compact single-line summary for table columns and header badges:
 * E.g.: "🌍 India, UAE | 📍 Dubai, Mumbai | 🏷️ Construction, Textiles"
 */
export function RunScopeSummaryLine({
  run,
  maxItems = 2,
}: {
  run?: AgentRun | {
    configSnapshot?: Record<string, any> | null;
    summary?: Record<string, any> | null;
    config?: Record<string, any> | null;
  } | null;
  maxItems?: number;
}) {
  const scope = useMemo(() => extractRunScope(run), [run]);

  if (!run) return <span className="text-muted-foreground">—</span>;

  const countryText = scope.isWorldwide
    ? 'Worldwide'
    : scope.countries.length === 0
    ? 'Worldwide'
    : scope.countries.length <= maxItems
    ? scope.countries.join(', ')
    : `${scope.countries.slice(0, maxItems).join(', ')} +${scope.countries.length - maxItems}`;

  const cityText = scope.cities.length === 0
    ? 'All Cities'
    : scope.cities.length <= maxItems
    ? scope.cities.join(', ')
    : `${scope.cities.slice(0, maxItems).join(', ')} +${scope.cities.length - maxItems}`;

  const sectorText = scope.sectors.length === 0
    ? 'All Sectors'
    : scope.sectors.length <= maxItems
    ? scope.sectors.join(', ')
    : `${scope.sectors.slice(0, maxItems).join(', ')} +${scope.sectors.length - maxItems}`;

  return (
    <div className="flex flex-col gap-0.5 text-[10px] leading-tight">
      <div className="flex items-center gap-1 text-foreground font-medium truncate" title={`Countries: ${scope.countries.join(', ') || 'Worldwide'}`}>
        <Globe size={10} className="text-accent shrink-0" />
        <span className="truncate">{countryText}</span>
      </div>
      <div className="flex items-center gap-1 text-muted-foreground truncate" title={`Cities: ${scope.cities.join(', ') || 'All Cities'}`}>
        <MapPin size={10} className="text-accent shrink-0" />
        <span className="truncate">{cityText}</span>
      </div>
      <div className="flex items-center gap-1 text-accent font-medium truncate" title={`Sectors: ${scope.sectors.join(', ') || 'All Sectors'}`}>
        <Layers size={10} className="text-accent shrink-0" />
        <span className="truncate">{sectorText}</span>
      </div>
    </div>
  );
}

/**
 * Compact pill/badges row for headers (like DiscoveryPage banner)
 */
export function RunScopeHeaderBadges({
  run,
}: {
  run?: AgentRun | {
    configSnapshot?: Record<string, any> | null;
    summary?: Record<string, any> | null;
    config?: Record<string, any> | null;
  } | null;
}) {
  const scope = useMemo(() => extractRunScope(run), [run]);

  if (!run) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      <span className="inline-flex items-center gap-1 rounded bg-accent/15 px-2 py-0.5 font-medium text-accent border border-accent/25">
        <Globe size={11} />
        {scope.isWorldwide
          ? 'Worldwide'
          : scope.countries.length > 0
          ? scope.countries.slice(0, 3).join(', ') + (scope.countries.length > 3 ? ` +${scope.countries.length - 3}` : '')
          : 'Worldwide'}
      </span>
      <span className="inline-flex items-center gap-1 rounded bg-muted/40 px-2 py-0.5 font-medium text-foreground border border-foreground/10">
        <MapPin size={11} className="text-accent" />
        {scope.cities.length > 0
          ? scope.cities.slice(0, 3).join(', ') + (scope.cities.length > 3 ? ` +${scope.cities.length - 3}` : '')
          : 'All Cities'}
      </span>
      <span className="inline-flex items-center gap-1 rounded bg-accent/10 px-2 py-0.5 font-medium text-accent border border-accent/20">
        <Layers size={11} />
        {scope.sectors.length > 0
          ? scope.sectors.slice(0, 3).join(', ') + (scope.sectors.length > 3 ? ` +${scope.sectors.length - 3}` : '')
          : 'All Sectors'}
      </span>
      {(scope.dateFrom || scope.dateTo) && (
        <span className="inline-flex items-center gap-1 rounded bg-muted/40 px-2 py-0.5 font-medium text-muted-foreground border border-foreground/10">
          <Calendar size={11} />
          {scope.dateFrom || 'Start'} → {scope.dateTo || 'End'}
        </span>
      )}
    </div>
  );
}
