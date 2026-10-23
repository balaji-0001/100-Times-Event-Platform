import { useEffect, useMemo, useState } from 'react';
import { useLocation, useSearch } from 'wouter';
import { Play, RotateCcw } from 'lucide-react';
import { type CommunityPromotionOpportunity, useCommunityPromotionAutoStatus, usePromotionOpportunities, useRunCommunityPromotion, useSetCommunityPromotionAuto } from './api';
import { AdminTable, Badge, Btn, ErrorState, EmptyState, ExtLink, LoadingState, NA, Notice, PageHeader, Pager, SearchBox, SelectFilter, StatCard, Switch, cell, cellMuted, fmtDate, useDebounce, usePagination } from './ui';
import { CommunityPromotionDrawer } from './CommunityPromotionDrawer';

const ALL = '__all__';
const uniq = (vals: Array<string | null | undefined>) => Array.from(new Set(vals.filter((v): v is string => Boolean(v)))).sort();

const STATUS_TONE: Record<string, 'neutral' | 'good' | 'warn' | 'danger' | 'accent' | 'info'> = {
  pending: 'accent', approved: 'warn', rejected: 'danger', scheduled: 'warn',
  ready_for_manual_publishing: 'warn', published: 'good',
};

function AutoCommunityPromotionToggle() {
  const auto = useCommunityPromotionAutoStatus();
  const setAuto = useSetCommunityPromotionAuto();
  const enabled = auto.data?.enabled ?? false;
  const interval = auto.data?.intervalMinutes;

  return (
    <div className="flex items-center gap-2 rounded-full border border-foreground/15 bg-background px-3 py-1.5">
      <Switch checked={enabled} disabled={auto.isLoading || setAuto.isPending} onChange={(next) => setAuto.mutate(next)} label="Automatic promotion drafting" />
      <span className="text-[11px]">
        <span className="font-bold">Automatic drafting {enabled ? 'on' : 'off'}</span>
        <span className="block text-muted-foreground">{enabled ? `Drafts new matches every ${interval ?? '—'} min — still waits for approval before publishing` : 'Off — use the button to draft now'}</span>
      </span>
    </div>
  );
}

