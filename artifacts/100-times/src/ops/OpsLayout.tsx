import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { Link, Redirect, useLocation } from 'wouter';
import { Activity, CalendarSearch, LayoutDashboard, Mail, Search, Settings2, Sparkles, X } from 'lucide-react';
import { useDebounce, cx, Kicker, LoadingState, StatusBadge, Badge } from './ui';
import { useDiscoveredEvents, useDiscoveredOrganizers, useMe, useOutreachMessages } from './api';

const TOKEN_KEY = '100-times-auth-token';

// ---------------------------------------------------------------------------
// Auth gate — every ops endpoint requires ADMIN, so resolve the role up front
// via the existing GET /api/auth/me instead of letting each table 401.
// ---------------------------------------------------------------------------

function RequireAdmin({ children }: { children: ReactNode }) {
  const hasToken = typeof window !== 'undefined' && Boolean(localStorage.getItem(TOKEN_KEY));
  const me = useMe(hasToken);

  if (!hasToken) return <Redirect to="/login" />;
  if (me.isLoading) return <div className="mx-auto max-w-[1440px] px-5 py-16 lg:px-10"><LoadingState label="Checking your access" /></div>;
  if (me.isError) {
    localStorage.removeItem(TOKEN_KEY);
    return <Redirect to="/login" />;
  }
  if (me.data?.role !== 'ADMIN') {
    return (
      <div className="mx-auto max-w-xl px-5 py-32 text-center">
        <Kicker>Admin only</Kicker>
        <h1 className="mt-4 font-display text-4xl font-extrabold tracking-[-.06em]">This console is for 100Times admins.</h1>
        <p className="mt-3 text-sm text-muted-foreground">You are signed in as {me.data?.email} ({me.data?.role.toLowerCase()}). Ask an admin to upgrade your role.</p>
        <Link href="/" className="mt-8 inline-block rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground">Back to 100Times</Link>
      </div>
    );
  }
  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

type NavItem = { label: string; href: string; exact?: boolean };
type NavGroup = { title: string; icon: typeof LayoutDashboard; items: NavItem[]; href?: string };

const NAV: NavGroup[] = [
  { title: 'Dashboard', icon: LayoutDashboard, href: '/admin', items: [] },
  {
    title: 'Organizer Discovery', icon: CalendarSearch, items: [
      { label: 'New Discoveries', href: '/admin/discovery', exact: true },
      { label: 'Events Found', href: '/admin/discovery/events' },
      { label: 'All Organizers', href: '/admin/discovery/organizers' },
      { label: 'Contacts', href: '/admin/discovery/contacts' },
    ],
  },
  {
    title: 'Organizer Outreach', icon: Mail, items: [
      { label: 'Pending', href: '/admin/outreach/pending' },
      { label: 'Sent', href: '/admin/outreach/sent' },
      { label: 'Delivered', href: '/admin/outreach/delivered' },
      { label: 'Replies', href: '/admin/outreach/replies' },
      { label: 'Follow-ups', href: '/admin/outreach/follow-ups' },
    ],
  },
  { title: 'Trust Review (Agent 3)', icon: Sparkles, href: '/admin/trust-review', items: [] },
  { title: 'Attendee Agent', icon: CalendarSearch, href: '/admin/attendee-agent', items: [] },
  { title: 'n8n Workflows', icon: Activity, href: '/admin/workflows', items: [] },
  { title: 'Audit & System Logs', icon: Activity, href: '/admin/audit-logs', items: [] },
  { title: 'Agent Activity', icon: Activity, href: '/admin/activity', items: [] },
  { title: 'Settings', icon: Settings2, href: '/admin/settings', items: [] },
];

function isActive(location: string, href: string, exact?: boolean) {
  return exact ? location === href : location === href || location.startsWith(href + '/') || location.startsWith(href + '?');
}

function SideNav({ location }: { location: string }) {
  return (
    <aside className="rounded-2xl border border-foreground/10 bg-card p-3 lg:sticky lg:top-24 lg:h-fit">
      <p className="px-3 py-3 font-mono-face text-[10px] uppercase tracking-[.16em] text-muted-foreground">100 Times Admin</p>
      {NAV.map((group) => {
        const Icon = group.icon;
        if (group.href) {
          const active = group.href === '/admin' ? location === '/admin' : isActive(location, group.href);
          return (
            <Link key={group.title} href={group.href} className={cx('flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold hover:bg-muted', active && 'bg-muted text-accent')}>
              <Icon size={16} className="text-accent" />{group.title}
            </Link>
          );
        }
        const groupActive = group.items.some((i) => isActive(location, i.href, i.exact));
        return (
          <div key={group.title} className="mt-1">
            <p className={cx('flex items-center gap-3 px-3 py-2.5 text-sm font-semibold', groupActive ? 'text-foreground' : 'text-foreground/80')}>
              <Icon size={16} className="text-accent" />{group.title}
            </p>
            <div className="ml-4 border-l border-foreground/10 pl-2">
              {group.items.map((item) => {
                const active = isActive(location, item.href, item.exact);
                return (
                  <Link key={item.href} href={item.href} className={cx('block rounded-lg px-3 py-2 text-[13px] hover:bg-muted', active ? 'bg-muted font-semibold text-accent' : 'text-muted-foreground')}>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Global search — client-side over the three loaded lists (all cached by react-query).
// ---------------------------------------------------------------------------

function GlobalSearch() {
  const [, setLocation] = useLocation();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const term = useDebounce(q.trim().toLowerCase(), 200);
  const events = useDiscoveredEvents();
  const organizers = useDiscoveredOrganizers();
  const messages = useOutreachMessages();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === '/' && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) { e.preventDefault(); setOpen(true); } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const results = useMemo(() => {
    if (term.length < 2) return { events: [], organizers: [], messages: [] };
    const has = (...vals: Array<string | null | undefined>) => vals.some((v) => v && v.toLowerCase().includes(term));
    return {
      events: (events.data ?? []).filter((e) => has(e.name, e.city, e.state, e.category, e.subcategory, e.venue)).slice(0, 6),
      organizers: (organizers.data ?? []).filter((o) => has(o.name, o.email, o.phone, o.website, o.city, o.state)).slice(0, 6),
      messages: (messages.data ?? []).filter((m) => has(m.recipient, m.subject, m.organizer?.name, m.event?.name, m.event?.city)).slice(0, 6),
    };
  }, [term, events.data, organizers.data, messages.data]);

  const go = (href: string) => { setOpen(false); setQ(''); setLocation(href); };
  const none = results.events.length + results.organizers.length + results.messages.length === 0;

  return (
    <>
      <button onClick={() => setOpen(true)} data-testid="ops-global-search" className="flex w-full items-center gap-2 rounded-xl border border-foreground/15 bg-background px-3 py-2 text-left text-xs text-muted-foreground hover:border-accent">
        <Search size={14} /><span className="flex-1">Search events, organizers, emails…</span><kbd className="rounded bg-muted px-1.5 font-mono-face text-[10px]">/</kbd>
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-[12vh] backdrop-blur-sm animate-in fade-in" onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-foreground/10 bg-card shadow-2xl">
            <div className="flex items-center gap-3 border-b border-foreground/10 px-4">
              <Search size={16} className="text-muted-foreground" />
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Event name, organizer, email, phone, city, state, category…" className="h-12 flex-1 bg-transparent text-sm outline-none" />
              <button onClick={() => setOpen(false)} className="rounded-full p-1.5 hover:bg-muted"><X size={14} /></button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto p-2">
              {term.length < 2 ? (
                <p className="p-4 text-center text-xs text-muted-foreground">Type at least two characters.</p>
              ) : none ? (
                <p className="p-4 text-center text-xs text-muted-foreground">No matches in discovered events, organizers or outreach records.</p>
              ) : (
                <>
                  {results.events.length > 0 && <SearchGroup title="Events">{results.events.map((e) => (
                    <SearchRow key={e.id} onClick={() => go(`/admin/discovery/events?event=${e.id}`)} title={e.name ?? `Event #${e.id}`} meta={[e.city, e.category].filter(Boolean).join(' · ')} right={<Badge tone={e.verificationStatus === 'VERIFIED' ? 'good' : 'warn'}>{e.verificationStatus.replace('_', ' ')}</Badge>} />
                  ))}</SearchGroup>}
                  {results.organizers.length > 0 && <SearchGroup title="Organizers">{results.organizers.map((o) => (
                    <SearchRow key={o.id} onClick={() => go(`/admin/discovery/organizers/${o.id}`)} title={o.name} meta={[o.email, o.city].filter(Boolean).join(' · ')} />
                  ))}</SearchGroup>}
                  {results.messages.length > 0 && <SearchGroup title="Outreach">{results.messages.map((m) => (
                    <SearchRow key={m.id} onClick={() => go(`/admin/outreach/all?message=${m.id}`)} title={m.subject ?? `Outreach #${m.id}`} meta={[m.organizer?.name, m.recipient].filter(Boolean).join(' · ')} right={<StatusBadge status={m.status} />} />
                  ))}</SearchGroup>}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function SearchGroup({ title, children }: { title: string; children: ReactNode }) {
  return <div className="p-1"><p className="px-3 py-1.5 font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground">{title}</p>{children}</div>;
}
function SearchRow({ title, meta, right, onClick }: { title: string; meta?: string; right?: ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left hover:bg-muted">
      <span className="min-w-0"><span className="block truncate text-sm font-semibold">{title}</span>{meta && <span className="block truncate text-xs text-muted-foreground">{meta}</span>}</span>
      {right}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export function OpsLayout({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  return (
    <RequireAdmin>
      <div className="page-enter mx-auto max-w-[1440px] px-5 py-8 lg:px-10 lg:py-10">
        <div className="grid gap-8 lg:grid-cols-[240px_1fr]">
          <div className="space-y-3">
            <GlobalSearch />
            <SideNav location={location} />
            <p className="flex items-center gap-2 px-3 text-[11px] text-muted-foreground"><Sparkles size={12} className="text-accent" /> Agent 2 always waits for approval. Agent 1's automatic scan is off unless you turn it on.</p>
          </div>
          <div className="min-w-0">{children}</div>
        </div>
      </div>
    </RequireAdmin>
  );
}

