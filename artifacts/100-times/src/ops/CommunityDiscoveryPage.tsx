import { useEffect, useMemo, useState } from 'react';
import { useLocation, useSearch } from 'wouter';
import { Play, RotateCcw } from 'lucide-react';
import { type DiscoveredCommunity, PLATFORM_CATEGORIES, useCategories, useCommunityDiscoveryAutoStatus, useDiscoveredCommunities, useRunCommunityDiscovery, useSetCommunityDiscoveryAuto } from './api';
import { AdminTable, Badge, Btn, ErrorState, EmptyState, LoadingState, NA, Notice, PageHeader, Pager, SearchBox, SelectFilter, StatCard, Switch, cell, cellMuted, fmtDate, useDebounce, usePagination } from './ui';
import { CommunityDrawer } from './CommunityDrawer';

const ALL = '__all__';
const uniq = (vals: Array<string | null | undefined>) => Array.from(new Set(vals.filter((v): v is string => Boolean(v)))).sort();

const STATUS_TONE: Record<string, 'neutral' | 'good' | 'warn' | 'danger' | 'accent' | 'info'> = {
  DISCOVERED: 'accent', NEEDS_REVIEW: 'warn', APPROVED: 'good', REJECTED: 'danger',
  CONNECTION_REQUIRED: 'warn', CONNECTED: 'good', PERMISSION_MISSING: 'danger', PROMOTION_RESTRICTED: 'danger',
};

function AutoCommunityDiscoveryToggle() {
  const auto = useCommunityDiscoveryAutoStatus();
  const setAuto = useSetCommunityDiscoveryAuto();
  const enabled = auto.data?.enabled ?? false;
  const interval = auto.data?.intervalMinutes;

  return (
    <div className="flex items-center gap-2 rounded-full border border-foreground/15 bg-background px-3 py-1.5">
      <Switch checked={enabled} disabled={auto.isLoading || setAuto.isPending} onChange={(next) => setAuto.mutate(next)} label="Automatic community discovery" />
      <span className="text-[11px]">
        <span className="font-bold">Automatic discovery {enabled ? 'on' : 'off'}</span>
        <span className="block text-muted-foreground">{enabled ? `Runs by itself every ${interval ?? '—'} min` : 'Off — use the button to search now'}</span>
      </span>
    </div>
  );
}

