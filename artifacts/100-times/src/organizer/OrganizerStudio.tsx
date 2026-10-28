import { FormEvent, useEffect, useState } from 'react';
import { DeleteAccountModal } from '../components/AccountSecurityPages';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  customFetch,
  useGetNotifications,
  useGetOrganizerAnalytics,
  useGetOrganizerDashboard,
  useListCategories,
} from '@workspace/api-client-react';
import {
  Bell,
  CalendarDays,
  CalendarPlus,
  Check,
  CheckCircle2,
  Clock,
  ExternalLink,
  LineChart,
  Loader2,
  Plus,
  Send,
  Share2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Ticket,
  TrendingUp,
  UserCheck,
  Users,
  XCircle,
} from 'lucide-react';
import { Link, useLocation } from 'wouter';
import { EventPictureField } from './EventPictureField';

const ORGANIZER_LIFECYCLE_STAGES = [
  'DISCOVERY',
  'INVITED',
  'SIGNED_UP',
  'CREATED_EVENT',
  'SUBMITTED',
  'TRUST_CHECK',
  'APPROVED',
  'PUBLISHED',
  'REGISTRATIONS',
  'EVENT_COMPLETED',
  'FOLLOW_UP',
  'REPEAT_ORGANIZER',
];

interface OrganizerProfileData {
  userId: number;
  organizerId: number;
  organizerName: string;
  organizationName: string;
  slug: string;
  contactName: string;
  contactEmail: string;
  contactPhone: string;
  website: string;
  city: string;
  state: string;
  country: string;
  bio: string;
  socialLinks: Record<string, string>;
  emailVerified: boolean;
  identityVerified: boolean;
  lifecycleStage: string;
  lifecycleHistory: Array<{ stage: string; timestamp: string; actor: string; note: string }>;
}

interface RichEventRecord {
  id: number;
  title: string;
  slug: string;
  description: string;
  eventType: string;
  category: string;
  startDate: string;
  endDate: string;
  startTime: string;
  endTime: string;
  timezone: string;
  location: string;
  venue: string;
  fullAddress: string;
  cityName: string;
  stateName: string;
  countryName: string;
  format: string;
  onlineMeetingUrl: string;
  registrationUrl: string;
  isFree: boolean;
  /** Decimal from the API — may arrive as a string like "1500.00". */
  price: number | string | null;
  capacity: number | null;
  attendeeCount: number;
  status: string;
  lifecycleState: string;
  trustScore?: number | null;
  trustStatus?: string | null;
  trustConfidence?: string | null;
  shareUrl: string;
  calendarLinks?: {
    googleCalendarUrl: string;
    outlookCalendarUrl: string;
    icsContent: string;
  };
  trustReview?: {
    id: number;
    status: 'APPROVED' | 'NEEDS_REVIEW' | 'REJECTED' | 'DUPLICATE';
    score: number;
    confidence: 'HIGH' | 'MEDIUM' | 'LOW';
    reasons: string[];
    warnings: string[];
    missingFields: string[];
    recommendedAction: string;
    checksSummary: {
      information_complete?: boolean;
      organizer_verified?: boolean;
      no_duplicate_detected?: boolean;
      no_major_risk_detected?: boolean;
    };
  } | null;
}

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const errText = (e: unknown) => (e instanceof Error ? e.message : (e as { message?: string })?.message || 'Request failed');

/** Price from the API (number or decimal string) → display text. Never invents a value. */
function fmtPrice(isFree: boolean, price: number | string | null | undefined) {
  if (isFree) return 'Free Entry';
  const n = Number(price);
  if (price == null || price === '' || !Number.isFinite(n)) return 'Price not set';
  if (n === 0) return 'Free Entry';
  return `₹${n.toLocaleString('en-IN')}`;
}

