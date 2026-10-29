import { type ReactNode, useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'wouter';
import { CalendarSearch, ChevronRight, Compass, Database, LayoutDashboard, Mail, Search, Settings2, SlidersHorizontal, Sparkles, X, Zap } from 'lucide-react';
import { useDebounce, cx, Kicker, LoadingState, StatusBadge, Badge } from './ui';
import { useDiscoveredEvents, useDiscoveredOrganizers, useMe, useOutreachMessages } from './api';
import { accountTypeOf, homePathFor } from '@/lib/account';

const TOKEN_KEY = '100-times-auth-token';

// ---------------------------------------------------------------------------
// Auth gate — every ops endpoint requires ADMIN, so resolve the role up front
// via the existing GET /api/auth/me instead of letting each table 401.
// ---------------------------------------------------------------------------

function RequireAdmin({ children }: { children: ReactNode }) {
  const [hasToken] = useState(() => typeof window !== 'undefined' && Boolean(localStorage.getItem(TOKEN_KEY)));
  const me = useMe(hasToken);

  if (!hasToken) {
    return (
      <div className="mx-auto max-w-xl px-5 py-32 text-center">
        <Kicker>Admin Console</Kicker>
        <h1 className="mt-4 font-display text-4xl font-extrabold tracking-[-.06em]">Administrator Access Required</h1>
        <p className="mt-3 text-sm text-muted-foreground">Sign in with an authorized administrator account to access platform operations.</p>
        <div className="mt-6 flex justify-center">
          <Link href="/login?redirect=/admin" className="rounded-full bg-primary px-6 py-3 text-sm font-bold text-primary-foreground hover:bg-accent">
            Sign In as Admin
          </Link>
        </div>
      </div>
    );
  }

  if (me.isLoading) {
    return (
      <div className="mx-auto max-w-[1440px] px-5 py-24 lg:px-10 text-center">
        <LoadingState label="Verifying administrator credentials..." />
      </div>
    );
  }

  if (me.isError || me.data?.role !== 'ADMIN') {
    return (
      <div className="mx-auto max-w-xl px-5 py-32 text-center">
        <Kicker>Restricted Area</Kicker>
        <h1 className="mt-4 font-display text-4xl font-extrabold tracking-[-.06em]">Access Denied</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          You are signed in as <strong>{me.data?.email}</strong>. This operational console is restricted to verified administrators.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link href={homePathFor(accountTypeOf(me.data))} className="rounded-full bg-primary px-6 py-3 text-sm font-bold text-primary-foreground hover:bg-accent">
            Return to Dashboard
          </Link>
          <Link
            href="/login?redirect=/admin"
            onClick={() => {
              localStorage.removeItem(TOKEN_KEY);
              window.dispatchEvent(new Event('auth-change'));
            }}
            className="rounded-full border border-foreground/15 px-6 py-3 text-sm font-semibold hover:border-accent hover:text-accent"
          >
            Sign in with Another Account
          </Link>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Navigation — one connected workflow: discover events -> manage what was found
// -> configure discovery -> outreach -> agents -> administration. Every entry is
// a real route in App.tsx.
// ---------------------------------------------------------------------------

/** `exact`: only this path, not its children. `aliases`: other exact paths that also show this entry as current. */
type NavItem = { label: string; href: string; exact?: boolean; aliases?: string[] };
/** `prefix`: any path under it marks the group as current even when no item matches. */
type NavGroup = { title: string; icon: typeof LayoutDashboard; items: NavItem[]; href?: string; prefix?: string };

const NAV: NavGroup[] = [
  { title: 'Overview', icon: LayoutDashboard, items: [{ label: 'Dashboard', href: '/admin', exact: true }] },
  {
    title: 'Discover events', icon: Compass, items: [
      { label: 'Run discovery', href: '/admin/discover', exact: true },
      { label: 'Automatic discovery', href: '/admin/discover/automatic' },
      // /admin/activity is a redirect to this page, kept for old links.
      { label: 'Run history & reports', href: '/admin/discover/runs', aliases: ['/admin/activity'] },
    ],
  },
  {
    title: 'Event management', icon: CalendarSearch, items: [
      { label: 'New discoveries', href: '/admin/discovery', exact: true },
      { label: 'All events', href: '/admin/discovery/events' },
      { label: 'Organizers', href: '/admin/discovery/organizers' },
      { label: 'Contacts', href: '/admin/discovery/contacts' },
    ],
  },
  { title: 'Discovery configuration', icon: SlidersHorizontal, href: '/admin/discover/configuration', items: [] },
  {
    title: 'Organizer outreach', icon: Mail, prefix: '/admin/outreach', items: [
      { label: 'All messages', href: '/admin/outreach/all', aliases: ['/admin/outreach'] },
      { label: 'Pending', href: '/admin/outreach/pending' },
      { label: 'Sent', href: '/admin/outreach/sent' },
      { label: 'Delivered', href: '/admin/outreach/delivered' },
      { label: 'Replies', href: '/admin/outreach/replies' },
      { label: 'Follow-ups', href: '/admin/outreach/follow-ups' },
    ],
  },
  {
    title: 'Platform data', icon: Database, items: [
      { label: 'Overview', href: '/admin/platform' },
      { label: 'Events', href: '/admin/events' },
      { label: 'Users', href: '/admin/users' },
      { label: 'Organizers', href: '/admin/organizers' },
      { label: 'Sectors', href: '/admin/categories' },
      { label: 'Venues', href: '/admin/venues' },
      { label: 'Reviews', href: '/admin/reviews' },
    ],
  },
  {
    title: 'Agents', icon: Sparkles, items: [
      { label: 'Trust agent', href: '/admin/trust-review' },
    ],
  },
  {
    title: 'Automations', icon: Zap, items: [
      { label: 'All automations', href: '/admin/automations' },
      { label: 'Social promotion', href: '/admin/social-promotions' },
    ],
  },
  {
    title: 'Administration', icon: Settings2, items: [
      { label: 'Providers & API keys', href: '/admin/settings' },
      { label: 'System health', href: '/admin/observability' },
      { label: 'n8n workflows', href: '/admin/workflows' },
      { label: 'Audit & system logs', href: '/admin/audit-logs' },
    ],
  },
];

/** `location` is the pathname (wouter's useLocation never includes ?query or #hash); any query/hash on `href` is ignored. */
function pathMatches(location: string, href: string, exact?: boolean) {
  const path = href.split(/[?#]/)[0].replace(/\/+$/, '') || '/';
  const here = location.split(/[?#]/)[0].replace(/\/+$/, '') || '/';
  return exact ? here === path : here === path || here.startsWith(`${path}/`);
}

function itemActive(location: string, item: NavItem) {
  return pathMatches(location, item.href, item.exact) || (item.aliases ?? []).some((a) => pathMatches(location, a, true));
}

function SideNav({ location }: { location: string }) {
  return (
    <aside className="rounded-2xl border border-foreground/10 bg-card p-3 lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
      <p className="px-3 py-3 font-mono-face text-[10px] uppercase tracking-[.16em] text-muted-foreground">100 Times Admin</p>
      <nav aria-label="Admin">
        {NAV.map((group) => {
          const Icon = group.icon;
          if (group.href) {
            const active = pathMatches(location, group.href);
            return (
              <Link key={group.title} href={group.href} aria-current={active ? 'page' : undefined} className={cx('mt-1 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold hover:bg-muted', active && 'bg-muted text-accent')}>
                <Icon size={16} className="text-accent" />{group.title}
              </Link>
            );
          }
          // The first item whose path matches wins, so "/admin/outreach" (no tab) lights up "All messages" only.
          const activeItem = group.items.find((i) => pathMatches(location, i.href, i.exact)) ?? group.items.find((i) => itemActive(location, i));
          const groupActive = Boolean(activeItem) || (group.prefix ? pathMatches(location, group.prefix) : false);
          return (
            <div key={group.title} className="mt-1">
              <p className={cx('flex items-center gap-3 px-3 py-2.5 text-sm font-semibold', groupActive ? 'text-foreground' : 'text-foreground/80')}>
                <Icon size={16} className="text-accent" />{group.title}
              </p>
              <div className="ml-4 border-l border-foreground/10 pl-2">
                {group.items.map((item) => {
                  const active = item === activeItem;
                  return (
                    <Link key={item.href} href={item.href} aria-current={active ? 'page' : undefined} className={cx('block rounded-lg px-3 py-2 text-[13px] hover:bg-muted', active ? 'bg-muted font-semibold text-accent' : 'text-muted-foreground')}>
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

/** Small "Section / Page" trail shown above a page header, so nested admin pages say where they sit. */
export function Breadcrumbs({ items }: { items: Array<{ label: string; href?: string }> }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-1.5 font-mono-face text-[10px] uppercase tracking-[.14em] text-muted-foreground">
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`} className="inline-flex items-center gap-1.5">
          {i > 0 && <ChevronRight size={10} className="opacity-60" />}
          {item.href ? <Link href={item.href} className="hover:text-accent hover:underline">{item.label}</Link> : <span className="text-foreground/80">{item.label}</span>}
        </span>
      ))}
    </nav>
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
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Event name, organizer, email, phone, city, state, sector…" className="h-12 flex-1 bg-transparent text-sm outline-none" />
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
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[240px_1fr]">
          <div className="space-y-3">
            <GlobalSearch />
            <SideNav location={location} />
            <p className="flex items-start gap-2 px-3 text-[11px] text-muted-foreground"><Sparkles size={12} className="mt-0.5 shrink-0 text-accent" /> Automatic discovery runs only when an admin switches it on. Outreach e-mails always wait for approval.</p>
          </div>
          <div className="min-w-0">{children}</div>
        </div>
      </div>
    </RequireAdmin>
  );
}

