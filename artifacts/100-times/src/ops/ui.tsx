// Presentation primitives for the operations admin. These deliberately reuse the exact
// Tailwind idiom App.tsx is built from (bg-card panels on the dotted bg-background,
// border-foreground/10, font-mono-face kickers, rounded-2xl, .page-enter, .button-press)
// rather than the vendored shadcn set, which the app never adopted and whose theme tokens
// (bg-popover, bg-sidebar-*) index.css does not define.

import { type ReactNode, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'wouter';
import { AlertCircle, ChevronLeft, ChevronRight, ExternalLink, Loader2, X } from 'lucide-react';
import type { OutreachStatus } from './api';
import { STATUS_LABEL } from './api';

export const cx = (...values: Array<string | false | null | undefined>) => values.filter(Boolean).join(' ');

export const NA = 'Not available';

const dateFmt = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
const dateTimeFmt = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const timeFmt = new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit' });

/** The API emits naive ISO datetimes that are UTC; without a zone marker JS would read them as local time. */
export function parseDate(value?: string | null) {
  if (!value) return null;
  const iso = value.includes('T') && !/[zZ]$|[+-]\d\d:?\d\d$/.test(value) ? `${value}Z` : value;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}
const parse = parseDate;
export const fmtDate = (value?: string | null) => { const d = parse(value); return d ? dateFmt.format(d) : NA; };
export const fmtDateTime = (value?: string | null) => { const d = parse(value); return d ? dateTimeFmt.format(d) : NA; };
export const fmtTime = (value?: string | null) => { const d = parse(value); return d ? timeFmt.format(d) : NA; };
export const fmtDuration = (start?: string | null, end?: string | null) => {
  const a = parse(start); const b = parse(end);
  if (!a || !b) return NA;
  const s = Math.max(0, Math.round((b.getTime() - a.getTime()) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60); const r = s % 60;
  return m < 60 ? `${m}m ${r}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
};
/** Text or "Not available" — never an invented value. */
export const val = (v?: string | number | null) => (v === null || v === undefined || v === '' ? NA : String(v));

export function useDebounce<T>(value: T, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => { const t = setTimeout(() => setDebounced(value), delay); return () => clearTimeout(t); }, [value, delay]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Typography & layout
// ---------------------------------------------------------------------------

export function Kicker({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx('font-mono-face text-[10px] uppercase tracking-[.16em] text-accent', className)}>{children}</p>;
}

export function PageHeader({ kicker, title, subtitle, actions }: { kicker: string; title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <Kicker>{kicker}</Kicker>
        <h1 className="mt-3 font-display text-4xl font-extrabold tracking-[-.06em]">{title}</h1>
        {subtitle && <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('rounded-2xl border border-foreground/10 bg-card', className)}>{children}</div>;
}

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="mt-8 first:mt-0">
      <div className="flex items-center justify-between">
        <Kicker className="text-muted-foreground">{title}</Kicker>
        {aside}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** Label / value rows. Values fall back to "Not available" rather than rendering blanks. */
export function DL({ rows }: { rows: Array<[label: string, value: ReactNode]> }) {
  return (
    <dl className="grid gap-x-6 gap-y-2.5 text-sm sm:grid-cols-[max-content_1fr]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground sm:pt-0.5">{label}</dt>
          <dd className={cx('break-words', (value === NA || value === null || value === undefined || value === '') && 'text-muted-foreground')}>
            {value === null || value === undefined || value === '' ? NA : value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ExtLink({ href, children, className }: { href?: string | null; children?: ReactNode; className?: string }) {
  if (!href) return <span className="text-muted-foreground">{NA}</span>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={cx('inline-flex max-w-full items-center gap-1 break-all text-accent hover:underline', className)}>
      <span className="truncate">{children ?? href}</span>
      <ExternalLink size={12} className="shrink-0" />
    </a>
  );
}

export function Notice({ tone = 'warn', children }: { tone?: 'warn' | 'info' | 'danger'; children: ReactNode }) {
  const styles = {
    warn: 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300',
    info: 'border-foreground/15 bg-muted/50 text-foreground/80',
    danger: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  }[tone];
  return <div className={cx('flex gap-2 rounded-lg border p-3 text-xs leading-relaxed', styles)}><AlertCircle size={14} className="mt-0.5 shrink-0" /><div>{children}</div></div>;
}

// ---------------------------------------------------------------------------
// State displays
// ---------------------------------------------------------------------------

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="rounded-2xl border border-foreground/10 bg-card p-8">
      <p className="font-mono-face text-[10px] uppercase tracking-[.16em] text-muted-foreground">{label}</p>
      <div className="mt-4 space-y-3">
        {[0, 1, 2].map((i) => <div key={i} className={cx('loading-bar h-3 rounded-full bg-muted', i === 1 ? 'w-2/3' : 'w-full')} />)}
      </div>
    </div>
  );
}

export function ErrorState({ error, retry, title = 'Could not load this data.' }: { error?: unknown; retry?: () => void; title?: string }) {
  const message = error instanceof Error ? error.message : typeof error === 'string' ? error : null;
  return (
    <div className="rounded-2xl border border-red-500/30 bg-red-500/5 p-8 text-center">
      <p className="font-display text-xl font-bold">{title}</p>
      {message && <p className="mt-2 break-words font-mono-face text-[11px] text-muted-foreground">{message}</p>}
      {retry && <button onClick={retry} className="button-press mt-5 rounded-full border border-foreground/15 px-4 py-2 text-xs font-bold hover:border-accent hover:text-accent">Try again</button>}
    </div>
  );
}

export function EmptyState({ title = 'Nothing here yet.', body }: { title?: string; body?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-foreground/15 bg-card/60 p-10 text-center">
      <p className="font-display text-lg font-bold">{title}</p>
      {body && <p className="mt-2 text-sm text-muted-foreground">{body}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats & badges
// ---------------------------------------------------------------------------

/** A headline number. Pass `href` to make the whole card a link to the rows behind that number. */
export function StatCard({ label, value, sub, tone, href }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'accent' | 'warn' | 'good' | 'danger'; href?: string }) {
  const toneClass = { accent: 'text-accent', warn: 'text-amber-600 dark:text-amber-300', good: 'text-emerald-600 dark:text-emerald-300', danger: 'text-red-600 dark:text-red-300' }[tone ?? 'accent'];
  const body = (
    <>
      <p className="font-mono-face text-[10px] uppercase tracking-[.14em] text-muted-foreground">{label}</p>
      <p className={cx('mt-2 font-display text-3xl font-extrabold tracking-[-.04em]', toneClass)}>{value}</p>
      {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
      {href && <p className="mt-2 font-mono-face text-[10px] uppercase tracking-wider text-accent">View details →</p>}
    </>
  );
  const base = 'block rounded-2xl border border-foreground/10 bg-card p-5';
  if (href) return <Link href={href} className={cx(base, 'button-press transition-colors hover:border-accent/60 hover:bg-muted/30')}>{body}</Link>;
  return <div className={base}>{body}</div>;
}

const STATUS_STYLE: Record<OutreachStatus, string> = {
  NEW: 'border-foreground/15 bg-muted text-muted-foreground',
  RESEARCHED: 'border-foreground/15 bg-muted text-muted-foreground',
  EMAIL_GENERATED: 'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  PENDING_APPROVAL: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  APPROVED: 'border-sky-600/40 bg-sky-600/10 text-sky-700 dark:text-sky-300',
  SENT: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  DELIVERED: 'border-emerald-600/50 bg-emerald-600/15 text-emerald-700 dark:text-emerald-300',
  BOUNCED: 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300',
  REPLIED: 'border-emerald-700/50 bg-emerald-700/15 text-emerald-800 dark:text-emerald-200',
  OPTED_OUT: 'border-red-500/40 bg-red-500/5 text-red-700 line-through dark:text-red-300',
  FOLLOW_UP_DUE: 'border-accent/40 bg-accent/10 text-accent',
  COMPLETED: 'border-foreground/15 bg-muted text-muted-foreground',
  REJECTED: 'border-foreground/15 bg-muted text-muted-foreground line-through',
};

export function StatusBadge({ status }: { status: OutreachStatus | string }) {
  const known = (STATUS_STYLE as Record<string, string>)[status];
  const label = (STATUS_LABEL as Record<string, string>)[status] ?? status.replace(/_/g, ' ').toLowerCase();
  return <span className={cx('inline-block whitespace-nowrap rounded-full border px-2.5 py-0.5 font-mono-face text-[10px] font-bold uppercase', known ?? 'border-foreground/15 bg-muted text-muted-foreground')}>{label}</span>;
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'good' | 'warn' | 'danger' | 'accent' | 'info' }) {
  const styles = {
    neutral: 'border-foreground/15 bg-muted text-muted-foreground',
    good: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    warn: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    danger: 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300',
    accent: 'border-accent/40 bg-accent/10 text-accent',
    info: 'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  }[tone];
  return <span className={cx('inline-block whitespace-nowrap rounded-full border px-2.5 py-0.5 font-mono-face text-[10px] font-bold uppercase', styles)}>{children}</span>;
}

export function Switch({ checked, onChange, disabled, label }: { checked: boolean; onChange: (next: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        'button-press relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'border-accent bg-accent' : 'border-foreground/20 bg-muted',
      )}
    >
      <span className={cx('inline-block h-3.5 w-3.5 transform rounded-full bg-background shadow transition-transform', checked ? 'translate-x-4' : 'translate-x-0.5')} />
    </button>
  );
}

export function verificationTone(status: string): 'good' | 'warn' | 'danger' | 'neutral' {
  return status === 'VERIFIED' ? 'good' : status === 'NEEDS_REVIEW' ? 'warn' : status === 'REJECTED' ? 'danger' : 'neutral';
}

export function ConfidenceBar({ value }: { value?: number | null }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">{NA}</span>;
  const tone = value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted"><span className={cx('block h-full', tone)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></span>
      <span className="font-mono-face text-[11px]">{value}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' | 'ghost'; size?: 'sm' | 'md'; loading?: boolean };
export function Btn({ variant = 'secondary', size = 'md', loading, className, children, disabled, ...rest }: BtnProps) {
  const base = 'button-press inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50';
  const sizes = size === 'sm' ? 'px-3 py-1 text-[11px]' : 'px-4 py-2 text-xs';
  const variants = {
    primary: 'bg-accent text-accent-foreground hover:bg-primary hover:text-primary-foreground',
    secondary: 'border border-foreground/15 bg-background hover:border-accent hover:text-accent',
    danger: 'border border-red-500/40 text-red-700 hover:bg-red-500/10 dark:text-red-300',
    ghost: 'text-muted-foreground hover:bg-muted hover:text-foreground',
  }[variant];
  return (
    <button className={cx(base, sizes, variants, className)} disabled={disabled || loading} {...rest}>
      {loading && <Loader2 size={12} className="animate-spin" />}
      {children}
    </button>
  );
}

export const inputClass = 'w-full rounded-lg border border-foreground/15 bg-background px-3 py-2 text-xs outline-none focus:border-accent';

export function SearchBox({ value, onChange, placeholder = 'Search…' }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className={cx(inputClass, 'max-w-xs')} />;
}

export function SelectFilter({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: Array<{ value: string; label: string }> }) {
  return (
    <label className="flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground">
      <span className="font-mono-face uppercase tracking-wider">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="max-w-[220px] rounded-lg border border-foreground/15 bg-background px-2 py-1.5 text-xs text-foreground outline-none focus:border-accent">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function Chips<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: Array<{ key: T; label: string; count?: number }> }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button key={o.key} onClick={() => onChange(o.key)} className={cx('rounded-full px-3 py-1 font-mono-face text-[11px] transition-colors', value === o.key ? 'bg-accent font-bold text-accent-foreground' : 'border border-foreground/15 text-muted-foreground hover:text-foreground')}>
          {o.label}{o.count !== undefined && <span className="ml-1.5 opacity-70">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Table (the App.tsx table chrome, plus sticky header + pagination)
// ---------------------------------------------------------------------------

export function AdminTable({ columns, children, minWidth = 900 }: { columns: Array<string | { label: string; className?: string }>; children: ReactNode; minWidth?: number }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-foreground/10 bg-card">
      <div className="max-h-[70vh] overflow-auto">
        <table className="w-full text-left text-xs" style={{ minWidth }}>
          <thead className="sticky top-0 z-10 border-b border-foreground/10 bg-muted/90 font-mono-face text-[10px] uppercase text-muted-foreground backdrop-blur">
            <tr>
              {/* keyed by index, not label: action columns legitimately have blank, non-unique headers */}
              {columns.map((c, i) => { const col = typeof c === 'string' ? { label: c } : c; return <th key={i} className={cx('whitespace-nowrap p-3.5 font-normal', col.className)}>{col.label}</th>; })}
            </tr>
          </thead>
          <tbody className="divide-y divide-foreground/10">{children}</tbody>
        </table>
      </div>
    </div>
  );
}

export const cell = 'p-3.5 align-top';
export const cellMuted = 'p-3.5 align-top text-muted-foreground';

export function usePagination<T>(rows: T[], pageSize = 25) {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, pages);
  useEffect(() => { if (page !== safePage) setPage(safePage); }, [page, safePage]);
  const slice = rows.slice((safePage - 1) * pageSize, safePage * pageSize);
  return { page: safePage, pages, slice, setPage, total: rows.length, pageSize };
}

export function Pager({ page, pages, total, pageSize, setPage }: { page: number; pages: number; total: number; pageSize: number; setPage: (p: number) => void }) {
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1; const to = Math.min(total, page * pageSize);
  return (
    <div className="mt-3 flex items-center justify-between font-mono-face text-[11px] text-muted-foreground">
      <span>Showing {from}–{to} of {total}</span>
      <div className="flex items-center gap-1">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-full p-1.5 hover:bg-muted disabled:opacity-40"><ChevronLeft size={14} /></button>
        <span>Page {page} / {pages}</span>
        <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-full p-1.5 hover:bg-muted disabled:opacity-40"><ChevronRight size={14} /></button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Right-anchored drawer (portal + overlay — the app's modal pattern, anchored to the edge)
// ---------------------------------------------------------------------------

export function Drawer({ open, onClose, title, kicker, children, footer, width = 'max-w-2xl' }: { open: boolean; onClose: () => void; title: ReactNode; kicker?: string; children: ReactNode; footer?: ReactNode; width?: string }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm animate-in fade-in" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className={cx('flex h-full w-full flex-col border-l border-foreground/10 bg-card shadow-2xl animate-in slide-in-from-right', width)} role="dialog" aria-modal="true">
        <header className="flex items-start justify-between gap-4 border-b border-foreground/10 px-6 py-5">
          <div className="min-w-0">
            {kicker && <Kicker>{kicker}</Kicker>}
            <h2 className="mt-1 truncate font-display text-xl font-bold">{title}</h2>
          </div>
          <button onClick={onClose} aria-label="Close" className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-foreground/10 bg-background hover:bg-muted"><X size={16} /></button>
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-6">{children}</div>
        {footer && <footer className="border-t border-foreground/10 px-6 py-4">{footer}</footer>}
      </aside>
    </div>,
    document.body,
  );
}