export function CommunityDiscoveryPage() {
  const communities = useDiscoveredCommunities();
  const runDiscovery = useRunCommunityDiscovery();
  const [, setLocation] = useLocation();
  const search = useSearch();
  const selectedId = Number(new URLSearchParams(search).get('community')) || null;

  const [q, setQ] = useState(''); const term = useDebounce(q.trim().toLowerCase());
  const [platform, setPlatform] = useState(ALL); const [category, setCategory] = useState(ALL);
  const [city, setCity] = useState(ALL); const [status, setStatus] = useState(ALL);

  const all = communities.data ?? [];
  const rows = useMemo(() => {
    let list = [...all].sort((a, b) => (b.discoveredAt ?? '').localeCompare(a.discoveredAt ?? ''));
    if (platform !== ALL) list = list.filter((c) => c.platform === platform);
    if (category !== ALL) list = list.filter((c) => c.category === category);
    if (city !== ALL) list = list.filter((c) => c.city === city);
    if (status !== ALL) list = list.filter((c) => c.approvalStatus === status);
    if (term) list = list.filter((c) => [c.name, c.description, c.category, c.city, c.state].some((v) => v?.toLowerCase().includes(term)));
    return list;
  }, [all, platform, category, city, status, term]);

  const categoriesQuery = useCategories();
  const categoryOptions = useMemo(() => {
    const fromApi = categoriesQuery.data?.map((c) => c.name) ?? [];
    const base = fromApi.length > 0 ? fromApi : Array.from(PLATFORM_CATEGORIES);
    return uniq([...base, ...all.map((c) => c.category)]);
  }, [categoriesQuery.data, all]);

  const pager = usePagination(rows, 25);
  const selected = selectedId ? all.find((c) => c.id === selectedId) ?? null : null;
  const openCommunity = (c: DiscoveredCommunity) => setLocation(`/admin/community-discovery?community=${c.id}`);
  const closeCommunity = () => setLocation('/admin/community-discovery');
  useEffect(() => { if (selectedId && communities.isSuccess && !selected) closeCommunity(); }, [selectedId, communities.isSuccess, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  if (communities.isLoading) return <LoadingState label="Loading discovered communities" />;
  if (communities.isError) return <ErrorState error={communities.error} retry={() => communities.refetch()} />;

  const needsReview = all.filter((c) => c.approvalStatus === 'NEEDS_REVIEW').length;
  const approved = all.filter((c) => c.approvalStatus === 'APPROVED').length;
  const telegram = all.filter((c) => c.platform === 'telegram').length;
  const discord = all.filter((c) => c.platform === 'discord').length;

  const resetFilters = () => { setQ(''); setPlatform(ALL); setCategory(ALL); setCity(ALL); setStatus(ALL); };

  return (
    <div>
      <PageHeader
        kicker="Community Discovery · Agent 5"
        title="Community Discovery"
        subtitle="Finds public Telegram groups/channels and Discord servers relevant to 100Times' event sectors, via public web search — no bot joins a community and no promotion happens without your approval."
        actions={<Btn variant="primary" loading={runDiscovery.isPending} onClick={() => runDiscovery.mutate({})}><Play size={13} /> Run manual search</Btn>}
      />

      <div className="mt-6"><AutoCommunityDiscoveryToggle /></div>
      {runDiscovery.isError && <div className="mt-4"><ErrorState error={runDiscovery.error} title="Discovery run failed" /></div>}
      {runDiscovery.isSuccess && <div className="mt-4"><Notice tone="info">Run finished: {JSON.stringify(runDiscovery.data)}</Notice></div>}

      <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Communities found" value={all.length} />
        <StatCard label="Needs review" value={needsReview} tone={needsReview ? 'warn' : 'good'} />
        <StatCard label="Approved" value={approved} tone="good" />
        <StatCard label="Telegram / Discord" value={`${telegram} / ${discord}`} />
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl font-bold">{rows.length} communit{rows.length === 1 ? 'y' : 'ies'}</h2>
        <SearchBox value={q} onChange={setQ} placeholder="Search name, description, city…" />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-foreground/10 bg-card px-4 py-3">
        <SelectFilter label="Platform" value={platform} onChange={setPlatform} options={[{ value: ALL, label: 'All' }, { value: 'telegram', label: 'Telegram' }, { value: 'discord', label: 'Discord' }]} />
        <SelectFilter label="Sector" value={category} onChange={setCategory} options={[{ value: ALL, label: 'All' }, ...categoryOptions.map((v) => ({ value: v, label: v }))]} />
        <SelectFilter label="City" value={city} onChange={setCity} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((c) => c.city)).map((v) => ({ value: v, label: v }))]} />
        <SelectFilter label="Status" value={status} onChange={setStatus} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((c) => c.approvalStatus)).map((v) => ({ value: v, label: v.replace(/_/g, ' ') }))]} />
        <Btn variant="ghost" size="sm" onClick={resetFilters}><RotateCcw size={11} /> Reset</Btn>
      </div>

      <div className="mt-4">
        {rows.length === 0 ? <EmptyState title={all.length === 0 ? 'No communities discovered yet.' : 'No communities match these filters.'} body={all.length === 0 ? 'Use “Run manual search” to start finding communities.' : undefined} /> : (
          <>
            <AdminTable columns={['Community', 'Platform', 'Sector', 'City', 'Members', 'Status', 'Discovered', '']} minWidth={1100}>
              {pager.slice.map((c) => (
                <tr key={c.id} className="cursor-pointer hover:bg-muted/20" onClick={() => openCommunity(c)}>
                  <td className={cell}><span className="block max-w-[260px] truncate font-semibold" title={c.name}>{c.name}</span></td>
                  <td className={cellMuted}>{c.platform}</td>
                  <td className={cellMuted}><span className="block max-w-[140px] truncate">{c.category ?? NA}</span></td>
                  <td className={cell}>{c.city ?? <span className="text-muted-foreground">{NA}</span>}</td>
                  <td className={cellMuted}>{c.memberCount != null ? c.memberCount.toLocaleString() : NA}</td>
                  <td className={cell}><Badge tone={STATUS_TONE[c.approvalStatus] ?? 'neutral'}>{c.approvalStatus.replace(/_/g, ' ')}</Badge></td>
                  <td className={cellMuted}>{fmtDate(c.discoveredAt)}</td>
                  <td className={cell}><Btn size="sm" onClick={(ev) => { ev.stopPropagation(); openCommunity(c); }}>View details</Btn></td>
                </tr>
              ))}
            </AdminTable>
            <Pager {...pager} />
          </>
        )}
      </div>

      <CommunityDrawer community={selected} onClose={closeCommunity} />
    </div>
  );
}
