import { type FormEvent, type ReactNode, useMemo, useState, useEffect, useRef } from 'react';
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle, ArrowDownRight, ArrowLeft, ArrowRight, Bell, CalendarDays, CalendarPlus, Check, ChevronDown,
  Compass, Download, ExternalLink, Filter, Globe, Heart, LayoutDashboard,
  LineChart, ListFilter, Loader2, LockKeyhole, LogOut, MapPin, Menu, MessageSquare, Plus, Printer,
  QrCode, Search, Send, Settings2, ShieldCheck, Sparkles, Star, Ticket, Trash2,
  TrendingUp, UserCheck, UserPlus, UserRound, Users, X, Zap,
} from 'lucide-react';
import {
  getGetCategoryQueryKey, getGetCityQueryKey, getGetDashboardQueryKey,
  getGetEventQueryKey, getGetOrganizerQueryKey, getGetRegistrationsQueryKey, getGetSavedEventsQueryKey,
  getGetSpeakerQueryKey, getGetVenueQueryKey, getListEventsQueryKey,
  useCreateReview, useGetAdminDashboard, useGetCategory,
  useGetCity, useGetDashboard, useGetEvent, useGetHome, useGetNotifications,
  useGetOrganizer, useGetSavedEvents, useGetRegistrations, useGetSpeaker,
  useGetVenue, useHealthCheck, useListCategories, useListCities, useListEvents,
  useListOrganizers, useListVenues, useLogin, useRegisterForEvent, useRegisterUser,
  useSaveEvent, useUnsaveEvent, customFetch,
} from '@workspace/api-client-react';
import type {
  Category, City, DirectoryDetail, EventCard, EventDetail,
  ListEventsParams, Organizer, OrganizerDetail, RegistrationInput, ReviewInput,
  Venue, VenueDetail,
} from '@workspace/api-client-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Link, Redirect, Route, Switch, Router as WouterRouter, useLocation, useParams } from 'wouter';
import { ErrorBoundary } from '@/components/error-boundary';
import { CountrySelect } from '@/components/CountrySelect';
import { OpsLayout } from '@/ops/OpsLayout';
import { DashboardPage as OpsDashboardPage } from '@/ops/DashboardPage';
import { DiscoveryPage } from '@/ops/DiscoveryPage';
import { OrganizersPage } from '@/ops/OrganizersPage';
import { OrganizerProfilePage } from '@/ops/OrganizerProfilePage';
import { ContactsPage } from '@/ops/ContactsPage';
import { OutreachPage } from '@/ops/OutreachPage';
import { ActivityPage } from '@/ops/ActivityPage';
import { RunWizardPage } from '@/ops/RunWizardPage';
import { RunReportPage } from '@/ops/RunReportPage';
import { DiscoveryConfigPage } from '@/ops/DiscoveryConfigPage';
import { AutomaticDiscoveryPage } from '@/ops/AutomaticDiscoveryPage';
import { SettingsPage } from '@/ops/SettingsPage';
import { TrustReviewPage } from '@/ops/TrustReviewPage';
import { AutomationsPage } from '@/ops/AutomationsPage';
import { SocialPromotionsPage } from '@/ops/SocialPromotionsPage';
import { WorkflowsLogsPage } from '@/ops/WorkflowsLogsPage';
import { OrganizerStudioPage } from '@/organizer/OrganizerStudio';
import { ObservabilityPage } from '@/ops/ObservabilityPage';
import {
  PrivacyPolicyPage,
  TermsOfServicePage,
  VerifyEmailPage,
  ResetPasswordPage,
  DeleteAccountModal,
  EmailVerificationBanner,
} from '@/components/AccountSecurityPages';
import { keys, useMe, type Me } from '@/ops/api';
import { type AccountType, accountTypeOf, canOpenPath, homePathFor, useAccount } from '@/lib/account';
import {
  AssistantPanel, AttendeeOverview, DiscoverPanel, ExternalRegistrationsPanel, MatchesPanel, NotificationsPanel,
  PreferencesPanel, ProfilePanel, SavedEventsPanel,
} from '@/attendee/pages';
import { useAttendeeProfile } from '@/attendee/api';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import '@/index.css';

const queryClient = new QueryClient();

// ---------------------------------------------------------------------------
// Attendee Types & React Query Hooks
// ---------------------------------------------------------------------------

export interface RegistrationPass {
  id: number;
  eventId: number;
  eventTitle: string;
  eventSlug: string;
  ticketType: string;
  registeredAt: string;
  status: string;
  userName?: string;
  company?: string | null;
  jobTitle?: string | null;
  ticketCode?: string;
  qrCode?: string;
  eventLocation?: string;
  eventVenue?: string;
  eventStartDate?: string;
  eventEndDate?: string;
  eventStartTime?: string;
}

export interface AttendeeProfile {
  id: number;
  name: string;
  jobTitle?: string | null;
  company?: string | null;
  bio?: string | null;
  country?: string | null;
  role: string;
  registeredEventCount: number;
  connectionStatus: 'none' | 'pending_sent' | 'pending_received' | 'connected';
  connectionId?: number | null;
}

export interface Connection {
  id: number;
  requesterId: number;
  addresseeId: number;
  status: 'pending' | 'accepted' | 'declined';
  createdAt: string;
  peerId: number;
  peerName: string;
  peerCompany?: string | null;
  peerJobTitle?: string | null;
  peerBio?: string | null;
  isRequester: boolean;
}

export interface Message {
  id: number;
  senderId: number;
  senderName: string;
  recipientId: number;
  content: string;
  isRead: boolean;
  createdAt: string;
}

export interface ScheduleItem {
  id: number;
  eventId: number;
  eventTitle: string;
  eventSlug: string;
  eventDate: string;
  sessionTitle: string;
  sessionTime: string;
  sessionDetail?: string | null;
  createdAt: string;
}


export interface UserOut {
  id: number;
  name: string;
  email: string;
  role: 'USER' | 'ORGANIZER' | 'ADMIN';
  createdAt?: string;
}


function useListAttendees(params?: { q?: string; eventId?: number }) {
  const q = params?.q ? `q=${encodeURIComponent(params.q)}` : '';
  const eid = params?.eventId ? `eventId=${params.eventId}` : '';
  const qs = [q, eid].filter(Boolean).join('&');
  return useQuery({
    queryKey: ['attendees', params?.q, params?.eventId],
    queryFn: () => customFetch<AttendeeProfile[]>(`/api/connections/attendees${qs ? `?${qs}` : ''}`),
  });
}

function useListConnections() {
  return useQuery({
    queryKey: ['connections'],
    queryFn: () => customFetch<Connection[]>('/api/connections'),
  });
}

function useRequestConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (addresseeId: number) =>
      customFetch<Connection>('/api/connections', {
        method: 'POST',
        body: JSON.stringify({ addresseeId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendees'] });
      qc.invalidateQueries({ queryKey: ['connections'] });
    },
  });
}

function useUpdateConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'accepted' | 'declined' }) =>
      customFetch<Connection>(`/api/connections/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendees'] });
      qc.invalidateQueries({ queryKey: ['connections'] });
    },
  });
}

function useGetMessages(peerId: number | null) {
  return useQuery({
    queryKey: ['messages', peerId],
    queryFn: () => (peerId ? customFetch<Message[]>(`/api/connections/messages/${peerId}`) : Promise.resolve([])),
    enabled: Boolean(peerId),
    refetchInterval: 3000,
  });
}

function useSendMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ recipientId, content }: { recipientId: number; content: string }) =>
      customFetch<Message>('/api/connections/messages', {
        method: 'POST',
        body: JSON.stringify({ recipientId, content }),
      }),
    onSuccess: (msg: Message) => {
      qc.invalidateQueries({ queryKey: ['messages', msg.recipientId] });
      qc.invalidateQueries({ queryKey: ['messages', msg.senderId] });
    },
  });
}

function useGetSchedule() {
  return useQuery({
    queryKey: ['schedule'],
    queryFn: () => customFetch<ScheduleItem[]>('/api/dashboard/schedule'),
  });
}

function useAddScheduleItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { eventId: number; sessionTitle: string; sessionTime: string; sessionDetail?: string }) =>
      customFetch<ScheduleItem>('/api/dashboard/schedule', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schedule'] });
    },
  });
}

function useDeleteScheduleItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      customFetch(`/api/dashboard/schedule/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['schedule'] });
    },
  });
}

function useLogout() {
  const qc = useQueryClient();
  const [, setLocation] = useLocation();
  return useMutation({
    mutationFn: () => customFetch<{ status: string; message: string }>('/api/auth/logout', { method: 'POST' }).catch(() => ({ status: 'ok', message: 'Logged out' })),
    onSettled: () => {
      localStorage.removeItem('100-times-auth-token');
      window.dispatchEvent(new Event('auth-change'));
      qc.clear();
      setLocation('/login');
    },
  });
}

function useGetAdminEvents() {
  return useQuery({
    queryKey: ['admin', 'events'],
    queryFn: () => customFetch<EventCard[]>('/api/admin/events'),
  });
}

function useUpdateAdminEventStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'draft' | 'published' | 'pending' }) =>
      customFetch<EventCard>(`/api/admin/events/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'events'] });
      qc.invalidateQueries({ queryKey: getListEventsQueryKey() });
    },
  });
}

function useGetAdminUsers() {
  return useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => customFetch<UserOut[]>('/api/admin/users'),
  });
}

function useUpdateAdminUserRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, role }: { id: number; role: 'USER' | 'ORGANIZER' | 'ADMIN' }) =>
      customFetch<UserOut>(`/api/admin/users/${id}/role`, {
        method: 'PATCH',
        body: JSON.stringify({ role }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });
}

export interface AdminReview {
  id: number;
  author: string;
  rating: number;
  title: string;
  comment: string;
  eventId: number;
  eventTitle: string;
  createdAt: string | null;
}

function useGetAdminReviews() {
  return useQuery({
    queryKey: ['admin', 'reviews'],
    queryFn: () => customFetch<AdminReview[]>('/api/admin/reviews'),
  });
}

function useDeleteAdminReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      customFetch<{ status: string; message: string }>(`/api/admin/reviews/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'reviews'] });
    },
  });
}

// ---------------------------------------------------------------------------
// Calendar & Pass Utilities
// ---------------------------------------------------------------------------

