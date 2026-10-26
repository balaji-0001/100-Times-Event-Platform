import { useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock,
  ExternalLink,
  Filter,
  KeyRound,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
  Wifi,
  X,
} from 'lucide-react';
import {
  type EventDiscoverySource,
  useDiscoverySources,
  useDiscoverySourceStats,
  useProbeSourceHealth,
  useSyncDiscoverySources,
  useTestSourceExtraction,
  useUpdateDiscoverySource,
} from './api';
import {
  AdminTable,
  Badge,
  Btn,
  DL,
  Drawer,
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  Section,
  StatCard,
  cell,
  cellMuted,
  cx,
  fmtDateTime,
  inputClass,
  useDebounce,
} from './ui';

const CATEGORIES = [
  '__all__',
  'Global Event Discovery',
  'Event Platform & API',
  'International Exhibition Organizer',
  'Industry Association',
  'Venue Calendar',
  'Government & Trade',
  'Search & Research Tool',
];

const STATUSES = [
  '__all__',
  'Operational',
  'Implemented',
  'Awaiting Credentials',
  'Approved',
  'Testing',
  'Permission Review',
  'Under Evaluation',
  'Temporarily Unavailable',
  'Disabled',
  'Unsupported',
];

const ACCESS_METHODS = [
  '__all__',
  'schema_org',
  'html_listing',
  'official_api',
  'rss_ical',
  'search_engine',
];

const statusTone = (status: string) => {
  switch (status) {
    case 'Operational':
      return 'good';
    case 'Implemented':
    case 'Approved':
      return 'accent';
    case 'Awaiting Credentials':
    case 'Testing':
    case 'Under Evaluation':
      return 'warn';
    case 'Disabled':
    case 'Temporarily Unavailable':
    case 'Unsupported':
      return 'danger';
    default:
      return 'neutral';
  }
};

const healthTone = (health: string) => {
  switch (health) {
    case 'healthy':
      return 'good';
    case 'degraded':
      return 'warn';
    case 'failing':
    case 'unreachable':
      return 'danger';
    default:
      return 'neutral';
  }
};

