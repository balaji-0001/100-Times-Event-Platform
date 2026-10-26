import { useState, type ReactNode } from 'react';
import { Link } from 'wouter';
import {
  BadgeCheck, CalendarDays, CheckCircle2, Clock, ExternalLink, Globe, Heart, Mail, MapPin, Phone, ShieldCheck, Tag, Ticket, Users,
} from 'lucide-react';
import { ApiError } from '@workspace/api-client-react';
import { Badge, Btn, Drawer, LoadingState, Notice, ErrorState, cx } from '@/ops/ui';
import {
  type AttendeeEvent, type EventKind, type MatchInfo, type RegistrationStatus,
  useAttendeeEvent, useRegistrationOpened, useSetExternalRegistration, useToggleSave,
} from './api';

export const NOT_PUBLISHED = 'Not published';

const dateFmt = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

export function fmtDay(value?: string | null) {
  if (!value) return NOT_PUBLISHED;
  const d = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? value : dateFmt.format(d);
}

export function dateRange(ev: AttendeeEvent) {
  return ev.endDate && ev.endDate !== ev.startDate ? `${fmtDay(ev.startDate)} – ${fmtDay(ev.endDate)}` : fmtDay(ev.startDate);
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const data = error.data as { detail?: unknown } | null;
    if (typeof data?.detail === 'string') return data.detail;
    if (Array.isArray(data?.detail)) {
      return (data!.detail as Array<{ msg?: string }>).map((d) => d.msg?.replace(/^Value error, /, '') ?? '').filter(Boolean).join(' · ');
    }
    return `${error.status} ${error.statusText}`;
  }
  return error instanceof Error ? error.message : 'Something went wrong.';
}

const MODE_LABEL: Record<string, string> = { online: 'Online', offline: 'In person', hybrid: 'Hybrid' };

const STATUS_LABEL: Record<RegistrationStatus, { label: string; tone: 'good' | 'warn' | 'neutral' | 'danger' | 'info' }> = {
  NOT_REGISTERED: { label: 'Not registered', tone: 'neutral' },
  REGISTRATION_PAGE_OPENED: { label: 'Registration page opened — not confirmed', tone: 'warn' },
  REGISTERED: { label: 'Registered', tone: 'good' },
  WAITLISTED: { label: 'Waitlisted', tone: 'warn' },
  CANCELLED: { label: 'Registration cancelled', tone: 'danger' },
  NOT_ATTENDING: { label: 'Not attending', tone: 'neutral' },
};

export function RegistrationBadge({ ev }: { ev: AttendeeEvent }) {
  const status = ev.state?.registrationStatus ?? 'NOT_REGISTERED';
  const meta = STATUS_LABEL[status] ?? { label: status, tone: 'neutral' as const };
  const suffix = status === 'REGISTERED' && ev.state?.registrationSource === 'self_reported' ? ' (you confirmed)' : '';
  return <Badge tone={meta.tone}>{meta.label + suffix}</Badge>;
}

export function MatchPill({ match }: { match: MatchInfo | null }) {
  if (!match) return null;
  const tone = match.percent >= 75 ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' : match.percent >= 50 ? 'bg-accent/15 text-accent' : 'bg-muted text-muted-foreground';
  return (
    <span className={cx('rounded-full px-2.5 py-1 font-mono-face text-[11px] font-bold', tone)} title={`${match.criteriaChecked} preference(s) checked`}>
      {match.percent}% match
    </span>
  );
}

export function MatchBreakdown({ match }: { match: MatchInfo }) {
  return (
    <div className="space-y-1.5">
      {match.criteria.map((c) => (
        <div key={c.key} className="flex items-start justify-between gap-3 text-xs">
          <div className="flex items-start gap-2">
            <span
              className={cx(
                'mt-1 h-2 w-2 shrink-0 rounded-full',
                c.status === 'matched' ? 'bg-emerald-500' : c.status === 'partial' ? 'bg-amber-500' : c.status === 'missed' ? 'bg-rose-500' : 'bg-muted-foreground/40',
              )}
            />
            <span>
              <span className="font-semibold">{c.label}:</span> {c.detail}
            </span>
          </div>
          <span className="shrink-0 font-mono-face text-[11px] text-muted-foreground">
            {c.status === 'not_checked' ? 'not checked' : `${Math.round(c.earned)}/${c.weight}`}
          </span>
        </div>
      ))}
      <p className="pt-1 font-mono-face text-[10px] text-muted-foreground">
        {Math.round(match.earned)} of {match.possible} points across {match.criteriaChecked} checked preference(s) = {match.percent}%
      </p>
    </div>
  );
}