function downloadIcs(event: {
  title: string;
  description?: string;
  location?: string;
  startDate: string;
  endDate?: string;
  startTime?: string;
}) {
  if (!event.startDate) return; // no real date → no calendar file
  const cleanDate = (d: string) => d.replaceAll('-', '');
  const start = cleanDate(event.startDate);
  const end = event.endDate ? cleanDate(event.endDate) : start;

  const icsContent = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//100 TIMES//Event Platform//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:100times-${Date.now()}@100times.in`,
    `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').split('.')[0]}Z`,
    `DTSTART;VALUE=DATE:${start}`,
    `DTEND;VALUE=DATE:${end}`,
    `SUMMARY:${event.title.replace(/[,;]/g, ' ')}`,
    ...(event.description ? [`DESCRIPTION:${event.description.replace(/\n/g, ' ')}`] : []),
    ...(event.location ? [`LOCATION:${event.location.replace(/[,;]/g, ' ')}`] : []),
    'STATUS:CONFIRMED',
    'END:VEVENT',
    'END:VCALENDAR',
  ].join('\r\n');

  const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
  const link = document.createElement('a');
  link.href = window.URL.createObjectURL(blob);
  link.setAttribute('download', `${event.title.toLowerCase().replace(/[^a-z0-9]/g, '_')}_pass.ics`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function downloadScheduleIcs(items: ScheduleItem[]) {
  const vevents = items.filter((item) => Boolean(item.eventDate)).map((item, i) => {
    const cleanDate = item.eventDate.replaceAll('-', '');
    return [
      'BEGIN:VEVENT',
      `UID:100times-sched-${item.id}-${i}@100times.in`,
      `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').split('.')[0]}Z`,
      `DTSTART;VALUE=DATE:${cleanDate}`,
      `DTEND;VALUE=DATE:${cleanDate}`,
      `SUMMARY:[${item.eventTitle}] ${item.sessionTitle.replace(/[,;]/g, ' ')} (${item.sessionTime})`,
      `DESCRIPTION:${(item.sessionDetail || 'Session on your 100 TIMES itinerary.').replace(/\n/g, ' ')}`,
      `LOCATION:${item.eventTitle.replace(/[,;]/g, ' ')}`,
      'STATUS:CONFIRMED',
      'END:VEVENT',
    ].join('\r\n');
  }).join('\r\n');

  const ics = `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//100 TIMES//Itinerary//EN\r\nCALSCALE:GREGORIAN\r\nMETHOD:PUBLISH\r\n${vevents}\r\nEND:VCALENDAR`;
  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
  const link = document.createElement('a');
  link.href = window.URL.createObjectURL(blob);
  link.setAttribute('download', 'my_100times_itinerary.ics');
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function googleCalendarUrl(event: { title: string; location?: string; startDate: string; endDate?: string; description?: string }) {
  const cleanDate = (d: string) => d.replaceAll('-', '');
  const params = new URLSearchParams({ action: 'TEMPLATE', text: event.title });
  if (event.startDate) {
    const start = cleanDate(event.startDate);
    const end = event.endDate ? cleanDate(event.endDate) : start;
    params.set('dates', `${start}/${end}`);
  }
  if (event.description) params.set('details', event.description);
  if (event.location) params.set('location', event.location);
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

// ---------------------------------------------------------------------------
// SVG Vector QR Code Generator Component
// ---------------------------------------------------------------------------

function QRCodeSvg({ value, size = 140 }: { value: string; size?: number }) {
  const gridSize = 21;
  const hash = Array.from(value).reduce((acc, char, i) => (acc * 31 + char.charCodeAt(0) + i) % 2147483647, 7);

  const isFinder = (r: number, c: number) => {
    if (r <= 6 && c <= 6) {
      if (r === 0 || r === 6 || c === 0 || c === 6) return true;
      if (r >= 2 && r <= 4 && c >= 2 && c <= 4) return true;
      return false;
    }
    if (r <= 6 && c >= 14) {
      if (r === 0 || r === 6 || c === 14 || c === 20) return true;
      if (r >= 2 && r <= 4 && c >= 16 && c <= 18) return true;
      return false;
    }
    if (r >= 14 && c <= 6) {
      if (r === 14 || r === 20 || c === 0 || c === 6) return true;
      if (r >= 16 && r <= 18 && c >= 2 && c <= 4) return true;
      return false;
    }
    return null;
  };

  const isTiming = (r: number, c: number) => {
    if (r === 6 || c === 6) return (r + c) % 2 === 0;
    return null;
  };

  const cells: boolean[][] = [];
  for (let r = 0; r < gridSize; r++) {
    const row: boolean[] = [];
    for (let c = 0; c < gridSize; c++) {
      const finder = isFinder(r, c);
      if (finder !== null) {
        row.push(finder);
      } else {
        const timing = isTiming(r, c);
        if (timing !== null) {
          row.push(timing);
        } else {
          const cellHash = (hash ^ (r * 37 + c * 59)) % 100;
          row.push(cellHash > 48);
        }
      }
    }
    cells.push(row);
  }

  const cellSize = size / gridSize;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="rounded-xl bg-white p-2.5 shadow-sm">
      {cells.map((row, r) =>
        row.map((active, c) =>
          active ? (
            <rect
              key={`${r}-${c}`}
              x={c * cellSize}
              y={r * cellSize}
              width={cellSize - 0.3}
              height={cellSize - 0.3}
              fill="#193d42"
              rx={cellSize * 0.15}
            />
          ) : null
        )
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Digital QR Badge & Event Pass Modal
// ---------------------------------------------------------------------------

function DigitalPassModal({ reg, open, onClose }: { reg: RegistrationPass | null; open: boolean; onClose: () => void }) {
  if (!open || !reg) return null;

  // Only the server-issued ticket code / QR payload are shown — never a client-generated stand-in.
  const ticketCode = reg.ticketCode?.trim() || '';
  const qrString = reg.qrCode?.trim() || ticketCode;
  const isVip = reg.ticketType === 'VIP';
  const isPremium = reg.ticketType === 'Premium';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-md overflow-hidden rounded-3xl border border-foreground/20 bg-card p-6 shadow-2xl sm:p-8">
        <button
          onClick={onClose}
          className="absolute right-5 top-5 grid h-9 w-9 place-items-center rounded-full border border-foreground/10 bg-background hover:bg-muted"
          aria-label="Close pass"
          data-testid="button-close-pass-modal"
        >
          <X size={17} />
        </button>

        {/* Lanyard punch hole aesthetic */}
        <div className="mx-auto -mt-2 mb-6 h-3.5 w-16 rounded-full border border-foreground/25 bg-muted/90 shadow-inner" />

        <div className="flex items-center justify-between border-b border-foreground/10 pb-4">
          <div className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-full bg-accent text-accent-foreground font-display text-xs font-bold">1</span>
            <span className="font-display text-sm font-extrabold tracking-tight">100 TIMES PASS</span>
          </div>
          <span
            className={cx(
              'rounded-full px-3 py-1 font-mono-face text-[10px] font-bold uppercase tracking-wider',
              isVip ? 'bg-amber-400/20 text-amber-600 dark:text-amber-300' : isPremium ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300' : 'bg-secondary text-secondary-foreground'
            )}
          >
            {reg.ticketType} PASS
          </span>
        </div>

        <div className="mt-6 text-center">
          <p className="font-mono-face text-[10px] uppercase tracking-[.18em] text-accent">
            {reg.status ? `Registration ${reg.status.replace('_', ' ')}` : 'Attendee'}
          </p>
          <h2 className="mt-1 font-display text-3xl font-bold tracking-tight">{reg.userName || '—'}</h2>
          {(reg.jobTitle || reg.company) && (
            <p className="mt-1 text-sm font-medium text-muted-foreground">
              {reg.jobTitle}{reg.jobTitle && reg.company && ' · '}{reg.company}
            </p>
          )}
        </div>

        <div className="my-6 flex justify-center">
          {ticketCode ? (
            <div className="rounded-2xl border border-foreground/15 bg-muted/40 p-4 text-center">
              <QRCodeSvg value={qrString} size={150} />
              <p className="mt-3 font-mono-face text-[11px] font-bold tracking-widest text-foreground">{ticketCode}</p>
            </div>
          ) : (
            <div className="max-w-xs rounded-2xl border border-dashed border-foreground/20 bg-muted/30 p-5 text-center" data-testid="status-pass-unavailable">
              <p className="font-display text-base font-bold">Pass not available yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                No ticket code has been issued for this registration, so there is no scannable pass to show.
              </p>
            </div>
          )}
        </div>

        <div className="space-y-3 rounded-2xl border border-foreground/10 bg-background/80 p-4 text-xs">
          <div>
            <p className="font-mono-face text-[9px] uppercase tracking-widest text-muted-foreground">Event</p>
            <p className="font-semibold text-foreground">{reg.eventTitle}</p>
          </div>
          <div className="flex justify-between">
            <div>
              <p className="font-mono-face text-[9px] uppercase tracking-widest text-muted-foreground">Date & Time</p>
              <p className="font-semibold text-foreground">{reg.eventStartDate ? fmtDate(reg.eventStartDate) : 'Date to be announced'}</p>
            </div>
            <div className="text-right">
              <p className="font-mono-face text-[9px] uppercase tracking-widest text-muted-foreground">Venue</p>
              <p className="font-semibold text-foreground">{reg.eventVenue || reg.eventLocation || '—'}</p>
            </div>
          </div>
        </div>

        {reg.eventStartDate ? (
        <div className="mt-6 grid grid-cols-2 gap-2.5">
          <button
            onClick={() => downloadIcs({ title: reg.eventTitle, location: reg.eventVenue || reg.eventLocation, startDate: reg.eventStartDate || '', endDate: reg.eventEndDate })}
            className="button-press flex items-center justify-center gap-2 rounded-full border border-foreground/15 bg-background py-2.5 text-xs font-semibold hover:border-accent hover:text-accent"
            data-testid="button-download-pass-ics"
          >
            <Download size={14} /> Apple / iCal
          </button>
          <a
            href={googleCalendarUrl({ title: reg.eventTitle, location: reg.eventVenue || reg.eventLocation, startDate: reg.eventStartDate || '', endDate: reg.eventEndDate })}
            target="_blank"
            rel="noopener noreferrer"
            className="button-press flex items-center justify-center gap-2 rounded-full border border-foreground/15 bg-background py-2.5 text-xs font-semibold hover:border-accent hover:text-accent"
            data-testid="button-google-calendar"
          >
            <ExternalLink size={14} /> Google Cal
          </a>
        </div>
        ) : (
          <p className="mt-6 text-center text-xs text-muted-foreground">Calendar export becomes available once the event date is announced.</p>
        )}

        <button
          onClick={() => window.print()}
          disabled={!ticketCode}
          className="button-press mt-2.5 flex w-full disabled:opacity-40 items-center justify-center gap-2 rounded-full bg-primary py-3 text-xs font-bold text-primary-foreground hover:bg-accent"
          data-testid="button-print-pass"
        >
          <Printer size={15} /> Print / Save Badge
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Direct Chat Drawer Component
// ---------------------------------------------------------------------------

function ChatDrawer({
  peerId,
  peerName,
  peerCompany,
  open,
  onClose,
}: {
  peerId: number | null;
  peerName: string;
  peerCompany?: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const [content, setContent] = useState('');
  const messagesQuery = useGetMessages(peerId);
  const sendMutation = useSendMessage();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const messages = messagesQuery.data ?? [];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  if (!open || !peerId) return null;

  const handleSend = (e: FormEvent) => {
    e.preventDefault();
    if (!content.trim() || sendMutation.isPending) return;
    sendMutation.mutate(
      { recipientId: peerId, content: content.trim() },
      { onSuccess: () => setContent('') }
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm animate-in fade-in">
      <div className="relative flex h-[580px] w-full max-w-lg flex-col overflow-hidden rounded-3xl border border-foreground/15 bg-card shadow-2xl">
        {/* Chat Header */}
        <div className="flex items-center justify-between border-b border-foreground/10 bg-background/80 px-6 py-4 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-full bg-accent text-accent-foreground font-display font-bold">
              {peerName.charAt(0)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-display text-base font-bold">{peerName}</h3>
                <span className="h-2 w-2 rounded-full bg-[#2f9c76]" />
              </div>
              {peerCompany && <p className="text-xs text-muted-foreground">{peerCompany}</p>}
            </div>
          </div>
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-full hover:bg-muted"
            aria-label="Close chat"
            data-testid="button-close-chat"
          >
            <X size={18} />
          </button>
        </div>

        {/* Messages Feed */}
        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          {messagesQuery.isLoading ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="animate-spin text-accent" size={24} />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <MessageSquare size={32} className="text-muted-foreground/50" />
              <p className="mt-3 font-display text-lg font-bold">Start the conversation</p>
              <p className="mt-1 max-w-xs text-xs text-muted-foreground">
                Say hello to {peerName}, coordinate meeting times, or discuss shared sessions.
              </p>
            </div>
          ) : (
            messages.map((m: Message) => {
              const isMe = m.senderId !== peerId;
              return (
                <div key={m.id} className={cx('flex flex-col', isMe ? 'items-end' : 'items-start')}>
                  <div
                    className={cx(
                      'max-w-[78%] rounded-2xl px-4 py-2.5 text-sm',
                      isMe ? 'bg-primary text-primary-foreground rounded-br-none' : 'bg-muted text-foreground rounded-bl-none'
                    )}
                  >
                    <p>{m.content}</p>
                  </div>
                  <span className="mt-1 font-mono-face text-[9px] uppercase tracking-wider text-muted-foreground">
                    {new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit' }).format(new Date(m.createdAt))}
                  </span>
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <form onSubmit={handleSend} className="border-t border-foreground/10 bg-background p-4">
          <div className="flex items-center gap-2">
            <input
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={`Message ${peerName}...`}
              className="flex-1 rounded-full border border-foreground/15 bg-card px-4 py-2.5 text-sm outline-none focus:border-accent"
              autoFocus
              data-testid="input-chat-message"
            />
            <button
              type="submit"
              disabled={!content.trim() || sendMutation.isPending}
              className="grid h-10 w-10 place-items-center rounded-full bg-accent text-accent-foreground disabled:opacity-40"
              data-testid="button-send-chat"
            >
              {sendMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const cx = (...values: Array<string | false | null | undefined>) => values.filter(Boolean).join(' ');
const fmtDate = (value?: string) => value ? new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value)) : 'Date to be announced';
/** Event price → label. The API sends a Decimal (often a string like "1500.00"); never invents a price. */
const money = (value?: number | string | null) => {
  if (value === null || value === undefined || value === '') return 'Price not available';
  const n = Number(value);
  if (!Number.isFinite(n)) return 'Price not available';
  if (n === 0) return 'Free';
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
};


// ---------------------------------------------------------------------------
// AI Suite Components
// ---------------------------------------------------------------------------

function AIConciergeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { hasToken, type } = useAccount();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-md" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="flex h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-accent/30 bg-background shadow-2xl">
        <div className="flex items-center justify-between border-b border-foreground/10 bg-secondary/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-2xl bg-accent text-accent-foreground">
              <Sparkles size={20} />
            </div>
            <div>
              <h2 className="font-display text-lg font-bold">100 TIMES Event Assistant</h2>
              <p className="text-xs text-muted-foreground">Answers only from verified upcoming events</p>
            </div>
          </div>
          <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-full border border-foreground/10 text-muted-foreground hover:bg-muted" data-testid="button-close-ai-modal">
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 p-4">
          {type === 'organiser' ? (
            <div className="grid h-full place-items-center text-center">
              <div>
                <p className="font-display text-xl font-bold">The event assistant is for attendee accounts</p>
                <p className="mt-2 text-sm text-muted-foreground">You're signed in with an organiser account. Manage your events from the organiser dashboard.</p>
                <Link href="/organizer" onClick={onClose} className="mt-5 inline-block rounded-full bg-primary px-6 py-3 text-sm font-bold text-primary-foreground hover:bg-accent">Organiser dashboard</Link>
              </div>
            </div>
          ) : hasToken ? (
            <AssistantPanel compact />
          ) : (
            <div className="grid h-full place-items-center text-center">
              <div>
                <p className="font-display text-xl font-bold">Sign in to use the assistant</p>
                <p className="mt-2 text-sm text-muted-foreground">It uses your saved preferences and tracks the events you save or register for.</p>
                <Link href="/login?redirect=/dashboard/assistant" onClick={onClose} className="mt-5 inline-block rounded-full bg-primary px-6 py-3 text-sm font-bold text-primary-foreground hover:bg-accent">Sign in</Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5" data-testid="link-logo">
      <span className="grid h-9 w-9 place-items-center rounded-full bg-accent text-accent-foreground font-display text-lg font-bold">1</span>
      <span className="font-display text-[1.1rem] font-extrabold tracking-[-.04em]">100 TIMES<span className="text-accent">.</span></span>
    </Link>
  );
}

const ACCOUNT_LABEL: Record<AccountType, string> = { admin: 'Admin', organiser: 'Organiser', attendee: 'Attendee' };

type MenuLink = { label: string; href: string; icon: typeof UserRound; testId: string };

// Everything a signed-in account can open, grouped per account type.
const ACCOUNT_MENU: Record<AccountType, MenuLink[]> = {
  attendee: [
    { label: 'My dashboard', href: '/dashboard', icon: LayoutDashboard, testId: 'dashboard' },
    { label: 'Discover events', href: '/dashboard/discover', icon: Compass, testId: 'discover' },
    { label: 'Saved events', href: '/dashboard/saved-events', icon: Heart, testId: 'saved' },
    { label: 'My registrations', href: '/dashboard/registrations', icon: Ticket, testId: 'registrations' },
    { label: 'Notifications', href: '/dashboard/notifications', icon: Bell, testId: 'notifications' },
    { label: 'My profile', href: '/dashboard/profile', icon: UserRound, testId: 'profile' },
  ],
  organiser: [
    { label: 'Organiser dashboard', href: '/organizer', icon: LayoutDashboard, testId: 'dashboard' },
    { label: 'My events', href: '/organizer/events', icon: CalendarDays, testId: 'events' },
    { label: 'List an event', href: '/organizer/events/create', icon: Plus, testId: 'list-event' },
    { label: 'Analytics', href: '/organizer/analytics', icon: LineChart, testId: 'analytics' },
    { label: 'Organiser profile', href: '/organizer/profile', icon: UserRound, testId: 'profile' },
  ],
  admin: [
    { label: 'Admin console', href: '/admin', icon: ShieldCheck, testId: 'admin' },
    { label: 'Event discovery', href: '/admin/discovery', icon: Compass, testId: 'discovery' },
    { label: 'List an event', href: '/organizer/events/create', icon: Plus, testId: 'list-event' },
    { label: 'Providers & API keys', href: '/admin/settings', icon: Settings2, testId: 'settings' },
  ],
};

function AccountMenu({ type, name, email }: { type: AccountType; name?: string | null; email?: string | null }) {
  const [location, setLocation] = useLocation();
  const logout = useLogout();
  const display = name || email?.split('@')[0] || 'Account';
  const isActive = (href: string) => location === href || (href !== '/admin' && href !== '/dashboard' && href !== '/organizer' && location.startsWith(`${href}/`));
  const itemClass =
    'flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium outline-none data-[highlighted]:bg-muted data-[highlighted]:text-foreground';

  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="button-press group flex items-center gap-1.5 rounded-full border border-foreground/15 py-1.5 pl-1.5 pr-2.5 text-sm font-semibold hover:border-accent data-[state=open]:border-accent data-[state=open]:bg-accent/10"
          aria-label={`Account menu for ${display}`}
          data-testid="button-account-menu"
        >
          <span className="grid h-7 w-7 place-items-center rounded-full bg-primary text-xs font-bold uppercase text-primary-foreground">
            {display.charAt(0)}
          </span>
          <span className="hidden max-w-[120px] truncate lg:inline">{display}</span>
          <ChevronDown size={15} className="text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          collisionPadding={16}
          className="z-50 w-[min(18rem,calc(100vw-32px))] rounded-2xl border border-foreground/10 bg-background p-1.5 shadow-xl"
          data-testid="menu-account"
        >
          <div className="flex items-center gap-3 px-3 pb-3 pt-2">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary text-sm font-bold uppercase text-primary-foreground">
              {display.charAt(0)}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{display}</p>
              {email && <p className="truncate text-xs text-muted-foreground">{email}</p>}
            </div>
            <span className="ml-auto shrink-0 rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-bold text-accent">{ACCOUNT_LABEL[type]}</span>
          </div>
          <DropdownMenu.Separator className="mx-1 mb-1 h-px bg-foreground/10" />
          {ACCOUNT_MENU[type].map(({ label, href, icon: Icon, testId }) => (
            <DropdownMenu.Item
              key={href}
              onSelect={() => setLocation(href)}
              className={cx(itemClass, isActive(href) ? 'text-accent font-semibold' : 'text-foreground')}
              data-testid={`menu-account-${testId}`}
            >
              <Icon size={16} className={isActive(href) ? 'text-accent' : 'text-muted-foreground'} />
              {label}
            </DropdownMenu.Item>
          ))}
          <DropdownMenu.Separator className="mx-1 my-1 h-px bg-foreground/10" />
          <DropdownMenu.Item
            onSelect={() => logout.mutate()}
            disabled={logout.isPending}
            className={cx(itemClass, 'text-destructive data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive data-[disabled]:opacity-50')}
            data-testid="menu-account-logout"
          >
            <LogOut size={16} />
            {logout.isPending ? 'Signing out…' : 'Sign out'}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function Header() {
  const [open, setOpen] = useState(false);
  const [location] = useLocation();
  const logout = useLogout();

  // Attendee and organiser accounts get different headers: attendees never see
  // "List an event"; organisers never see attendee tools (assistant, dashboard).
  const { me, signedIn: isLoggedIn, type } = useAccount();
  const isAdmin = type === 'admin';
  const isOrganiser = type === 'organiser';
  const showListEvent = !isLoggedIn || isOrganiser || isAdmin;
  const showAssistant = !isOrganiser;
  const homeHref = isLoggedIn ? homePathFor(type) : '/login';
  const homeLabel = isOrganiser ? 'Organiser dashboard' : isAdmin ? 'Admin console' : 'My dashboard';

  const nav = [
    ['Explore', '/events'],
    ...(isAdmin ? [['Discovery', '/admin/discovery']] : []),
    ['Sectors', '/categories'],
    ['Cities', '/cities'],
    ['Organizers', '/organizers'],
    ['Venues', '/venues'],
  ];
  return (
    <header className="sticky top-0 z-40 border-b border-foreground/10 bg-background/90 backdrop-blur-xl">
      <div className="mx-auto flex h-[72px] max-w-[1440px] items-center justify-between px-5 lg:px-10">
        <Logo />
        <nav className="hidden items-center gap-4 whitespace-nowrap md:flex xl:gap-6">
          {nav.map(([label, href]) => (
            <Link key={href} href={href} data-testid={`link-nav-${label.toLowerCase()}`} className={cx('text-sm font-medium transition-colors hover:text-accent', location.startsWith(href) && 'text-accent font-semibold')}>
              {label}
            </Link>
          ))}
        </nav>
        {/* Never wrap a button label (it doubles the button's height); lower-priority extras
            appear only on wider screens so the row always fits. */}
        <div className="flex shrink-0 items-center gap-2 whitespace-nowrap">
          {showAssistant && <button
            onClick={() => window.dispatchEvent(new CustomEvent('open-ai-concierge'))}
            className="button-press flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-2.5 py-1.5 text-xs font-bold text-accent hover:bg-accent hover:text-accent-foreground sm:px-3.5"
            data-testid="button-header-ai-concierge"
            aria-label="AI Assistant"
          >
            <Sparkles size={14} />
            <span className="hidden sm:inline">AI Assistant</span>
            <kbd className="hidden rounded bg-accent/20 px-1 py-0.2 font-mono-face text-[9px] text-accent 2xl:inline-block">Ctrl K</kbd>
          </button>}
          {/* Signed in: every account option lives in the profile menu. */}
          {isLoggedIn && type ? (
            <AccountMenu type={type} name={me.data?.name} email={me.data?.email} />
          ) : (
            <>
              <Link
                href="/register?role=organiser&redirect=/organizer/events/create"
                className="hidden rounded-full border border-foreground/15 px-4 py-2 text-sm font-semibold hover:border-accent hover:text-accent xl:block"
                data-testid="link-organizer-portal"
              >
                List an event
              </Link>
              <Link href="/login" className="button-press rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-accent" data-testid="link-login">
                Sign in
              </Link>
            </>
          )}

          <button className="rounded-full p-2 md:hidden" onClick={() => setOpen(!open)} aria-label="Open navigation" data-testid="button-toggle-menu">
            {open ? <X size={21} /> : <Menu size={21} />}
          </button>
        </div>
      </div>
      {open && (
        <nav className="border-t border-foreground/10 px-5 py-4 md:hidden">
          {nav.map(([label, href]) => (
            <Link key={href} href={href} onClick={() => setOpen(false)} data-testid={`link-mobile-${label.toLowerCase()}`} className="block border-b border-foreground/10 py-3 text-sm font-semibold">
              {label}
            </Link>
          ))}
          {isAdmin && (
            <Link href="/admin" onClick={() => setOpen(false)} className="block border-b border-foreground/10 py-3 text-sm font-semibold text-accent" data-testid="link-mobile-admin">
              Admin console
            </Link>
          )}
          {showListEvent && (
            <Link
              href={isOrganiser || isAdmin ? '/organizer/events/create' : '/register?role=organiser&redirect=/organizer/events/create'}
              onClick={() => setOpen(false)}
              className="block border-b border-foreground/10 py-3 text-sm font-semibold text-accent"
              data-testid="link-mobile-organizer"
            >
              List an event
            </Link>
          )}
          {isLoggedIn && !isAdmin && (
            <Link href={homeHref} onClick={() => setOpen(false)} className="block border-b border-foreground/10 py-3 text-sm font-semibold" data-testid="link-mobile-dashboard">
              {homeLabel}
            </Link>
          )}
          {isLoggedIn ? (
            <div className="pt-3">
              <div className="flex items-center justify-between py-2 text-xs text-muted-foreground">
                <span className="truncate">Signed in: <strong>{me.data?.email}</strong></span>
                <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-bold text-accent">
                  {type && ACCOUNT_LABEL[type]}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  logout.mutate();
                }}
                disabled={logout.isPending}
                className="mt-2 block w-full rounded-full border border-destructive/30 px-4 py-2 text-center text-sm font-semibold text-destructive hover:bg-destructive/10"
                data-testid="button-mobile-logout"
              >
                Sign out
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="mt-3 block rounded-full bg-primary px-4 py-2.5 text-center text-sm font-semibold text-primary-foreground hover:bg-accent"
              data-testid="link-mobile-login"
            >
              Sign in
            </Link>
          )}
        </nav>
      )}
    </header>
  );
}

function Footer() {
  const { type } = useAccount();
  const yours =
    type === 'organiser'
      ? [['Organiser dashboard', '/organizer'], ['My events', '/organizer/events'], ['Create an event', '/organizer/events/create'], ['Organiser profile', '/organizer/profile']]
      : [['Dashboard', '/dashboard'], ['Discover events', '/dashboard/discover'], ['Saved events', '/dashboard/saved-events'], ['Registrations & Pass', '/dashboard/registrations'], ['My profile', '/dashboard/profile']];
  return (
    <footer className="mt-20 border-t border-foreground/10 bg-primary text-primary-foreground">
      <div className="mx-auto grid max-w-[1440px] gap-10 px-5 py-14 lg:grid-cols-[1.4fr_1fr_1fr_1fr] lg:px-10">
        <div>
          <Logo />
          <p className="mt-5 max-w-xs text-sm leading-6 text-primary-foreground/65">A high-signal guide to the events worth leaving home for.</p>
          <p className="mt-8 font-mono-face text-[10px] uppercase tracking-[.2em] text-primary-foreground/45">Made for curious people</p>
        </div>
        <FooterCol title="Discover" links={[['Explore events', '/events'], ['Sectors', '/categories'], ['Cities', '/cities']]} />
        <FooterCol title="Connect" links={[['Organizers', '/organizers'], ['Venues', '/venues'], ...(type === 'attendee' ? [] : [['For organizers', '/organizer']])]} />
        <FooterCol title="Your 100 TIMES" links={yours} />
      </div>
      <div className="mx-auto flex max-w-[1440px] flex-wrap justify-between items-center gap-3 border-t border-primary-foreground/15 px-5 py-5 text-xs text-primary-foreground/45 lg:px-10">
        <span>© 2026 100 TIMES</span>
        <div className="flex gap-5">
          <Link href="/privacy" className="hover:text-primary-foreground transition">Privacy Policy</Link>
          <Link href="/terms" className="hover:text-primary-foreground transition">Terms of Service</Link>
        </div>
        <span>Good events. Better conversations.</span>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: string[][] }) {
  return (
    <div>
      <p className="font-mono-face text-[10px] uppercase tracking-[.18em] text-accent">{title}</p>
      <div className="mt-4 space-y-3">
        {links.map(([label, href]) => (
          <Link key={href} href={href} className="block text-sm text-primary-foreground/70 hover:text-primary-foreground" data-testid={`link-footer-${label.toLowerCase().replaceAll(' ', '-')}`}>
            {label}
          </Link>
        ))}
      </div>
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const [aiModalOpen, setAiModalOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setAiModalOpen((prev) => !prev);
      }
    };
    const handleOpen = () => setAiModalOpen(true);
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('open-ai-concierge', handleOpen);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('open-ai-concierge', handleOpen);
    };
  }, []);

  return (
    <div className="site-shell">
      <Header />
      <main>{children}</main>
      <Footer />
      <AIConciergeModal open={aiModalOpen} onClose={() => setAiModalOpen(false)} />
    </div>
  );
}

function LoadingState({ label = 'Finding the signal' }: { label?: string }) {
  return (
    <div className="mx-auto max-w-[1440px] px-5 py-24 lg:px-10">
      <div className="loading-bar h-1 w-20 rounded bg-accent" />
      <p className="mt-5 font-mono-face text-xs uppercase tracking-[.16em] text-muted-foreground">{label}</p>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <div className="h-48 animate-pulse rounded-2xl bg-muted" />
        <div className="h-48 animate-pulse rounded-2xl bg-muted" />
        <div className="h-48 animate-pulse rounded-2xl bg-muted" />
      </div>
    </div>
  );
}

function ErrorState({ retry, title = 'That page missed its cue.' }: { retry?: () => void; title?: string }) {
  return (
    <div className="mx-auto max-w-xl px-5 py-28 text-center">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-accent/15 text-accent">
        <Zap size={24} />
      </div>
      <h2 className="mt-5 font-display text-3xl font-bold">{title}</h2>
      <p className="mt-3 text-muted-foreground">We could not load this right now. Give it another beat.</p>
      {retry && (
        <button onClick={retry} className="button-press mt-7 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground" data-testid="button-retry">
          Try again
        </button>
      )}
    </div>
  );
}

function EmptyState({ title = 'Nothing here yet.', body = 'Check back soon for a new signal.' }: { title?: string; body?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-foreground/20 bg-card/60 px-6 py-20 text-center">
      <Compass className="mx-auto text-accent" size={28} />
      <h3 className="mt-4 font-display text-2xl font-bold">{title}</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">{body}</p>
    </div>
  );
}

function SectionHeading({ kicker, title, action, href }: { kicker?: string; title: string; action?: string; href?: string }) {
  return (
    <div className="mb-7 flex items-end justify-between gap-4">
      <div>
        {kicker && <p className="font-mono-face text-[10px] uppercase tracking-[.18em] text-accent">{kicker}</p>}
        <h2 className="mt-2 font-display text-3xl font-bold tracking-[-.04em] sm:text-4xl">{title}</h2>
      </div>
      {action && href && (
        <Link href={href} className="hidden items-center gap-2 text-sm font-semibold hover:text-accent sm:flex" data-testid={`link-section-${title.toLowerCase().replaceAll(' ', '-')}`}>
          {action}
          <ArrowRight size={16} />
        </Link>
      )}
    </div>
  );
}

function EventArt({ event, className = '' }: { event: EventCard; className?: string }) {
  return (
    <div className={cx('relative overflow-hidden bg-[#dbe8de]', className)}>
      {event.image ? (
        <img src={event.image} alt="" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
      ) : (
        <>
          <div className="absolute -right-10 -top-14 h-48 w-48 rounded-full border-[28px] border-[#ec715c]/65" />
          <div className="absolute bottom-[-30px] left-[-10px] h-40 w-40 -rotate-12 rounded-[42%] bg-[#193d42]" />
          <span className="absolute left-5 top-5 font-display text-5xl font-extrabold leading-none text-[#193d42]/80">{event.category.slice(0, 1)}</span>
          <span className="absolute bottom-4 right-5 font-mono-face text-[9px] uppercase tracking-[.15em] text-[#193d42]/65">100 / {event.id}</span>
        </>
      )}
      <div className="absolute left-4 top-4 rounded-full bg-background/90 px-2.5 py-1 font-mono-face text-[9px] uppercase tracking-[.1em] text-foreground">
        {event.format === 'online' ? 'Online' : event.eventType}
      </div>
    </div>
  );
}

function SaveButton({ event, compact = false }: { event: EventCard; compact?: boolean }) {
  const qc = useQueryClient();
  const [saved, setSaved] = useState(event.isSaved);
  const [flash, setFlash] = useState('');
  const save = useSaveEvent();
  const unsave = useUnsaveEvent();
  const [, setLocation] = useLocation();
  const { type } = useAccount();
  // Saving is an attendee feature; organiser accounts don't get the button.
  if (type === 'organiser') return null;

  const toggle = () => {
    const hasToken = typeof window !== 'undefined' && Boolean(localStorage.getItem('100-times-auth-token'));
    if (!hasToken) {
      setLocation(`/register?role=attendee&redirect=/events/${event.slug}`);
      return;
    }
    const next = !saved;
    setSaved(next);
    setFlash(next ? 'Saved' : 'Removed');
    window.setTimeout(() => setFlash(''), 1600);
    (next ? save : unsave).mutate(
      { id: event.id },
      {
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: getGetSavedEventsQueryKey() });
          qc.invalidateQueries({ queryKey: getGetDashboardQueryKey() });
          qc.invalidateQueries({ queryKey: getListEventsQueryKey() });
        },
        onError: () => setSaved(!next),
      }
    );
  };
  return (
    <div className="relative">
      <button
        onClick={toggle}
        disabled={save.isPending || unsave.isPending}
        className={cx('button-press grid place-items-center rounded-full border border-foreground/15 bg-card/90 transition-colors hover:border-accent hover:text-accent', compact ? 'h-9 w-9' : 'h-11 w-11')}
        aria-label={saved ? 'Remove saved event' : 'Save event'}
        data-testid={`button-save-event-${event.id}`}
      >
        {save.isPending || unsave.isPending ? <Loader2 size={16} className="animate-spin" /> : <Heart size={compact ? 16 : 18} fill={saved ? 'currentColor' : 'none'} />}
      </button>
      {flash && <span className="absolute right-0 top-12 z-10 whitespace-nowrap rounded-full bg-primary px-2.5 py-1 text-[10px] font-semibold text-primary-foreground">{flash}</span>}
    </div>
  );
}

function EventCardView({ event, featured = false }: { event: EventCard; featured?: boolean }) {
  return (
    <article className={cx('group paper-card overflow-hidden rounded-2xl border border-foreground/10', featured && 'md:grid md:grid-cols-[1.18fr_1fr]')} data-testid={`card-event-${event.id}`}>
      <Link href={`/events/${event.slug}`} className={cx('relative block', featured ? 'h-64 md:h-full' : 'h-48')} data-testid={`link-event-${event.id}`}>
        <EventArt event={event} className="h-full w-full" />
      </Link>
      <div className="p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-mono-face text-[10px] uppercase tracking-[.13em] text-accent">{event.category} / {event.eventType}</p>
            <Link href={`/events/${event.slug}`} className="mt-2 block font-display text-xl font-bold leading-tight tracking-[-.03em] hover:text-accent" data-testid={`link-event-title-${event.id}`}>
              {event.title}
            </Link>
          </div>
          <SaveButton event={event} compact />
        </div>
        <div className="mt-6 space-y-2.5 text-sm text-muted-foreground">
          <p className="flex items-center gap-2">
            <CalendarDays size={15} className="text-accent" />
            {fmtDate(event.startDate)}
            {event.endDate !== event.startDate && ` — ${fmtDate(event.endDate)}`}
          </p>
          <p className="flex items-center gap-2">
            <MapPin size={15} className="text-accent" />
            {event.location} · {event.venue}
          </p>
        </div>
        <div className="mt-6 flex items-center justify-between border-t border-foreground/10 pt-4">
          <span className="font-mono-face text-xs">{money(event.price)}</span>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Star size={13} fill="currentColor" className="text-accent" /> {event.rating.toFixed(1)} <span className="hidden sm:inline">· {event.attendeeCount} going</span>
          </span>
        </div>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Add to Schedule Button
// ---------------------------------------------------------------------------

function AddToScheduleButton({
  eventId,
  eventTitle,
  session,
}: {
  eventId: number;
  eventTitle: string;
  session: { time: string; title: string; detail?: string };
}) {
  const scheduleQuery = useGetSchedule();
  const addMutation = useAddScheduleItem();
  const deleteMutation = useDeleteScheduleItem();

  const items = scheduleQuery.data ?? [];
  const existing = items.find((it: ScheduleItem) => it.eventId === eventId && it.sessionTitle === session.title);

  const toggle = () => {
    if (existing) {
      deleteMutation.mutate(existing.id);
    } else {
      addMutation.mutate({
        eventId,
        sessionTitle: session.title,
        sessionTime: session.time,
        sessionDetail: session.detail,
      });
    }
  };

  const isPending = addMutation.isPending || deleteMutation.isPending;

  return (
    <button
      onClick={toggle}
      disabled={isPending}
      className={cx(
        'button-press inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-all',
        existing
          ? 'bg-secondary text-secondary-foreground hover:bg-destructive/10 hover:text-destructive'
          : 'border border-foreground/15 bg-card hover:border-accent hover:text-accent'
      )}
      data-testid={`button-toggle-schedule-${session.title.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
    >
      {isPending ? (
        <Loader2 size={12} className="animate-spin" />
      ) : existing ? (
        <>
          <Check size={12} /> In Schedule
        </>
      ) : (
        <>
          <CalendarPlus size={12} /> + Add
        </>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Pages
// ---------------------------------------------------------------------------

function HomePage() {
  const home = useGetHome();
  const health = useHealthCheck();
  if (home.isLoading) return <LoadingState label="Curating this week" />;
  if (home.isError) return <ErrorState retry={() => home.refetch()} />;
  const payload = home.data;
  const featured = payload?.featured ?? [];
  const cats = payload?.trending ?? [];
  const cities = payload?.cities ?? [];
  const indexedCities = typeof payload?.stats?.cities === 'number' ? payload.stats.cities : null;
  return (
    <div className="page-enter">
      <section className="mx-auto max-w-[1440px] px-5 pb-16 pt-14 lg:px-10 lg:pb-24 lg:pt-24">
        <div className="grid items-end gap-12 lg:grid-cols-[1.1fr_.9fr]">
          <div>
            <p className="font-mono-face text-xs uppercase tracking-[.2em] text-accent">The event signal · India & beyond</p>
            <h1 className="mt-5 max-w-3xl font-display text-[clamp(3.4rem,8vw,7.8rem)] font-extrabold leading-[.88] tracking-[-.08em]">
              Go where<br /><span className="text-accent">things happen.</span>
            </h1>
          </div>
          <div className="max-w-md pb-2 lg:pb-4">
            <p className="text-lg leading-7 text-muted-foreground">100 TIMES is your considered shortlist of conferences, exhibitions, workshops and the conversations around them.</p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href="/events" className="button-press inline-flex items-center gap-2 rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:bg-accent" data-testid="link-hero-explore">
                Explore the calendar <ArrowRight size={16} />
              </Link>
              <span className="flex items-center gap-2 px-2 text-xs text-muted-foreground">
                <span className={cx('h-2 w-2 rounded-full', health.isError ? 'bg-destructive' : 'bg-[#2f9c76]')} />
                {health.isError ? 'Signal offline' : indexedCities ? `${indexedCities} ${indexedCities === 1 ? 'city' : 'cities'} indexed` : 'Live'}
              </span>
            </div>
          </div>
        </div>
        <div className="mt-16 border-y border-foreground/15 py-4">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3 font-mono-face text-[10px] uppercase tracking-[.15em] text-muted-foreground">
            <span>Not everything. The right things.</span>
            <span className="h-px w-10 bg-accent" />
            <span>Updated daily</span>
            <span className="h-px w-10 bg-accent" />
            <span>Built for the curious</span>
          </div>
        </div>
      </section>
      <section className="mx-auto max-w-[1440px] px-5 lg:px-10">
        <SectionHeading kicker="01 / This week" title="Worth the commute" action="See all events" href="/events" />
        <div className="grid gap-5 md:grid-cols-2">
          {featured.slice(0, 4).map((event, i) => (
            <div key={event.id} className={cx('page-enter', `stagger-${i + 1}`)}>
              <EventCardView event={event} featured={i === 0} />
            </div>
          ))}
          {featured.length === 0 && (
            <div className="md:col-span-2">
              <EmptyState title="No published events yet." body="New events will appear here as soon as they are published." />
            </div>
          )}
        </div>
      </section>

      <section className="mx-auto mt-24 max-w-[1440px] px-5 lg:px-10">
        <SectionHeading kicker="02 / Browse by energy" title="Find your room" action="All sectors" href="/categories" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {cats.length === 0 && (
            <div className="col-span-2 lg:col-span-4">
              <EmptyState title="No sectors indexed yet." />
            </div>
          )}
          {cats.slice(0, 4).map((cat, i) => (
            <Link href={`/categories/${cat.slug}`} key={cat.id} className={cx('hover-lift group rounded-2xl border border-foreground/10 bg-card p-5 sm:p-7', i === 1 && 'bg-secondary')} data-testid={`card-category-${cat.id}`}>
              <span className="font-display text-3xl text-accent">{cat.icon}</span>
              <h3 className="mt-9 font-display text-xl font-bold leading-tight">{cat.name}</h3>
              <p className="mt-2 text-xs text-muted-foreground">{cat.eventCount} events</p>
              <ArrowDownRight size={19} className="mt-8 transition-transform group-hover:translate-x-1 group-hover:translate-y-1" />
            </Link>
          ))}
        </div>
      </section>
      <section className="mx-auto mt-24 max-w-[1440px] px-5 lg:px-10">
        <div className="rounded-3xl bg-[#193d42] px-6 py-12 text-[#f3eadb] sm:px-12 lg:flex lg:items-end lg:justify-between">
          <div>
            <p className="font-mono-face text-[10px] uppercase tracking-[.18em] text-[#ec715c]">03 / Out there</p>
            <h2 className="mt-5 max-w-2xl font-display text-4xl font-bold leading-[.95] tracking-[-.05em] sm:text-6xl">
              Your next city<br />is a conversation.
            </h2>
          </div>
          <Link href="/cities" className="mt-8 inline-flex items-center gap-2 rounded-full bg-[#ec715c] px-5 py-3 text-sm font-semibold text-[#193d42] hover:bg-[#f5a08d] lg:mt-0" data-testid="link-home-cities">
            Explore cities <ArrowRight size={16} />
          </Link>
        </div>
      </section>
      <section className="mx-auto mt-24 max-w-[1440px] px-5 lg:px-10">
        <SectionHeading kicker="04 / Go further" title="Cities with a pulse" action="View all cities" href="/cities" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {cities.length === 0 && (
            <div className="sm:col-span-2 lg:col-span-4">
              <EmptyState title="No cities indexed yet." />
            </div>
          )}
          {cities.slice(0, 4).map((city) => (
            <Link href={`/cities/${city.slug}`} key={city.id} className="group relative min-h-44 overflow-hidden rounded-2xl border border-foreground/10 bg-muted p-5" data-testid={`card-city-${city.id}`}>
              <div className="absolute inset-0 bg-gradient-to-br from-[#e4b77d]/45 via-transparent to-[#193d42]/40" />
              <div className="relative flex h-full flex-col justify-between">
                <span className="font-mono-face text-[10px] uppercase tracking-[.15em] text-foreground/60">{city.country}</span>
                <div>
                  <h3 className="font-display text-2xl font-bold">{city.name}</h3>
                  <p className="mt-1 text-xs text-foreground/60">{city.eventCount} events indexed</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

// Explore date filter. `dateFrom`/`dateTo` match any event running on a day in
// the range (see GET /api/events); dates are the visitor's local calendar days.
type ExploreParams = ListEventsParams & { dateFrom?: string; dateTo?: string };
type DatePreset = 'any' | 'today' | 'weekend' | 'week' | 'month' | 'quarter' | 'custom';

const DATE_PRESETS: [DatePreset, string][] = [
  ['any', 'Any date'],
  ['today', 'Today'],
  ['weekend', 'This weekend'],
  ['week', 'Next 7 days'],
  ['month', 'This month'],
  ['quarter', 'Next 3 months'],
  ['custom', 'Pick dates…'],
];

function localIso(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function presetRange(preset: DatePreset): { dateFrom?: string; dateTo?: string } {
  const today = new Date();
  const plus = (days: number) => new Date(today.getFullYear(), today.getMonth(), today.getDate() + days);
  switch (preset) {
    case 'today':
      return { dateFrom: localIso(today), dateTo: localIso(today) };
    case 'weekend': {
      const day = today.getDay(); // 0 = Sunday, 6 = Saturday
      if (day === 0) return { dateFrom: localIso(today), dateTo: localIso(today) };
      return { dateFrom: localIso(day === 6 ? today : plus(6 - day)), dateTo: localIso(plus(7 - day)) };
    }
    case 'week':
      return { dateFrom: localIso(today), dateTo: localIso(plus(6)) };
    case 'month':
      return { dateFrom: localIso(today), dateTo: localIso(new Date(today.getFullYear(), today.getMonth() + 1, 0)) };
    case 'quarter':
      return { dateFrom: localIso(today), dateTo: localIso(plus(90)) };
    default:
      return { dateFrom: undefined, dateTo: undefined };
  }
}

function EventsPage() {
  const hasToken = typeof window !== 'undefined' && Boolean(localStorage.getItem('100-times-auth-token'));
  const [filters, setFilters] = useState<ExploreParams>({ page: 1, pageSize: 8, sort: 'soonest', format: 'all' });
  const [datePreset, setDatePreset] = useState<DatePreset>('any');
  const [term, setTerm] = useState('');
  const params = useMemo(() => ({ ...filters, q: term || undefined }), [filters, term]);
  const query = useListEvents(params as ListEventsParams);
  const categoriesQuery = useListCategories();
  const rawEvents = query.data?.items ?? [];
  const events = useMemo(() => {
    if (!filters.country || query.data?.items?.length) return rawEvents;
    const cLower = filters.country.toLowerCase();
    return rawEvents.filter(e => {
      const loc = (e.location || '').toLowerCase();
      const ven = (e.venue || '').toLowerCase();
      if (cLower === 'dubai') {
        return loc.includes('dubai') || loc.includes('united arab emirates') || ven.includes('dubai');
      }
      return loc.includes(cLower) || ven.includes(cLower) ||
        (cLower === 'india' && ['hyderabad', 'new delhi', 'mumbai', 'bengaluru'].some(c => loc.includes(c)));
    });
  }, [rawEvents, filters.country, query.data?.items]);
  const total = query.data?.total ?? events.length;
  const pages = query.data?.totalPages ?? Math.max(1, Math.ceil(events.length / (filters.pageSize || 8)));
  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-12 lg:px-10 lg:py-20">
      <div className="max-w-3xl">
        <p className="font-mono-face text-xs uppercase tracking-[.2em] text-accent">The directory</p>
        <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em] sm:text-7xl">Make a date<br />with an idea.</h1>
      </div>

      {!hasToken && (
        <div className="mt-8 rounded-2xl border border-accent/25 bg-accent/5 p-5 sm:p-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-accent" />
              <span className="font-mono-face text-xs uppercase tracking-wider text-accent font-bold">Attendee & Organiser Access</span>
            </div>
            <p className="font-display text-lg font-bold">Create an account to reserve passes, save events & network</p>
            <p className="text-xs text-muted-foreground">Hosting a conference, summit or expo? Create an organiser account to list your events on 100 TIMES.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <Link
              href="/register?role=attendee&redirect=/events"
              className="button-press rounded-full bg-primary px-4 py-2 text-xs font-bold text-primary-foreground hover:bg-accent"
            >
              Create Attendee Account
            </Link>
            <Link
              href="/register?role=organiser&redirect=/organizer/events/create"
              className="button-press rounded-full border border-foreground/15 bg-background px-4 py-2 text-xs font-semibold hover:border-accent hover:text-accent"
            >
              List an Event
            </Link>
            <Link
              href="/login?redirect=/events"
              className="text-xs font-semibold text-muted-foreground hover:text-foreground px-2"
            >
              Sign in
            </Link>
          </div>
        </div>
      )}

      <div className="mt-12 grid gap-8 lg:grid-cols-[250px_1fr]">
        <aside className="h-fit rounded-2xl border border-foreground/10 bg-card p-5 lg:sticky lg:top-24">
          <div className="flex items-center justify-between">
            <h2 className="font-display font-bold">Filter events</h2>
            <Filter size={16} className="text-accent" />
          </div>

          <label className="mt-6 block text-xs font-semibold text-muted-foreground">
            Country
            <CountrySelect
              value={filters.country}
              onChange={(country) => setFilters((f) => ({ ...f, country, page: 1 }))}
            />
          </label>

          {filters.country && (
            <div className="mt-3 rounded-lg border border-accent/20 bg-accent/5 p-2.5 text-xs">
              <div className="flex items-center justify-between font-semibold text-accent">
                <span className="flex items-center gap-1.5"><Globe size={13} /> {filters.country}</span>
                <button
                  type="button"
                  onClick={() => setFilters((f) => ({ ...f, country: undefined, page: 1 }))}
                  className="text-[10px] text-muted-foreground hover:text-accent"
                >
                  ✕
                </button>
              </div>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Showing worldwide events discovered in {filters.country}.
              </p>
            </div>
          )}

          <label className="mt-4 block text-xs font-semibold text-muted-foreground">
            Sector
            <select
              value={filters.category ?? ''}
              onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value || undefined, page: 1 }))}
              className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-sm"
              data-testid="select-filter-category"
            >
              <option value="">{categoriesQuery.isError ? 'Everything (sectors unavailable)' : 'Everything'}</option>
              {(categoriesQuery.data ?? []).map((c) => (
                <option key={c.slug} value={c.slug}>{c.name}</option>
              ))}
            </select>
          </label>
          <label className="mt-4 block text-xs font-semibold text-muted-foreground">
            Format
            <select
              value={filters.format ?? 'all'}
              onChange={(e) => setFilters((f) => ({ ...f, format: e.target.value as ListEventsParams['format'], page: 1 }))}
              className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-sm"
              data-testid="select-filter-format"
            >
              <option value="all">All formats</option>
              <option value="in-person">In person</option>
              <option value="online">Online</option>
            </select>
          </label>
          <label className="mt-4 block text-xs font-semibold text-muted-foreground">
            City
            <input
              value={filters.city ?? ''}
              onChange={(e) => setFilters((f) => ({ ...f, city: e.target.value || undefined, page: 1 }))}
              placeholder={filters.country ? `Try cities in ${filters.country}...` : "Try London, New York, Bengaluru..."}
              className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-sm outline-none focus:border-accent"
              data-testid="input-filter-city"
            />
          </label>
          <label className="mt-4 block text-xs font-semibold text-muted-foreground">
            Date
            <select
              value={datePreset}
              onChange={(e) => {
                const preset = e.target.value as DatePreset;
                setDatePreset(preset);
                // "Pick dates…" keeps the current range so the inputs below start from it.
                if (preset !== 'custom') setFilters((f) => ({ ...f, ...presetRange(preset), page: 1 }));
              }}
              className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-sm"
              data-testid="select-filter-date"
            >
              {DATE_PRESETS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          {datePreset === 'custom' && (
            <div className="mt-2 grid gap-2">
              <label className="block text-[11px] font-semibold text-muted-foreground">
                From
                <input
                  type="date"
                  value={filters.dateFrom ?? ''}
                  max={filters.dateTo || undefined}
                  onChange={(e) => setFilters((f) => ({ ...f, dateFrom: e.target.value || undefined, page: 1 }))}
                  className="mt-1 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2 text-sm outline-none focus:border-accent"
                  data-testid="input-filter-date-from"
                />
              </label>
              <label className="block text-[11px] font-semibold text-muted-foreground">
                To
                <input
                  type="date"
                  value={filters.dateTo ?? ''}
                  min={filters.dateFrom || undefined}
                  onChange={(e) => setFilters((f) => ({ ...f, dateTo: e.target.value || undefined, page: 1 }))}
                  className="mt-1 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2 text-sm outline-none focus:border-accent"
                  data-testid="input-filter-date-to"
                />
              </label>
            </div>
          )}
          {datePreset !== 'any' && datePreset !== 'custom' && filters.dateFrom && (
            <p className="mt-2 text-[11px] text-muted-foreground" data-testid="text-filter-date-range">
              {filters.dateFrom === filters.dateTo ? filters.dateFrom : `${filters.dateFrom} → ${filters.dateTo}`}
            </p>
          )}
          <button
            onClick={() => { setFilters({ page: 1, pageSize: 8, sort: 'soonest', format: 'all', country: undefined }); setDatePreset('any'); setTerm(''); }}
            className="mt-6 text-xs font-semibold text-accent hover:underline"
            data-testid="button-clear-filters"
          >
            Clear all
          </button>
        </aside>
        <div>
          <div className="flex flex-col justify-between gap-4 border-b border-foreground/15 pb-5 sm:flex-row sm:items-center">
            <div className="relative flex-1 sm:max-w-md">
              <Search className="absolute left-3 top-3 text-muted-foreground" size={17} />
              <input
                value={term}
                onChange={(e) => { setTerm(e.target.value); setFilters((f) => ({ ...f, page: 1 })); }}
                placeholder="Search events, topics, places..."
                className="w-full rounded-full border border-foreground/15 bg-card py-2.5 pl-10 pr-4 text-sm outline-none focus:border-accent"
                data-testid="input-search-events"
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <ListFilter size={15} />
              <select
                value={filters.sort}
                onChange={(e) => setFilters((f) => ({ ...f, sort: e.target.value as ListEventsParams['sort'] }))}
                className="bg-transparent py-2 font-semibold text-foreground outline-none"
                data-testid="select-sort-events"
              >
                <option value="soonest">Soonest</option>
                <option value="popular">Most popular</option>
                <option value="newest">Newest</option>
              </select>
            </label>
          </div>
          {query.isLoading ? (
            <LoadingState label="Loading the calendar" />
          ) : query.isError && !events.length ? (
            <ErrorState retry={() => query.refetch()} />
          ) : events.length ? (
            <>
              <p className="my-5 text-sm text-muted-foreground">
                <span className="font-semibold text-foreground">{total}</span> events worth your time
              </p>
              <div className="grid gap-5 md:grid-cols-2">
                {events.map((event) => (
                  <EventCardView key={event.id} event={event} />
                ))}
              </div>
              <div className="mt-9 flex items-center justify-between border-t border-foreground/10 pt-5">
                <span className="font-mono-face text-[10px] uppercase tracking-[.13em] text-muted-foreground">
                  Page {query.data?.page ?? 1} of {pages}
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={(filters.page ?? 1) <= 1}
                    onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))}
                    className="grid h-9 w-9 place-items-center rounded-full border border-foreground/15 disabled:opacity-30"
                    data-testid="button-events-prev"
                  >
                    <ArrowLeft size={15} />
                  </button>
                  <button
                    disabled={(filters.page ?? 1) >= pages}
                    onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))}
                    className="grid h-9 w-9 place-items-center rounded-full border border-foreground/15 disabled:opacity-30"
                    data-testid="button-events-next"
                  >
                    <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <EmptyState title="No events match that brief." body="Try widening your search or clearing one of the filters." />
          )}
        </div>
      </div>
    </div>
  );
}

function EventDetailPage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const { hasToken, type } = useAccount();
  const query = useGetEvent(slug, { query: { queryKey: getGetEventQueryKey(slug) } });
  if (query.isLoading) return <LoadingState label="Opening the event" />;
  if (query.isError || !query.data) return <ErrorState retry={() => query.refetch()} title="We could not find that event." />;
  const event = query.data;
  return (
    <div className="page-enter">
      <div className="mx-auto max-w-[1440px] px-5 pt-8 lg:px-10 lg:pt-12">
        <Link href="/events" className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-accent" data-testid="link-back-events">
          <ArrowLeft size={15} /> All events
        </Link>
        <div className="mt-8 grid gap-8 lg:grid-cols-[1.12fr_.88fr]">
          <div className="h-[340px] overflow-hidden rounded-3xl sm:h-[470px]">
            <EventArt event={event} className="h-full" />
          </div>
          <div className="flex flex-col justify-end pb-2">
            <p className="font-mono-face text-xs uppercase tracking-[.16em] text-accent">{event.category} / {event.eventType}</p>
            <h1 className="mt-4 font-display text-5xl font-extrabold leading-[.92] tracking-[-.07em] sm:text-7xl">{event.title}</h1>
            <p className="mt-5 text-lg leading-7 text-muted-foreground">{event.description}</p>
            {type === 'organiser' ? (
              <p className="mt-8 rounded-2xl border border-foreground/10 bg-muted/40 p-4 text-xs text-muted-foreground" data-testid="text-organiser-cannot-register">
                You're signed in with an organiser account. Registering for events is done from an attendee account.
              </p>
            ) : (
              <div className="mt-8 flex flex-wrap gap-3">
                <Link
                  href={hasToken ? `/events/${event.slug}/register` : `/register?role=attendee&redirect=/events/${event.slug}/register`}
                  className="button-press inline-flex items-center gap-2 rounded-full bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
                  data-testid="link-register-event"
                >
                  Register now <ArrowRight size={16} />
                </Link>
                <SaveButton event={event} />
              </div>
            )}

            {!hasToken && (
              <div className="mt-6 rounded-2xl border border-accent/25 bg-accent/5 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs">
                <div>
                  <span className="font-bold text-accent">Attending this event?</span>
                  <p className="text-muted-foreground mt-0.5">
                    Create a free attendee account to reserve tickets, receive your Digital Pass with QR badge, and add it to your schedule.
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Link
                    href={`/register?role=attendee&redirect=/events/${event.slug}/register`}
                    className="button-press rounded-full bg-primary px-3.5 py-1.5 text-xs font-bold text-primary-foreground hover:bg-accent"
                  >
                    Create Account
                  </Link>
                  <Link
                    href={`/login?role=attendee&redirect=/events/${event.slug}/register`}
                    className="rounded-full border border-foreground/15 px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent"
                  >
                    Sign in
                  </Link>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="mx-auto mt-14 grid max-w-[1440px] gap-12 px-5 lg:grid-cols-[1.1fr_.9fr] lg:px-10">
        <div>
          <div>
            <InfoRows event={event} />
          </div>
          <div className="mt-14">
            <SectionHeading kicker="The reason to go" title="A room with a point of view" />
            <p className="max-w-2xl text-base leading-8 text-muted-foreground">{event.description}</p>
          </div>
          {event.agenda?.length > 0 && (
            <div className="mt-14">
              <SectionHeading kicker="Program" title="A day well spent" />
              <div className="divide-y divide-foreground/10 border-y border-foreground/10">
                {event.agenda.map((item: { time: string; title: string; detail?: string }, i: number) => (
                  <div key={`${item.time}-${i}`} className="flex flex-col justify-between gap-3 py-4 sm:flex-row sm:items-center">
                    <div className="grid gap-2 sm:grid-cols-[100px_1fr]">
                      <span className="font-mono-face text-xs text-accent">{item.time}</span>
                      <div>
                        <h3 className="font-semibold">{item.title}</h3>
                        <p className="mt-1 text-sm text-muted-foreground">{item.detail}</p>
                      </div>
                    </div>
                    <div className="shrink-0">
                      <AddToScheduleButton eventId={event.id} eventTitle={event.title} session={item} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <aside>
          <div className="rounded-2xl bg-secondary p-6">
            <p className="font-mono-face text-[10px] uppercase tracking-[.15em] text-secondary-foreground/65">The essentials</p>
            <div className="mt-5 space-y-5 text-sm">
              <div>
                <p className="text-xs text-secondary-foreground/60">Date & time</p>
                <p className="mt-1 font-semibold">{fmtDate(event.startDate)} · {event.startTime}</p>
              </div>
              <div>
                <p className="text-xs text-secondary-foreground/60">Where</p>
                <p className="mt-1 font-semibold">{event.venue}<br />{event.location}</p>
              </div>
              <div>
                <p className="text-xs text-secondary-foreground/60">Tickets from</p>
                <p className="mt-1 font-semibold">{money(event.price)}</p>
              </div>
            </div>
            {event.organizer && (
              <p className="mt-7 border-t border-secondary-foreground/15 pt-5 text-sm font-semibold" data-testid="text-event-organizer">
                By{' '}
                {(event as typeof event & { organizerSlug?: string | null }).organizerSlug ? (
                  <Link href={`/organizers/${(event as typeof event & { organizerSlug?: string | null }).organizerSlug}`} className="underline-offset-4 hover:underline">
                    {event.organizer}
                  </Link>
                ) : (
                  event.organizer
                )}
              </p>
            )}
          </div>
          <div className="mt-5 rounded-2xl border border-foreground/10 bg-card p-6">
            <p className="font-mono-face text-[10px] uppercase tracking-[.15em] text-accent">People are saying</p>
            {event.reviews?.slice(0, 2).map((review) => (
              <div key={review.id} className="mt-5 border-b border-foreground/10 pb-5 last:border-0 last:pb-0">
                <div className="flex items-center gap-1 text-accent">
                  {Array.from({ length: review.rating }).map((_, i) => (
                    <Star key={i} size={13} fill="currentColor" />
                  ))}
                </div>
                <p className="mt-2 text-sm font-semibold">{review.title}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">“{review.comment}”</p>
                <p className="mt-2 text-xs text-muted-foreground">{review.author}</p>
              </div>
            ))}
            <ReviewForm eventId={event.id} eventSlug={event.slug} />
          </div>
        </aside>
      </div>
    </div>
  );
}

function InfoRows({ event }: { event: EventDetail }) {
  return (
    <div className="grid gap-4 border-y border-foreground/15 py-5 sm:grid-cols-3">
      <div>
        <p className="font-mono-face text-[10px] uppercase tracking-[.14em] text-muted-foreground">Format</p>
        <p className="mt-2 text-sm font-semibold">{event.format === 'online' ? 'Online' : 'In person'}</p>
      </div>
      <div>
        <p className="font-mono-face text-[10px] uppercase tracking-[.14em] text-muted-foreground">People going</p>
        <p className="mt-2 text-sm font-semibold">{event.attendeeCount}</p>
      </div>
      <div>
        <p className="font-mono-face text-[10px] uppercase tracking-[.14em] text-muted-foreground">Rating</p>
        <p className="mt-2 flex items-center gap-1 text-sm font-semibold">
          <Star size={14} fill="currentColor" className="text-accent" /> {event.rating}
        </p>
      </div>
    </div>
  );
}

function ReviewForm({ eventId, eventSlug }: { eventId: number; eventSlug: string }) {
  const qc = useQueryClient();
  const review = useCreateReview();
  const [form, setForm] = useState<ReviewInput>({ rating: 5, title: '', comment: '' });
  const [sent, setSent] = useState(false);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    review.mutate(
      { id: eventId, data: form },
      {
        onSuccess: () => {
          setSent(true);
          qc.invalidateQueries({ queryKey: getGetEventQueryKey(eventSlug) });
        },
        onError: () => setSent(false),
      }
    );
  };
  return (
    <div className="mt-7 border-t border-foreground/10 pt-6">
      {sent ? (
        <p className="flex items-center gap-2 text-sm font-semibold text-secondary-foreground">
          <Check size={16} /> Review shared with the room.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <p className="font-display text-lg font-bold">Been there?</p>
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((value) => (
              <button
                type="button"
                key={value}
                onClick={() => setForm((f) => ({ ...f, rating: value }))}
                className="text-accent"
                aria-label={`Rate ${value} stars`}
                data-testid={`button-rating-${value}`}
              >
                <Star size={15} fill={value <= form.rating ? 'currentColor' : 'none'} />
              </button>
            ))}
          </div>
          <input
            required
            placeholder="Give your take a title"
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            className="w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-xs outline-none focus:border-accent"
            data-testid="input-review-title"
          />
          <textarea
            required
            placeholder="What should people know?"
            value={form.comment}
            onChange={(e) => setForm((f) => ({ ...f, comment: e.target.value }))}
            className="min-h-20 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-xs outline-none focus:border-accent"
            data-testid="input-review-comment"
          />
          <button disabled={review.isPending} className="rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:bg-accent" data-testid="button-submit-review">
            {review.isPending ? 'Sharing...' : 'Share review'}
          </button>
        </form>
      )}
    </div>
  );
}

function RegisterPage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const eventQuery = useGetEvent(slug, { query: { queryKey: getGetEventQueryKey(slug) } });
  const mutation = useRegisterForEvent();
  const hasToken = typeof window !== 'undefined' && Boolean(localStorage.getItem('100-times-auth-token'));
  const me = useMe(hasToken);
  const attendeeProfile = useAttendeeProfile(hasToken && Boolean(me.data));
  const [createdPass, setCreatedPass] = useState<RegistrationPass | null>(null);
  const [showPassModal, setShowPassModal] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState<RegistrationInput>({ firstName: '', lastName: '', email: '', phone: '', company: '', jobTitle: '', country: '', ticketType: 'Standard' });
  const update = (key: keyof RegistrationInput, value: string) => setForm((f) => ({ ...f, [key]: value }));

  // Auto-fill from the signed-in attendee's account and attendee profile
  useEffect(() => {
    if (me.data) {
      const parts = (me.data.name || '').split(' ');
      const details = attendeeProfile.data;
      setForm((f) => ({
        ...f,
        firstName: f.firstName || parts[0] || '',
        lastName: f.lastName || parts.slice(1).join(' ') || '',
        email: f.email || me.data?.email || '',
        phone: f.phone || details?.phone || '',
        company: f.company || details?.company || '',
        jobTitle: f.jobTitle || details?.jobTitle || '',
        country: f.country || details?.country || '',
      }));
    }
  }, [me.data, attendeeProfile.data]);

  if (eventQuery.isLoading) return <LoadingState label="Preparing registration" />;
  if (eventQuery.isError || !eventQuery.data) return <ErrorState title="That event is no longer available." />;
  const event = eventQuery.data;

  if (!hasToken) {
    return (
      <div className="page-enter mx-auto max-w-xl px-5 py-24 text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-accent/10 text-accent">
          <Ticket size={30} />
        </div>
        <p className="mt-6 font-mono-face text-xs uppercase tracking-[.18em] text-accent">Attendee Registration</p>
        <h1 className="mt-3 font-display text-4xl sm:text-5xl font-extrabold tracking-[-.06em]">
          Create an account to reserve your place.
        </h1>
        <p className="mt-4 text-sm text-muted-foreground leading-relaxed">
          Please create a free attendee account or sign in to reserve your ticket for <strong>{event.title}</strong> and receive your digital pass with instant QR verification.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link
            href={`/register?role=attendee&redirect=/events/${slug}/register`}
            className="button-press rounded-full bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground hover:bg-accent"
            data-testid="link-register-to-book"
          >
            Create Attendee Account
          </Link>
          <Link
            href={`/login?role=attendee&redirect=/events/${slug}/register`}
            className="rounded-full border border-foreground/15 px-6 py-3.5 text-sm font-semibold hover:border-accent hover:text-accent"
            data-testid="link-login-to-book"
          >
            Sign In
          </Link>
        </div>
        <p className="mt-8 text-xs text-muted-foreground">
          Are you hosting an event? <Link href="/register?role=organiser&redirect=/organizer/events/create" className="text-accent underline font-semibold">List your event here</Link>
        </p>
      </div>
    );
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    mutation.mutate(
      // country: explicit null when blank so the API doesn't substitute a default.
      { id: event.id, data: { ...form, country: form.country?.trim() || (null as unknown as undefined) } },
      {
        onSuccess: (res: any) => {
          const passData: RegistrationPass = {
            id: res.id,
            eventId: event.id,
            eventTitle: event.title,
            eventSlug: event.slug,
            ticketType: res.ticketType || form.ticketType,
            registeredAt: res.registeredAt,
            status: res.status ?? '',
            userName: `${form.firstName} ${form.lastName}`.trim(),
            company: res.company ?? form.company,
            jobTitle: res.jobTitle ?? form.jobTitle,
            ticketCode: res.ticketCode,
            qrCode: res.qrCode,
            eventVenue: event.venue,
            eventLocation: event.location,
            eventStartDate: event.startDate,
            eventEndDate: event.endDate,
            eventStartTime: event.startTime,
          };
          setCreatedPass(passData);
        },
        onError: (err: any) =>
          setError(
            err?.data?.detail ||
              err?.message ||
              'We could not complete that registration. Please check your details and try again.'
          ),
      }
    );
  };

  return (
    <div className="page-enter mx-auto max-w-[1100px] px-5 py-12 lg:px-10 lg:py-20">
      <Link href={`/events/${slug}`} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-accent" data-testid="link-back-register">
        <ArrowLeft size={15} /> Back to event
      </Link>
      {createdPass ? (
        <div className="mx-auto max-w-xl py-20 text-center">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-secondary text-secondary-foreground">
            <Check size={30} />
          </div>
          <p className="mt-7 font-mono-face text-xs uppercase tracking-[.18em] text-accent">You are on the list</p>
          <h1 className="mt-3 font-display text-5xl font-extrabold tracking-[-.06em]">See you at<br />{event.title}.</h1>
          <p className="mt-5 leading-7 text-muted-foreground">A confirmation is heading to {form.email}. Your Digital Pass & QR Badge is ready.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <button
              onClick={() => setShowPassModal(true)}
              className="button-press inline-flex items-center gap-2 rounded-full bg-accent px-5 py-3 text-sm font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
              data-testid="button-view-instant-pass"
            >
              <QrCode size={16} /> View Digital Pass & Badge
            </button>
            <Link href="/dashboard/registrations" className="button-press inline-flex items-center gap-2 rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground" data-testid="link-view-registration">
              My registrations <ArrowRight size={16} />
            </Link>
          </div>
          <DigitalPassModal reg={createdPass} open={showPassModal} onClose={() => setShowPassModal(false)} />
        </div>
      ) : (
        <div className="mt-10 grid gap-12 lg:grid-cols-[.72fr_1.28fr]">
          <div>
            <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Registration / {event.category}</p>
            <h1 className="mt-4 font-display text-5xl font-extrabold leading-[.92] tracking-[-.07em]">Reserve your<br />place.</h1>
            <p className="mt-5 text-sm leading-6 text-muted-foreground">{event.title}<br />{fmtDate(event.startDate)} · {event.location}</p>
            <div className="mt-10 rounded-2xl bg-secondary p-5">
              <p className="text-xs text-secondary-foreground/65">Ticket type</p>
              <div className="mt-3 flex items-center justify-between">
                <span className="font-semibold">{form.ticketType}</span>
                <span className="font-mono-face text-sm">{money(event.price)}</span>
              </div>
            </div>
          </div>
          <form onSubmit={submit} className="rounded-3xl border border-foreground/10 bg-card p-6 sm:p-9">
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="First name" value={form.firstName} onChange={(v) => update('firstName', v)} required testId="input-registration-first-name" />
              <Field label="Last name" value={form.lastName} onChange={(v) => update('lastName', v)} required testId="input-registration-last-name" />
              <Field label="Email" type="email" value={form.email} onChange={(v) => update('email', v)} required testId="input-registration-email" />
              <Field label="Phone" value={form.phone ?? ''} onChange={(v) => update('phone', v)} testId="input-registration-phone" />
              <Field label="Company" value={form.company ?? ''} onChange={(v) => update('company', v)} testId="input-registration-company" />
              <Field label="Job title" value={form.jobTitle ?? ''} onChange={(v) => update('jobTitle', v)} testId="input-registration-job-title" />
              <Field label="Country" value={form.country ?? ''} onChange={(v) => update('country', v)} testId="input-registration-country" />
            </div>
            <label className="mt-5 block text-xs font-semibold text-muted-foreground">
              Ticket type
              <select value={form.ticketType} onChange={(e) => update('ticketType', e.target.value)} className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-3 text-sm" data-testid="select-registration-ticket">
                <option>Standard</option>
                <option>Free</option>
                <option>Premium</option>
                <option>VIP</option>
              </select>
            </label>
            {error && <p className="mt-5 rounded-lg bg-destructive/10 p-3 text-sm text-destructive" data-testid="status-registration-error">{error}</p>}
            <button disabled={mutation.isPending} className="button-press mt-7 flex w-full items-center justify-center gap-2 rounded-full bg-accent px-5 py-3.5 text-sm font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground disabled:opacity-60" data-testid="button-submit-registration">
              {mutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Ticket size={16} />}
              {mutation.isPending ? 'Confirming...' : 'Confirm registration'}
            </button>
            <p className="mt-4 text-center text-xs text-muted-foreground">Your details are formatted onto your digital badge.</p>
          </form>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  required = false,
  minLength,
  testId,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  minLength?: number;
  testId: string;
}) {
  return (
    <label className="block text-xs font-semibold text-muted-foreground">
      {label}
      <input
        type={type}
        required={required}
        minLength={minLength}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-3 text-sm outline-none focus:border-accent"
        data-testid={testId}
      />
    </label>
  );
}

function DirectoryListPage({ kind }: { kind: 'categories' | 'cities' | 'organizers' | 'venues' }) {
  const config = {
    categories: { title: 'Find your people.', kicker: 'Sectors / The right rooms', hook: useListCategories, empty: [] as Category[] },
    cities: { title: 'Change your coordinates.', kicker: 'Cities / Go somewhere', hook: useListCities, empty: [] as City[] },
    organizers: { title: 'Follow the curators.', kicker: 'Organizers / People behind the rooms', hook: useListOrganizers, empty: [] as Organizer[] },
    venues: { title: 'Know the room.', kicker: 'Venues / Places with a point of view', hook: useListVenues, empty: [] as Venue[] },
  }[kind];
  const query = config.hook();
  if (query.isLoading) return <LoadingState label={kind === 'categories' ? 'Loading sectors' : `Loading ${kind}`} />;
  if (query.isError && !query.data) return <ErrorState retry={() => query.refetch()} />;
  const data = (query.data?.length ? query.data : config.empty) as Array<Category | City | Organizer | Venue>;
  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-14 lg:px-10 lg:py-20">
      <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">{config.kicker}</p>
      <h1 className="mt-4 max-w-3xl font-display text-5xl font-extrabold leading-[.9] tracking-[-.07em] sm:text-7xl">{config.title}</h1>
      <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.length ? (
          data.map((item, i) => <DirectoryCard key={item.id} item={item} kind={kind} index={i} />)
        ) : (
          <div className="sm:col-span-2 lg:col-span-3">
            <EmptyState title={kind === 'categories' ? 'No sectors indexed yet.' : `No ${kind} indexed yet.`} />
          </div>
        )}
      </div>
    </div>
  );
}

function DirectoryCard({ item, kind, index }: { item: Category | City | Organizer | Venue; kind: string; index: number }) {
  const href = `/${kind}/${item.slug}`;
  const name = item.name;
  const count = 'capacity' in item ? `${item.capacity} capacity` : 'rating' in item ? `${item.rating.toFixed(1)} rating` : 'eventCount' in item ? item.eventCount : '';
  return (
    <Link href={href} className={cx('hover-lift group min-h-52 rounded-2xl border border-foreground/10 bg-card p-6', index % 5 === 1 && 'bg-secondary', index % 5 === 3 && 'bg-[#193d42] text-[#f3eadb]')} data-testid={`card-${kind.slice(0, -1)}-${item.id}`}>
      <div className="flex items-start justify-between">
        <span className="grid h-10 w-10 place-items-center rounded-full bg-accent/15 font-display text-lg text-accent">{'icon' in item ? item.icon : '⌁'}</span>
        <ArrowDownRight size={19} className="transition-transform group-hover:translate-x-1 group-hover:translate-y-1" />
      </div>
      <h2 className="mt-10 font-display text-2xl font-bold leading-tight">{name}</h2>
      <p className={cx('mt-2 text-xs', index % 5 === 3 ? 'text-[#f3eadb]/60' : 'text-muted-foreground')}>
        {count}{'country' in item && ` · ${item.country}`}
      </p>
    </Link>
  );
}

function DirectoryDetailPage({ kind }: { kind: 'category' | 'city' }) {
  const { slug = '' } = useParams<{ slug: string }>();
  const query = kind === 'category' ? useGetCategory(slug, { query: { queryKey: getGetCategoryQueryKey(slug) } }) : useGetCity(slug, { query: { queryKey: getGetCityQueryKey(slug) } });
  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) return <ErrorState title={`We could not find that ${kind === 'category' ? 'sector' : kind}.`} retry={() => query.refetch()} />;
  const detail = query.data as DirectoryDetail;
  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-12 lg:px-10 lg:py-20">
      <Link href={`/${kind === 'category' ? 'categories' : 'cities'}`} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-accent" data-testid="link-back-directory">
        <ArrowLeft size={15} /> Back to directory
      </Link>
      <div className="mt-10 max-w-3xl">
        <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">{kind === 'category' ? 'Sector' : kind} / Directory</p>
        <h1 className="mt-4 font-display text-6xl font-extrabold tracking-[-.07em]">{detail.name}</h1>
        <p className="mt-5 max-w-xl text-lg leading-7 text-muted-foreground">{detail.description}</p>
      </div>
      <div className="mt-16">
        <SectionHeading kicker="On the calendar" title={`${detail.events?.length ?? 0} events to explore`} />
        <div className="grid gap-5 md:grid-cols-3">
          {detail.events?.length ? (
            detail.events.map((event) => <EventCardView event={event} key={event.id} />)
          ) : (
            <div className="md:col-span-3">
              <EmptyState title="The calendar is being written." />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function OrganizerDetailPage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const query = useGetOrganizer(slug, { query: { queryKey: getGetOrganizerQueryKey(slug) } });
  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) return <ErrorState title="Organizer not found." retry={() => query.refetch()} />;
  const detail = query.data as OrganizerDetail;
  return (
    <div className="page-enter mx-auto max-w-[1200px] px-5 py-12 lg:px-10 lg:py-20">
      <Link href="/organizers" className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-accent" data-testid="link-back-organizers">
        <ArrowLeft size={15} /> All organizers
      </Link>
      <div className="mt-10 grid gap-8 border-b border-foreground/15 pb-12 md:grid-cols-[150px_1fr]">
        <div className="grid h-36 w-36 place-items-center rounded-3xl bg-secondary font-display text-6xl font-bold text-secondary-foreground">
          {detail.organizer.name.charAt(0)}
        </div>
        <div>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Organizer profile</p>
          <h1 className="mt-3 font-display text-5xl font-extrabold tracking-[-.07em]">{detail.organizer.name}</h1>
          <p className="mt-4 max-w-2xl leading-7 text-muted-foreground">{detail.organizer.description}</p>
          <div className="mt-5 flex gap-5 text-sm">
            <span className="flex items-center gap-1"><Star size={15} fill="currentColor" className="text-accent" /> {detail.organizer.rating}</span>
            <span className="text-muted-foreground">{detail.organizer.eventCount} events hosted</span>
          </div>
        </div>
      </div>
      <div className="mt-12">
        <SectionHeading kicker="Their calendar" title="Upcoming events" />
        <div className="grid gap-5 md:grid-cols-3">
          {detail.events?.length ? detail.events.map((event) => <EventCardView key={event.id} event={event} />) : <EmptyState title="No upcoming events." />}
        </div>
      </div>
    </div>
  );
}

function VenueDetailPage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const query = useGetVenue(slug, { query: { queryKey: getGetVenueQueryKey(slug) } });
  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) return <ErrorState title="Venue not found." retry={() => query.refetch()} />;
  const detail = query.data as VenueDetail;
  return (
    <div className="page-enter mx-auto max-w-[1200px] px-5 py-12 lg:px-10 lg:py-20">
      <Link href="/venues" className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-accent" data-testid="link-back-venues">
        <ArrowLeft size={15} /> All venues
      </Link>
      <div className="mt-10 rounded-3xl bg-[#193d42] p-7 text-[#f3eadb] sm:p-12">
        <p className="font-mono-face text-xs uppercase tracking-[.18em] text-[#ec715c]">Venue profile</p>
        <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em] sm:text-7xl">{detail.venue.name}</h1>
        <p className="mt-4 max-w-2xl leading-7 text-[#f3eadb]/65">{detail.description}</p>
        <div className="mt-8 flex flex-wrap gap-6 text-sm">
          <span className="flex items-center gap-2"><MapPin size={15} className="text-[#ec715c]" /> {detail.venue.address}, {detail.venue.city}</span>
          <span className="flex items-center gap-2"><Users size={15} className="text-[#ec715c]" /> {detail.venue.capacity} capacity</span>
        </div>
      </div>
      <div className="mt-12">
        <SectionHeading kicker="What is happening here" title="Events at this venue" />
        <div className="grid gap-5 md:grid-cols-3">
          {detail.events?.map((event) => <EventCardView key={event.id} event={event} />) ?? <EmptyState />}
        </div>
      </div>
    </div>
  );
}

function SpeakerPage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const query = useGetSpeaker(slug, { query: { queryKey: getGetSpeakerQueryKey(slug) } });
  if (query.isLoading) return <LoadingState />;
  if (query.isError || !query.data) return <ErrorState title="Speaker not found." retry={() => query.refetch()} />;
  const detail = query.data;
  return (
    <div className="page-enter mx-auto max-w-[1100px] px-5 py-12 lg:px-10 lg:py-20">
      <Link href="/events" className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-accent" data-testid="link-back-speaker">
        <ArrowLeft size={15} /> Explore events
      </Link>
      <div className="mt-10 grid gap-8 md:grid-cols-[170px_1fr]">
        <div className="grid h-40 w-40 place-items-center rounded-full bg-accent/20 font-display text-6xl font-bold text-accent">
          {detail.speaker.name.charAt(0)}
        </div>
        <div>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Speaker / {detail.speaker.company}</p>
          <h1 className="mt-4 font-display text-6xl font-extrabold tracking-[-.07em]">{detail.speaker.name}</h1>
          <p className="mt-3 text-lg text-muted-foreground">{detail.speaker.title} · {detail.speaker.company}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            {detail.speaker.expertise.map((topic) => (
              <span key={topic} className="rounded-full bg-secondary px-3 py-1 text-xs font-semibold">{topic}</span>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-14 max-w-2xl border-t border-foreground/15 pt-8">
        <p className="font-mono-face text-[10px] uppercase tracking-[.18em] text-accent">In their own words</p>
        <p className="mt-4 text-lg leading-8 text-muted-foreground">{detail.biography}</p>
      </div>
      <div className="mt-14">
        <SectionHeading kicker="On the calendar" title="Speaking soon" />
        <div className="grid gap-5 md:grid-cols-3">
          {detail.events?.map((event) => <EventCardView event={event} key={event.id} />) ?? <EmptyState />}
        </div>
      </div>
    </div>
  );
}

function AuthPage({ mode: initialMode }: { mode: 'login' | 'register' | 'forgot' }) {
  const [, setLocation] = useLocation();
  const qc = useQueryClient();
  const login = useLogin();
  const register = useRegisterUser();
  const [currentMode, setCurrentMode] = useState<'login' | 'register' | 'forgot'>(initialMode);

  // Read URL query params: e.g. ?role=admin or ?role=organiser or ?role=attendee or ?redirect=...
  const queryParams = useMemo(() => {
    if (typeof window === 'undefined') return new URLSearchParams();
    return new URLSearchParams(window.location.search);
  }, []);

  const [roleType, setRoleType] = useState<'attendee' | 'organiser' | 'admin'>(() => {
    const r = queryParams.get('role');
    if (r === 'admin') return 'admin';
    if (r === 'organiser' || r === 'organizer') return 'organiser';
    return 'attendee';
  });

  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    company: '',
    website: '',
    city: '',
    country: '',
  });
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [isAccountNotFound, setIsAccountNotFound] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const sanitizeAuthError = (err: any): { message: string; isNotFound: boolean } => {
    let raw = '';
    if (err?.data && typeof err.data === 'object' && err.data.detail) {
      raw = typeof err.data.detail === 'string' ? err.data.detail : JSON.stringify(err.data.detail);
    } else if (typeof err?.message === 'string') {
      raw = err.message;
    } else if (typeof err === 'string') {
      raw = err;
    }

    // Strip HTTP status prefix like "HTTP 401 Unauthorized: " or "HTTP 409 Conflict: "
    const cleaned = raw.replace(/^HTTP\s+\d+\s+[^:]+:\s*/i, '').trim();
    const lower = cleaned.toLowerCase();

    // Credential failures: never claim the account doesn't exist (a wrong password looks the same).
    if (
      lower.includes('no account details found') ||
      lower.includes('incorrect') ||
      lower.includes('user not found') ||
      lower.includes('account not found') ||
      lower.includes('no user found') ||
      lower.includes('unauthorized')
    ) {
      return {
        message: 'Incorrect email or password.',
        isNotFound: false,
      };
    }

    if (lower.includes('already exists')) {
      return {
        message: 'An account with this email already exists. Please sign in instead.',
        isNotFound: false,
      };
    }

    return {
      message: cleaned || 'Unable to authenticate. Please verify your details and try again.',
      isNotFound: false,
    };
  };

  // Sync mode state if initialMode prop changes (e.g. route transitions)
  useEffect(() => {
    setCurrentMode(initialMode);
    setError('');
    setIsAccountNotFound(false);
  }, [initialMode]);

  const isForgot = currentMode === 'forgot';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsAccountNotFound(false);
    setIsSubmitting(true);

    if (isForgot) {
      try {
        await customFetch('/api/auth/forgot-password', {
          method: 'POST',
          body: JSON.stringify({ email: form.email.trim().toLowerCase() }),
        });
      } catch {
        // generic response prevents user enumeration
      } finally {
        setIsSubmitting(false);
        setSubmitted(true);
      }
      return;
    }

    if (currentMode === 'login') {
      login.mutate(
        { data: { email: form.email.trim().toLowerCase(), password: form.password } } as never,
        {
          onSuccess: (session) => {
            if (roleType === 'admin' && session.user?.role !== 'ADMIN') {
              setIsSubmitting(false);
              setError('This account does not have administrator privileges. Please switch to Attendee or Organiser.');
              return;
            }

            localStorage.setItem('100-times-auth-token', session.token);
            window.dispatchEvent(new Event('auth-change'));
            qc.invalidateQueries({ queryKey: keys.me });
            // Attendees land on the attendee dashboard and organisers on the organiser
            // dashboard; a ?redirect= is only followed when that account may open it.
            const account = accountTypeOf(session.user as Me);
            const redirect = queryParams.get('redirect');
            setLocation(redirect && redirect.startsWith('/') && canOpenPath(account, redirect) ? redirect : homePathFor(account));
          },
          onError: (err: any) => {
            setIsSubmitting(false);
            // Any rejected credential (unknown email or wrong password) is reported the same way.
            if (err?.status === 401 || err?.status === 403) {
              setError('Incorrect email or password.');
              setIsAccountNotFound(false);
              return;
            }
            const { message, isNotFound } = sanitizeAuthError(err);
            setError(message);
            setIsAccountNotFound(isNotFound);
          },
        }
      );
      return;
    }

    // currentMode === 'register'
    if (roleType === 'admin') {
      setIsSubmitting(false);
      setError('Administrator accounts must be provisioned internally. Please sign in with existing admin credentials.');
      return;
    }

    try {
      const regRes = await customFetch<{ token: string; user: any }>('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          name: form.name.trim(),
          email: form.email.trim().toLowerCase(),
          password: form.password,
          country: form.country?.trim() || null,
          company: roleType === 'organiser' ? form.company.trim() || undefined : undefined,
          accountType: roleType === 'organiser' ? 'organiser' : 'attendee',
        }),
      });

      if (!regRes?.token) {
        throw new Error('Registration failed to create session');
      }

      localStorage.setItem('100-times-auth-token', regRes.token);
      window.dispatchEvent(new Event('auth-change'));

      if (roleType === 'organiser') {
        // Perform secure organizer onboarding initialization
        try {
          await customFetch('/api/organizer/onboarding', {
            method: 'POST',
            body: JSON.stringify({
              organizerName: form.name.trim(),
              organizationName: form.company.trim(),
              contactEmail: form.email.trim().toLowerCase(),
              website: form.website?.trim() || null,
              city: form.city?.trim() || null,
              state: null,
              country: form.country?.trim() || null,
            }),
          });
        } catch (onboardErr) {
          console.warn('Auto organizer onboarding warning:', onboardErr);
        }
        await qc.invalidateQueries({ queryKey: keys.me });
        const redirect = queryParams.get('redirect');
        setLocation(redirect && canOpenPath('organiser', redirect) ? redirect : '/organizer');
      } else {
        await qc.invalidateQueries({ queryKey: keys.me });
        const redirect = queryParams.get('redirect');
        setLocation(redirect && canOpenPath('attendee', redirect) ? redirect : '/dashboard');
      }
    } catch (regErr: any) {
      setIsSubmitting(false);
      const { message } = sanitizeAuthError(regErr);
      setError(message || 'Unable to create account. Please check your details and try again.');
      setIsAccountNotFound(false);
    }
  };

  const getKicker = () => {
    if (isForgot) return 'Account / Access Recovery';
    if (currentMode === 'login') {
      if (roleType === 'admin') return 'Admin Console / Secure Access';
      if (roleType === 'organiser') return 'Organiser Studio / Sign In';
      return 'Attendee Portal / Sign In';
    }
    if (roleType === 'admin') return 'Platform Administration / Access Control';
    if (roleType === 'organiser') return 'Organiser Account / Host with 100 TIMES';
    return 'Attendee Account / New Member';
  };

  const getTitle = () => {
    if (isForgot) return 'Reset your password.';
    if (currentMode === 'login') {
      if (roleType === 'admin') return 'Operations sign in.';
      if (roleType === 'organiser') return 'Welcome back, Host.';
      return 'Welcome back.';
    }
    if (roleType === 'admin') return 'Privileged provisioning.';
    if (roleType === 'organiser') return 'Publish & grow your event.';
    return 'Make room for more.';
  };

  const getSubtitle = () => {
    if (isForgot) return 'Enter your account email to receive a single-use password reset link.';
    if (currentMode === 'login') {
      if (roleType === 'admin') {
        return 'Sign in with your verified administrator credentials to access platform operations, telemetry, and agents.';
      }
      if (roleType === 'organiser') {
        return 'Sign in to manage your events, view attendee registrations, and run promotions.';
      }
      return 'Sign in to access your curated schedule, saved events, and digital passes.';
    }
    if (roleType === 'admin') {
      return 'Platform administrator accounts require privileged internal assignment and cannot be created through public self-registration.';
    }
    if (roleType === 'organiser') {
      return 'Create your verified organiser workspace to list events and reach qualified attendees.';
    }
    return 'Create your attendee account to discover high-signal events and network with peers.';
  };

  return (
    <div className="grid min-h-[calc(100dvh-72px)] lg:grid-cols-[.8fr_1.2fr]">
      <div className="hidden bg-[#193d42] p-12 text-[#f3eadb] lg:flex lg:flex-col lg:justify-between">
        <Logo />
        <div>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-[#ec715c]">
            {roleType === 'admin'
              ? 'Platform Operations'
              : roleType === 'organiser'
              ? 'Organiser Portal'
              : 'Attendee Field Guide'}
          </p>
          <p className="mt-5 max-w-md font-display text-5xl font-bold leading-[.95] tracking-[-.06em]">
            {roleType === 'admin'
              ? 'Autonomous agents, observability, and trusted event governance.'
              : roleType === 'organiser'
              ? 'Put your events in front of the people who matter.'
              : 'The right room can change the shape of a year.'}
          </p>
        </div>
        <p className="text-sm text-[#f3eadb]/55">100 TIMES · A trusted event guide</p>
      </div>

      <div className="flex items-center justify-center px-5 py-12 sm:py-16">
        <div className="w-full max-w-md">
          <Link href="/" className="mb-8 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-accent" data-testid="link-auth-home">
            <ArrowLeft size={15} /> Back to 100 TIMES
          </Link>

          {/* Three-Role Selection Tabs (Attendee vs Organiser vs Admin) */}
          {!isForgot && (
            <div className="mb-6 rounded-2xl border border-foreground/10 bg-secondary/50 p-1.5 flex gap-1">
              <button
                type="button"
                onClick={() => {
                  setRoleType('attendee');
                  setError('');
                  setIsAccountNotFound(false);
                }}
                className={cx(
                  'flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2.5 text-xs font-bold transition-all',
                  roleType === 'attendee'
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
                data-testid="tab-auth-attendee"
              >
                <UserRound size={15} className={roleType === 'attendee' ? 'text-accent' : ''} />
                <span>Attendee</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setRoleType('organiser');
                  setError('');
                  setIsAccountNotFound(false);
                }}
                className={cx(
                  'flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2.5 text-xs font-bold transition-all',
                  roleType === 'organiser'
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
                data-testid="tab-auth-organiser"
              >
                <Sparkles size={15} className={roleType === 'organiser' ? 'text-accent' : ''} />
                <span>Organiser</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setRoleType('admin');
                  setError('');
                  setIsAccountNotFound(false);
                }}
                className={cx(
                  'flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2.5 text-xs font-bold transition-all',
                  roleType === 'admin'
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
                data-testid="tab-auth-admin"
              >
                <ShieldCheck size={15} className={roleType === 'admin' ? 'text-accent' : ''} />
                <span>Admin</span>
              </button>
            </div>
          )}

          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">
            {getKicker()}
          </p>
          <h1 className="mt-3 font-display text-4xl sm:text-5xl font-extrabold tracking-[-.07em]">
            {getTitle()}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {getSubtitle()}
          </p>

          {submitted ? (
            <div className="mt-8 rounded-2xl bg-secondary p-6">
              <Check className="text-secondary-foreground" />
              <p className="mt-4 font-semibold">Check your inbox.</p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                If an account exists for {form.email}, you will receive a secure single-use password reset link shortly.
              </p>
              <button
                type="button"
                onClick={() => {
                  setSubmitted(false);
                  setCurrentMode('login');
                }}
                className="mt-5 rounded-full bg-primary px-5 py-2 text-xs font-bold text-primary-foreground hover:bg-accent"
              >
                Back to Sign in
              </button>
            </div>
          ) : currentMode === 'register' && roleType === 'admin' ? (
            <div className="mt-8 rounded-2xl border border-foreground/10 bg-secondary/40 p-6 space-y-4">
              <div className="flex items-center gap-3">
                <ShieldCheck size={24} className="text-accent" />
                <h3 className="font-display text-lg font-bold">Privileged Access Only</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Platform administrator accounts cannot be created publicly. Administrators must be provisioned internally. If you are a designated administrator, please sign in.
              </p>
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setCurrentMode('login');
                    setError('');
                  }}
                  className="button-press w-full rounded-full bg-primary px-5 py-3.5 text-xs font-bold text-primary-foreground hover:bg-accent transition shadow-sm"
                  data-testid="button-switch-admin-login"
                >
                  Sign In to Admin Console
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="mt-8 space-y-4">
              {currentMode === 'register' && (
                <Field
                  label={roleType === 'organiser' ? 'Organizer / Contact Name *' : 'Your Full Name *'}
                  value={form.name}
                  onChange={(v) => setForm((f) => ({ ...f, name: v }))}
                  required
                  testId="input-auth-name"
                />
              )}

              <Field
                label={roleType === 'admin' ? 'Administrator Email *' : roleType === 'organiser' && currentMode === 'register' ? 'Official Work Email *' : 'Email Address *'}
                type="email"
                value={form.email}
                onChange={(v) => setForm((f) => ({ ...f, email: v }))}
                required
                testId="input-auth-email"
              />

              {currentMode === 'register' && roleType === 'organiser' && (
                <>
                  <Field
                    label="Organization / Company Name *"
                    value={form.company}
                    onChange={(v) => setForm((f) => ({ ...f, company: v }))}
                    required
                    testId="input-auth-company"
                  />
                  <Field
                    label="Organization Website (optional)"
                    type="url"
                    value={form.website}
                    onChange={(v) => setForm((f) => ({ ...f, website: v }))}
                    testId="input-auth-website"
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <Field
                      label="Headquarters City"
                      value={form.city}
                      onChange={(v) => setForm((f) => ({ ...f, city: v }))}
                      testId="input-auth-city"
                    />
                    <Field
                      label="Country"
                      value={form.country}
                      onChange={(v) => setForm((f) => ({ ...f, country: v }))}
                      testId="input-auth-country"
                    />
                  </div>
                </>
              )}

              {!isForgot && (
                <Field
                  label="Password *"
                  type="password"
                  value={form.password}
                  onChange={(v) => setForm((f) => ({ ...f, password: v }))}
                  required
                  minLength={8}
                  testId="input-auth-password"
                />
              )}

              {currentMode === 'register' && roleType === 'attendee' && (
                <Field
                  label="Country"
                  value={form.country}
                  onChange={(v) => setForm((f) => ({ ...f, country: v }))}
                  testId="input-auth-country"
                />
              )}

              {error && (
                isAccountNotFound && roleType !== 'admin' ? (
                  <div
                    className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm animate-in fade-in"
                    data-testid="status-auth-error"
                  >
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="mt-0.5 shrink-0 text-amber-500" size={18} />
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-foreground">No account details found</p>
                        <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                          We couldn't find an existing account for <strong className="text-foreground">{form.email || 'this email'}</strong>. Please create a new account to continue.
                        </p>
                        <div className="mt-3">
                          <button
                            type="button"
                            onClick={() => {
                              setCurrentMode('register');
                              setError('');
                              setIsAccountNotFound(false);
                            }}
                            className="button-press inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-xs font-bold text-accent-foreground shadow-sm hover:opacity-90"
                            data-testid="button-switch-to-create-account"
                          >
                            <UserPlus size={14} />
                            Create New {roleType === 'organiser' ? 'Organiser' : 'Attendee'} Account
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div
                    className="rounded-xl bg-destructive/10 border border-destructive/20 p-3 text-sm text-destructive flex items-center gap-2.5 animate-in fade-in"
                    data-testid="status-auth-error"
                  >
                    <AlertTriangle size={16} className="shrink-0 text-destructive" />
                    <p className="text-xs leading-relaxed">{error}</p>
                  </div>
                )
              )}

              <button
                type="submit"
                disabled={login.isPending || register.isPending || isSubmitting}
                className="button-press flex w-full items-center justify-center gap-2 rounded-full bg-primary px-5 py-3.5 text-sm font-bold text-primary-foreground hover:bg-accent disabled:opacity-50 transition-colors shadow-sm"
                data-testid="button-auth-submit"
              >
                {login.isPending || register.isPending || isSubmitting ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : roleType === 'admin' ? (
                  <ShieldCheck size={16} />
                ) : roleType === 'organiser' && currentMode === 'register' ? (
                  <Sparkles size={16} />
                ) : (
                  <LockKeyhole size={16} />
                )}
                {isForgot
                  ? 'Send password reset link'
                  : currentMode === 'login'
                  ? roleType === 'admin'
                    ? 'Sign In to Admin Console'
                    : roleType === 'organiser'
                    ? 'Sign In to Organiser Desk'
                    : 'Sign In as Attendee'
                  : roleType === 'organiser'
                  ? 'Create Organiser Account'
                  : 'Create Attendee Account'}
              </button>
            </form>
          )}

          {/* Mode Switcher Footer */}
          <div className="mt-8 border-t border-foreground/10 pt-5 text-sm text-muted-foreground">
            {currentMode === 'login' ? (
              <div className="flex flex-wrap items-center justify-between gap-2">
                {roleType === 'admin' ? (
                  <span className="text-xs text-muted-foreground">
                    Restricted operational console
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setCurrentMode('register');
                      setError('');
                      setIsAccountNotFound(false);
                    }}
                    className="font-semibold text-foreground hover:text-accent"
                    data-testid="link-create-account"
                  >
                    {roleType === 'organiser' ? 'New organiser? Create account' : 'New attendee? Create account'}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setCurrentMode('forgot');
                    setError('');
                    setIsAccountNotFound(false);
                  }}
                  className="text-xs text-muted-foreground hover:text-foreground"
                  data-testid="link-forgot-password"
                >
                  Forgot password?
                </button>
              </div>
            ) : currentMode === 'register' ? (
              <div className="text-center">
                <span>Already have an account? </span>
                <button
                  type="button"
                  onClick={() => {
                    setCurrentMode('login');
                    setError('');
                    setIsAccountNotFound(false);
                  }}
                  className="font-semibold text-foreground hover:text-accent ml-1"
                  data-testid="link-existing-account"
                >
                  Sign in here
                </button>
              </div>
            ) : (
              <div className="text-center">
                <button
                  type="button"
                  onClick={() => {
                    setCurrentMode('login');
                    setError('');
                    setIsAccountNotFound(false);
                  }}
                  className="font-semibold text-foreground hover:text-accent"
                >
                  ← Back to Sign in
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Navigation & Tabs
// ---------------------------------------------------------------------------

function DashboardNav() {
  const me = useMe();
  const [location] = useLocation();
  const links = [
    ['Overview', '/dashboard', LayoutDashboard],
    ['Discover events', '/dashboard/discover', Search],
    ['Preferences', '/dashboard/preferences', ListFilter],
    ['Match My Events', '/dashboard/recommendations', Sparkles],
    ['Event Assistant', '/dashboard/assistant', MessageSquare],
    ['Saved events', '/dashboard/saved-events', Heart],
    ['Registrations & Pass', '/dashboard/registrations', Ticket],
    ['My Schedule', '/dashboard/schedule', CalendarDays],
    ['Networking', '/dashboard/networking', Users],
    ['Notifications', '/dashboard/notifications', Bell],
    ['My profile', '/dashboard/profile', UserRound],
    ...(me.data?.role === 'ADMIN' ? ([['Admin Console', '/admin', ShieldCheck]] as const) : []),
  ] as const;

  return (
    <aside className="rounded-2xl border border-foreground/10 bg-card p-3 lg:h-fit lg:sticky lg:top-24">
      <p className="px-3 py-3 font-mono-face text-[10px] uppercase tracking-[.16em] text-muted-foreground">Attendee · Your 100 TIMES</p>
      {links.map(([label, href, Icon]) => (
        <Link
          href={href}
          key={href}
          className={cx('flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold hover:bg-muted', location === href && 'bg-muted text-accent')}
          data-testid={`link-dashboard-${label.toLowerCase().replaceAll(' ', '-')}`}
        >
          <Icon size={16} className="text-accent" />
          {label}
        </Link>
      ))}
    </aside>
  );
}

function ScheduleTab() {
  const scheduleQuery = useGetSchedule();
  const deleteMutation = useDeleteScheduleItem();
  const items = scheduleQuery.data ?? [];

  if (scheduleQuery.isLoading) return <LoadingState label="Loading your itinerary" />;

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 rounded-2xl bg-secondary p-6 sm:flex-row sm:items-center">
        <div>
          <h2 className="font-display text-2xl font-bold">Personalized Itinerary</h2>
          <p className="mt-1 text-sm text-secondary-foreground/75">
            {items.length} sessions bookmarked across your registered events.
          </p>
        </div>
        {items.length > 0 && (
          <button
            onClick={() => downloadScheduleIcs(items)}
            className="button-press inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-xs font-bold text-primary-foreground hover:bg-accent"
            data-testid="button-export-all-schedule"
          >
            <Download size={14} /> Export Schedule (.ics)
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="No sessions in your schedule."
          body="Explore event agendas and click '+ Add to Schedule' on sessions you want to attend."
        />
      ) : (
        <div className="space-y-3">
          {items.map((item: ScheduleItem) => (
            <div
              key={item.id}
              className="flex flex-col justify-between gap-4 rounded-2xl border border-foreground/10 bg-card p-5 sm:flex-row sm:items-center"
              data-testid={`schedule-item-${item.id}`}
            >
              <div className="grid gap-2 sm:grid-cols-[110px_1fr]">
                <div className="flex flex-col">
                  <span className="font-mono-face text-xs font-bold text-accent">{item.sessionTime}</span>
                  <span className="font-mono-face text-[10px] text-muted-foreground">{fmtDate(item.eventDate)}</span>
                </div>
                <div>
                  <h3 className="font-display text-lg font-bold">{item.sessionTitle}</h3>
                  {item.sessionDetail && <p className="mt-1 text-xs text-muted-foreground">{item.sessionDetail}</p>}
                  <Link
                    href={`/events/${item.eventSlug}`}
                    className="mt-2 inline-flex items-center gap-1 font-mono-face text-[10px] font-semibold text-accent hover:underline"
                  >
                    {item.eventTitle} <ArrowRight size={11} />
                  </Link>
                </div>
              </div>
              <button
                onClick={() => deleteMutation.mutate(item.id)}
                disabled={deleteMutation.isPending}
                className="grid h-9 w-9 self-end place-items-center rounded-full border border-foreground/10 text-muted-foreground hover:border-destructive/30 hover:bg-destructive/10 hover:text-destructive sm:self-center"
                aria-label="Remove session from itinerary"
                data-testid={`button-delete-schedule-${item.id}`}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function NetworkingTab() {
  const [subtab, setSubtab] = useState<'attendees' | 'connections'>('attendees');
  const [search, setSearch] = useState('');
  const [chatPeer, setChatPeer] = useState<{ id: number; name: string; company?: string | null } | null>(null);

  const attendeesQuery = useListAttendees({ q: search || undefined });
  const connectionsQuery = useListConnections();
  const requestMutation = useRequestConnection();
  const updateMutation = useUpdateConnection();

  const attendees = attendeesQuery.data ?? [];
  const connections = connectionsQuery.data ?? [];

  const pendingRequests = connections.filter((c: Connection) => c.status === 'pending' && !c.isRequester);
  const activeConnections = connections.filter((c: Connection) => c.status === 'accepted');

  return (
    <div className="space-y-6">
      {/* Subtab Switcher */}
      <div className="flex items-center justify-between border-b border-foreground/10 pb-4">
        <div className="flex gap-2">
          <button
            onClick={() => setSubtab('attendees')}
            className={cx(
              'rounded-full px-5 py-2 text-xs font-bold transition-all',
              subtab === 'attendees' ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-card'
            )}
            data-testid="tab-discover-attendees"
          >
            Discover Attendees ({attendees.length})
          </button>
          <button
            onClick={() => setSubtab('connections')}
            className={cx(
              'rounded-full px-5 py-2 text-xs font-bold transition-all',
              subtab === 'connections' ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-card'
            )}
            data-testid="tab-my-connections"
          >
            My Network ({activeConnections.length})
            {pendingRequests.length > 0 && (
              <span className="ml-1.5 rounded-full bg-accent px-1.5 py-0.5 text-[9px] text-accent-foreground">
                {pendingRequests.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {subtab === 'attendees' && (
        <div className="space-y-5">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-3 text-muted-foreground" size={16} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, company, or job title..."
              className="w-full rounded-full border border-foreground/15 bg-card py-2.5 pl-10 pr-4 text-xs outline-none focus:border-accent"
              data-testid="input-search-attendees"
            />
          </div>

          {attendeesQuery.isLoading ? (
            <LoadingState label="Finding community signals" />
          ) : attendees.length === 0 ? (
            <EmptyState title="No attendees match that search." body="Try searching another skill, title, or company." />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {attendees.map((att: AttendeeProfile) => (
                <div
                  key={att.id}
                  className="flex flex-col justify-between rounded-2xl border border-foreground/10 bg-card p-5 hover:border-accent/40"
                  data-testid={`attendee-card-${att.id}`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="grid h-11 w-11 place-items-center rounded-full bg-secondary font-display text-lg font-bold text-secondary-foreground">
                          {att.name.charAt(0)}
                        </div>
                        <div>
                          <h3 className="font-display text-base font-bold leading-tight">{att.name}</h3>
                          <p className="text-xs font-medium text-muted-foreground">
                            {att.jobTitle || 'Attendee'}{att.jobTitle && att.company && ' · '}{att.company}
                          </p>
                        </div>
                      </div>
                      {att.country && (
                        <span className="rounded-full bg-muted px-2 py-0.5 font-mono-face text-[9px] text-muted-foreground">
                          {att.country}
                        </span>
                      )}
                    </div>
                    {att.bio && <p className="mt-3 text-xs leading-5 text-muted-foreground line-clamp-2">{att.bio}</p>}
                  </div>

                  <div className="mt-5 flex items-center justify-between border-t border-foreground/10 pt-4">
                    <span className="font-mono-face text-[10px] text-muted-foreground">
                      {att.registeredEventCount} {att.registeredEventCount === 1 ? 'event' : 'events'}
                    </span>
                    {att.connectionStatus === 'connected' ? (
                      <button
                        onClick={() => setChatPeer({ id: att.id, name: att.name, company: att.company })}
                        className="button-press inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-1.5 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
                        data-testid={`button-message-attendee-${att.id}`}
                      >
                        <MessageSquare size={13} /> Message
                      </button>
                    ) : att.connectionStatus === 'pending_sent' ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 font-mono-face text-[10px] text-muted-foreground">
                        <Check size={11} /> Request Sent
                      </span>
                    ) : att.connectionStatus === 'pending_received' ? (
                      <button
                        onClick={() => att.connectionId && updateMutation.mutate({ id: att.connectionId, status: 'accepted' })}
                        className="button-press inline-flex items-center gap-1 rounded-full bg-[#2f9c76] px-3 py-1 text-xs font-semibold text-white"
                        data-testid={`button-accept-attendee-${att.id}`}
                      >
                        <UserCheck size={13} /> Accept
                      </button>
                    ) : (
                      <button
                        onClick={() => requestMutation.mutate(att.id)}
                        disabled={requestMutation.isPending}
                        className="button-press inline-flex items-center gap-1.5 rounded-full border border-foreground/15 bg-background px-3.5 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent"
                        data-testid={`button-connect-attendee-${att.id}`}
                      >
                        <UserPlus size={13} /> Connect
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {subtab === 'connections' && (
        <div className="space-y-6">
          {pendingRequests.length > 0 && (
            <div>
              <p className="mb-3 font-mono-face text-[10px] uppercase tracking-[.16em] text-accent">Pending Invitations</p>
              <div className="space-y-3">
                {pendingRequests.map((req: Connection) => (
                  <div
                    key={req.id}
                    className="flex flex-col justify-between gap-4 rounded-2xl border border-accent/30 bg-card p-5 sm:flex-row sm:items-center"
                    data-testid={`invitation-card-${req.id}`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="grid h-10 w-10 place-items-center rounded-full bg-accent text-accent-foreground font-display font-bold">
                        {req.peerName.charAt(0)}
                      </div>
                      <div>
                        <h3 className="font-display text-base font-bold">{req.peerName}</h3>
                        <p className="text-xs text-muted-foreground">{req.peerJobTitle} · {req.peerCompany}</p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => updateMutation.mutate({ id: req.id, status: 'accepted' })}
                        className="button-press inline-flex items-center gap-1 rounded-full bg-primary px-4 py-2 text-xs font-bold text-primary-foreground hover:bg-accent"
                        data-testid={`button-accept-invite-${req.id}`}
                      >
                        <Check size={13} /> Accept
                      </button>
                      <button
                        onClick={() => updateMutation.mutate({ id: req.id, status: 'declined' })}
                        className="button-press rounded-full border border-foreground/15 bg-background px-4 py-2 text-xs font-semibold hover:bg-muted"
                        data-testid={`button-decline-invite-${req.id}`}
                      >
                        Decline
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <p className="mb-3 font-mono-face text-[10px] uppercase tracking-[.16em] text-muted-foreground">Connected Peers ({activeConnections.length})</p>
            {activeConnections.length === 0 ? (
              <EmptyState title="You have not connected with peers yet." body="Browse the Discover Attendees tab to start building your event network." />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {activeConnections.map((c: Connection) => (
                  <div
                    key={c.id}
                    className="flex items-center justify-between rounded-2xl border border-foreground/10 bg-card p-4 hover:border-accent"
                    data-testid={`connection-row-${c.id}`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="grid h-10 w-10 place-items-center rounded-full bg-secondary font-display font-bold text-secondary-foreground">
                        {c.peerName.charAt(0)}
                      </div>
                      <div>
                        <h4 className="font-display font-bold">{c.peerName}</h4>
                        <p className="text-xs text-muted-foreground">{c.peerCompany || 'Attendee'}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => setChatPeer({ id: c.peerId, name: c.peerName, company: c.peerCompany })}
                      className="button-press inline-flex items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
                      data-testid={`button-chat-connection-${c.id}`}
                    >
                      <MessageSquare size={13} /> Chat
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Direct Chat Drawer */}
      <ChatDrawer
        peerId={chatPeer?.id ?? null}
        peerName={chatPeer?.name ?? ''}
        peerCompany={chatPeer?.company}
        open={Boolean(chatPeer)}
        onClose={() => setChatPeer(null)}
      />
    </div>
  );
}

function RegistrationsTab({
  registrations,
  onOpenPass,
}: {
  registrations: RegistrationPass[];
  onOpenPass: (reg: RegistrationPass) => void;
}) {
  if (!registrations.length) {
    return <EmptyState title="No registrations yet." body="Find a gathering with a point of view and reserve your ticket." />;
  }

  return (
    <div className="space-y-4">
      {registrations.map((reg) => (
        <div
          key={reg.id}
          className="flex flex-col justify-between gap-4 rounded-2xl border border-foreground/10 bg-card p-5 hover:border-accent/40 sm:flex-row sm:items-center"
          data-testid={`row-registration-${reg.id}`}
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-secondary px-2.5 py-0.5 font-mono-face text-[9px] font-bold uppercase text-secondary-foreground">
                {reg.ticketType}
              </span>
              <span className="font-mono-face text-[10px] text-muted-foreground">
                {reg.ticketCode || 'No ticket code issued'}
              </span>
            </div>
            <Link href={`/events/${reg.eventSlug}`} className="mt-1.5 block font-display text-xl font-bold hover:text-accent">
              {reg.eventTitle}
            </Link>
            <p className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
              <CalendarDays size={13} className="text-accent" />
              {reg.eventStartDate ? fmtDate(reg.eventStartDate) : 'Date to be announced'}
              {reg.eventVenue && ` · ${reg.eventVenue}`}
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => onOpenPass(reg)}
              className="button-press inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
              data-testid={`button-view-pass-${reg.id}`}
            >
              <QrCode size={14} /> View Digital Pass
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function SettingsPanel() {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  return (
    <>
      <ProfilePanel
        footer={
          <div className="space-y-3 rounded-2xl border border-rose-500/20 bg-card p-6">
            <h3 className="font-display text-base font-bold text-rose-500">Danger Zone</h3>
            <p className="text-xs text-muted-foreground">
              Permanently remove your 100 TIMES account, personal profile, and associated event data.
            </p>
            <button
              type="button"
              onClick={() => setShowDeleteModal(true)}
              className="rounded-full border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-xs font-bold text-rose-500 hover:bg-rose-500 hover:text-white transition"
              data-testid="button-open-delete-account"
            >
              Delete Account
            </button>
          </div>
        }
      />
      <DeleteAccountModal isOpen={showDeleteModal} onClose={() => setShowDeleteModal(false)} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Role gates: attendee and organiser accounts are separate. The server refuses
// the other account type's endpoints; these keep the interface consistent with
// that when someone types the other area's URL.
// ---------------------------------------------------------------------------

function RoleGate({ allow, children }: { allow: AccountType[]; children: ReactNode }) {
  const { hasToken, signedIn, type, resolving, me } = useAccount();
  const logout = useLogout();
  // Signed-out visitors get each page's own sign-in prompt.
  if (!hasToken || (!resolving && !signedIn)) return <>{children}</>;
  if (resolving || !type) return <LoadingState label="Checking your account" />;
  if (allow.includes(type)) return <>{children}</>;

  const organiserArea = allow.includes('organiser');
  return (
    <div className="page-enter mx-auto max-w-xl px-5 py-28 text-center" data-testid="role-gate-blocked">
      <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">{organiserArea ? 'Organiser area' : 'Attendee area'}</p>
      <h1 className="mt-4 font-display text-4xl font-extrabold tracking-[-.06em]">
        This page is for {organiserArea ? 'organiser' : 'attendee'} accounts.
      </h1>
      <p className="mt-4 text-sm leading-6 text-muted-foreground">
        You're signed in as <strong>{me.data?.email}</strong> with {type === 'organiser' ? 'an organiser' : 'an attendee'} account.{' '}
        {organiserArea
          ? 'Listing and managing events needs a separate organiser account.'
          : 'Saved events, registrations, recommendations and networking belong to attendee accounts.'}
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link href={homePathFor(type)} className="rounded-full bg-primary px-6 py-3 text-sm font-bold text-primary-foreground hover:bg-accent" data-testid="link-role-gate-home">
          {type === 'organiser' ? 'Go to organiser dashboard' : 'Go to my dashboard'}
        </Link>
        <button type="button" onClick={() => logout.mutate()} className="rounded-full border border-foreground/15 px-6 py-3 text-sm font-semibold hover:border-accent hover:text-accent">
          Sign in with another account
        </button>
      </div>
    </div>
  );
}

function AttendeeArea({ tab }: { tab: string }) {
  return <RoleGate allow={['attendee', 'admin']}><DashboardPage tab={tab} /></RoleGate>;
}

function OrganiserArea({ tab }: { tab: string }) {
  return <RoleGate allow={['organiser', 'admin']}><OrganizerStudioPage initialTab={tab} /></RoleGate>;
}

function DashboardPage({ tab = 'overview' }: { tab?: string }) {
  const me = useMe();
  const dash = useGetDashboard();
  const saved = useGetSavedEvents();
  const regs = useGetRegistrations();
  const notes = useGetNotifications();
  const [selectedPass, setSelectedPass] = useState<RegistrationPass | null>(null);

  const token = typeof window !== 'undefined' ? localStorage.getItem('100-times-auth-token') : null;

  if (dash.isLoading) return <LoadingState label="Loading your dashboard" />;
  if (dash.isError || !token) {
    return (
      <div className="page-enter mx-auto max-w-xl px-5 py-32 text-center">
        <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Attendee Dashboard</p>
        <h1 className="mt-4 font-display text-4xl font-extrabold tracking-[-.06em]">Sign in to access your dashboard</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Sign in to view your personalized schedule, attendee networking connections, saved events, and digital passes.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link href="/login?redirect=/dashboard" className="rounded-full bg-primary px-6 py-3 text-sm font-bold text-primary-foreground hover:bg-accent" data-testid="link-dashboard-login">
            Sign in
          </Link>
          <Link href="/register?redirect=/dashboard" className="rounded-full border border-foreground/15 px-6 py-3 text-sm font-semibold hover:border-accent hover:text-accent">
            Create account
          </Link>
        </div>
      </div>
    );
  }

  const data = dash.data;
  const savedEvents = saved.data ?? data?.saved ?? [];
  const registrations = (regs.data ?? data?.upcoming ?? []) as RegistrationPass[];
  const notifications = notes.data ?? data?.notifications ?? [];

  const titles: Record<string, string> = {
    overview: 'Your field guide.',
    schedule: 'My personal itinerary.',
    networking: 'Attendee networking hub.',
    'saved-events': 'Saved for later.',
    registrations: 'Your digital passes.',
    recommendations: 'Match my events.',
    preferences: 'What you want to find.',
    assistant: 'Ask for events.',
    notifications: 'Keep in the loop.',
    discover: 'Find your next event.',
    profile: 'Your attendee profile.',
  };

  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-12 lg:px-10 lg:py-16">
      {me.data?.emailVerified === false && (
        <EmailVerificationBanner userEmail={me.data?.email} />
      )}
      <div className="mb-10">
        <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Dashboard / {tab}</p>
        <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em]">{titles[tab] ?? titles.overview}</h1>
        <p className="mt-3 text-muted-foreground">Good to see you, {me.data?.name || data?.userName || 'Member'}.</p>
      </div>
      <div className="grid gap-8 lg:grid-cols-[235px_1fr]">
        <DashboardNav />
        <div>
          {tab === 'overview' && <AttendeeOverview />}
          {tab === 'discover' && <DiscoverPanel />}
          {tab === 'preferences' && <PreferencesPanel />}
          {tab === 'assistant' && <AssistantPanel />}
          {tab === 'schedule' && <ScheduleTab />}
          {tab === 'networking' && <NetworkingTab />}
          {tab === 'saved-events' && <SavedEventsPanel />}
          {tab === 'recommendations' && <MatchesPanel />}
          {tab === 'registrations' && (
            <>
              <RegistrationsTab registrations={registrations} onOpenPass={(p) => setSelectedPass(p)} />
              <ExternalRegistrationsPanel />
            </>
          )}
          {tab === 'notifications' && <NotificationsPanel />}
          {tab === 'profile' && <SettingsPanel />}
        </div>
      </div>
      <DigitalPassModal reg={selectedPass} open={Boolean(selectedPass)} onClose={() => setSelectedPass(null)} />
    </div>
  );
}

function Metric({ label, value, icon: Icon }: { label: string; value: number; icon: typeof Heart }) {
  return (
    <div className="rounded-2xl border border-foreground/10 bg-card p-5">
      <Icon size={18} className="text-accent" />
      <p className="mt-7 font-display text-4xl font-bold">{value}</p>
      <p className="mt-1 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

const ADMIN_NAV = [
  { view: 'overview', label: 'Overview', href: '/admin/platform' },
  { view: 'events', label: 'Events', href: '/admin/events' },
  { view: 'users', label: 'Users', href: '/admin/users' },
  { view: 'organizers', label: 'Organizers', href: '/admin/organizers' },
  { view: 'categories', label: 'Sectors', href: '/admin/categories' },
  { view: 'venues', label: 'Venues', href: '/admin/venues' },
  { view: 'reviews', label: 'Reviews', href: '/admin/reviews' },
];

function AdminEventsWorkspace() {
  const query = useGetAdminEvents();
  const updateStatus = useUpdateAdminEventStatus();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'published' | 'draft' | 'pending'>('all');

  if (query.isLoading) return <LoadingState label="Loading platform events" />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;

  const events = (query.data ?? []).filter((e) => {
    const matchesSearch = !search || e.title.toLowerCase().includes(search.toLowerCase()) || e.organizer.toLowerCase().includes(search.toLowerCase()) || e.category.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || e.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="mt-8 space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3.5 top-3.5 text-muted-foreground" size={16} />
          <input
            type="text"
            placeholder="Search events, organizers, sectors..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-full border border-foreground/15 bg-card py-2.5 pl-10 pr-4 text-sm focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-2">
          {(['all', 'published', 'draft', 'pending'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-full px-3.5 py-1.5 text-xs font-semibold capitalize transition ${
                statusFilter === s ? 'bg-primary text-primary-foreground' : 'border border-foreground/15 bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-foreground/10 bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-foreground/10 bg-muted/30 font-mono-face text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-6 py-3.5">Event</th>
                <th className="px-6 py-3.5">Sector</th>
                <th className="px-6 py-3.5">Date & Time</th>
                <th className="px-6 py-3.5">Format & Price</th>
                <th className="px-6 py-3.5">Status</th>
                <th className="px-6 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-foreground/10">
              {events.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-muted-foreground">
                    No events matching filter criteria.
                  </td>
                </tr>
              ) : (
                events.map((e) => (
                  <tr key={e.id} className="transition hover:bg-muted/10">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-foreground">
                        <Link href={`/events/${e.slug}`} className="inline-flex items-center gap-1.5 hover:text-accent">
                          {e.title} <ExternalLink size={12} className="opacity-60" />
                        </Link>
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">{e.organizer}</div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-foreground">{e.category}</span>
                    </td>
                    <td className="px-6 py-4 text-xs text-muted-foreground">
                      <div>{String(e.startDate)}</div>
                      <div>{e.startTime}</div>
                    </td>
                    <td className="px-6 py-4 text-xs">
                      <span className="capitalize text-foreground">{e.format}</span>
                      <div className="text-muted-foreground">{money(e.price)}</div>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${
                          e.status === 'published'
                            ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                            : e.status === 'pending'
                            ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
                            : 'bg-zinc-500/15 text-zinc-600 dark:text-zinc-400'
                        }`}
                      >
                        {e.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="inline-flex items-center gap-2">
                        {e.status !== 'published' && (
                          <button
                            disabled={updateStatus.isPending}
                            onClick={() => updateStatus.mutate({ id: e.id, status: 'published' })}
                            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
                          >
                            Publish
                          </button>
                        )}
                        {e.status !== 'draft' && (
                          <button
                            disabled={updateStatus.isPending}
                            onClick={() => updateStatus.mutate({ id: e.id, status: 'draft' })}
                            className="rounded-lg border border-foreground/15 bg-card px-3 py-1.5 text-xs font-semibold text-muted-foreground transition hover:text-foreground disabled:opacity-50"
                          >
                            Draft
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-foreground/10 px-6 py-3 font-mono-face text-xs text-muted-foreground">
          Showing {events.length} of {query.data?.length ?? 0} events
        </div>
      </div>
    </div>
  );
}

function AdminUsersWorkspace() {
  const query = useGetAdminUsers();
  const updateRole = useUpdateAdminUserRole();
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<'all' | 'USER' | 'ORGANIZER' | 'ADMIN'>('all');

  if (query.isLoading) return <LoadingState label="Loading platform users" />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;

  const users = (query.data ?? []).filter((u) => {
    const matchesSearch = !search || u.name.toLowerCase().includes(search.toLowerCase()) || u.email.toLowerCase().includes(search.toLowerCase());
    const matchesRole = roleFilter === 'all' || u.role === roleFilter;
    return matchesSearch && matchesRole;
  });

  return (
    <div className="mt-8 space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3.5 top-3.5 text-muted-foreground" size={16} />
          <input
            type="text"
            placeholder="Search users by name, email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-full border border-foreground/15 bg-card py-2.5 pl-10 pr-4 text-sm focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-2">
          {(['all', 'USER', 'ORGANIZER', 'ADMIN'] as const).map((r) => (
            <button
              key={r}
              onClick={() => setRoleFilter(r)}
              className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
                roleFilter === r ? 'bg-primary text-primary-foreground' : 'border border-foreground/15 bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {r === 'all' ? 'All Roles' : r}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-foreground/10 bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-foreground/10 bg-muted/30 font-mono-face text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-6 py-3.5">ID</th>
                <th className="px-6 py-3.5">User</th>
                <th className="px-6 py-3.5">Email</th>
                <th className="px-6 py-3.5">Current Role</th>
                <th className="px-6 py-3.5 text-right">Assign Role</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-foreground/10">
              {users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    No users matching search filter.
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="transition hover:bg-muted/10">
                    <td className="px-6 py-4 font-mono-face text-xs text-muted-foreground">#{u.id}</td>
                    <td className="px-6 py-4">
                      <div className="font-semibold text-foreground">{u.name}</div>
                    </td>
                    <td className="px-6 py-4 font-mono-face text-xs text-muted-foreground">{u.email}</td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${
                          u.role === 'ADMIN'
                            ? 'bg-purple-500/15 text-purple-600 dark:text-purple-400'
                            : u.role === 'ORGANIZER'
                            ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400'
                            : 'bg-zinc-500/15 text-zinc-600 dark:text-zinc-400'
                        }`}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <select
                        value={u.role}
                        disabled={updateRole.isPending}
                        onChange={(e) => updateRole.mutate({ id: u.id, role: e.target.value as 'USER' | 'ORGANIZER' | 'ADMIN' })}
                        className="rounded-lg border border-foreground/15 bg-background px-3 py-1.5 text-xs font-medium focus:border-accent focus:outline-none"
                      >
                        <option value="USER">USER</option>
                        <option value="ORGANIZER">ORGANIZER</option>
                        <option value="ADMIN">ADMIN</option>
                      </select>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-foreground/10 px-6 py-3 font-mono-face text-xs text-muted-foreground">
          Showing {users.length} of {query.data?.length ?? 0} users
        </div>
      </div>
    </div>
  );
}

function AdminOrganizersWorkspace() {
  const query = useListOrganizers();
  const [search, setSearch] = useState('');

  if (query.isLoading) return <LoadingState label="Loading platform organizers" />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;

  const organizers = (query.data ?? []).filter((o) => {
    return !search || o.name.toLowerCase().includes(search.toLowerCase()) || o.slug.toLowerCase().includes(search.toLowerCase());
  });

  return (
    <div className="mt-8 space-y-6">
      <div className="relative max-w-sm">
        <Search className="absolute left-3.5 top-3.5 text-muted-foreground" size={16} />
        <input
          type="text"
          placeholder="Search organizers..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-full border border-foreground/15 bg-card py-2.5 pl-10 pr-4 text-sm focus:border-accent focus:outline-none"
        />
      </div>

      <div className="overflow-hidden rounded-2xl border border-foreground/10 bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-foreground/10 bg-muted/30 font-mono-face text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-6 py-3.5">Organizer</th>
                <th className="px-6 py-3.5">Slug</th>
                <th className="px-6 py-3.5">Rating</th>
                <th className="px-6 py-3.5">Events</th>
                <th className="px-6 py-3.5 text-right">View</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-foreground/10">
              {organizers.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    No organizers found.
                  </td>
                </tr>
              ) : (
                organizers.map((o) => (
                  <tr key={o.id} className="transition hover:bg-muted/10">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-foreground">{o.name}</div>
                      {o.description && <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{o.description}</div>}
                    </td>
                    <td className="px-6 py-4 font-mono-face text-xs text-muted-foreground">{o.slug}</td>
                    <td className="px-6 py-4 text-xs">
                      <div className="flex items-center gap-1 text-amber-500 font-semibold">
                        <Star size={12} fill="currentColor" /> {o.rating > 0 ? o.rating.toFixed(1) : 'New'}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-xs font-mono-face text-muted-foreground">
                      <span className="rounded-md bg-muted px-2 py-0.5 text-foreground">{o.eventCount ?? 0} events</span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link href={`/organizers/${o.slug}`} className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline">
                        Details <ArrowRight size={12} />
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-foreground/10 px-6 py-3 font-mono-face text-xs text-muted-foreground">
          Showing {organizers.length} of {query.data?.length ?? 0} organizers
        </div>
      </div>
    </div>
  );
}

function AdminCategoriesWorkspace() {
  const query = useListCategories();
  const [search, setSearch] = useState('');

  if (query.isLoading) return <LoadingState label="Loading sectors" />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;

  const sourceCategories = query.data ?? [];
  const categories = sourceCategories.filter((c) => {
    return !search || c.name.toLowerCase().includes(search.toLowerCase()) || c.slug.toLowerCase().includes(search.toLowerCase());
  });

  return (
    <div className="mt-8 space-y-6">
      <div className="relative max-w-sm">
        <Search className="absolute left-3.5 top-3.5 text-muted-foreground" size={16} />
        <input
          type="text"
          placeholder="Search sectors..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-full border border-foreground/15 bg-card py-2.5 pl-10 pr-4 text-sm focus:border-accent focus:outline-none"
        />
      </div>

      <div className="overflow-hidden rounded-2xl border border-foreground/10 bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-foreground/10 bg-muted/30 font-mono-face text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-6 py-3.5">Sector</th>
                <th className="px-6 py-3.5">Slug</th>
                <th className="px-6 py-3.5">Description</th>
                <th className="px-6 py-3.5 text-right">View</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-foreground/10">
              {categories.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-muted-foreground">
                    No sectors found.
                  </td>
                </tr>
              ) : (
                categories.map((c) => (
                  <tr key={c.id} className="transition hover:bg-muted/10">
                    <td className="px-6 py-4 font-semibold text-foreground">{c.name}</td>
                    <td className="px-6 py-4 font-mono-face text-xs text-muted-foreground">{c.slug}</td>
                    <td className="px-6 py-4 text-xs text-muted-foreground">{c.description || '—'}</td>
                    <td className="px-6 py-4 text-right">
                      <Link href={`/categories/${c.slug}`} className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline">
                        Explore <ArrowRight size={12} />
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-foreground/10 px-6 py-3 font-mono-face text-xs text-muted-foreground">
          Showing {categories.length} of {query.data?.length ?? 0} sectors
        </div>
      </div>
    </div>
  );
}

function AdminVenuesWorkspace() {
  const query = useListVenues();
  const [search, setSearch] = useState('');

  if (query.isLoading) return <LoadingState label="Loading venues" />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;

  const venues = (query.data ?? []).filter((v) => {
    return !search || v.name.toLowerCase().includes(search.toLowerCase()) || (v.address && v.address.toLowerCase().includes(search.toLowerCase()));
  });

  return (
    <div className="mt-8 space-y-6">
      <div className="relative max-w-sm">
        <Search className="absolute left-3.5 top-3.5 text-muted-foreground" size={16} />
        <input
          type="text"
          placeholder="Search venues by name, address..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-full border border-foreground/15 bg-card py-2.5 pl-10 pr-4 text-sm focus:border-accent focus:outline-none"
        />
      </div>

      <div className="overflow-hidden rounded-2xl border border-foreground/10 bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-foreground/10 bg-muted/30 font-mono-face text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-6 py-3.5">Venue</th>
                <th className="px-6 py-3.5">Slug</th>
                <th className="px-6 py-3.5">Address</th>
                <th className="px-6 py-3.5 text-right">View</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-foreground/10">
              {venues.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-muted-foreground">
                    No venues found.
                  </td>
                </tr>
              ) : (
                venues.map((v) => (
                  <tr key={v.id} className="transition hover:bg-muted/10">
                    <td className="px-6 py-4 font-semibold text-foreground">{v.name}</td>
                    <td className="px-6 py-4 font-mono-face text-xs text-muted-foreground">{v.slug}</td>
                    <td className="px-6 py-4 text-xs text-muted-foreground">{v.address || '—'}</td>
                    <td className="px-6 py-4 text-right">
                      <Link href={`/venues/${v.slug}`} className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline">
                        Details <ArrowRight size={12} />
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-foreground/10 px-6 py-3 font-mono-face text-xs text-muted-foreground">
          Showing {venues.length} of {query.data?.length ?? 0} venues
        </div>
      </div>
    </div>
  );
}

function AdminReviewsWorkspace() {
  const query = useGetAdminReviews();
  const deleteReview = useDeleteAdminReview();
  const [search, setSearch] = useState('');
  const [ratingFilter, setRatingFilter] = useState<number | 0>(0);

  if (query.isLoading) return <LoadingState label="Loading reviews" />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;

  const reviews = (query.data ?? []).filter((r) => {
    const matchesSearch = !search || r.author.toLowerCase().includes(search.toLowerCase()) || r.title.toLowerCase().includes(search.toLowerCase()) || r.comment.toLowerCase().includes(search.toLowerCase()) || r.eventTitle.toLowerCase().includes(search.toLowerCase());
    const matchesRating = ratingFilter === 0 || r.rating === ratingFilter;
    return matchesSearch && matchesRating;
  });

  return (
    <div className="mt-8 space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-3.5 top-3.5 text-muted-foreground" size={16} />
          <input
            type="text"
            placeholder="Search reviews by author, event, comments..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-full border border-foreground/15 bg-card py-2.5 pl-10 pr-4 text-sm focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setRatingFilter(0)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
              ratingFilter === 0 ? 'bg-primary text-primary-foreground' : 'border border-foreground/15 bg-card text-muted-foreground hover:text-foreground'
            }`}
          >
            All Ratings
          </button>
          {[5, 4, 3, 2, 1].map((stars) => (
            <button
              key={stars}
              onClick={() => setRatingFilter(stars)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                ratingFilter === stars ? 'bg-primary text-primary-foreground' : 'border border-foreground/15 bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {stars} ★
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-foreground/10 bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-foreground/10 bg-muted/30 font-mono-face text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="px-6 py-3.5">Reviewer</th>
                <th className="px-6 py-3.5">Event</th>
                <th className="px-6 py-3.5">Rating</th>
                <th className="px-6 py-3.5">Title & Comment</th>
                <th className="px-6 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-foreground/10">
              {reviews.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-muted-foreground">
                    No reviews found.
                  </td>
                </tr>
              ) : (
                reviews.map((r) => (
                  <tr key={r.id} className="transition hover:bg-muted/10">
                    <td className="px-6 py-4 font-semibold text-foreground">{r.author}</td>
                    <td className="px-6 py-4 text-xs font-medium text-accent">
                      <Link href={`/events/${r.eventId}`} className="hover:underline">
                        {r.eventTitle}
                      </Link>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-0.5 text-amber-500">
                        {Array.from({ length: r.rating }).map((_, i) => (
                          <Star key={i} size={13} fill="currentColor" />
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-xs">
                      <div className="font-semibold text-foreground">{r.title}</div>
                      <div className="mt-0.5 text-muted-foreground line-clamp-2">{r.comment}</div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        disabled={deleteReview.isPending}
                        onClick={() => {
                          if (window.confirm('Are you sure you want to delete this review?')) {
                            deleteReview.mutate(r.id);
                          }
                        }}
                        className="rounded-lg p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition disabled:opacity-50"
                        title="Delete Review"
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-foreground/10 px-6 py-3 font-mono-face text-xs text-muted-foreground">
          Showing {reviews.length} of {query.data?.length ?? 0} reviews
        </div>
      </div>
    </div>
  );
}

function AdminPage({ view = 'overview' }: { view?: string }) {
  const query = useGetAdminDashboard();
  if (query.isLoading) return <LoadingState label="Loading admin console" />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;
  const d = query.data;
  const cards = [
    ['Users', d?.users ?? 0, UserRound],
    ['Events', d?.events ?? 0, CalendarDays],
    ['Organizers', d?.organizers ?? 0, ShieldCheck],
    ['Reviews', d?.reviews ?? 0, Star],
  ];
  return (
    <div className="page-enter">
      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Admin / Platform data / {view}</p>
          <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em]">
            {view === 'overview' ? 'Keep the signal clean.' : `Manage ${view}.`}
          </h1>
        </div>
        <ShieldCheck className="hidden text-accent sm:block" size={30} />
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2 border-b border-foreground/10 pb-4">
        {ADMIN_NAV.map((tab) => (
          <Link
            key={tab.view}
            href={tab.href}
            className={`rounded-full px-4 py-2 text-xs font-semibold transition ${
              view === tab.view
                ? 'bg-accent text-accent-foreground font-bold'
                : 'border border-foreground/15 bg-card text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab.label}
          </Link>
        ))}
        <Link
          href="/admin"
          className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-4 py-2 text-xs font-semibold text-accent hover:bg-accent hover:text-accent-foreground transition"
        >
          Operations Dashboard <ArrowRight size={12} />
        </Link>
      </div>

      <div className="mt-8 grid gap-3 sm:grid-cols-4">
        {cards.map(([label, value, Icon]) => (
          <Metric key={label as string} label={label as string} value={value as number} icon={Icon as typeof Heart} />
        ))}
      </div>

      {view === 'overview' && (
        <div className="mt-12 grid gap-5 lg:grid-cols-2">
          <div className="rounded-2xl border border-foreground/10 bg-card p-6">
            <div className="flex items-center justify-between">
              <p className="font-mono-face text-[10px] uppercase tracking-[.15em] text-accent">Popular sectors</p>
              <Link href="/admin/categories" className="font-mono-face text-[10px] text-accent hover:underline flex items-center gap-1">
                View all sectors <ArrowRight size={10} />
              </Link>
            </div>
            <div className="mt-5 space-y-3">
              {(d?.popularCategories ?? []).map((name) => (
                <div key={name} className="flex items-center justify-between border-b border-foreground/10 pb-3 text-sm">
                  <span>{name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {view === 'events' && <AdminEventsWorkspace />}
      {view === 'users' && <AdminUsersWorkspace />}
      {view === 'organizers' && <AdminOrganizersWorkspace />}
      {view === 'categories' && <AdminCategoriesWorkspace />}
      {view === 'venues' && <AdminVenuesWorkspace />}
      {view === 'reviews' && <AdminReviewsWorkspace />}
    </div>
  );
}

function NotFoundPage() {
  return (
    <div className="mx-auto max-w-xl px-5 py-32 text-center">
      <p className="font-mono-face text-xs uppercase tracking-[.2em] text-accent">404 / Off the map</p>
      <h1 className="mt-5 font-display text-6xl font-extrabold tracking-[-.07em]">Wrong room.</h1>
      <p className="mt-4 text-muted-foreground">This page does not exist, but something interesting probably does.</p>
      <Link href="/events" className="mt-8 inline-flex items-center gap-2 rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground" data-testid="link-404-explore">
        Explore events <ArrowRight size={16} />
      </Link>
    </div>
  );
}

function Router() {
  const [location] = useLocation();
  return (
    <ErrorBoundary resetKey={location}>
      <Switch>
        <Route path="/" component={HomePage} />
        <Route path="/events" component={EventsPage} />
        <Route path="/events/:slug/register" component={() => <RoleGate allow={['attendee', 'admin']}><RegisterPage /></RoleGate>} />
        <Route path="/events/:slug" component={EventDetailPage} />
        <Route path="/categories" component={() => <DirectoryListPage kind="categories" />} />
        <Route path="/categories/:slug" component={() => <DirectoryDetailPage kind="category" />} />
        <Route path="/cities" component={() => <DirectoryListPage kind="cities" />} />
        <Route path="/cities/:slug" component={() => <DirectoryDetailPage kind="city" />} />
        <Route path="/organizers" component={() => <DirectoryListPage kind="organizers" />} />
        <Route path="/organizers/:slug" component={OrganizerDetailPage} />
        <Route path="/venues" component={() => <DirectoryListPage kind="venues" />} />
        <Route path="/venues/:slug" component={VenueDetailPage} />
        <Route path="/speakers/:slug" component={SpeakerPage} />
        <Route path="/login" component={() => <AuthPage mode="login" />} />
        <Route path="/register" component={() => <AuthPage mode="register" />} />
        <Route path="/forgot-password" component={() => <AuthPage mode="forgot" />} />

        {/* Attendee Experience Dashboard Routes */}
        <Route path="/dashboard" component={() => <AttendeeArea tab="overview" />} />
        <Route path="/dashboard/discover" component={() => <AttendeeArea tab="discover" />} />
        <Route path="/dashboard/profile" component={() => <AttendeeArea tab="profile" />} />
        <Route path="/dashboard/schedule" component={() => <AttendeeArea tab="schedule" />} />
        <Route path="/dashboard/networking" component={() => <AttendeeArea tab="networking" />} />
        <Route path="/dashboard/registrations" component={() => <AttendeeArea tab="registrations" />} />
        <Route path="/dashboard/saved-events" component={() => <AttendeeArea tab="saved-events" />} />
        <Route path="/dashboard/recommendations" component={() => <AttendeeArea tab="recommendations" />} />
        <Route path="/dashboard/preferences" component={() => <AttendeeArea tab="preferences" />} />
        <Route path="/dashboard/assistant" component={() => <AttendeeArea tab="assistant" />} />
        <Route path="/dashboard/notifications" component={() => <AttendeeArea tab="notifications" />} />
        <Route path="/dashboard/settings" component={() => <Redirect to="/dashboard/profile" replace />} />

        {/* Organizer Desk */}
        <Route path="/organizer" component={() => <OrganiserArea tab="overview" />} />
        <Route path="/organizer/events" component={() => <OrganiserArea tab="events" />} />
        <Route path="/organizer/events/create" component={() => <OrganiserArea tab="create" />} />
        <Route path="/organizer/analytics" component={() => <OrganiserArea tab="analytics" />} />
        <Route path="/organizer/profile" component={() => <OrganiserArea tab="profile" />} />

        {/* Admin Console — Organizer Discovery, Outreach, Trust Agent 3, Attendee Agent & n8n Automations */}
        <Route path="/admin" component={() => <OpsLayout><OpsDashboardPage /></OpsLayout>} />
        <Route path="/admin/observability" component={() => <OpsLayout><ObservabilityPage /></OpsLayout>} />
        <Route path="/privacy" component={() => <PrivacyPolicyPage />} />
        <Route path="/terms" component={() => <TermsOfServicePage />} />
        <Route path="/verify-email" component={() => <VerifyEmailPage />} />
        <Route path="/reset-password" component={() => <ResetPasswordPage />} />
        <Route path="/admin/automations" component={() => <OpsLayout><AutomationsPage /></OpsLayout>} />
        <Route path="/admin/community-discovery" component={() => <Redirect to="/admin/automations" />} />
        <Route path="/admin/community-promotion" component={() => <Redirect to="/admin/automations" />} />
        <Route path="/admin/social-promotions" component={() => <OpsLayout><SocialPromotionsPage /></OpsLayout>} />
        <Route path="/admin/trust-review" component={() => <OpsLayout><TrustReviewPage /></OpsLayout>} />
        <Route path="/admin/attendee-agent" component={() => <Redirect to="/admin/automations" />} />
        <Route path="/admin/workflows" component={() => <OpsLayout><WorkflowsLogsPage mode="workflows" /></OpsLayout>} />
        <Route path="/admin/audit-logs" component={() => <OpsLayout><WorkflowsLogsPage mode="audit" /></OpsLayout>} />
        <Route path="/admin/acquisition" component={() => <Redirect to="/admin" />} />
        <Route path="/acquisition-agent" component={() => <Redirect to="/admin" />} />
        <Route path="/discovery" component={() => <Redirect to="/admin/discovery" />} />
        <Route path="/admin/discovery" component={() => <OpsLayout><DiscoveryPage mode="new" /></OpsLayout>} />
        <Route path="/admin/discovery/events" component={() => <OpsLayout><DiscoveryPage mode="events" /></OpsLayout>} />
        <Route path="/admin/discovery/organizers" component={() => <OpsLayout><OrganizersPage /></OpsLayout>} />
        <Route path="/admin/discovery/organizers/:id" component={() => <OpsLayout><OrganizerProfilePage /></OpsLayout>} />
        <Route path="/admin/discovery/contacts" component={() => <OpsLayout><ContactsPage /></OpsLayout>} />
        <Route path="/admin/outreach" component={() => <OpsLayout><OutreachPage /></OpsLayout>} />
        <Route path="/admin/outreach/:tab" component={() => <OpsLayout><OutreachPage /></OpsLayout>} />
        {/* Discover events: guided run, automatic schedule, history and reports, configuration */}
        <Route path="/admin/discover" component={() => <OpsLayout><RunWizardPage /></OpsLayout>} />
        <Route path="/admin/discover/automatic" component={() => <OpsLayout><AutomaticDiscoveryPage /></OpsLayout>} />
        <Route path="/admin/discover/configuration" component={() => <OpsLayout><DiscoveryConfigPage /></OpsLayout>} />
        <Route path="/admin/discover/runs" component={() => <OpsLayout><ActivityPage /></OpsLayout>} />
        <Route path="/admin/discover/runs/:id" component={() => <OpsLayout><RunReportPage /></OpsLayout>} />
        {/* Old "Agent Activity" URL — run history now lives under Discover events. */}
        <Route path="/admin/activity" component={() => <Redirect to="/admin/discover/runs" replace />} />
        <Route path="/admin/settings" component={() => <OpsLayout><SettingsPage /></OpsLayout>} />
        {/* Platform data moderation — admin-guarded and listed in the admin side navigation via OpsLayout */}
        <Route path="/admin/platform" component={() => <OpsLayout><AdminPage view="overview" /></OpsLayout>} />
        <Route path="/admin/events" component={() => <OpsLayout><AdminPage view="events" /></OpsLayout>} />
        <Route path="/admin/users" component={() => <OpsLayout><AdminPage view="users" /></OpsLayout>} />
        <Route path="/admin/organizers" component={() => <OpsLayout><AdminPage view="organizers" /></OpsLayout>} />
        <Route path="/admin/categories" component={() => <OpsLayout><AdminPage view="categories" /></OpsLayout>} />
        <Route path="/admin/venues" component={() => <OpsLayout><AdminPage view="venues" /></OpsLayout>} />
        <Route path="/admin/reviews" component={() => <OpsLayout><AdminPage view="reviews" /></OpsLayout>} />

        <Route component={NotFoundPage} />
      </Switch>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
          <Shell>
            <Router />
          </Shell>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