export function SourceRegistryView() {
  const [category, setCategory] = useState('__all__');
  const [status, setStatus] = useState('__all__');
  const [accessMethod, setAccessMethod] = useState('__all__');
  const [searchTerm, setSearchTerm] = useState('');
  const debouncedSearch = useDebounce(searchTerm.trim(), 250);

  const [activeTest, setActiveTest] = useState<{
    source: EventDiscoverySource;
    result: any;
  } | null>(null);

  const statsQuery = useDiscoverySourceStats();
  const sourcesQuery = useDiscoverySources({
    category,
    status,
    access_method: accessMethod,
    search: debouncedSearch,
  });

  const updateSource = useUpdateDiscoverySource();
  const probeHealth = useProbeSourceHealth();
  const testExtraction = useTestSourceExtraction();
  const syncSources = useSyncDiscoverySources();

  const stats = statsQuery.data;
  const sources = sourcesQuery.data?.sources ?? [];

  const handleToggle = (source: EventDiscoverySource) => {
    updateSource.mutate({
      sourceId: source.id,
      updates: { is_enabled: !source.is_enabled },
    });
  };

  const handleProbe = (source: EventDiscoverySource) => {
    probeHealth.mutate(source.id, {
      onSuccess: (data) => {
        alert(
          `Health Check for ${source.name}:\nStatus: ${data.status.toUpperCase()}\nLatency: ${data.latency_ms} ms\n${data.error ? `Error: ${data.error}` : 'Connection verified successfully.'}`
        );
      },
    });
  };

  const handleTest = (source: EventDiscoverySource) => {
    testExtraction.mutate(
      { sourceId: source.id },
      {
        onSuccess: (data) => {
          setActiveTest({ source, result: data });
        },
      }
    );
  };

  return (
    <div className="space-y-6">
      {/* KPI Overview Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard
          label="Total Sources"
          value={stats?.total_sources ?? 76}
        />
        <StatCard
          label="Operational"
          value={stats?.operational_sources ?? 35}
          tone="good"
        />
        <StatCard
          label="Implemented"
          value={stats?.sources_integrated ?? 29}
          tone="accent"
        />
        <StatCard
          label="Awaiting Credentials"
          value={stats?.awaiting_credentials ?? 5}
          tone="warn"
        />
        <StatCard
          label="Venue Calendars"
          value={stats?.by_category?.['Venue Calendar'] ?? 10}
          tone="accent"
        />
        <StatCard
          label="Enabled Active"
          value={stats?.enabled_sources ?? 76}
          tone="good"
        />
      </div>

      {/* Filter and Control Bar */}
      <Panel className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-1 flex-wrap items-center gap-2 min-w-[300px]">
            <div className="relative flex-1 min-w-[200px]">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <input
                type="text"
                placeholder="Search 76+ sources by name, URL, or ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className={cx(inputClass, 'pl-8 text-xs')}
              />
            </div>

            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className={cx(inputClass, 'w-auto text-xs font-medium')}
            >
              <option value="__all__">All Categories</option>
              {CATEGORIES.filter((c) => c !== '__all__').map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className={cx(inputClass, 'w-auto text-xs font-medium')}
            >
              <option value="__all__">All Statuses</option>
              {STATUSES.filter((s) => s !== '__all__').map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>

            <select
              value={accessMethod}
              onChange={(e) => setAccessMethod(e.target.value)}
              className={cx(inputClass, 'w-auto text-xs font-medium')}
            >
              <option value="__all__">All Access Methods</option>
              {ACCESS_METHODS.filter((m) => m !== '__all__').map((m) => (
                <option key={m} value={m}>
                  {m.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <Btn
              size="sm"
              variant="secondary"
              loading={syncSources.isPending}
              onClick={() => syncSources.mutate()}
              title="Resynchronize all 74+ sources with master catalog"
            >
              <RefreshCw size={12} className="mr-1.5" /> Sync Catalog
            </Btn>
          </div>
        </div>
      </Panel>

      {/* Main Sources Table */}
      <Panel className="p-0 overflow-hidden">
        {sourcesQuery.isLoading ? (
          <div className="p-8">
            <LoadingState label="Loading Global Source Registry..." />
          </div>
        ) : sources.length === 0 ? (
          <div className="p-8">
            <EmptyState
              title="No sources match filter criteria"
              body="Try resetting search or category filters to view all sources."
            />
          </div>
        ) : (
          <AdminTable
            columns={[
              'Source Name',
              'Category',
              'Access Method',
              'Integration Status',
              'Health',
              'Discovered',
              'Extracted',
              'Enabled',
              'Actions',
            ]}
            minWidth={1150}
          >
            {sources.map((s) => (
              <tr key={s.id} className="hover:bg-muted/15 transition-colors">
                <td className={cell}>
                  <div className="min-w-0 pr-2">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-foreground truncate">
                        {s.name}
                      </span>
                      <a
                        href={s.website_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-muted-foreground hover:text-accent"
                        title={`Open ${s.website_url}`}
                      >
                        <ExternalLink size={12} />
                      </a>
                    </div>
                    <span className="font-mono-face text-[10px] text-muted-foreground">
                      {s.id}
                    </span>
                  </div>
                </td>

                <td className={cell}>
                  <span className="text-xs text-foreground font-medium">
                    {s.source_category}
                  </span>
                </td>

                <td className={cell}>
                  <Badge tone="neutral">
                    {s.access_method.replace(/_/g, ' ')}
                  </Badge>
                </td>

                <td className={cell}>
                  <Badge tone={statusTone(s.integration_status)}>
                    {s.integration_status}
                  </Badge>
                </td>

                <td className={cell}>
                  <div className="flex items-center gap-1.5">
                    <span
                      className={cx(
                        'h-2 w-2 rounded-full',
                        s.health_status === 'healthy'
                          ? 'bg-emerald-500'
                          : s.health_status === 'degraded'
                          ? 'bg-amber-500'
                          : s.health_status === 'failing' || s.health_status === 'unreachable'
                          ? 'bg-rose-500'
                          : 'bg-muted-foreground/40'
                      )}
                    />
                    <span className="text-xs text-muted-foreground capitalize">
                      {s.health_status}
                    </span>
                  </div>
                </td>

                <td className={cellMuted}>
                  <span className="font-mono-face font-semibold text-foreground">
                    {s.events_discovered}
                  </span>
                </td>

                <td className={cellMuted}>
                  <span className="font-mono-face text-muted-foreground">
                    {s.events_extracted}
                  </span>
                </td>

                <td className={cell}>
                  <button
                    onClick={() => handleToggle(s)}
                    disabled={updateSource.isPending}
                    className="cursor-pointer text-foreground/80 hover:text-foreground"
                    title={s.is_enabled ? 'Disable source' : 'Enable source'}
                  >
                    {s.is_enabled ? (
                      <ToggleRight size={24} className="text-accent" />
                    ) : (
                      <ToggleLeft size={24} className="text-muted-foreground/50" />
                    )}
                  </button>
                </td>

                <td className={cell}>
                  <div className="flex items-center gap-1.5 whitespace-nowrap">
                    <Btn
                      size="sm"
                      variant="ghost"
                      className="h-7 px-2 text-xs"
                      onClick={() => handleProbe(s)}
                      loading={probeHealth.isPending && probeHealth.variables === s.id}
                      title="Probe connectivity and latency"
                    >
                      <Wifi size={11} className="mr-1 text-accent" /> Probe
                    </Btn>

                    <Btn
                      size="sm"
                      variant="secondary"
                      className="h-7 px-2 text-xs"
                      onClick={() => handleTest(s)}
                      loading={testExtraction.isPending && testExtraction.variables?.sourceId === s.id}
                      title="Run real extraction test"
                    >
                      <Play size={11} className="mr-1 fill-current text-accent" /> Test
                    </Btn>

                    {s.api_docs_url && (
                      <a
                        href={s.api_docs_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center rounded px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-muted/30 hover:text-foreground"
                        title={`View API Docs (${s.api_auth_requirements || 'Auth required'})`}
                      >
                        <KeyRound size={11} className="mr-1 text-amber-500" /> Docs
                      </a>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </AdminTable>
        )}
      </Panel>

      {/* Extraction Test Result Modal */}
      {activeTest && (
        <Drawer
          open={Boolean(activeTest)}
          title={`Extraction Test Results: ${activeTest.source.name}`}
          onClose={() => setActiveTest(null)}
        >
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-xl border border-foreground/10 bg-muted/20 p-4">
              <div>
                <div className="text-xs text-muted-foreground">Test Status</div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  {activeTest.result.success ? (
                    <Badge tone="good">Success (Operational)</Badge>
                  ) : (
                    <Badge tone="danger">Failed / Needs Configuration</Badge>
                  )}
                  <span className="text-xs text-muted-foreground font-mono-face">
                    {activeTest.result.duration_ms} ms
                  </span>
                </div>
              </div>

              <div>
                <div className="text-xs text-muted-foreground">Events Recognized</div>
                <div className="text-base font-bold font-mono-face text-foreground">
                  {activeTest.result.events_found ?? 0}
                </div>
              </div>
            </div>

            {activeTest.result.error && (
              <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-700 dark:text-rose-300">
                <strong>Error Note:</strong> {activeTest.result.error}
              </div>
            )}

            <Section title="Sample Events Extracted">
              {activeTest.result.sample_events &&
              activeTest.result.sample_events.length > 0 ? (
                <div className="space-y-2.5">
                  {activeTest.result.sample_events.map((ev: any, idx: number) => (
                    <div
                      key={idx}
                      className="rounded-lg border border-foreground/10 bg-background p-3 text-xs space-y-1"
                    >
                      <div className="font-bold text-foreground">
                        {ev.name || 'Untitled Event'}
                      </div>
                      <div className="flex flex-wrap gap-2 text-muted-foreground text-[11px]">
                        {ev.date && <span>📅 {ev.date}</span>}
                        {ev.city && <span>📍 {ev.city}</span>}
                        {ev.country && <span>🌐 {ev.country}</span>}
                        {ev.venue && <span>🏢 {ev.venue}</span>}
                      </div>
                      {ev.url && (
                        <a
                          href={ev.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-accent hover:underline pt-1"
                        >
                          Source Link <ExternalLink size={10} />
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No sample events extracted during this probe.
                </p>
              )}
            </Section>

            <Section title="Source Provenance & Schema">
              <DL
                rows={[
                  ['Source ID', activeTest.source.id],
                  ['Access Method', activeTest.source.access_method],
                  ['Website URL', activeTest.source.website_url],
                  ['Category', activeTest.source.source_category],
                  ['Permission Status', activeTest.source.permission_status],
                  ['Auth Requirements', activeTest.source.api_auth_requirements || 'None (Public Web)'],
                ]}
              />
            </Section>
          </div>
        </Drawer>
      )}
    </div>
  );
}