function Meta({ icon: Icon, children }: { icon: typeof MapPin; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <Icon size={13} className="text-accent" />
      {children}
    </span>
  );
}

export function AttendeeEventCard({ ev, onOpen, showReasons = true }: { ev: AttendeeEvent; onOpen: (ev: AttendeeEvent) => void; showReasons?: boolean }) {
  const save = useToggleSave();
  const saved = ev.state?.saved ?? false;
  return (
    <article className="flex flex-col justify-between rounded-2xl border border-foreground/10 bg-card p-5 transition hover:border-accent/50" data-testid={`attendee-event-${ev.kind}-${ev.id}`}>
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {ev.sector && <Badge tone="accent">{ev.sector}</Badge>}
            {ev.eventType && <Badge>{ev.eventType}</Badge>}
            {!ev.eligible && <Badge tone="danger">{ev.ineligibleReason}</Badge>}
          </div>
          <MatchPill match={ev.match} />
        </div>
        <button onClick={() => onOpen(ev)} className="mt-3 text-left font-display text-lg font-bold leading-snug hover:text-accent">
          {ev.title}
        </button>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          <Meta icon={CalendarDays}>{dateRange(ev)}</Meta>
          <Meta icon={MapPin}>{ev.location ?? NOT_PUBLISHED}</Meta>
          <Meta icon={Globe}>{ev.attendanceMode ? MODE_LABEL[ev.attendanceMode] : 'Format not stated'}</Meta>
          <Meta icon={Tag}>{ev.price.display}</Meta>
        </div>
        {ev.organizer.name && <p className="mt-2 text-xs text-muted-foreground">By {ev.organizer.name}</p>}
        {showReasons && ev.match && ev.match.reasons.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs">
            {ev.match.reasons.slice(0, 3).map((r) => (
              <li key={r} className="flex items-start gap-1.5">
                <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-emerald-500" />
                {r}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-foreground/10 pt-3">
        <RegistrationBadge ev={ev} />
        <div className="flex gap-2">
          <Btn
            size="sm"
            variant="ghost"
            loading={save.isPending}
            onClick={() => save.mutate({ kind: ev.kind, id: ev.id, saved: !saved })}
            disabled={!ev.eligible && !saved}
            aria-pressed={saved}
            data-testid={`button-save-${ev.kind}-${ev.id}`}
          >
            <Heart size={13} className={saved ? 'fill-accent text-accent' : ''} /> {saved ? 'Saved' : 'Save'}
          </Btn>
          <Btn size="sm" onClick={() => onOpen(ev)}>Details</Btn>
        </div>
      </div>
    </article>
  );
}

export function EventGrid({ events, onOpen, empty }: { events: AttendeeEvent[]; onOpen: (ev: AttendeeEvent) => void; empty: ReactNode }) {
  if (!events.length) return <>{empty}</>;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {events.map((ev) => (
        <AttendeeEventCard key={ev.ref} ev={ev} onOpen={onOpen} />
      ))}
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-3 border-b border-foreground/5 py-2 text-sm last:border-0">
      <span className="text-xs font-semibold text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words">{children}</span>
    </div>
  );
}

function Url({ href }: { href: string | null }) {
  if (!href) return <span className="text-muted-foreground">{NOT_PUBLISHED}</span>;
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-accent hover:underline">
      {href.replace(/^https?:\/\/(www\.)?/, '').slice(0, 60)} <ExternalLink size={12} />
    </a>
  );
}

/** Detail drawer: real event facts, why it matches, favourite, and registration. */
export function AttendeeEventDrawer({ target, onClose }: { target: { kind: EventKind; id: number } | null; onClose: () => void }) {
  const q = useAttendeeEvent(target?.kind ?? null, target?.id ?? null);
  const save = useToggleSave();
  const opened = useRegistrationOpened();
  const setReg = useSetExternalRegistration();
  const [confirming, setConfirming] = useState(false);
  const [checked, setChecked] = useState(false);
  const ev = q.data;

  const close = () => {
    setConfirming(false);
    setChecked(false);
    onClose();
  };

  const openRegistration = () => {
    if (!ev) return;
    if (ev.registerOnPlatform && ev.internalUrl) {
      opened.mutate({ kind: ev.kind, id: ev.id });
      window.location.assign(`${ev.internalUrl}/register`);
      return;
    }
    const url = ev.registrationUrl || ev.officialUrl;
    if (url) window.open(url, '_blank', 'noopener,noreferrer');
    opened.mutate({ kind: ev.kind, id: ev.id });
  };

  const status = ev?.state?.registrationStatus ?? 'NOT_REGISTERED';

  return (
    <Drawer
      open={Boolean(target)}
      onClose={close}
      kicker={ev ? `${ev.kind === 'platform' ? 'Listed on 100 TIMES' : 'Verified external event'}` : 'Event'}
      title={ev?.title ?? 'Loading…'}
      footer={
        ev && (
          <div className="space-y-3">
            {(setReg.error || save.error || opened.error) && <Notice tone="danger">{errorText(setReg.error || save.error || opened.error)}</Notice>}
            {confirming && !ev.registerOnPlatform && (
              <div className="rounded-xl border border-accent/30 bg-accent/5 p-3">
                <label className="flex items-start gap-2 text-xs">
                  <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} className="mt-0.5" data-testid="checkbox-confirm-registration" />
                  I have completed registration on the organizer's own site for this event.
                </label>
                <div className="mt-3 flex gap-2">
                  <Btn
                    variant="primary"
                    size="sm"
                    disabled={!checked}
                    loading={setReg.isPending}
                    onClick={() => setReg.mutate({ id: ev.id, status: 'REGISTERED', confirm: true }, { onSuccess: () => setConfirming(false) })}
                    data-testid="button-confirm-registration"
                  >
                    Confirm I'm registered
                  </Btn>
                  <Btn size="sm" variant="ghost" onClick={() => setConfirming(false)}>Cancel</Btn>
                </div>
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <RegistrationBadge ev={ev} />
              <div className="flex flex-wrap gap-2">
                <Btn size="sm" variant="ghost" loading={save.isPending} disabled={!ev.eligible && !ev.state?.saved}
                  onClick={() => save.mutate({ kind: ev.kind, id: ev.id, saved: !ev.state?.saved })}>
                  <Heart size={13} className={ev.state?.saved ? 'fill-accent text-accent' : ''} /> {ev.state?.saved ? 'Saved' : 'Save'}
                </Btn>
                {ev.eligible && status !== 'REGISTERED' && status !== 'WAITLISTED' && (
                  <Btn size="sm" variant="primary" onClick={openRegistration} disabled={!ev.registerOnPlatform && !ev.registrationUrl && !ev.officialUrl}
                    data-testid="button-open-registration">
                    <Ticket size={13} /> {ev.registerOnPlatform ? 'Register on 100 TIMES' : 'Open official registration'}
                  </Btn>
                )}
                {!ev.registerOnPlatform && status !== 'REGISTERED' && ev.eligible && (
                  <Btn size="sm" onClick={() => setConfirming(true)} data-testid="button-mark-registered">I registered</Btn>
                )}
                {!ev.registerOnPlatform && status === 'REGISTERED' && (
                  <Btn size="sm" variant="ghost" loading={setReg.isPending} onClick={() => setReg.mutate({ id: ev.id, status: 'NONE', confirm: false })}>
                    Undo registered
                  </Btn>
                )}
                {!ev.registerOnPlatform && status !== 'NOT_ATTENDING' && (
                  <Btn size="sm" variant="ghost" loading={setReg.isPending} onClick={() => setReg.mutate({ id: ev.id, status: 'NOT_ATTENDING', confirm: false })}>
                    Not attending
                  </Btn>
                )}
              </div>
            </div>
          </div>
        )
      }
    >
      {q.isLoading && <LoadingState label="Loading event" />}
      {q.isError && <ErrorState error={q.error} retry={() => q.refetch()} />}
      {ev && (
        <div className="space-y-6">
          {!ev.eligible && <Notice tone="danger">No longer recommended: {ev.ineligibleReason}.</Notice>}
          {ev.match ? (
            <section className="rounded-2xl border border-accent/30 bg-accent/5 p-4">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-display text-base font-bold">Why this matches you</h3>
                <MatchPill match={ev.match} />
              </div>
              <MatchBreakdown match={ev.match} />
            </section>
          ) : (
            <Notice tone="info">
              Set your preferences to see how well this event matches you. <Link href="/dashboard/preferences" className="font-semibold underline">Preferences</Link>
            </Notice>
          )}

          <section>
            <h3 className="mb-2 font-display text-base font-bold">Event</h3>
            <Row label="Date">{dateRange(ev)}{ev.startTime ? ` · ${ev.startTime}` : ''}</Row>
            <Row label="Location">{Array.from(new Set([ev.venue, ev.city, ev.country].filter(Boolean))).join(', ') || (ev.attendanceMode === 'online' ? 'Online' : NOT_PUBLISHED)}</Row>
            <Row label="Format">{ev.attendanceMode ? MODE_LABEL[ev.attendanceMode] : NOT_PUBLISHED}</Row>
            <Row label="Sector">{ev.sector ?? NOT_PUBLISHED}</Row>
            <Row label="Type">{ev.eventType ?? NOT_PUBLISHED}</Row>
            <Row label="Price">{ev.price.display}</Row>
            <Row label="Registration closes">{ev.registrationDeadline ? fmtDay(ev.registrationDeadline) : NOT_PUBLISHED}</Row>
            <Row label="Official website">{ev.registerOnPlatform && ev.internalUrl ? <Link href={ev.internalUrl} className="text-accent hover:underline">{`100times${ev.internalUrl}`}</Link> : <Url href={ev.officialUrl} />}</Row>
            <Row label="Registration link">{ev.registerOnPlatform ? 'Register through 100 TIMES (issues your ticket)' : <Url href={ev.registrationUrl} />}</Row>
          </section>

          {ev.description && (
            <section>
              <h3 className="mb-2 font-display text-base font-bold">About</h3>
              <p className="whitespace-pre-line text-sm leading-6 text-muted-foreground">{ev.description}</p>
            </section>
          )}

          <section>
            <h3 className="mb-2 flex items-center gap-2 font-display text-base font-bold">
              <Users size={15} className="text-accent" /> Organizer
            </h3>
            <Row label="Name">
              {ev.organizer.name ?? NOT_PUBLISHED}
              {ev.organizer.verified && <BadgeCheck size={14} className="ml-1 inline text-emerald-500" />}
            </Row>
            <Row label="Website"><Url href={ev.organizer.website} /></Row>
            <Row label="Email">{ev.organizer.email ? <a className="inline-flex items-center gap-1 text-accent hover:underline" href={`mailto:${ev.organizer.email}`}><Mail size={12} />{ev.organizer.email}</a> : NOT_PUBLISHED}</Row>
            <Row label="Phone">{ev.organizer.phone ? <span className="inline-flex items-center gap-1"><Phone size={12} />{ev.organizer.phone}</span> : NOT_PUBLISHED}</Row>
          </section>

          <section className="rounded-xl bg-muted/50 p-3 text-xs text-muted-foreground">
            <p className="flex items-center gap-1.5 font-semibold text-foreground"><ShieldCheck size={13} className="text-emerald-500" /> {ev.verification.basis}</p>
            {ev.verification.sourceUrl && (
              <p className="mt-1">Source: <Url href={ev.verification.sourceUrl} /></p>
            )}
            {ev.state?.registrationConfirmedAt && (
              <p className="mt-1 flex items-center gap-1"><Clock size={12} /> Registration {ev.state.registrationSource === 'platform' ? 'recorded' : 'confirmed by you'} {fmtDay(ev.state.registrationConfirmedAt)}</p>
            )}
          </section>
        </div>
      )}
    </Drawer>
  );
}

/** Small hook so any list can open the shared detail drawer. */
export function useEventDrawer() {
  const [target, setTarget] = useState<{ kind: EventKind; id: number } | null>(null);
  return {
    open: (ev: { kind: EventKind; id: number }) => setTarget({ kind: ev.kind, id: ev.id }),
    drawer: <AttendeeEventDrawer target={target} onClose={() => setTarget(null)} />,
  };
}
