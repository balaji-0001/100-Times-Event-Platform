import { useEffect, useMemo, useRef, useState, type FormEvent, type InputHTMLAttributes, type ReactNode } from 'react';
import { Link } from 'wouter';
import { Bell, CalendarClock, Heart, Loader2, Send, Sparkles, Ticket, Wand2, X } from 'lucide-react';
import { Badge, Btn, EmptyState, ErrorState, LoadingState, Notice, Switch, cx, inputClass, useDebounce } from '@/ops/ui';
import {
  type AssistantResponse, type AttendeeEvent, type AttendeePreferences, type AttendeeProfileInput, type EventSearchParams,
  useAskAssistant, useAttendeeDashboard, useAttendeeNotifications, useAttendeeOptions, useAttendeePreferences, useAttendeeProfile,
  useMarkNotificationRead, useMatchMyEvents, useSaveAttendeeProfile, useSavePreferences, useSearchEvents,
} from './api';
import { AttendeeEventCard, EventGrid, MatchPill, dateRange, errorText, fmtDay, useEventDrawer } from './components';

function SectionTitle({ title, sub, action }: { title: string; sub?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="font-display text-2xl font-bold tracking-tight">{title}</h2>
        {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

function CompactRow({ ev, onOpen, right }: { ev: AttendeeEvent; onOpen: (ev: AttendeeEvent) => void; right?: ReactNode }) {
  return (
    <button onClick={() => onOpen(ev)} className="flex w-full items-center justify-between gap-4 rounded-2xl border border-foreground/10 bg-card p-4 text-left hover:border-accent/50">
      <div className="min-w-0">
        <p className="truncate font-display text-base font-bold">{ev.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{dateRange(ev)} · {ev.location ?? 'Location not published'}</p>
      </div>
      <div className="shrink-0">{right}</div>
    </button>
  );
}

function PreferencesCta() {
  return (
    <Notice tone="info">
      Tell us your interests, industries and countries to get matched events with a real match percentage.{' '}
      <Link href="/dashboard/preferences" className="font-semibold underline">Set preferences</Link>
    </Notice>
  );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

export function AttendeeOverview() {
  const q = useAttendeeDashboard();
  const { open, drawer } = useEventDrawer();
  if (q.isLoading) return <LoadingState label="Loading your dashboard" />;
  if (q.isError || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const d = q.data;

  const stat = (label: string, value: number, href: string, Icon: typeof Heart) => (
    <Link href={href} className="rounded-2xl border border-foreground/10 bg-card p-5 hover:border-accent/50">
      <Icon size={18} className="text-accent" />
      <p className="mt-5 font-display text-4xl font-bold">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{label}</p>
    </Link>
  );

  return (
    <div className="space-y-12">
      <div className="grid gap-3 sm:grid-cols-4">
        {stat('Saved events', d.counts.saved, '/dashboard/saved-events', Heart)}
        {stat('Registered', d.counts.registered, '/dashboard/registrations', Ticket)}
        {stat('Upcoming', d.counts.upcoming, '/dashboard', CalendarClock)}
        {stat('Unread notifications', d.counts.unreadNotifications, '/dashboard/notifications', Bell)}
      </div>

      <section>
        <SectionTitle
          title="Recommended for you"
          sub={`Ranked by your preferences against ${d.catalogSize} verified upcoming events. Only events matching at least 50% are shown.`}
          action={<Link href="/dashboard/recommendations" className="text-xs font-bold text-accent hover:underline">Match my events →</Link>}
        />
        {!d.hasPreferences ? <PreferencesCta /> : (
          <EventGrid events={d.recommended} onOpen={open} empty={<EmptyState title="No event matches 50% or more right now." body="Try widening your preferences — or check back after the next discovery run." />} />
        )}
      </section>

      <div className="grid gap-10 lg:grid-cols-2">
        <section>
          <SectionTitle title="Upcoming" sub="Events you saved or registered for that haven't happened yet." />
          {d.upcoming.length ? (
            <div className="space-y-2">{d.upcoming.map((ev) => <CompactRow key={ev.ref} ev={ev} onOpen={open} right={<Badge tone={ev.state?.registrationStatus === 'REGISTERED' ? 'good' : 'neutral'}>{ev.state?.registrationStatus === 'REGISTERED' ? 'Registered' : 'Saved'}</Badge>} />)}</div>
          ) : <EmptyState title="Nothing upcoming yet." body="Save or register for an event and it will show here." />}
        </section>
        <section>
          <SectionTitle title="Registration deadlines" sub="For saved events you haven't registered for, as published by each organizer." />
          {d.deadlines.length ? (
            <div className="space-y-2">{d.deadlines.map((ev) => <CompactRow key={ev.ref} ev={ev} onOpen={open} right={<Badge tone="warn">Closes {fmtDay(ev.registrationDeadline)}</Badge>} />)}</div>
          ) : <EmptyState title="No published deadlines." body={d.savedWithoutPublishedDeadline ? `${d.savedWithoutPublishedDeadline} saved event(s) have no registration deadline published by the organizer.` : undefined} />}
          {d.deadlines.length > 0 && d.savedWithoutPublishedDeadline > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">{d.savedWithoutPublishedDeadline} other saved event(s) have no published deadline.</p>
          )}
        </section>
      </div>

      <section>
        <SectionTitle title="Registered" sub="Registrations made on 100 TIMES, plus external ones you confirmed yourself." />
        <EventGrid events={d.registered} onOpen={open} empty={<EmptyState title="No registrations yet." />} />
      </section>

      <section>
        <SectionTitle title="Recently viewed" />
        {d.recentlyViewed.length ? (
          <div className="space-y-2">{d.recentlyViewed.map((ev) => <CompactRow key={ev.ref} ev={ev} onOpen={open} right={<span className="font-mono-face text-[10px] text-muted-foreground">{fmtDay(ev.state?.lastViewedAt)}</span>} />)}</div>
        ) : <EmptyState title="You haven't opened any events yet." />}
      </section>
      {drawer}
    </div>
  );
}

export function SavedEventsPanel() {
  const q = useAttendeeDashboard();
  const { open, drawer } = useEventDrawer();
  if (q.isLoading) return <LoadingState label="Loading saved events" />;
  if (q.isError || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  return (
    <>
      <EventGrid events={q.data.saved} onOpen={open} empty={<EmptyState title="Your shortlist is empty." body="Tap Save on any event to keep it here." />} />
      {drawer}
    </>
  );
}

export function ExternalRegistrationsPanel() {
  const q = useAttendeeDashboard();
  const { open, drawer } = useEventDrawer();
  const external = (q.data?.registered ?? []).filter((e) => e.kind === 'discovered');
  if (!external.length) return null;
  return (
    <section className="mt-10">
      <SectionTitle title="External registrations" sub="Events you registered for on the organizer's own site and confirmed here." />
      <EventGrid events={external} onOpen={open} empty={null} />
      {drawer}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Preferences
// ---------------------------------------------------------------------------

const EMPTY_PREFS: AttendeePreferences = {
  interests: [], industries: [], countries: [], eventTypes: [], budgetMax: null, budgetCurrency: null, freeOnly: false,
  dateFrom: null, dateTo: null, attendanceMode: 'any', notifyConsent: false, notifyEventReminders: true, notifyDeadlines: true,
  notifyEventChanges: true, notifyNewMatches: true, notifyByEmail: false,
};

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
      className={cx('rounded-full border px-3 py-1.5 text-xs font-semibold transition', active ? 'border-accent bg-accent text-accent-foreground' : 'border-foreground/15 bg-background hover:border-accent hover:text-accent')}>
      {children}
    </button>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-foreground/10 bg-card p-5">
      <p className="text-sm font-bold">{label}</p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      <div className="mt-3">{children}</div>
    </div>
  );
}

const toggle = (list: string[], value: string) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

export function PreferencesPanel() {
  const prefsQ = useAttendeePreferences();
  const optsQ = useAttendeeOptions();
  const save = useSavePreferences();
  const [form, setForm] = useState<AttendeePreferences>(EMPTY_PREFS);
  const [interestDraft, setInterestDraft] = useState('');
  const [countryDraft, setCountryDraft] = useState('');
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    if (prefsQ.data) setForm({ ...EMPTY_PREFS, ...prefsQ.data });
  }, [prefsQ.data]);

  if (prefsQ.isLoading || optsQ.isLoading) return <LoadingState label="Loading preferences" />;
  if (prefsQ.isError || optsQ.isError || !optsQ.data) return <ErrorState error={prefsQ.error || optsQ.error} retry={() => { prefsQ.refetch(); optsQ.refetch(); }} />;
  const opts = optsQ.data;
  const countryCounts = new Map(opts.countries.map((c) => [c.value, c.count]));
  const set = <K extends keyof AttendeePreferences>(key: K, value: AttendeePreferences[K]) => setForm((f) => ({ ...f, [key]: value }));

  const addInterest = (value: string) => {
    const v = value.trim();
    if (v && !form.interests.some((i) => i.toLowerCase() === v.toLowerCase())) set('interests', [...form.interests, v]);
    setInterestDraft('');
  };
  const addCountry = (value: string) => {
    const match = opts.allCountries.find((c) => c.toLowerCase() === value.trim().toLowerCase());
    if (match && !form.countries.includes(match)) set('countries', [...form.countries, match]);
    setCountryDraft('');
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(form, { onSuccess: () => setSavedAt(Date.now()) });
  };

  return (
    <form onSubmit={submit} className="space-y-4" data-testid="form-attendee-preferences">
      <p className="text-sm text-muted-foreground">
        These drive "Match My Events", your recommendations and new-match alerts. Counts show how many of the {opts.catalogSize} verified upcoming events fit each option right now.
      </p>

      <Field label="Interests" hint="Topics you care about — matched against each event's title, description and published keywords.">
        <div className="flex flex-wrap gap-2">
          {form.interests.map((i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-xs font-semibold text-accent-foreground">
              {i}
              <button type="button" aria-label={`Remove ${i}`} onClick={() => set('interests', form.interests.filter((x) => x !== i))}><X size={12} /></button>
            </span>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input value={interestDraft} onChange={(e) => setInterestDraft(e.target.value)} placeholder="e.g. AI, cybersecurity, robotics"
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addInterest(interestDraft); } }} className={inputClass} data-testid="input-interest" />
          <Btn type="button" onClick={() => addInterest(interestDraft)}>Add</Btn>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {opts.interestSuggestions.filter((s) => !form.interests.some((i) => i.toLowerCase() === s)).slice(0, 14).map((s) => (
            <button type="button" key={s} onClick={() => addInterest(s)} className="rounded-full border border-dashed border-foreground/20 px-2.5 py-1 text-[11px] text-muted-foreground hover:border-accent hover:text-accent">+ {s}</button>
          ))}
        </div>
      </Field>

      <Field label="Industries">
        <div className="flex flex-wrap gap-2">
          {opts.industries.map((o) => (
            <Chip key={o.value} active={form.industries.includes(o.value)} onClick={() => set('industries', toggle(form.industries, o.value))}>
              {o.value} <span className="opacity-60">{o.count}</span>
            </Chip>
          ))}
        </div>
      </Field>

      <Field label="Preferred countries" hint="Online events always count as reachable from your countries.">
        <div className="flex flex-wrap gap-2">
          {form.countries.map((c) => (
            <span key={c} className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-xs font-semibold text-accent-foreground">
              {c} <span className="opacity-70">{countryCounts.get(c) ?? 0}</span>
              <button type="button" aria-label={`Remove ${c}`} onClick={() => set('countries', form.countries.filter((x) => x !== c))}><X size={12} /></button>
            </span>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input list="attendee-country-list" value={countryDraft} onChange={(e) => setCountryDraft(e.target.value)} placeholder="Type a country"
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCountry(countryDraft); } }} className={inputClass} data-testid="input-country" />
          <datalist id="attendee-country-list">{opts.allCountries.map((c) => <option key={c} value={c} />)}</datalist>
          <Btn type="button" onClick={() => addCountry(countryDraft)}>Add</Btn>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {opts.countries.filter((c) => !form.countries.includes(c.value)).slice(0, 10).map((c) => (
            <button type="button" key={c.value} onClick={() => addCountry(c.value)} className="rounded-full border border-dashed border-foreground/20 px-2.5 py-1 text-[11px] text-muted-foreground hover:border-accent hover:text-accent">+ {c.value} ({c.count})</button>
          ))}
        </div>
      </Field>

      <Field label="Event types">
        <div className="flex flex-wrap gap-2">
          {opts.eventTypes.map((o) => (
            <Chip key={o.value} active={form.eventTypes.includes(o.value)} onClick={() => set('eventTypes', toggle(form.eventTypes, o.value))}>
              {o.value} <span className="opacity-60">{o.count}</span>
            </Chip>
          ))}
        </div>
      </Field>

      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Attendance mode">
          <div className="flex flex-wrap gap-2">
            {(['any', 'online', 'offline', 'hybrid'] as const).map((m) => (
              <Chip key={m} active={form.attendanceMode === m} onClick={() => set('attendanceMode', m)}>{m === 'offline' ? 'in person' : m}</Chip>
            ))}
          </div>
        </Field>
        <Field label="Dates" hint="Leave empty for any upcoming date.">
          <div className="flex gap-2">
            <input type="date" value={form.dateFrom ?? ''} onChange={(e) => set('dateFrom', e.target.value || null)} className={inputClass} aria-label="From" />
            <input type="date" value={form.dateTo ?? ''} onChange={(e) => set('dateTo', e.target.value || null)} className={inputClass} aria-label="To" />
          </div>
        </Field>
      </div>

      <Field label="Budget" hint="Events whose source didn't publish a price aren't scored on budget — they're marked 'not checked'.">
        <label className="flex items-center gap-2 text-sm"><Switch checked={form.freeOnly} onChange={(v) => set('freeOnly', v)} /> Free events only</label>
        {!form.freeOnly && (
          <div className="mt-3 flex gap-2">
            <input type="number" min={0} value={form.budgetMax ?? ''} onChange={(e) => set('budgetMax', e.target.value === '' ? null : Number(e.target.value))} placeholder="Max ticket price" className={inputClass} />
            <select value={form.budgetCurrency ?? ''} onChange={(e) => set('budgetCurrency', e.target.value || null)} className={inputClass}>
              <option value="">Any currency</option>
              {Array.from(new Set(['INR', 'USD', 'EUR', 'GBP', 'AED', ...opts.currencies.map((c) => c.value)])).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        )}
      </Field>

      <Field label="Notifications" hint="Nothing is ever sent until you switch on consent. You can withdraw it at any time.">
        <label className="flex items-center gap-2 text-sm font-semibold"><Switch checked={form.notifyConsent} onChange={(v) => set('notifyConsent', v)} /> I agree to receive event notifications from 100 TIMES</label>
        <div className={cx('mt-3 grid gap-2 sm:grid-cols-2', !form.notifyConsent && 'pointer-events-none opacity-40')}>
          <label className="flex items-center gap-2 text-xs"><Switch checked={form.notifyEventReminders} onChange={(v) => set('notifyEventReminders', v)} /> Reminders for events I'm registered for</label>
          <label className="flex items-center gap-2 text-xs"><Switch checked={form.notifyDeadlines} onChange={(v) => set('notifyDeadlines', v)} /> Registration deadlines for saved events</label>
          <label className="flex items-center gap-2 text-xs"><Switch checked={form.notifyEventChanges} onChange={(v) => set('notifyEventChanges', v)} /> Changes to events I saved or registered for</label>
          <label className="flex items-center gap-2 text-xs"><Switch checked={form.notifyNewMatches} onChange={(v) => set('notifyNewMatches', v)} /> Newly discovered events that match me</label>
          <label className="flex items-center gap-2 text-xs"><Switch checked={form.notifyByEmail} onChange={(v) => set('notifyByEmail', v)} /> Also email me (in-app is always on)</label>
        </div>
        {form.notifyByEmail && opts.emailDelivery.status !== 'REAL' && (
          <div className="mt-3"><Notice tone="warn">Email delivery isn't configured on this server yet, so you'll get in-app notifications only.</Notice></div>
        )}
        {prefsQ.data?.notifyConsentAt && form.notifyConsent && <p className="mt-2 text-[11px] text-muted-foreground">Consent given {fmtDay(prefsQ.data.notifyConsentAt)}</p>}
      </Field>

      {save.isError && <Notice tone="danger">{errorText(save.error)}</Notice>}
      <div className="flex items-center gap-3">
        <Btn type="submit" variant="primary" loading={save.isPending} data-testid="button-save-preferences">Save preferences</Btn>
        {savedAt && !save.isPending && !save.isError && <span className="text-xs text-emerald-600">Saved. <Link href="/dashboard/recommendations" className="underline">Match my events →</Link></span>}
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Match My Events
// ---------------------------------------------------------------------------

export function MatchesPanel() {
  const prefsQ = useAttendeePreferences();
  const match = useMatchMyEvents();
  const { open, drawer } = useEventDrawer();
  const [minPercent, setMinPercent] = useState(0);
  const data = match.data;
  const rows = useMemo(() => (data?.results ?? []).filter((e) => (e.match?.percent ?? 0) >= minPercent), [data, minPercent]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-accent/30 bg-accent/5 p-5">
        <div>
          <p className="font-display text-lg font-bold">Match My Events</p>
          <p className="text-xs text-muted-foreground">
            Scores every verified upcoming event against your saved preferences. Weights: industry 30 · interests 25 · country 15 · type 10 · mode 10 · budget 5 · dates 5.
          </p>
        </div>
        <Btn variant="primary" onClick={() => match.mutate(200)} loading={match.isPending} data-testid="button-match-my-events">
          <Wand2 size={14} /> Match My Events
        </Btn>
      </div>
      {prefsQ.data && !prefsQ.data.saved && <PreferencesCta />}
      {match.isError && <Notice tone="danger">{errorText(match.error)}</Notice>}
      {data && !data.hasPreferences && <PreferencesCta />}
      {data && data.hasPreferences && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
            <span>Ranked {data.totalRanked} of {data.catalogSize} verified upcoming events · showing {rows.length}</span>
            <label className="flex items-center gap-2">
              Minimum match
              <select value={minPercent} onChange={(e) => setMinPercent(Number(e.target.value))} className="rounded-lg border border-foreground/15 bg-background px-2 py-1">
                {[0, 25, 50, 75, 90].map((p) => <option key={p} value={p}>{p}%</option>)}
              </select>
            </label>
          </div>
          <EventGrid events={rows} onOpen={open} empty={<EmptyState title="No events at this match level." />} />
        </>
      )}
      {!data && !match.isPending && prefsQ.data?.saved && <EmptyState title="Press Match My Events to rank the catalog for you." />}
      {drawer}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Assistant
// ---------------------------------------------------------------------------

type Turn = { role: 'user'; text: string } | { role: 'assistant'; data: AssistantResponse } | { role: 'error'; text: string };

const STARTERS = [
  'Find 10 construction conferences in India',
  'Show free pharmaceutical events worldwide next month',
  'Find healthcare exhibitions in the USA',
  'Recommend events matching my profile',
  'Find online workshops this weekend',
];

export function AssistantPanel({ compact = false }: { compact?: boolean }) {
  const ask = useAskAssistant();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const { open, drawer } = useEventDrawer();
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }); }, [turns, ask.isPending]);

  const send = (text: string) => {
    const message = text.trim();
    if (message.length < 2 || ask.isPending) return;
    setTurns((t) => [...t, { role: 'user', text: message }]);
    setDraft('');
    ask.mutate(message, {
      onSuccess: (data) => setTurns((t) => [...t, { role: 'assistant', data }]),
      onError: (err) => setTurns((t) => [...t, { role: 'error', text: errorText(err) }]),
    });
  };

  return (
    <div className={cx('flex flex-col rounded-2xl border border-foreground/10 bg-card', compact ? 'h-full' : 'h-[70vh]')}>
      <div className="flex-1 space-y-4 overflow-y-auto p-5">
        {!turns.length && (
          <div>
            <p className="text-sm text-muted-foreground">
              Ask in plain English. I search only verified upcoming events in the 100 TIMES catalog and apply every country, sector, date, price and count you mention.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {STARTERS.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-full border border-foreground/15 px-3 py-1.5 text-xs hover:border-accent hover:text-accent">{s}</button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, i) => {
          if (turn.role === 'user') {
            return <div key={i} className="ml-auto max-w-[85%] rounded-2xl rounded-br-none bg-primary px-4 py-2.5 text-sm text-primary-foreground">{turn.text}</div>;
          }
          if (turn.role === 'error') {
            return <Notice key={i} tone="danger">{turn.text}</Notice>;
          }
          const d = turn.data;
          return (
            <div key={i} className="space-y-3">
              <div className="max-w-[92%] rounded-2xl rounded-bl-none border border-foreground/10 bg-background px-4 py-3 text-sm">
                <p className="mb-1 flex items-center gap-1.5 font-mono-face text-[10px] font-bold text-accent"><Sparkles size={11} /> 100 TIMES ASSISTANT</p>
                <p>{d.reply}</p>
                {d.notes.map((n) => <p key={n} className="mt-1 text-xs text-muted-foreground">{n}</p>)}
                {d.appliedFilters.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {d.appliedFilters.map((f) => <Badge key={f}>{f}</Badge>)}
                    {d.requestedCount && <Badge>up to {d.requestedCount}</Badge>}
                  </div>
                )}
              </div>
              <div className={cx('grid gap-3', !compact && 'md:grid-cols-2')}>
                {d.results.map((ev) => <AttendeeEventCard key={ev.ref} ev={ev} onOpen={open} />)}
              </div>
            </div>
          );
        })}
        {ask.isPending && <p className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 size={13} className="animate-spin text-accent" /> Searching the verified catalog…</p>}
        <div ref={bottom} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(draft); }} className="flex gap-2 border-t border-foreground/10 p-3">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. Find 5 fintech summits in the UK next month" className={cx(inputClass, 'py-2.5 text-sm')} data-testid="input-attendee-assistant" />
        <Btn type="submit" variant="primary" disabled={draft.trim().length < 2} loading={ask.isPending} data-testid="button-attendee-assistant-send"><Send size={14} /> Ask</Btn>
      </form>
      {drawer}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export function NotificationsPanel() {
  const q = useAttendeeNotifications();
  const prefs = useAttendeePreferences();
  const mark = useMarkNotificationRead();
  if (q.isLoading) return <LoadingState label="Loading notifications" />;
  if (q.isError || !q.data) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  return (
    <div className="space-y-4">
      {prefs.data && !prefs.data.notifyConsent && (
        <Notice tone="info">Event notifications are off. <Link href="/dashboard/preferences" className="font-semibold underline">Turn them on in Preferences</Link> to get reminders, deadline alerts, change notices and new matches.</Notice>
      )}
      {q.data.unread > 0 && <Btn size="sm" onClick={() => mark.mutate('all')} loading={mark.isPending}>Mark all as read</Btn>}
      {q.data.items.length ? q.data.items.map((n) => (
        <div key={n.id} className={cx('rounded-2xl border bg-card p-5', n.isRead ? 'border-foreground/10' : 'border-accent/40')}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex gap-3">
              <Bell size={17} className={cx('mt-0.5 shrink-0', n.isRead ? 'text-muted-foreground' : 'text-accent')} />
              <div>
                <p className="font-semibold">{n.title}</p>
                <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{n.message}</p>
                <p className="mt-2 font-mono-face text-[10px] uppercase tracking-[.12em] text-muted-foreground">
                  {fmtDay(n.createdAt)}{n.kind ? ` · ${n.kind.replace(/^attendee_/, '').replace(/_/g, ' ')}` : ''}{n.emailStatus === 'sent' ? ' · also emailed' : ''}
                </p>
              </div>
            </div>
            {!n.isRead && <Btn size="sm" variant="ghost" onClick={() => mark.mutate(n.id)}>Mark read</Btn>}
          </div>
        </div>
      )) : <EmptyState title="You are all caught up." />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Discover: search & filter every verified upcoming event
// ---------------------------------------------------------------------------

const EMPTY_FILTERS: EventSearchParams = { q: '', sector: '', country: '', mode: '', free: false, dateFrom: '', dateTo: '', sort: 'soonest' };

export function DiscoverPanel() {
  const optsQ = useAttendeeOptions();
  const [filters, setFilters] = useState<EventSearchParams>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const q = useDebounce(filters.q ?? '', 300);
  const search = useSearchEvents({ ...filters, q, page, pageSize: 24 });
  const { open, drawer } = useEventDrawer();
  const set = <K extends keyof EventSearchParams>(key: K, value: EventSearchParams[K]) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };
  const data = search.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1;
  const active = JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-foreground/10 bg-card p-5" data-testid="discover-filters">
        <input
          value={filters.q}
          onChange={(e) => set('q', e.target.value)}
          placeholder="Search events, topics, cities or organisers"
          className={cx(inputClass, 'py-3 text-sm')}
          aria-label="Search events"
          data-testid="input-discover-search"
        />
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <select value={filters.sector} onChange={(e) => set('sector', e.target.value)} className={inputClass} aria-label="Sector" data-testid="select-discover-sector">
            <option value="">All sectors</option>
            {(optsQ.data?.industries ?? []).filter((o) => o.count > 0).map((o) => <option key={o.value} value={o.value}>{o.value} ({o.count})</option>)}
          </select>
          <select value={filters.country} onChange={(e) => set('country', e.target.value)} className={inputClass} aria-label="Country" data-testid="select-discover-country">
            <option value="">All countries</option>
            {(optsQ.data?.countries ?? []).map((o) => <option key={o.value} value={o.value}>{o.value} ({o.count})</option>)}
          </select>
          <select value={filters.mode} onChange={(e) => set('mode', e.target.value as EventSearchParams['mode'])} className={inputClass} aria-label="Format">
            <option value="">Any format</option>
            <option value="offline">In person</option>
            <option value="online">Online</option>
            <option value="hybrid">Hybrid</option>
          </select>
          <select value={filters.sort} onChange={(e) => set('sort', e.target.value as EventSearchParams['sort'])} className={inputClass} aria-label="Sort">
            <option value="soonest">Soonest first</option>
            <option value="match">Best match for me</option>
          </select>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-2">From <input type="date" value={filters.dateFrom} onChange={(e) => set('dateFrom', e.target.value)} className={cx(inputClass, 'w-auto')} /></label>
          <label className="flex items-center gap-2">To <input type="date" value={filters.dateTo} onChange={(e) => set('dateTo', e.target.value)} className={cx(inputClass, 'w-auto')} /></label>
          <label className="flex items-center gap-2"><Switch checked={Boolean(filters.free)} onChange={(v) => set('free', v)} /> Free only</label>
          {active && <button type="button" onClick={() => { setFilters(EMPTY_FILTERS); setPage(1); }} className="font-semibold text-accent hover:underline">Clear filters</button>}
        </div>
      </div>

      {filters.sort === 'match' && data && !data.hasPreferences && <PreferencesCta />}
      {search.isError && <ErrorState error={search.error} retry={() => search.refetch()} />}
      {search.isLoading && <LoadingState label="Searching events" />}
      {data && (
        <>
          <p className="text-xs text-muted-foreground" data-testid="text-discover-count">
            {data.total} of {data.catalogSize} verified upcoming events{active ? ' match your filters' : ''}{search.isFetching ? ' · updating…' : ''}
          </p>
          <EventGrid
            events={data.results}
            onOpen={open}
            empty={<EmptyState title="No events match these filters." body="Try a wider date range, another country, or clear the filters." />}
          />
          {pages > 1 && (
            <div className="flex items-center justify-center gap-3 text-xs">
              <Btn type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Btn>
              <span>Page {page} of {pages}</span>
              <Btn type="button" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</Btn>
            </div>
          )}
        </>
      )}
      {drawer}
    </div>
  );
}

// ---------------------------------------------------------------------------
// My profile — personal details (attendee_profiles), separate from organisers
// ---------------------------------------------------------------------------

const EMPTY_PROFILE: AttendeeProfileInput = { name: '', phone: '', city: '', country: '', jobTitle: '', company: '', bio: '', linkedinUrl: '' };

function TextField({ label, value, onChange, testId, ...rest }: { label: string; value: string; onChange: (v: string) => void; testId: string } & Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'>) {
  return (
    <label className="block text-xs font-semibold text-muted-foreground">
      {label}
      <input value={value} onChange={(e) => onChange(e.target.value)} className={cx(inputClass, 'mt-1.5 py-2.5')} data-testid={testId} {...rest} />
    </label>
  );
}

export function ProfilePanel({ footer }: { footer?: ReactNode }) {
  const profileQ = useAttendeeProfile();
  const prefsQ = useAttendeePreferences();
  const optsQ = useAttendeeOptions();
  const dashQ = useAttendeeDashboard();
  const save = useSaveAttendeeProfile();
  const [form, setForm] = useState<AttendeeProfileInput>(EMPTY_PROFILE);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    const p = profileQ.data;
    if (p) {
      setForm({ name: p.name, phone: p.phone ?? '', city: p.city ?? '', country: p.country ?? '', jobTitle: p.jobTitle ?? '', company: p.company ?? '', bio: p.bio ?? '', linkedinUrl: p.linkedinUrl ?? '' });
    }
  }, [profileQ.data]);

  if (profileQ.isLoading) return <LoadingState label="Loading your profile" />;
  if (profileQ.isError || !profileQ.data) return <ErrorState error={profileQ.error} retry={() => profileQ.refetch()} />;
  const profile = profileQ.data;
  const prefs = prefsQ.data;
  const set = (key: keyof AttendeeProfileInput) => (v: string) => setForm((f) => ({ ...f, [key]: v }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const blankToNull = (v: string | null) => (v && v.trim() ? v.trim() : null);
    save.mutate(
      {
        name: form.name.trim(),
        phone: blankToNull(form.phone), city: blankToNull(form.city), country: blankToNull(form.country),
        jobTitle: blankToNull(form.jobTitle), company: blankToNull(form.company), bio: blankToNull(form.bio), linkedinUrl: blankToNull(form.linkedinUrl),
      },
      { onSuccess: () => setSavedAt(Date.now()) },
    );
  };

  const chips = (items: string[] | undefined, empty: string) =>
    items && items.length ? (
      <div className="mt-2 flex flex-wrap gap-1.5">{items.map((i) => <Badge key={i}>{i}</Badge>)}</div>
    ) : <p className="mt-1 text-xs text-muted-foreground">{empty}</p>;

  return (
    <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
      <form onSubmit={submit} className="space-y-4 rounded-2xl border border-foreground/10 bg-card p-6" data-testid="form-attendee-profile">
        <div>
          <h2 className="font-display text-2xl font-bold">Personal details</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Your attendee profile. Other attendees at the same events see your name, job title, company, country and bio in Networking — never your e-mail or phone.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="Full name" value={form.name} onChange={set('name')} required minLength={2} testId="input-profile-name" />
          <label className="block text-xs font-semibold text-muted-foreground">
            E-mail (sign-in)
            <input value={profile.email} disabled className={cx(inputClass, 'mt-1.5 py-2.5 opacity-70')} />
          </label>
          <TextField label="Phone" value={form.phone ?? ''} onChange={set('phone')} type="tel" placeholder="+91 98765 43210" testId="input-profile-phone" />
          <TextField label="City" value={form.city ?? ''} onChange={set('city')} testId="input-profile-city" />
          <label className="block text-xs font-semibold text-muted-foreground">
            Country
            <input list="profile-country-list" value={form.country ?? ''} onChange={(e) => set('country')(e.target.value)} className={cx(inputClass, 'mt-1.5 py-2.5')} data-testid="input-profile-country" />
            <datalist id="profile-country-list">{(optsQ.data?.allCountries ?? []).map((c) => <option key={c} value={c} />)}</datalist>
          </label>
          <TextField label="Job title" value={form.jobTitle ?? ''} onChange={set('jobTitle')} testId="input-profile-job-title" />
          <TextField label="Company" value={form.company ?? ''} onChange={set('company')} testId="input-profile-company" />
          <TextField label="LinkedIn" value={form.linkedinUrl ?? ''} onChange={set('linkedinUrl')} type="url" placeholder="https://www.linkedin.com/in/…" testId="input-profile-linkedin" />
        </div>
        <label className="block text-xs font-semibold text-muted-foreground">
          About you
          <textarea value={form.bio ?? ''} onChange={(e) => set('bio')(e.target.value)} maxLength={500} className={cx(inputClass, 'mt-1.5 min-h-24 py-2.5')} data-testid="input-profile-bio" />
        </label>
        {save.isError && <Notice tone="danger">{errorText(save.error)}</Notice>}
        <div className="flex items-center gap-3">
          <Btn type="submit" variant="primary" loading={save.isPending} data-testid="button-save-profile">Save profile</Btn>
          {savedAt && !save.isPending && !save.isError && <span className="text-xs text-emerald-600" data-testid="text-profile-saved">Saved.</span>}
        </div>
      </form>

      <div className="space-y-4">
        <div className="rounded-2xl border border-foreground/10 bg-card p-6">
          <div className="flex items-start justify-between gap-3">
            <h2 className="font-display text-xl font-bold">Interests</h2>
            <Link href="/dashboard/preferences" className="text-xs font-bold text-accent hover:underline">Edit →</Link>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Used to match and recommend events to you.</p>
          <p className="mt-4 text-xs font-bold">Topics</p>
          {chips(prefs?.interests, 'None yet.')}
          <p className="mt-3 text-xs font-bold">Preferred industries</p>
          {chips(prefs?.industries, 'None yet.')}
          <p className="mt-3 text-xs font-bold">Preferred countries</p>
          {chips(prefs?.countries, 'None yet.')}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Link href="/dashboard/saved-events" className="rounded-2xl border border-foreground/10 bg-card p-5 hover:border-accent/50">
            <Heart size={16} className="text-accent" />
            <p className="mt-3 font-display text-3xl font-bold">{dashQ.data?.counts.saved ?? '—'}</p>
            <p className="text-xs text-muted-foreground">Saved events</p>
          </Link>
          <Link href="/dashboard/registrations" className="rounded-2xl border border-foreground/10 bg-card p-5 hover:border-accent/50">
            <Ticket size={16} className="text-accent" />
            <p className="mt-3 font-display text-3xl font-bold">{dashQ.data?.counts.registered ?? '—'}</p>
            <p className="text-xs text-muted-foreground">Registrations</p>
          </Link>
        </div>
        <div className="rounded-2xl border border-foreground/10 bg-card p-6 text-xs text-muted-foreground">
          <p><span className="font-semibold text-foreground">Account type:</span> Attendee</p>
          {profile.memberSince && <p className="mt-1"><span className="font-semibold text-foreground">Member since:</span> {fmtDay(profile.memberSince)}</p>}
          <p className="mt-1"><span className="font-semibold text-foreground">E-mail verified:</span> {profile.emailVerified ? 'Yes' : 'Not yet'}</p>
        </div>
        {footer}
      </div>
    </div>
  );
}