export function OrganizerStudioPage({ initialTab = 'overview' }: { initialTab?: string }) {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>(initialTab);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  const dash = useGetOrganizerDashboard();
  const analytics = useGetOrganizerAnalytics();
  const notes = useGetNotifications();

  const profileQuery = useQuery({
    queryKey: ['organizer-profile'],
    queryFn: () => customFetch<OrganizerProfileData>('/api/organizer/profile'),
  });

  const eventsQuery = useQuery({
    queryKey: ['organizer-events-full'],
    queryFn: () => customFetch<RichEventRecord[]>('/api/organizer/events/full'),
  });

  const submitTrustMutation = useMutation({
    mutationFn: (eventId: number) =>
      customFetch<RichEventRecord>(`/api/organizer/events/${eventId}/submit-trust`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organizer-events-full'] });
      qc.invalidateQueries({ queryKey: ['organizer-profile'] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (eventId: number) =>
      customFetch(`/api/organizer/events/${eventId}/cancel`, {
        method: 'POST',
        body: JSON.stringify({ reason: 'Cancelled from Organizer Desk' }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['organizer-events-full'] }),
  });

  const profile = profileQuery.data;
  const eventsList = eventsQuery.data ?? [];

  const filteredEvents = eventsList.filter((ev) => {
    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'PUBLISHED') return ev.status === 'published' || ev.lifecycleState === 'PUBLISHED';
    if (statusFilter === 'DRAFT') return ev.lifecycleState === 'DRAFT';
    if (statusFilter === 'NEEDS_REVIEW') return ev.lifecycleState === 'NEEDS_REVIEW' || ev.trustStatus === 'NEEDS_REVIEW';
    if (statusFilter === 'REJECTED') return ev.lifecycleState === 'REJECTED' || ev.trustStatus === 'REJECTED';
    if (statusFilter === 'CANCELLED') return ev.lifecycleState === 'CANCELLED';
    return true;
  });

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'create', label: 'Create Event' },
    { id: 'events', label: `My Events (${eventsList.length})` },
    { id: 'registrations', label: 'Registrations' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'notifications', label: 'Notifications' },
    { id: 'profile', label: 'Organizer Profile' },
  ];

  const currentStageIdx = Math.max(
    0,
    ORGANIZER_LIFECYCLE_STAGES.indexOf(profile?.lifecycleStage || 'SIGNED_UP')
  );

  const token = typeof window !== 'undefined' ? localStorage.getItem('100-times-auth-token') : null;
  if (!token || profileQuery.isError) {
    return (
      <div className="page-enter mx-auto max-w-xl px-5 py-24 text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-accent/10 text-accent">
          <Sparkles size={30} />
        </div>
        <p className="mt-6 font-mono-face text-xs uppercase tracking-[.18em] text-accent">Organiser Studio</p>
        <h1 className="mt-3 font-display text-4xl sm:text-5xl font-extrabold tracking-[-.06em]">
          Create an account to list your event.
        </h1>
        <p className="mt-4 text-sm text-muted-foreground leading-relaxed">
          Create a verified organiser account to publish conferences, manage attendee registrations, issue digital passes, and reach thousands of attendees worldwide.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link
            href="/register?role=organiser&redirect=/organizer/events/create"
            className="button-press rounded-full bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground hover:bg-accent"
            data-testid="link-create-organizer-account"
          >
            Create Organiser Account
          </Link>
          <Link
            href="/login?role=organiser&redirect=/organizer"
            className="rounded-full border border-foreground/15 px-6 py-3.5 text-sm font-semibold hover:border-accent hover:text-accent"
            data-testid="link-organizer-login"
          >
            Sign In to Organiser Desk
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-10 lg:px-10 lg:py-14 space-y-8">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">
            Organizer Studio{profile?.organizationName ? ` · ${profile.organizationName}` : ''}
          </p>
          <h1 className="mt-2 font-display text-4xl font-extrabold tracking-tight sm:text-5xl">
            Make a room people remember.
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            End-to-end event creation, automated Trust Agent verification, attendee registration & lifecycle management.
          </p>
        </div>
        <button
          onClick={() => setActiveTab('create')}
          className="inline-flex items-center justify-center gap-2 rounded-full bg-accent px-5 py-3 text-sm font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
          data-testid="link-create-organizer-event"
        >
          <Plus size={17} /> Create Event
        </button>
      </div>

      {(submitTrustMutation.isError || cancelMutation.isError) && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs text-rose-400">
          {submitTrustMutation.isError && <p>Could not submit to Trust Agent: {errText(submitTrustMutation.error)}</p>}
          {cancelMutation.isError && <p>Could not cancel the event: {errText(cancelMutation.error)}</p>}
        </div>
      )}

      {/* Organizer Lifecycle Progress Bar */}
      <div className="rounded-2xl border border-foreground/10 bg-card p-4">
        <div className="flex items-center justify-between text-xs">
          <span className="font-mono-face uppercase tracking-wider text-accent">
            Automated Organizer Lifecycle
          </span>
          <span className="font-mono-face font-bold">
            Stage: {(profile?.lifecycleStage || 'SIGNED_UP').replace('_', ' ')}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {ORGANIZER_LIFECYCLE_STAGES.map((stage, idx) => {
            const done = idx <= currentStageIdx;
            return (
              <span
                key={stage}
                className={`rounded-full px-2.5 py-1 font-mono-face text-[10px] font-semibold ${
                  done ? 'bg-accent/20 text-accent border border-accent/40' : 'bg-muted text-muted-foreground'
                }`}
              >
                {done ? '✓ ' : ''}
                {stage.replace('_', ' ')}
              </span>
            );
          })}
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-foreground/10 pb-3">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`rounded-full px-4 py-2 text-xs font-bold transition ${
              activeTab === t.id
                ? 'bg-primary text-primary-foreground'
                : 'bg-card border border-foreground/10 text-muted-foreground hover:border-accent'
            }`}
            data-testid={`organizer-tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* KPI Metrics */}
      {activeTab === 'overview' && (
        <div className="space-y-8">
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="rounded-2xl border border-foreground/10 bg-card p-5">
              <CalendarDays size={18} className="text-accent" />
              <p className="mt-4 font-display text-3xl font-bold">{eventsList.length || dash.data?.totalEvents || 0}</p>
              <p className="text-xs text-muted-foreground">Total Events</p>
            </div>
            <div className="rounded-2xl border border-foreground/10 bg-card p-5">
              <Check size={18} className="text-accent" />
              <p className="mt-4 font-display text-3xl font-bold">
                {eventsList.filter((e) => e.status === 'published').length || dash.data?.publishedEvents || 0}
              </p>
              <p className="text-xs text-muted-foreground">Published Live</p>
            </div>
            <div className="rounded-2xl border border-foreground/10 bg-card p-5">
              <Users size={18} className="text-accent" />
              <p className="mt-4 font-display text-3xl font-bold">{isNum(dash.data?.registrations) ? dash.data.registrations : '—'}</p>
              <p className="text-xs text-muted-foreground">Total Registrations</p>
            </div>
            <div className="rounded-2xl border border-foreground/10 bg-card p-5">
              <TrendingUp size={18} className="text-accent" />
              <p className="mt-4 font-display text-3xl font-bold">{isNum(dash.data?.views) ? dash.data.views : '—'}</p>
              <p className="text-xs text-muted-foreground">Event Views</p>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-2xl font-bold">Recent Events & Trust Status</h2>
              <button onClick={() => setActiveTab('events')} className="text-xs font-bold text-accent hover:underline">
                View all events →
              </button>
            </div>
            {eventsList.slice(0, 5).map((ev) => (
              <EventStatusRow
                key={ev.id}
                event={ev}
                onSubmitTrust={() => submitTrustMutation.mutate(ev.id)}
                onCancel={() => cancelMutation.mutate(ev.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Multi-Step Create Event Flow */}
      {activeTab === 'create' && (
        <MultiStepEventWizard
          profile={profile}
          onCompleted={() => {
            qc.invalidateQueries({ queryKey: ['organizer-events-full'] });
            qc.invalidateQueries({ queryKey: ['organizer-profile'] });
          }}
        />
      )}

      {/* My Events Desk */}
      {activeTab === 'events' && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-2xl font-bold">My Events & Lifecycle Desk</h2>
            <div className="flex flex-wrap gap-2">
              {(['ALL', 'PUBLISHED', 'DRAFT', 'NEEDS_REVIEW', 'REJECTED', 'CANCELLED'] as const).map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`rounded-full px-3 py-1 font-mono-face text-xs font-semibold ${
                    statusFilter === st ? 'bg-accent text-accent-foreground' : 'bg-card border border-foreground/15 text-muted-foreground'
                  }`}
                >
                  {st.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
          {filteredEvents.length === 0 ? (
            <div className="rounded-2xl border border-foreground/10 bg-card p-10 text-center">
              <p className="font-display text-xl font-bold">No events in this status filter.</p>
              <button
                onClick={() => setActiveTab('create')}
                className="mt-4 rounded-full bg-accent px-5 py-2.5 text-xs font-bold text-accent-foreground"
              >
                + Create New Event
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredEvents.map((ev) => (
                <EventStatusRow
                  key={ev.id}
                  event={ev}
                  onSubmitTrust={() => submitTrustMutation.mutate(ev.id)}
                  onCancel={() => cancelMutation.mutate(ev.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Registrations Tab */}
      {activeTab === 'registrations' && (
        <div className="rounded-2xl border border-foreground/10 bg-card p-6 space-y-4">
          <h2 className="font-display text-2xl font-bold">Attendee Registrations & Capacity Tracking</h2>
          <p className="text-xs text-muted-foreground">
            Every registration automatically generates a unique ticket code (100T-XXXX), QR pass, .ics calendar invite, and schedules T-7d, T-24h, and T-1h reminders in the event&apos;s timezone.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {eventsList.map((ev) => (
              <div key={ev.id} className="rounded-xl border border-foreground/10 bg-background p-4 flex items-center justify-between">
                <div>
                  <p className="font-display text-base font-bold">{ev.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {ev.startDate} · {ev.timezone} · Capacity: {ev.attendeeCount} / {isNum(ev.capacity) ? ev.capacity : '—'}
                  </p>
                </div>
                <span className="rounded-full bg-accent/15 px-3 py-1 font-mono-face text-xs font-bold text-accent">
                  {ev.attendeeCount} Registered
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analytics Tab */}
      {activeTab === 'analytics' && (
        <div className="rounded-2xl border border-foreground/10 bg-card p-6 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-mono-face text-[10px] uppercase tracking-wider text-accent">Performance & Conversion</p>
              <h2 className="mt-1 font-display text-2xl font-bold">Event Views, Registrations & Attendance</h2>
            </div>
            <LineChart className="text-accent" />
          </div>
          {(dash.isError || analytics.isError) && (
            <p className="text-xs text-rose-400">
              Could not load {dash.isError ? 'dashboard metrics' : 'analytics'}: {errText(dash.isError ? dash.error : analytics.error)}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="rounded-xl border border-foreground/10 bg-background p-4">
              <p className="text-xs text-muted-foreground">Conversion Rate</p>
              <p className="mt-1 font-display text-2xl font-bold">
                {isNum(dash.data?.conversionRate) ? `${dash.data.conversionRate}%` : '—'}
              </p>
            </div>
            <div className="rounded-xl border border-foreground/10 bg-background p-4">
              <p className="text-xs text-muted-foreground">Event Views</p>
              <p className="mt-1 font-display text-2xl font-bold">{isNum(dash.data?.views) ? dash.data.views : '—'}</p>
            </div>
            <div className="rounded-xl border border-foreground/10 bg-background p-4">
              <p className="text-xs text-muted-foreground">Total Registrations</p>
              <p className="mt-1 font-display text-2xl font-bold">
                {isNum(dash.data?.registrations) ? dash.data.registrations : '—'}
              </p>
            </div>
            <div className="rounded-xl border border-foreground/10 bg-background p-4">
              <p className="text-xs text-muted-foreground">Attendance Rate</p>
              <p className="mt-1 text-sm font-semibold text-muted-foreground">Not available yet</p>
            </div>
          </div>
          {(() => {
            const series = (Array.isArray(analytics.data?.views) ? analytics.data.views : []).filter(isNum);
            const max = Math.max(0, ...series);
            if (!series.length || max === 0) {
              return (
                <div className="rounded-xl border border-dashed border-foreground/15 p-8 text-center text-xs text-muted-foreground">
                  No view data recorded yet.
                </div>
              );
            }
            return (
              <div className="flex h-44 items-end gap-2 border-b border-foreground/10 pt-6">
                {series.map((v, i) => (
                  <div
                    key={i}
                    title={`${v} views`}
                    className="flex-1 rounded-t-md bg-accent/80 hover:bg-accent transition-all"
                    style={{ height: `${Math.max(2, (v / max) * 100)}%` }}
                  />
                ))}
              </div>
            );
          })()}
        </div>
      )}

      {/* Notifications Tab */}
      {activeTab === 'notifications' && (
        <div className="space-y-3">
          <h2 className="font-display text-2xl font-bold">Organizer Notifications</h2>
          {(notes.data ?? []).map((n) => (
            <div key={n.id} className="rounded-2xl border border-foreground/10 bg-card p-4 flex items-start gap-3">
              <Bell size={16} className="mt-1 text-accent" />
              <div>
                <p className="font-semibold text-sm">{n.title}</p>
                <p className="mt-1 text-xs text-muted-foreground whitespace-pre-line">{n.message}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Organizer Profile & Onboarding Tab */}
      {activeTab === 'profile' && <OrganizerProfileForm profile={profile} />}
    </div>
  );
}

function EventStatusRow({
  event,
  onSubmitTrust,
  onCancel,
}: {
  event: RichEventRecord;
  onSubmitTrust: () => void;
  onCancel: () => void;
}) {
  const state = event.lifecycleState || event.status.toUpperCase();
  const badgeColor =
    state === 'PUBLISHED' || event.status === 'published'
      ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
      : state === 'NEEDS_REVIEW'
      ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
      : state === 'REJECTED' || state === 'CANCELLED'
      ? 'bg-rose-500/15 text-rose-400 border-rose-500/30'
      : 'bg-muted text-muted-foreground border-foreground/15';

  return (
    <div
      className="rounded-2xl border border-foreground/10 bg-card p-5 space-y-3"
      data-testid={`row-organizer-event-${event.id}`}
    >
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full border px-2.5 py-0.5 font-mono-face text-[10px] font-bold uppercase ${badgeColor}`}>
              {state}
            </span>
            {event.trustScore != null && (
              <span className="rounded-full bg-muted px-2.5 py-0.5 font-mono-face text-[10px] font-semibold">
                Trust Score: {event.trustScore}/100{event.trustConfidence ? ` (${event.trustConfidence})` : ''}
              </span>
            )}
            <span className="font-mono-face text-xs text-muted-foreground">
              {event.startDate} · {event.startTime} ({event.timezone})
            </span>
          </div>
          <Link href={`/events/${event.slug}`} className="mt-1.5 block font-display text-xl font-bold hover:text-accent">
            {event.title}
          </Link>
          <p className="text-xs text-muted-foreground">
            {event.cityName || event.location || '—'} · {fmtPrice(event.isFree, event.price)} · {event.attendeeCount} /{' '}
            {isNum(event.capacity) ? event.capacity : '—'} registered
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {state === 'DRAFT' && (
            <button
              onClick={onSubmitTrust}
              className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-xs font-bold text-accent-foreground"
            >
              <ShieldCheck size={14} /> Submit to Trust Agent
            </button>
          )}
          {event.status === 'published' && (
            <>
              <Link
                href={`/events/${event.slug}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-foreground/15 px-3 py-1.5 text-xs font-semibold hover:border-accent"
              >
                <ExternalLink size={13} /> Public Page
              </Link>
              {event.calendarLinks?.googleCalendarUrl && (
                <a
                  href={event.calendarLinks.googleCalendarUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-full border border-foreground/15 px-3 py-1.5 text-xs font-semibold hover:border-accent"
                >
                  <CalendarPlus size={13} /> Add Calendar
                </a>
              )}
            </>
          )}
          {state !== 'CANCELLED' && (
            <button
              onClick={() => {
                if (window.confirm(`Cancel "${event.title}"? Registered attendees will be affected and this cannot be undone.`)) {
                  onCancel();
                }
              }}
              className="inline-flex items-center gap-1 rounded-full border border-rose-500/30 px-3 py-1.5 text-xs text-rose-400 hover:bg-rose-500/10"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {state === 'NEEDS_REVIEW' && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          <strong>Your event is under review.</strong> Our moderation team is reviewing the listing. Your submission is saved—you do not need to submit everything again.
        </div>
      )}
    </div>
  );
}

function MultiStepEventWizard({
  profile,
  onCompleted,
}: {
  profile?: OrganizerProfileData;
  onCompleted: () => void;
}) {
  const [step, setStep] = useState<number>(1);
  const [createdEvent, setCreatedEvent] = useState<RichEventRecord | null>(null);
  const [error, setError] = useState<string>('');

  // Every field starts empty (or from the organizer's real profile) — nothing is pre-filled
  // with sample content, and nothing the form doesn't show is sent with invented values.
  const [form, setForm] = useState({
    title: '',
    description: '',
    organizerName: profile?.organizerName ?? '',
    organizationName: profile?.organizationName ?? '',
    category: '',
    eventType: '',
    startDate: '',
    endDate: '',
    startTime: '',
    endTime: '',
    timezone: 'Asia/Kolkata',
    fullAddress: '',
    city: '',
    state: '',
    country: '',
    format: 'in-person' as 'in-person' | 'online' | 'hybrid',
    onlineMeetingUrl: '',
    price: '',
    capacity: '',
    targetAudience: '',
    image: '', // uploaded or ready-made picture URL; '' = none
  });

  // The profile may load after the wizard mounts — fill organizer fields the user hasn't typed into.
  useEffect(() => {
    if (!profile) return;
    setForm((f) => ({
      ...f,
      organizerName: f.organizerName || profile.organizerName || '',
      organizationName: f.organizationName || profile.organizationName || '',
    }));
  }, [profile]);

  const categoriesQuery = useListCategories();
  const categories = categoriesQuery.data ?? [];

  const buildPayload = (saveAsDraft: boolean) => {
    const priceText = form.price.trim();
    const priceNum = priceText === '' ? 0 : Number(priceText);
    const isFree = !(priceNum > 0);
    const capacityText = form.capacity.trim();
    const contactInfo: Record<string, string> = {};
    if (profile?.contactEmail) contactInfo.email = profile.contactEmail;
    if (profile?.contactPhone) contactInfo.phone = profile.contactPhone;
    return {
      title: form.title.trim(),
      description: form.description.trim(),
      organizerName: form.organizerName.trim() || null,
      organizationName: form.organizationName.trim() || null,
      category: form.category,
      eventType: form.eventType.trim(),
      startDate: form.startDate,
      endDate: form.endDate || form.startDate,
      startTime: form.startTime,
      // Explicit nulls so the API doesn't substitute its own defaults for fields left blank.
      endTime: form.endTime || null,
      timezone: form.timezone,
      venueName: null,
      fullAddress: form.fullAddress.trim() || null,
      city: form.city.trim(),
      state: form.state.trim() || null,
      country: form.country.trim(),
      format: form.format,
      onlineMeetingUrl: form.format !== 'in-person' && form.onlineMeetingUrl.trim() ? form.onlineMeetingUrl.trim() : null,
      registrationUrl: null,
      isFree,
      price: isFree ? 0 : priceNum,
      capacity: capacityText === '' ? null : Number(capacityText),
      ticketInfo: {},
      speakerInfo: [],
      contactInfo,
      socialLinks: profile?.website ? { website: profile.website } : {},
      termsPolicy: null,
      tags: [],
      targetAudience: form.targetAudience.trim() || null,
      image: form.image || null,
      saveAsDraft,
    };
  };

  const createMutation = useMutation({
    mutationFn: (saveAsDraft: boolean) =>
      customFetch<RichEventRecord>('/api/organizer/events/full', {
        method: 'POST',
        body: JSON.stringify(buildPayload(saveAsDraft)),
      }),
    onSuccess: (res) => {
      setCreatedEvent(res);
      setStep(6);
      onCompleted();
    },
    onError: (err: unknown) => {
      setError((err as { message?: string })?.message || 'Could not submit event. Please verify required fields.');
    },
  });

  // "Save as Draft" bypasses native form validation, so check what the API requires.
  const validateMinimum = () => {
    if (form.title.trim().length < 3) return 'Add an event title (at least 3 characters).';
    if (form.description.trim().length < 10) return 'Add a description (at least 10 characters).';
    if (!form.category) return 'Choose a sector.';
    if (!form.startDate) return 'Choose a start date.';
    const price = form.price.trim();
    if (price !== '' && !(Number(price) >= 0)) return 'Price must be a number (leave blank or 0 for a free event).';
    const cap = form.capacity.trim();
    if (cap !== '' && !(Number.isInteger(Number(cap)) && Number(cap) >= 1)) return 'Capacity must be a whole number of at least 1, or left blank.';
    return '';
  };

  const stepLabels = [
    '1. Basic Details',
    '2. Date & Location',
    '3. Tickets & Capacity',
    '4. Speakers & Policy',
    '5. Review & Submit',
    '6. Trust Check & Publish',
  ];

  const handleDirectSubmit = (e: FormEvent) => {
    e.preventDefault();
    const problem = validateMinimum();
    setError(problem);
    if (!problem) createMutation.mutate(false);
  };

  return (
    <div className="rounded-3xl border border-foreground/10 bg-card p-6 sm:p-8 space-y-6">
      <div className="flex flex-wrap gap-2 border-b border-foreground/10 pb-4">
        {stepLabels.map((lbl, i) => {
          const s = i + 1;
          return (
            <button
              key={lbl}
              type="button"
              onClick={() => s < 6 && setStep(s)}
              className={`rounded-full px-3.5 py-1.5 font-mono-face text-xs font-bold ${
                step === s ? 'bg-accent text-accent-foreground' : 'bg-muted text-muted-foreground'
              }`}
            >
              {lbl}
            </button>
          );
        })}
      </div>

      {step < 6 ? (
        <form onSubmit={handleDirectSubmit} className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="block text-xs font-semibold text-muted-foreground">
                Event Name / Title *
                <input
                  required
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="e.g. Global AI & Distributed Systems Summit 2026"
                  className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm outline-none focus:border-accent"
                  data-testid="input-event-title"
                />
              </label>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs font-semibold text-muted-foreground">
                Event Description * (min 25 chars for Trust Agent completeness)
                <textarea
                  required
                  minLength={10}
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Describe the agenda, key takeaways, speaker lineup, and who should attend..."
                  className="mt-1.5 min-h-28 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm outline-none focus:border-accent"
                  data-testid="input-event-description"
                />
              </label>
            </div>

            <label className="block text-xs font-semibold text-muted-foreground">
              Organizer Name
              <input
                value={form.organizerName}
                onChange={(e) => setForm({ ...form, organizerName: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              Organization / Company
              <input
                value={form.organizationName}
                onChange={(e) => setForm({ ...form, organizationName: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
              />
            </label>

            <label className="block text-xs font-semibold text-muted-foreground">
              Event Type *
              <input
                required
                value={form.eventType}
                onChange={(e) => setForm({ ...form, eventType: e.target.value })}
                placeholder="e.g. Conference, Exhibition, Workshop"
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-type"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              Sector *
              <select
                required
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="select-event-category"
              >
                <option value="">
                  {categoriesQuery.isLoading ? 'Loading sectors…' : categoriesQuery.isError ? 'Could not load sectors' : 'Select a sector'}
                </option>
                {categories.map((c) => (
                  <option key={c.slug} value={c.slug}>{c.name}</option>
                ))}
              </select>
            </label>

            <div className="sm:col-span-2">
              <EventPictureField
                sectorSlug={form.category}
                sectorName={categories.find((c) => c.slug === form.category)?.name}
                value={form.image}
                onChange={(image) => setForm((f) => ({ ...f, image }))}
              />
            </div>

            <label className="block text-xs font-semibold text-muted-foreground">
              Start Date *
              <input
                required
                type="date"
                value={form.startDate}
                onChange={(e) => setForm({ ...form, startDate: e.target.value, endDate: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-start-date"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              End Date *
              <input
                required
                type="date"
                value={form.endDate}
                onChange={(e) => setForm({ ...form, endDate: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-end-date"
              />
            </label>

            <label className="block text-xs font-semibold text-muted-foreground">
              Start Time *
              <input
                required
                type="time"
                value={form.startTime}
                onChange={(e) => setForm({ ...form, startTime: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-start-time"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              End Time
              <input
                type="time"
                value={form.endTime}
                onChange={(e) => setForm({ ...form, endTime: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-end-time"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              Timezone (IANA) *
              <select
                value={form.timezone}
                onChange={(e) => setForm({ ...form, timezone: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
              >
                <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                <option value="UTC">UTC</option>
                <option value="America/New_York">America/New_York (EST/EDT)</option>
                <option value="Europe/London">Europe/London (GMT/BST)</option>
                <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
              </select>
            </label>

            <label className="block text-xs font-semibold text-muted-foreground">
              City / Location *
              <input
                required
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-location"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              State / Region
              <input
                value={form.state}
                onChange={(e) => setForm({ ...form, state: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-state"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              Country *
              <input
                required
                value={form.country}
                onChange={(e) => setForm({ ...form, country: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-country"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              Venue & Full Address
              <input
                value={form.fullAddress}
                onChange={(e) => setForm({ ...form, fullAddress: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
              />
            </label>

            <label className="block text-xs font-semibold text-muted-foreground">
              Format
              <select
                value={form.format}
                onChange={(e) => setForm({ ...form, format: e.target.value as 'in-person' | 'online' | 'hybrid' })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="select-event-format"
              >
                <option value="in-person">In-Person / Offline</option>
                <option value="online">Online</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </label>
            {form.format !== 'in-person' && (
              <label className="block text-xs font-semibold text-muted-foreground">
                Online Meeting URL
                <input
                  type="url"
                  value={form.onlineMeetingUrl}
                  onChange={(e) => setForm({ ...form, onlineMeetingUrl: e.target.value })}
                  placeholder="https://"
                  className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                  data-testid="input-event-meeting-url"
                />
              </label>
            )}
            <label className="block text-xs font-semibold text-muted-foreground">
              Price (INR)
              <input
                type="number"
                min={0}
                value={form.price}
                onChange={(e) => setForm({ ...form, price: e.target.value })}
                placeholder="Leave blank or 0 for a free event"
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
                data-testid="input-event-price"
              />
            </label>

            <label className="block text-xs font-semibold text-muted-foreground">
              Capacity
              <input
                type="number"
                min={1}
                step={1}
                value={form.capacity}
                onChange={(e) => setForm({ ...form, capacity: e.target.value })}
                placeholder="Leave blank if unlimited / not set"
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
              />
            </label>
            <label className="block text-xs font-semibold text-muted-foreground">
              Target Audience
              <input
                value={form.targetAudience}
                onChange={(e) => setForm({ ...form, targetAudience: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3.5 py-2.5 text-sm"
              />
            </label>
          </div>

          {error && <p className="text-sm text-rose-400" data-testid="status-create-event-error">{error}</p>}

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <button
              type="button"
              disabled={createMutation.isPending}
              onClick={() => {
                const problem = validateMinimum();
                setError(problem);
                if (!problem) createMutation.mutate(true);
              }}
              className="rounded-full border border-foreground/20 px-5 py-3 text-xs font-bold hover:border-accent"
              data-testid="button-save-draft"
            >
              Save as Draft
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-bold text-primary-foreground hover:bg-accent"
              data-testid="button-create-event"
            >
              {createMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              Validate with Trust Agent & Publish
            </button>
          </div>
        </form>
      ) : (
        createdEvent && (
          <div className="space-y-6" data-testid="trust-check-result-panel">
            <div className="rounded-2xl border border-foreground/10 bg-background p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-mono-face text-xs uppercase text-accent">Trust Agent Verification</p>
                  <h3 className="mt-1 font-display text-2xl font-bold">
                    {createdEvent.lifecycleState === 'PUBLISHED'
                      ? 'Event published successfully.'
                      : createdEvent.lifecycleState === 'DRAFT'
                      ? 'Event saved as draft.'
                      : 'Your event is under review.'}
                  </h3>
                </div>
                {createdEvent.trustReview && (
                  <span className="rounded-full bg-accent/20 px-4 py-1.5 font-mono-face text-xs font-bold text-accent">
                    Score: {createdEvent.trustReview.score}/100 ({createdEvent.trustReview.confidence})
                  </span>
                )}
              </div>

              {createdEvent.trustReview && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="flex items-center gap-2 text-xs">
                    <CheckCircle2 size={15} className="text-emerald-400" />
                    <span>
                      {createdEvent.trustReview.checksSummary?.information_complete
                        ? '✓ Event information complete'
                        : '⚠ Missing optional details'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <CheckCircle2 size={15} className="text-emerald-400" />
                    <span>
                      {createdEvent.trustReview.checksSummary?.organizer_verified
                        ? '✓ Organizer verified'
                        : '⚠ Organizer verification pending'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <CheckCircle2 size={15} className="text-emerald-400" />
                    <span>
                      {createdEvent.trustReview.checksSummary?.no_duplicate_detected
                        ? '✓ No duplicate detected'
                        : '⚠ Similar listing detected'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <CheckCircle2 size={15} className="text-emerald-400" />
                    <span>
                      {createdEvent.trustReview.checksSummary?.no_major_risk_detected
                        ? '✓ No major risk detected'
                        : '⚠ Flagged for manual moderation'}
                    </span>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3 pt-3">
                <Link
                  href={`/events/${createdEvent.slug}`}
                  className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-xs font-bold text-accent-foreground"
                >
                  <ExternalLink size={14} /> Open Public Event Page ({createdEvent.slug})
                </Link>
                {createdEvent.calendarLinks?.googleCalendarUrl && (
                  <a
                    href={createdEvent.calendarLinks.googleCalendarUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-full border border-foreground/15 px-4 py-2.5 text-xs font-semibold hover:border-accent"
                  >
                    <CalendarPlus size={14} /> Add to Google Calendar
                  </a>
                )}
                <button
                  onClick={() => {
                    setCreatedEvent(null);
                    setStep(1);
                  }}
                  className="rounded-full border border-foreground/15 px-4 py-2.5 text-xs font-semibold"
                >
                  Create Another Event
                </button>
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}

function OrganizerProfileForm({ profile }: { profile?: OrganizerProfileData }) {
  const qc = useQueryClient();
  const [, setLocation] = useLocation();
  const [saved, setSaved] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [dirty, setDirty] = useState(false);
  const fromProfile = (pr?: OrganizerProfileData) => ({
    organizerName: pr?.organizerName ?? '',
    organizationName: pr?.organizationName ?? '',
    contactEmail: pr?.contactEmail ?? '',
    contactPhone: pr?.contactPhone ?? '',
    website: pr?.website ?? '',
    city: pr?.city ?? '',
    state: pr?.state ?? '',
    country: pr?.country ?? '',
    bio: pr?.bio ?? '',
  });
  const [form, setFormState] = useState(() => fromProfile(profile));
  const setForm = (next: ReturnType<typeof fromProfile>) => {
    setDirty(true);
    setFormState(next);
  };

  // The profile usually arrives after first render — keep the form in sync with it until the user edits.
  useEffect(() => {
    if (profile && !dirty) setFormState(fromProfile(profile));
  }, [profile, dirty]);

  const onboardingMutation = useMutation({
    mutationFn: () =>
      customFetch('/api/organizer/onboarding', {
        method: 'POST',
        // Only what this form edits. socialLinks is passed through unchanged from the saved
        // profile because the onboarding endpoint would otherwise reset it to empty.
        body: JSON.stringify({
          organizerName: form.organizerName.trim(),
          organizationName: form.organizationName.trim(),
          contactEmail: form.contactEmail.trim(),
          contactPhone: form.contactPhone.trim() || null,
          website: form.website.trim() || null,
          city: form.city.trim() || null,
          state: form.state.trim() || null,
          country: form.country.trim() || null,
          bio: form.bio.trim() || null,
          socialLinks: profile?.socialLinks ?? {},
        }),
      }),
    onSuccess: () => {
      setSaved(true);
      setDirty(false);
      qc.invalidateQueries({ queryKey: ['organizer-profile'] });
      window.setTimeout(() => setSaved(false), 2500);
    },
  });

  const signOut = async () => {
    setSigningOut(true);
    try {
      await customFetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // Still clear the local session below even if the server call fails.
    } finally {
      localStorage.removeItem('100-times-auth-token');
      window.dispatchEvent(new Event('auth-change'));
      qc.clear();
      setLocation('/login');
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    onboardingMutation.mutate();
  };

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl rounded-2xl border border-foreground/10 bg-card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold">Organizer Profile & Organization Verification</h2>
          <p className="text-xs text-muted-foreground">
            Verified organizer profiles receive higher Trust Agent confidence scores for instant event publishing.
          </p>
        </div>
        <UserCheck className="text-accent" size={24} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-xs font-semibold text-muted-foreground">
          Organizer Name *
          <input
            required
            value={form.organizerName}
            onChange={(e) => setForm({ ...form, organizerName: e.target.value })}
            className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
        <label className="block text-xs font-semibold text-muted-foreground">
          Organization / Company Name *
          <input
            required
            value={form.organizationName}
            onChange={(e) => setForm({ ...form, organizationName: e.target.value })}
            className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
        <label className="block text-xs font-semibold text-muted-foreground">
          Official Contact Email *
          <input
            required
            type="email"
            value={form.contactEmail}
            onChange={(e) => setForm({ ...form, contactEmail: e.target.value })}
            className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
        <label className="block text-xs font-semibold text-muted-foreground">
          Contact Phone
          <input
            value={form.contactPhone}
            onChange={(e) => setForm({ ...form, contactPhone: e.target.value })}
            className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
        <label className="block text-xs font-semibold text-muted-foreground">
          Organization Website
          <input
            value={form.website}
            onChange={(e) => setForm({ ...form, website: e.target.value })}
            className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
        <label className="block text-xs font-semibold text-muted-foreground">
          Headquarters City
          <input
            value={form.city}
            onChange={(e) => setForm({ ...form, city: e.target.value })}
            className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
        <label className="block text-xs font-semibold text-muted-foreground">
          State / Region
          <input
            value={form.state}
            onChange={(e) => setForm({ ...form, state: e.target.value })}
            className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
        <label className="block text-xs font-semibold text-muted-foreground">
          Country
          <input
            value={form.country}
            onChange={(e) => setForm({ ...form, country: e.target.value })}
            className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
        <label className="block text-xs font-semibold text-muted-foreground sm:col-span-2">
          About the organization
          <textarea
            value={form.bio}
            onChange={(e) => setForm({ ...form, bio: e.target.value })}
            className="mt-1.5 min-h-20 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
          />
        </label>
      </div>

      {onboardingMutation.isError && (
        <p className="text-xs text-rose-400">Could not save the profile: {errText(onboardingMutation.error)}</p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
        <button
          type="submit"
          disabled={onboardingMutation.isPending}
          className="rounded-full bg-primary px-5 py-2.5 text-xs font-bold text-primary-foreground hover:bg-accent"
        >
          {onboardingMutation.isPending ? 'Saving…' : saved ? '✓ Organizer Profile Verified & Saved' : 'Save & Verify Organizer Profile'}
        </button>
        <button
          type="button"
          onClick={signOut}
          disabled={signingOut}
          className="rounded-full border border-destructive/30 px-4 py-2 text-xs font-semibold text-destructive hover:bg-destructive/10 disabled:opacity-50"
        >
          {signingOut ? 'Signing out…' : 'Sign out of organizer account'}
        </button>
        <button
          type="button"
          onClick={() => setShowDeleteModal(true)}
          className="rounded-full border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-xs font-bold text-rose-500 hover:bg-rose-500 hover:text-white"
        >
          Delete Account
        </button>
      </div>
      <DeleteAccountModal isOpen={showDeleteModal} onClose={() => setShowDeleteModal(false)} />
    </form>
  );
}