export function CommunityPromotionPage() {
  const opportunities = usePromotionOpportunities();
  const runPromotion = useRunCommunityPromotion();
  const [, setLocation] = useLocation();
  const search = useSearch();
  const selectedId = Number(new URLSearchParams(search).get('post')) || null;

  const [q, setQ] = useState(''); const term = useDebounce(q.trim().toLowerCase());
  const [status, setStatus] = useState(ALL); const [platform, setPlatform] = useState(ALL);

  const all = opportunities.data ?? [];
  const rows = useMemo(() => {
    let list = [...all].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    if (status !== ALL) list = list.filter((o) => o.approvalStatus === status);
    if (platform !== ALL) list = list.filter((o) => o.targetCommunity?.platform === platform);
    if (term) list = list.filter((o) => [o.promotedEvent?.title, o.targetCommunity?.name].some((v) => v?.toLowerCase().includes(term)));
    return list;
  }, [all, status, platform, term]);

  const pager = usePagination(rows, 25);
  const selected = selectedId ? all.find((o) => o.id === selectedId) ?? null : null;
  const openOpportunity = (o: CommunityPromotionOpportunity) => setLocation(`/admin/community-promotion?post=${o.id}`);
  const closeOpportunity = () => setLocation('/admin/community-promotion');
  useEffect(() => { if (selectedId && opportunities.isSuccess && !selected) closeOpportunity(); }, [selectedId, opportunities.isSuccess, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  if (opportunities.isLoading) return <LoadingState label="Loading community promotion drafts" />;
  if (opportunities.isError) return <ErrorState error={opportunities.error} retry={() => opportunities.refetch()} />;

  const pending = all.filter((o) => o.approvalStatus === 'pending').length;
  const published = all.filter((o) => o.approvalStatus === 'published').length;
  const clicks = all.reduce((n, o) => n + o.clicksCount, 0);
  const registrations = all.reduce((n, o) => n + o.registrationsCount, 0);

  const resetFilters = () => { setQ(''); setStatus(ALL); setPlatform(ALL); };

  return (
    <div>
      <PageHeader
        kicker="Community Promotion · Agent 4"
        title="Community Promotion"
        subtitle="Matches your published events to communities you've approved (Community Discovery) and drafts a standalone post for each good match. Every post waits for your approval, then a separate publish step, before anything goes out."
        actions={<Btn variant="primary" loading={runPromotion.isPending} onClick={() => runPromotion.mutate({})}><Play size={13} /> Draft matches now</Btn>}
      />

      <div className="mt-6"><AutoCommunityPromotionToggle /></div>
      {runPromotion.isError && <div className="mt-4"><ErrorState error={runPromotion.error} title="Draft run failed" /></div>}
      {runPromotion.isSuccess && <div className="mt-4"><Notice tone="info">Run finished: {JSON.stringify(runPromotion.data)}</Notice></div>}

      <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Drafts" value={all.length} />
        <StatCard label="Awaiting approval" value={pending} tone={pending ? 'warn' : 'good'} />
        <StatCard label="Published" value={published} tone="good" />
        <StatCard label="Clicks / registrations" value={`${clicks} / ${registrations}`} />
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-xl font-bold">{rows.length} draft{rows.length === 1 ? '' : 's'}</h2>
        <SearchBox value={q} onChange={setQ} placeholder="Search event, community…" />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 rounded-2xl border border-foreground/10 bg-card px-4 py-3">
        <SelectFilter label="Status" value={status} onChange={setStatus} options={[{ value: ALL, label: 'All' }, ...uniq(all.map((o) => o.approvalStatus)).map((v) => ({ value: v, label: v.replace(/_/g, ' ') }))]} />
        <SelectFilter label="Platform" value={platform} onChange={setPlatform} options={[{ value: ALL, label: 'All' }, { value: 'telegram', label: 'Telegram' }, { value: 'discord', label: 'Discord' }]} />
        <Btn variant="ghost" size="sm" onClick={resetFilters}><RotateCcw size={11} /> Reset</Btn>
      </div>

      <div className="mt-4">
        {rows.length === 0 ? <EmptyState title={all.length === 0 ? 'No promotion drafts yet.' : 'No drafts match these filters.'} body={all.length === 0 ? 'Approve at least one community in Community Discovery, then use “Draft matches now”.' : undefined} /> : (
          <>
            <AdminTable columns={['Event', 'Community', 'Platform', 'Score', 'Status', 'Published link', 'Drafted', '']} minWidth={1180}>
              {pager.slice.map((o) => (
                <tr key={o.id} className="cursor-pointer hover:bg-muted/20" onClick={() => openOpportunity(o)}>
                  <td className={cell}><span className="block max-w-[220px] truncate font-semibold" title={o.promotedEvent?.title}>{o.promotedEvent?.title ?? NA}</span></td>
                  <td className={cell}><span className="block max-w-[200px] truncate">{o.targetCommunity?.name ?? NA}</span></td>
                  <td className={cellMuted}>{o.targetCommunity?.platform ?? NA}</td>
                  <td className={cellMuted}>{o.relevanceScore} / 100</td>
                  <td className={cell}><Badge tone={STATUS_TONE[o.approvalStatus] ?? 'neutral'}>{o.approvalStatus.replace(/_/g, ' ')}</Badge></td>
                  <td className={cell} onClick={(ev) => ev.stopPropagation()}>{o.publishedUrl ? <ExtLink href={o.publishedUrl} /> : <span className="text-muted-foreground">{NA}</span>}</td>
                  <td className={cellMuted}>{fmtDate(o.createdAt)}</td>
                  <td className={cell}><Btn size="sm" onClick={(ev) => { ev.stopPropagation(); openOpportunity(o); }}>View details</Btn></td>
                </tr>
              ))}
            </AdminTable>
            <Pager {...pager} />
          </>
        )}
      </div>

      <CommunityPromotionDrawer opportunity={selected} onClose={closeOpportunity} />
    </div>
  );
}
