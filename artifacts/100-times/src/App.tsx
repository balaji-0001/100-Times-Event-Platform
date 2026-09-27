import { type FormEvent, type ReactNode, useMemo, useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowDownRight, ArrowLeft, ArrowRight, Bell, CalendarDays, CalendarPlus, Check, CheckCheck,
  Compass, Download, ExternalLink, Filter, Heart, LayoutDashboard,
  LineChart, ListFilter, Loader2, LockKeyhole, LogOut, MapPin, Menu, MessageSquare, Plus, Printer, Edit3, ChevronDown, ChevronUp, AlertCircle, Eye, EyeOff,
  QrCode, Search, Send, Settings2, Share2, ShieldCheck, Sparkles, Star, Ticket, Trash2,
  TrendingUp, UserCheck, UserPlus, UserRound, Users, X, Zap,
  Copy, ShieldAlert, Bot, ThumbsUp, ThumbsDown, CheckCircle2, Globe, Play, RefreshCw,
} from 'lucide-react';
import {
  getGetCategoryQueryKey, getGetCityQueryKey, getGetDashboardQueryKey,
  getGetEventQueryKey, getGetOrganizerQueryKey, getGetSavedEventsQueryKey,
  getGetSpeakerQueryKey, getGetVenueQueryKey, getListEventsQueryKey,
  useCreateOrganizerEvent, useCreateReview, useGetAdminDashboard, useGetCategory,
  useGetCity, useGetDashboard, useGetEvent, useGetHome, useGetNotifications,
  useGetOrganizer, useGetOrganizerAnalytics, useGetOrganizerDashboard,
  useGetOrganizerEvents, useGetSavedEvents, useGetRegistrations, useGetSpeaker,
  useGetVenue, useHealthCheck, useListCategories, useListCities, useListEvents,
  useListOrganizers, useListVenues, useLogin, useRegisterForEvent, useRegisterUser,
  useSaveEvent, useUnsaveEvent, customFetch,
} from '@workspace/api-client-react';
import type {
  Category, City, DirectoryDetail, EventCard, EventDetail, EventInput,
  ListEventsParams, Organizer, OrganizerDetail, RegistrationInput, ReviewInput,
  Venue, VenueDetail,
} from '@workspace/api-client-react';
import { Link, Redirect, Route, Switch, Router as WouterRouter, useLocation, useParams } from 'wouter';
import { ErrorBoundary } from '@/components/error-boundary';
import { OpsLayout } from '@/ops/OpsLayout';
import { DashboardPage as OpsDashboardPage } from '@/ops/DashboardPage';
import { DiscoveryPage } from '@/ops/DiscoveryPage';
import { OrganizersPage } from '@/ops/OrganizersPage';
import { OrganizerProfilePage } from '@/ops/OrganizerProfilePage';
import { ContactsPage } from '@/ops/ContactsPage';
import { OutreachPage } from '@/ops/OutreachPage';
import { ActivityPage } from '@/ops/ActivityPage';
import { SettingsPage } from '@/ops/SettingsPage';
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


export interface AIEventMatch {
  event: EventCard;
  matchScore: number;
  matchReason: string;
  tags: string[];
}

export interface AIConciergeResponse {
  reply: string;
  suggestedQueries: string[];
  matchedEvents: AIEventMatch[];
}

export interface AIPeerMatch {
  attendee: AttendeeProfile;
  matchScore: number;
  matchReason: string;
  mutualInterests: string[];
}

export interface AIEventBrief {
  eventId: number;
  title: string;
  summary: string;
  keyTakeaways: string[];
  targetAudience: string[];
  recommendedRole: string;
  highlightSession?: string | null;
}

export interface PersonalizedRecommendations {
  headline: string;
  userContext: string;
  items: AIEventMatch[];
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

function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name?: string; jobTitle?: string; company?: string; bio?: string; country?: string }) =>
      customFetch('/api/dashboard/profile', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: getGetDashboardQueryKey() });
      qc.invalidateQueries({ queryKey: ['registrations'] });
    },
  });
}



function useLogout() {
  const qc = useQueryClient();
  const [, setLocation] = useLocation();
  return useMutation({
    mutationFn: () => customFetch<{ status: string; message: string }>('/api/auth/logout', { method: 'POST' }),
    onSettled: () => {
      localStorage.removeItem('100-times-auth-token');
      qc.clear();
      setLocation('/login');
    },
  });
}

function useUpdateOrganizerEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<EventInput> & { status?: string } }) =>
      customFetch<EventCard>(`/api/organizer/events/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organizer', 'events'] });
      qc.invalidateQueries({ queryKey: ['organizer', 'dashboard'] });
      qc.invalidateQueries({ queryKey: getListEventsQueryKey() });
    },
  });
}

function useDeleteOrganizerEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      customFetch<{ status: string; message: string }>(`/api/organizer/events/${id}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['organizer', 'events'] });
      qc.invalidateQueries({ queryKey: ['organizer', 'dashboard'] });
      qc.invalidateQueries({ queryKey: getListEventsQueryKey() });
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

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

function useAIConcierge() {
  return useMutation({
    mutationFn: (query: string) =>
      customFetch<AIConciergeResponse>('/api/ai/concierge', {
        method: 'POST',
        body: JSON.stringify({ query }),
      }),
  });
}

function useGetRecommendations(limit = 6) {
  return useQuery({
    queryKey: ['ai-recommendations', limit],
    queryFn: () => customFetch<PersonalizedRecommendations>(`/api/ai/recommendations?limit=${limit}`),
  });
}

function useGetPeerMatches() {
  return useQuery({
    queryKey: ['ai-peer-matches'],
    queryFn: () => customFetch<AIPeerMatch[]>('/api/ai/peer-matches'),
  });
}

function useGetEventBrief(eventId: number) {
  return useQuery({
    queryKey: ['ai-event-brief', eventId],
    queryFn: () => customFetch<AIEventBrief>(`/api/ai/events/${eventId}/brief`),
    enabled: Boolean(eventId),
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
  const cleanDate = (d: string) => d.replaceAll('-', '');
  const start = cleanDate(event.startDate || new Date().toISOString().split('T')[0]);
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
    `DESCRIPTION:${(event.description || 'Your confirmed pass with 100 TIMES.').replace(/\n/g, ' ')}`,
    `LOCATION:${(event.location || '100 TIMES Event Venue').replace(/[,;]/g, ' ')}`,
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
  const vevents = items.map((item, i) => {
    const cleanDate = item.eventDate.replaceAll('-', '') || '20250315';
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
  const start = cleanDate(event.startDate || new Date().toISOString().split('T')[0]);
  const end = event.endDate ? cleanDate(event.endDate) : start;
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: event.title,
    dates: `${start}/${end}`,
    details: event.description || 'Confirmed event on 100 TIMES',
    location: event.location || '',
  });
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

  const ticketCode = reg.ticketCode || `100T-${reg.eventId.toString().padStart(4, '0')}-${reg.id.toString().padStart(5, '0')}`;
  const qrString = reg.qrCode || `100TIMES:EVENT=${reg.eventSlug}:REG=${ticketCode}:TIER=${reg.ticketType}`;
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
          <p className="font-mono-face text-[10px] uppercase tracking-[.18em] text-accent">Confirmed Attendee</p>
          <h2 className="mt-1 font-display text-3xl font-bold tracking-tight">{reg.userName || 'Aarav Mehta'}</h2>
          {(reg.jobTitle || reg.company) && (
            <p className="mt-1 text-sm font-medium text-muted-foreground">
              {reg.jobTitle}{reg.jobTitle && reg.company && ' · '}{reg.company}
            </p>
          )}
        </div>

        <div className="my-6 flex justify-center">
          <div className="rounded-2xl border border-foreground/15 bg-muted/40 p-4 text-center">
            <QRCodeSvg value={qrString} size={150} />
            <p className="mt-3 font-mono-face text-[11px] font-bold tracking-widest text-foreground">{ticketCode}</p>
          </div>
        </div>

        <div className="space-y-3 rounded-2xl border border-foreground/10 bg-background/80 p-4 text-xs">
          <div>
            <p className="font-mono-face text-[9px] uppercase tracking-widest text-muted-foreground">Event</p>
            <p className="font-semibold text-foreground">{reg.eventTitle}</p>
          </div>
          <div className="flex justify-between">
            <div>
              <p className="font-mono-face text-[9px] uppercase tracking-widest text-muted-foreground">Date & Time</p>
              <p className="font-semibold text-foreground">{reg.eventStartDate ? fmtDate(reg.eventStartDate) : 'Coming soon'}</p>
            </div>
            <div className="text-right">
              <p className="font-mono-face text-[9px] uppercase tracking-widest text-muted-foreground">Venue</p>
              <p className="font-semibold text-foreground">{reg.eventVenue || reg.eventLocation || 'Main Arena'}</p>
            </div>
          </div>
        </div>

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

        <button
          onClick={() => window.print()}
          className="button-press mt-2.5 flex w-full items-center justify-center gap-2 rounded-full bg-primary py-3 text-xs font-bold text-primary-foreground hover:bg-accent"
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

// ---------------------------------------------------------------------------
// Fallback demo data
// ---------------------------------------------------------------------------

const fallbackEvents: EventCard[] = [
  { id: 101, title: 'The Design of Everything', slug: 'the-design-of-everything', eventType: 'Conference', category: 'Design', categorySlug: 'design', startDate: '2025-02-12', endDate: '2025-02-14', startTime: '09:00', location: 'Bengaluru', venue: 'NIMHANS Convention Centre', organizer: 'Kyoorius', image: '', rating: 4.8, attendeeCount: 840, price: 4200, format: 'in-person', isSaved: false, status: 'published' },
  { id: 102, title: 'India Energy Week', slug: 'india-energy-week', eventType: 'Trade show', category: 'Energy', categorySlug: 'energy', startDate: '2025-02-11', endDate: '2025-02-14', startTime: '10:00', location: 'New Delhi', venue: 'Yashobhoomi', organizer: 'DMG Events', image: '', rating: 4.6, attendeeCount: 1200, price: 0, format: 'in-person', isSaved: true, status: 'published' },
  { id: 103, title: 'Future of Work: Mumbai', slug: 'future-of-work-mumbai', eventType: 'Summit', category: 'Business', categorySlug: 'business', startDate: '2025-03-05', endDate: '2025-03-05', startTime: '08:30', location: 'Mumbai', venue: 'Taj Lands End', organizer: 'The Ken', image: '', rating: 4.9, attendeeCount: 330, price: 1800, format: 'in-person', isSaved: false, status: 'published' },
  { id: 104, title: 'Objects of Desire', slug: 'objects-of-desire', eventType: 'Exhibition', category: 'Art & Culture', categorySlug: 'art-culture', startDate: '2025-02-20', endDate: '2025-03-02', startTime: '11:00', location: 'New Delhi', venue: 'Kiran Nadar Museum of Art', organizer: 'India Art Fair', image: '', rating: 4.7, attendeeCount: 560, price: 300, format: 'in-person', isSaved: false, status: 'published' },
];
const fallbackCategories: Category[] = [
  { id: 1, name: 'Design & Creative', slug: 'design', description: 'Ideas, craft, culture, and the people making what is next.', icon: '✦', eventCount: 128 },
  { id: 2, name: 'Business & Strategy', slug: 'business', description: 'Sharp rooms for ambitious operators and clear thinkers.', icon: '↗', eventCount: 94 },
  { id: 3, name: 'Technology', slug: 'technology', description: 'Build the future with the people closest to the work.', icon: '⌘', eventCount: 186 },
  { id: 4, name: 'Art & Culture', slug: 'art-culture', description: 'Exhibitions, conversations, and new ways of seeing.', icon: '◌', eventCount: 73 },
];
const fallbackCities: City[] = [
  { id: 1, name: 'Bengaluru', slug: 'bengaluru', country: 'India', image: '', eventCount: 218 },
  { id: 2, name: 'Mumbai', slug: 'mumbai', country: 'India', image: '', eventCount: 164 },
  { id: 3, name: 'New Delhi', slug: 'new-delhi', country: 'India', image: '', eventCount: 143 },
  { id: 4, name: 'Singapore', slug: 'singapore', country: 'Singapore', image: '', eventCount: 87 },
];

const cx = (...values: Array<string | false | null | undefined>) => values.filter(Boolean).join(' ');
const fmtDate = (value?: string) => value ? new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value)) : 'Date to be announced';
const money = (value?: number) => value === 0 ? 'Free' : value ? `₹${value.toLocaleString('en-IN')}` : 'Price on request';


// ---------------------------------------------------------------------------
// AI Suite Components
// ---------------------------------------------------------------------------

function AIConciergeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [history, setHistory] = useState<Array<{ sender: 'user' | 'ai'; text: string; events?: AIEventMatch[]; suggested?: string[] }>>([
    {
      sender: 'ai',
      text: 'Hello! I am your 100 TIMES AI Event Concierge. Ask me for tailored event recommendations, specific cities, topics, budget constraints, or formats.',
      suggested: [
        'Find AI summits in Bengaluru under ₹3000',
        'Show top design conferences with networking',
        'Free tech workshops this month',
        'Recommend summits for Product Architects',
      ],
    },
  ]);

  const conciergeMutation = useAIConcierge();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  }, [open, history]);

  if (!open) return null;

  const handleSend = (userText: string) => {
    const trimmed = userText.trim();
    if (!trimmed || conciergeMutation.isPending) return;

    setHistory((prev) => [...prev, { sender: 'user', text: trimmed }]);
    setQuery('');

    conciergeMutation.mutate(trimmed, {
      onSuccess: (res) => {
        setHistory((prev) => [
          ...prev,
          {
            sender: 'ai',
            text: res.reply,
            events: res.matchedEvents,
            suggested: res.suggestedQueries,
          },
        ]);
      },
      onError: () => {
        setHistory((prev) => [
          ...prev,
          {
            sender: 'ai',
            text: 'I ran into an issue connecting with the event signal. Please try another query!',
          },
        ]);
      },
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-md">
      <div className="flex h-[85vh] w-full max-w-3xl flex-col rounded-3xl border border-accent/30 bg-background shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-foreground/10 bg-secondary/50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-2xl bg-accent text-accent-foreground">
              <Sparkles size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-bold">100 TIMES AI Concierge</h2>
                <span className="rounded-full bg-accent/20 px-2 py-0.5 font-mono-face text-[9px] font-bold text-accent">Smart Assistant</span>
              </div>
              <p className="text-xs text-muted-foreground">Natural language discovery across 100+ high-signal events</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-full border border-foreground/10 text-muted-foreground hover:bg-muted"
            data-testid="button-close-ai-modal"
          >
            <X size={16} />
          </button>
        </div>

        {/* Chat Feed */}
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {history.map((msg, i) => (
            <div key={i} className={cx('flex flex-col', msg.sender === 'user' ? 'items-end' : 'items-start')}>
              <div
                className={cx(
                  'max-w-[88%] rounded-2xl p-4 text-sm leading-relaxed',
                  msg.sender === 'user'
                    ? 'bg-primary text-primary-foreground rounded-br-none'
                    : 'border border-foreground/10 bg-card text-foreground rounded-bl-none shadow-sm'
                )}
              >
                {msg.sender === 'ai' && (
                  <div className="mb-1.5 flex items-center gap-1.5 font-mono-face text-[10px] font-bold text-accent">
                    <Sparkles size={12} /> 100 TIMES AI
                  </div>
                )}
                <p>{msg.text}</p>

                {/* Render Matched Event Cards if available */}
                {msg.events && msg.events.length > 0 && (
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    {msg.events.map((match: AIEventMatch) => (
                      <div
                        key={match.event.id}
                        className="flex flex-col justify-between rounded-xl border border-foreground/10 bg-background/80 p-3.5 hover:border-accent/50"
                      >
                        <div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="rounded-full bg-accent/15 px-2 py-0.5 font-mono-face text-[9px] font-bold text-accent">
                              ✦ {match.matchScore}% Match
                            </span>
                            <span className="font-mono-face text-[9px] text-muted-foreground">{match.event.location}</span>
                          </div>
                          <h4 className="mt-2 font-display text-sm font-bold leading-snug line-clamp-1">{match.event.title}</h4>
                          <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2">{match.matchReason}</p>
                        </div>
                        <div className="mt-3 flex items-center justify-between border-t border-foreground/10 pt-2 text-[11px]">
                          <span className="font-mono-face font-bold">
                            {match.event.price === 0 ? 'Free' : `₹${match.event.price}`}
                          </span>
                          <Link
                            href={`/events/${match.event.slug}`}
                            onClick={onClose}
                            className="inline-flex items-center gap-1 font-semibold text-accent hover:underline"
                          >
                            View Event <ArrowRight size={11} />
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Render Suggested Queries if available */}
                {msg.suggested && msg.suggested.length > 0 && (
                  <div className="mt-4">
                    <p className="font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Suggested Inquiries:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.suggested.map((sug, sIdx) => (
                        <button
                          key={sIdx}
                          onClick={() => handleSend(sug)}
                          className="rounded-full border border-foreground/15 bg-background px-3 py-1 text-xs text-muted-foreground hover:border-accent hover:bg-accent/10 hover:text-accent"
                        >
                          {sug}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          {conciergeMutation.isPending && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono-face">
              <Loader2 size={14} className="animate-spin text-accent" />
              100 TIMES AI is analyzing the event catalog and scoring matches...
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(query);
          }}
          className="border-t border-foreground/10 bg-card p-4"
        >
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask anything: e.g. 'Show AI summits in Bengaluru under ₹3000'..."
              className="flex-1 rounded-full border border-foreground/15 bg-background px-5 py-3 text-sm focus:border-accent focus:outline-none"
              data-testid="input-ai-concierge"
            />
            <button
              type="submit"
              disabled={!query.trim() || conciergeMutation.isPending}
              className="button-press inline-flex items-center gap-2 rounded-full bg-accent px-6 py-3 font-display text-sm font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground disabled:opacity-40"
              data-testid="button-submit-ai-concierge"
            >
              {conciergeMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              <span>Search</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function AIEventBriefCard({ eventId }: { eventId: number }) {
  const briefQuery = useGetEventBrief(eventId);
  if (briefQuery.isLoading) return null;
  const brief = briefQuery.data;
  if (!brief) return null;

  return (
    <div className="mt-8 rounded-3xl border border-accent/30 bg-gradient-to-br from-accent/10 via-card to-background p-6 lg:p-8" data-testid="card-ai-event-brief">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-foreground/10 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-xl bg-accent text-accent-foreground">
            <Sparkles size={16} />
          </div>
          <div>
            <h3 className="font-display text-lg font-bold">100 TIMES AI Executive Brief</h3>
            <p className="text-xs text-muted-foreground">Automated intelligence & key learning outcomes</p>
          </div>
        </div>
        <span className="rounded-full bg-accent/20 px-3 py-1 font-mono-face text-[10px] font-bold text-accent">
          ✦ Role Fit: {brief.recommendedRole}
        </span>
      </div>

      <p className="mt-4 text-sm leading-6 text-foreground/90">{brief.summary}</p>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div>
          <h4 className="font-mono-face text-xs font-bold uppercase tracking-wider text-accent mb-3">Key Takeaways</h4>
          <ul className="space-y-2 text-xs leading-5 text-muted-foreground">
            {brief.keyTakeaways.map((takeaway, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-accent mt-0.5">✦</span>
                <span>{takeaway}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="font-mono-face text-xs font-bold uppercase tracking-wider text-accent mb-3">Target Audience</h4>
          <div className="flex flex-wrap gap-1.5">
            {brief.targetAudience.map((aud, i) => (
              <span key={i} className="rounded-lg border border-foreground/10 bg-background px-2.5 py-1 text-xs text-muted-foreground font-medium">
                {aud}
              </span>
            ))}
          </div>
          {brief.highlightSession && (
            <div className="mt-4 rounded-xl bg-secondary/60 p-3">
              <p className="font-mono-face text-[10px] uppercase tracking-wider text-secondary-foreground/70">Highlight Session</p>
              <p className="mt-1 text-xs font-semibold text-secondary-foreground">{brief.highlightSession}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AIRecommendationsSection() {
  const recommendationsQuery = useGetRecommendations(4);
  const data = recommendationsQuery.data;
  if (recommendationsQuery.isLoading || !data || data.items.length === 0) return null;

  return (
    <section className="mx-auto mt-24 max-w-[1440px] px-5 lg:px-10" data-testid="section-ai-recommendations">
      <div className="flex flex-col justify-between gap-4 border-b border-foreground/10 pb-4 sm:flex-row sm:items-end">
        <div>
          <div className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-lg bg-accent text-accent-foreground font-bold text-xs">✦</span>
            <p className="font-mono-face text-xs uppercase tracking-[.2em] text-accent">Smart Match Engine</p>
          </div>
          <h2 className="mt-2 font-display text-3xl font-extrabold tracking-tight lg:text-4xl">{data.headline}</h2>
          <p className="mt-1 text-xs text-muted-foreground">{data.userContext}</p>
        </div>
        <Link href="/events?view=recommended" className="font-mono-face text-xs font-bold text-accent hover:underline inline-flex items-center gap-1">
          Explore All Matches <ArrowRight size={13} />
        </Link>
      </div>

      <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {data.items.map((item: AIEventMatch) => (
          <div key={item.event.id} className="relative flex flex-col justify-between rounded-2xl border border-accent/30 bg-card p-5 hover:border-accent">
            <div className="absolute -top-3 right-4 rounded-full bg-accent px-3 py-0.5 font-mono-face text-[10px] font-bold text-accent-foreground shadow-sm">
              ✦ {item.matchScore}% Match
            </div>
            <div>
              <div className="flex flex-wrap gap-1 mb-2">
                {item.tags.map((t, ti) => (
                  <span key={ti} className="rounded bg-muted px-1.5 py-0.5 font-mono-face text-[9px] text-muted-foreground">{t}</span>
                ))}
              </div>
              <h3 className="font-display text-lg font-bold leading-snug line-clamp-2">{item.event.title}</h3>
              <p className="mt-2 text-xs text-muted-foreground line-clamp-2">{item.matchReason}</p>
            </div>
            <div className="mt-5 border-t border-foreground/10 pt-3 flex items-center justify-between text-xs">
              <span className="font-mono-face text-muted-foreground">{item.event.location}</span>
              <Link href={`/events/${item.event.slug}`} className="font-bold text-accent hover:underline inline-flex items-center gap-1">
                Details <ArrowRight size={12} />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AIPeerMatchesWidget({ onOpenChat }: { onOpenChat: (peer: { id: number; name: string; company?: string | null }) => void }) {
  const peerMatchesQuery = useGetPeerMatches();
  const requestMutation = useRequestConnection();
  const matches = peerMatchesQuery.data ?? [];
  if (peerMatchesQuery.isLoading || matches.length === 0) return null;

  return (
    <div className="rounded-3xl border border-accent/30 bg-gradient-to-r from-accent/10 via-card to-background p-6" data-testid="widget-ai-peer-matches">
      <div className="flex items-center justify-between border-b border-foreground/10 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-xl bg-accent text-accent-foreground">
            <Sparkles size={16} />
          </div>
          <div>
            <h3 className="font-display text-base font-bold">✦ AI Recommended Connections</h3>
            <p className="text-xs text-muted-foreground">Peers with complementary skills & shared event interests</p>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {matches.slice(0, 3).map((match: AIPeerMatch) => (
          <div key={match.attendee.id} className="flex flex-col justify-between rounded-2xl border border-foreground/10 bg-background/90 p-4 hover:border-accent">
            <div>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <div className="grid h-9 w-9 place-items-center rounded-full bg-secondary font-display font-bold text-sm text-secondary-foreground">
                    {match.attendee.name.charAt(0)}
                  </div>
                  <div>
                    <h4 className="font-display text-sm font-bold leading-tight">{match.attendee.name}</h4>
                    <p className="text-[11px] text-muted-foreground">{match.attendee.jobTitle} · {match.attendee.company}</p>
                  </div>
                </div>
                <span className="rounded-full bg-accent/20 px-2 py-0.5 font-mono-face text-[9px] font-bold text-accent">
                  {match.matchScore}% Fit
                </span>
              </div>

              <div className="mt-3 flex flex-wrap gap-1">
                {match.mutualInterests.map((mi, mIdx) => (
                  <span key={mIdx} className="rounded bg-muted px-1.5 py-0.5 font-mono-face text-[9px] text-muted-foreground">
                    {mi}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-4 flex items-center justify-between border-t border-foreground/10 pt-3">
              <span className="font-mono-face text-[10px] text-muted-foreground">{match.attendee.country || 'Global'}</span>
              {match.attendee.connectionStatus === 'connected' ? (
                <button
                  onClick={() => onOpenChat({ id: match.attendee.id, name: match.attendee.name, company: match.attendee.company })}
                  className="inline-flex items-center gap-1 rounded-full bg-accent px-3 py-1 text-xs font-bold text-accent-foreground"
                >
                  <MessageSquare size={12} /> Message
                </button>
              ) : match.attendee.connectionStatus === 'pending_sent' ? (
                <span className="text-[10px] font-mono-face text-muted-foreground">Request Sent</span>
              ) : (
                <button
                  onClick={() => requestMutation.mutate(match.attendee.id)}
                  disabled={requestMutation.isPending}
                  className="inline-flex items-center gap-1 rounded-full border border-foreground/15 px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent"
                >
                  <UserPlus size={12} /> Connect
                </button>
              )}
            </div>
          </div>
        ))}
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

function Header() {
  const [open, setOpen] = useState(false);
  const [location] = useLocation();
  const nav = [['Explore', '/events'], ['Categories', '/categories'], ['Cities', '/cities'], ['Organizers', '/organizers'], ['Venues', '/venues']];
  return (
    <header className="sticky top-0 z-40 border-b border-foreground/10 bg-background/90 backdrop-blur-xl">
      <div className="mx-auto flex h-[72px] max-w-[1440px] items-center justify-between px-5 lg:px-10">
        <Logo />
        <nav className="hidden items-center gap-7 md:flex">
          {nav.map(([label, href]) => (
            <Link key={href} href={href} data-testid={`link-nav-${label.toLowerCase()}`} className={cx('text-sm font-medium transition-colors hover:text-accent', location.startsWith(href) && 'text-accent')}>
              {label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link
            href="/admin"
            className="button-press hidden items-center gap-1.5 rounded-full border border-foreground/15 bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:border-accent hover:text-accent lg:flex"
            data-testid="link-header-admin"
          >
            <ShieldCheck size={14} className="text-accent" />
            <span>Admin</span>
          </Link>
          <button
            onClick={() => window.dispatchEvent(new CustomEvent('open-ai-concierge'))}
            className="button-press flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-3.5 py-1.5 text-xs font-bold text-accent hover:bg-accent hover:text-accent-foreground"
            data-testid="button-header-ai-concierge"
          >
            <Sparkles size={14} />
            <span>AI Assistant</span>
            <kbd className="hidden rounded bg-accent/20 px-1 py-0.2 font-mono-face text-[9px] text-accent lg:inline-block">Ctrl K</kbd>
          </button>
          <Link href="/dashboard" className="hidden rounded-full p-2.5 text-muted-foreground hover:bg-muted hover:text-foreground sm:block" data-testid="link-dashboard">
            <UserRound size={18} />
          </Link>
          <Link href="/organizer" className="hidden rounded-full border border-foreground/15 px-4 py-2 text-sm font-semibold hover:border-accent hover:text-accent lg:block" data-testid="link-organizer-portal">
            List an event
          </Link>
          <Link href="/login" className="button-press rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-accent" data-testid="link-login">
            Sign in
          </Link>
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
          <Link href="/admin" onClick={() => setOpen(false)} className="block border-b border-foreground/10 py-3 text-sm font-semibold text-accent" data-testid="link-mobile-admin">
            Admin console
          </Link>
          <Link href="/organizer" onClick={() => setOpen(false)} className="block py-3 text-sm font-semibold text-accent" data-testid="link-mobile-organizer">
            List an event
          </Link>
        </nav>
      )}
    </header>
  );
}

function Footer() {
  return (
    <footer className="mt-20 border-t border-foreground/10 bg-primary text-primary-foreground">
      <div className="mx-auto grid max-w-[1440px] gap-10 px-5 py-14 lg:grid-cols-[1.4fr_1fr_1fr_1fr] lg:px-10">
        <div>
          <Logo />
          <p className="mt-5 max-w-xs text-sm leading-6 text-primary-foreground/65">A high-signal guide to the events worth leaving home for.</p>
          <p className="mt-8 font-mono-face text-[10px] uppercase tracking-[.2em] text-primary-foreground/45">Made for curious people</p>
        </div>
        <FooterCol title="Discover" links={[['Explore events', '/events'], ['Categories', '/categories'], ['Cities', '/cities']]} />
        <FooterCol title="Connect" links={[['Organizers', '/organizers'], ['Venues', '/venues'], ['For organizers', '/organizer']]} />
        <FooterCol title="Your 100 TIMES" links={[['Dashboard', '/dashboard'], ['My Schedule', '/dashboard/schedule'], ['Networking Hub', '/dashboard/networking'], ['Registrations & Pass', '/dashboard/registrations']]} />
      </div>
      <div className="mx-auto flex max-w-[1440px] flex-wrap justify-between gap-3 border-t border-primary-foreground/15 px-5 py-5 text-xs text-primary-foreground/45 lg:px-10">
        <span>© 2025 100 TIMES</span>
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
  const toggle = () => {
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
  const featured = payload?.featured?.length ? payload.featured : fallbackEvents;
  const cats = payload?.trending?.length ? payload.trending : fallbackCategories;
  const cities = payload?.cities?.length ? payload.cities : fallbackCities;
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
                {health.isError ? 'Signal offline' : 'Live in 14 cities'}
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
        </div>
      </section>
      <AIRecommendationsSection />

      <section className="mx-auto mt-24 max-w-[1440px] px-5 lg:px-10">
        <SectionHeading kicker="02 / Browse by energy" title="Find your room" action="All categories" href="/categories" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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

function EventsPage() {
  const [filters, setFilters] = useState<ListEventsParams>({ page: 1, pageSize: 8, sort: 'soonest', format: 'all' });
  const [term, setTerm] = useState('');
  const params = useMemo(() => ({ ...filters, q: term || undefined }), [filters, term]);
  const query = useListEvents(params);
  const events = query.data?.items?.length ? query.data.items : fallbackEvents;
  const total = query.data?.total ?? events.length;
  const pages = query.data?.totalPages ?? 1;
  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-12 lg:px-10 lg:py-20">
      <div className="max-w-3xl">
        <p className="font-mono-face text-xs uppercase tracking-[.2em] text-accent">The directory</p>
        <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em] sm:text-7xl">Make a date<br />with an idea.</h1>
      </div>
      <div className="mt-12 grid gap-8 lg:grid-cols-[250px_1fr]">
        <aside className="h-fit rounded-2xl border border-foreground/10 bg-card p-5 lg:sticky lg:top-24">
          <div className="flex items-center justify-between">
            <h2 className="font-display font-bold">Filter events</h2>
            <Filter size={16} className="text-accent" />
          </div>
          <label className="mt-6 block text-xs font-semibold text-muted-foreground">
            Category
            <select
              value={filters.category ?? ''}
              onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value || undefined, page: 1 }))}
              className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-sm"
              data-testid="select-filter-category"
            >
              <option value="">Everything</option>
              {fallbackCategories.map((c) => (
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
              placeholder="Try Bengaluru"
              className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-sm outline-none focus:border-accent"
              data-testid="input-filter-city"
            />
          </label>
          <button
            onClick={() => { setFilters({ page: 1, pageSize: 8, sort: 'soonest', format: 'all' }); setTerm(''); }}
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
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href={`/events/${event.slug}/register`} className="button-press inline-flex items-center gap-2 rounded-full bg-accent px-5 py-3 text-sm font-semibold text-accent-foreground hover:bg-primary hover:text-primary-foreground" data-testid="link-register-event">
                Register now <ArrowRight size={16} />
              </Link>
              <SaveButton event={event} />
            </div>
          </div>
        </div>
      </div>
      <div className="mx-auto mt-14 grid max-w-[1440px] gap-12 px-5 lg:grid-cols-[1.1fr_.9fr] lg:px-10">
        <div>
          <AIEventBriefCard eventId={event.id} />
          <div className="mt-8">
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
            <Link href={`/organizers/${event.organizerId}`} className="mt-7 flex items-center justify-between border-t border-secondary-foreground/15 pt-5 text-sm font-semibold" data-testid="link-event-organizer">
              By {event.organizer}<ArrowRight size={15} />
            </Link>
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
  const [createdPass, setCreatedPass] = useState<RegistrationPass | null>(null);
  const [showPassModal, setShowPassModal] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState<RegistrationInput>({ firstName: '', lastName: '', email: '', phone: '', company: '', jobTitle: '', country: 'India', ticketType: 'Standard' });
  const update = (key: keyof RegistrationInput, value: string) => setForm((f) => ({ ...f, [key]: value }));

  if (eventQuery.isLoading) return <LoadingState label="Preparing registration" />;
  if (eventQuery.isError || !eventQuery.data) return <ErrorState title="That event is no longer available." />;
  const event = eventQuery.data;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    mutation.mutate(
      { id: event.id, data: form },
      {
        onSuccess: (res) => {
          const passData: RegistrationPass = {
            id: res.id,
            eventId: event.id,
            eventTitle: event.title,
            eventSlug: event.slug,
            ticketType: form.ticketType,
            registeredAt: res.registeredAt,
            status: 'confirmed',
            userName: `${form.firstName} ${form.lastName}`.trim(),
            company: form.company,
            jobTitle: form.jobTitle,
            eventVenue: event.venue,
            eventLocation: event.location,
            eventStartDate: event.startDate,
            eventEndDate: event.endDate,
            eventStartTime: event.startTime,
          };
          setCreatedPass(passData);
        },
        onError: () => setError('We could not complete that registration. Please check your details and try again.'),
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
    categories: { title: 'Find your people.', kicker: 'Categories / The right rooms', hook: useListCategories, empty: fallbackCategories },
    cities: { title: 'Change your coordinates.', kicker: 'Cities / Go somewhere', hook: useListCities, empty: fallbackCities },
    organizers: { title: 'Follow the curators.', kicker: 'Organizers / People behind the rooms', hook: useListOrganizers, empty: [] as Organizer[] },
    venues: { title: 'Know the room.', kicker: 'Venues / Places with a point of view', hook: useListVenues, empty: [] as Venue[] },
  }[kind];
  const query = config.hook();
  if (query.isLoading) return <LoadingState label={`Loading ${kind}`} />;
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
            <EmptyState title={`No ${kind} indexed yet.`} />
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
  if (query.isError || !query.data) return <ErrorState title={`We could not find that ${kind}.`} retry={() => query.refetch()} />;
  const detail = query.data as DirectoryDetail;
  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-12 lg:px-10 lg:py-20">
      <Link href={`/${kind === 'category' ? 'categories' : 'cities'}`} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-accent" data-testid="link-back-directory">
        <ArrowLeft size={15} /> Back to directory
      </Link>
      <div className="mt-10 max-w-3xl">
        <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">{kind} / Directory</p>
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

function AuthPage({ mode }: { mode: 'login' | 'register' | 'forgot' }) {
  const [, setLocation] = useLocation();
  const login = useLogin();
  const register = useRegisterUser();
  const [form, setForm] = useState({ name: '', email: '', password: '', country: 'India' });
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const isForgot = mode === 'forgot';
  const title = isForgot ? 'Reset your route.' : mode === 'login' ? 'Welcome back.' : 'Make room for more.';

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (isForgot) {
      setSubmitted(true);
      return;
    }
    const action = mode === 'login' ? login : register;
    const data = mode === 'login'
      ? { email: form.email.trim().toLowerCase(), password: form.password }
      : { ...form, email: form.email.trim().toLowerCase(), name: form.name.trim() };
    action.mutate(
      { data } as never,
      {
        onSuccess: (session) => {
          localStorage.setItem('100-times-auth-token', session.token);
          setLocation('/dashboard');
        },
        onError: () => setError('That did not work. Check your details and try again.'),
      }
    );
  };

  return (
    <div className="grid min-h-[calc(100dvh-72px)] lg:grid-cols-[.8fr_1.2fr]">
      <div className="hidden bg-[#193d42] p-12 text-[#f3eadb] lg:flex lg:flex-col lg:justify-between">
        <Logo />
        <div>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-[#ec715c]">Your field guide</p>
          <p className="mt-5 max-w-md font-display text-5xl font-bold leading-[.95] tracking-[-.06em]">
            The right room can change the shape of a year.
          </p>
        </div>
        <p className="text-sm text-[#f3eadb]/55">100 TIMES · A trusted event guide</p>
      </div>
      <div className="flex items-center justify-center px-5 py-16">
        <div className="w-full max-w-md">
          <Link href="/" className="mb-12 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-accent" data-testid="link-auth-home">
            <ArrowLeft size={15} /> Back to 100 TIMES
          </Link>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">
            {isForgot ? 'Account / Access' : mode === 'login' ? 'Account / Sign in' : 'Account / New here'}
          </p>
          <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em]">{title}</h1>
          {submitted ? (
            <div className="mt-8 rounded-2xl bg-secondary p-6">
              <Check className="text-secondary-foreground" />
              <p className="mt-4 font-semibold">Check your inbox.</p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">If there is an account for {form.email}, you will receive a reset link shortly.</p>
            </div>
          ) : (
            <form onSubmit={submit} className="mt-9 space-y-5">
              {mode === 'register' && <Field label="Your name" value={form.name} onChange={(v) => setForm((f) => ({ ...f, name: v }))} required testId="input-auth-name" />}
              <Field label="Email" type="email" value={form.email} onChange={(v) => setForm((f) => ({ ...f, email: v }))} required testId="input-auth-email" />
              {mode === 'login' && (
                <div className="rounded-2xl border border-foreground/10 bg-secondary/50 p-4">
                  <p className="font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Quick Demo Accounts (1-Click Fill):</p>
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, email: 'admin@100times.in', password: 'AdminPass123!' }))}
                      className="rounded-full border border-foreground/15 bg-background px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent"
                    >
                      👑 Admin
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, email: 'demo@100times.in', password: 'DemoPass123!' }))}
                      className="rounded-full border border-foreground/15 bg-background px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent"
                    >
                      👤 Attendee
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, email: 'organizer@100times.in', password: 'OrganizerPass123!' }))}
                      className="rounded-full border border-foreground/15 bg-background px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent"
                    >
                      🏢 Organizer
                    </button>
                  </div>
                </div>
              )}
              {!isForgot && <Field label="Password" type="password" value={form.password} onChange={(v) => setForm((f) => ({ ...f, password: v }))} required testId="input-auth-password" />}
              {mode === 'register' && <Field label="Country" value={form.country} onChange={(v) => setForm((f) => ({ ...f, country: v }))} testId="input-auth-country" />}
              {error && <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive" data-testid="status-auth-error">{error}</p>}
              <button disabled={login.isPending || register.isPending} className="button-press flex w-full items-center justify-center gap-2 rounded-full bg-primary px-5 py-3.5 text-sm font-bold text-primary-foreground hover:bg-accent" data-testid="button-auth-submit">
                {login.isPending || register.isPending ? <Loader2 size={16} className="animate-spin" /> : <LockKeyhole size={16} />}
                {isForgot ? 'Send reset link' : mode === 'login' ? 'Sign in' : 'Create account'}
              </button>
            </form>
          )}
          <div className="mt-7 text-sm text-muted-foreground">
            {mode === 'login' ? (
              <>
                <Link href="/forgot-password" className="font-semibold text-foreground hover:text-accent" data-testid="link-forgot-password">Forgot password?</Link>
                <span className="mx-2">·</span>
                <Link href="/register" className="font-semibold text-foreground hover:text-accent" data-testid="link-create-account">Create account</Link>
              </>
            ) : (
              !isForgot && <Link href="/login" className="font-semibold text-foreground hover:text-accent" data-testid="link-existing-account">Already have an account?</Link>
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
  const links = [
    ['Overview', '/dashboard', LayoutDashboard],
    ['My Schedule', '/dashboard/schedule', CalendarDays],
    ['Networking', '/dashboard/networking', Users],
    ['Registrations & Pass', '/dashboard/registrations', Ticket],
    ['Saved events', '/dashboard/saved-events', Heart],
    ['Recommendations', '/dashboard/recommendations', Sparkles],
    ['Notifications', '/dashboard/notifications', Bell],
    ['Settings', '/dashboard/settings', Settings2],
  ] as const;

  return (
    <aside className="rounded-2xl border border-foreground/10 bg-card p-3 lg:h-fit lg:sticky lg:top-24">
      <p className="px-3 py-3 font-mono-face text-[10px] uppercase tracking-[.16em] text-muted-foreground">Your 100 TIMES</p>
      {links.map(([label, href, Icon]) => (
        <Link
          href={href}
          key={href}
          className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold hover:bg-muted"
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
                      <span className="rounded-full bg-muted px-2 py-0.5 font-mono-face text-[9px] text-muted-foreground">
                        {att.country || 'Global'}
                      </span>
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
                {reg.ticketCode || `100T-REG-${reg.id}`}
              </span>
            </div>
            <Link href={`/events/${reg.eventSlug}`} className="mt-1.5 block font-display text-xl font-bold hover:text-accent">
              {reg.eventTitle}
            </Link>
            <p className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
              <CalendarDays size={13} className="text-accent" />
              {reg.eventStartDate ? fmtDate(reg.eventStartDate) : fmtDate(reg.registeredAt)}
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
  const [saved, setSaved] = useState(false);
  const updateMutation = useUpdateProfile();

  const [form, setForm] = useState({
    name: 'Aarav Mehta',
    jobTitle: 'Product Architect',
    company: 'Voxel Labs',
    bio: 'Designing interfaces and software systems for the physical world.',
    country: 'India',
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    updateMutation.mutate(form, {
      onSuccess: () => {
        setSaved(true);
        window.setTimeout(() => setSaved(false), 2000);
      },
    });
  };

  return (
    <div className="max-w-xl rounded-2xl border border-foreground/10 bg-card p-6 sm:p-8">
      <h2 className="font-display text-2xl font-bold">Attendee Profile & Settings</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Keep your details current so your digital badge, lanyard pass, and attendee networking profile look sharp.
      </p>
      <form onSubmit={handleSubmit} className="mt-7 space-y-5">
        <Field label="Full name" value={form.name} onChange={(v) => setForm((f) => ({ ...f, name: v }))} required testId="input-settings-name" />
        <Field label="Job title" value={form.jobTitle} onChange={(v) => setForm((f) => ({ ...f, jobTitle: v }))} testId="input-settings-job-title" />
        <Field label="Company / Studio" value={form.company} onChange={(v) => setForm((f) => ({ ...f, company: v }))} testId="input-settings-company" />
        <label className="block text-xs font-semibold text-muted-foreground">
          Bio / What you are building
          <textarea
            value={form.bio}
            onChange={(e) => setForm((f) => ({ ...f, bio: e.target.value }))}
            className="mt-2 min-h-20 w-full rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-xs outline-none focus:border-accent"
            data-testid="input-settings-bio"
          />
        </label>
        <Field label="Country" value={form.country} onChange={(v) => setForm((f) => ({ ...f, country: v }))} testId="input-settings-country" />
        <button
          type="submit"
          disabled={updateMutation.isPending}
          className="button-press rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground hover:bg-accent disabled:opacity-60"
          data-testid="button-save-settings"
        >
          {updateMutation.isPending ? 'Saving...' : saved ? '✓ Saved' : 'Save preferences'}
        </button>
      </form>
    </div>
  );
}

function DashboardPage({ tab = 'overview' }: { tab?: string }) {
  const dash = useGetDashboard();
  const saved = useGetSavedEvents();
  const regs = useGetRegistrations();
  const notes = useGetNotifications();
  const [selectedPass, setSelectedPass] = useState<RegistrationPass | null>(null);

  if (dash.isLoading) return <LoadingState label="Loading your dashboard" />;
  if (dash.isError) return <ErrorState retry={() => dash.refetch()} />;

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
    recommendations: 'A few good leads.',
    notifications: 'Keep in the loop.',
    settings: 'Your attendee profile.',
  };

  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-12 lg:px-10 lg:py-16">
      <div className="mb-10">
        <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Dashboard / {tab}</p>
        <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em]">{titles[tab] ?? titles.overview}</h1>
        <p className="mt-3 text-muted-foreground">Good to see you, {data?.userName ?? 'Aarav'}.</p>
      </div>
      <div className="grid gap-8 lg:grid-cols-[235px_1fr]">
        <DashboardNav />
        <div>
          {tab === 'overview' && (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <Metric label="Saved events" value={data?.savedCount ?? savedEvents.length} icon={Heart} />
                <Metric label="Registrations" value={data?.registrationCount ?? registrations.length} icon={Ticket} />
                <Metric label="Attended" value={data?.attendedCount ?? 0} icon={Check} />
              </div>
              <div className="mt-10">
                <SectionHeading kicker="Next up" title="Your upcoming rooms" action="All registrations" href="/dashboard/registrations" />
                <div className="space-y-3">
                  {registrations.length ? (
                    registrations.slice(0, 3).map((reg) => (
                      <div
                        key={reg.id}
                        className="flex items-center justify-between gap-4 rounded-2xl border border-foreground/10 bg-card p-5 hover:border-accent"
                      >
                        <div>
                          <p className="font-display text-lg font-bold">{reg.eventTitle}</p>
                          <p className="mt-1 text-xs text-muted-foreground">{reg.ticketType} · Registered {fmtDate(reg.registeredAt)}</p>
                        </div>
                        <button
                          onClick={() => setSelectedPass(reg)}
                          className="button-press inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
                          data-testid={`button-view-pass-overview-${reg.id}`}
                        >
                          <QrCode size={13} /> Pass
                        </button>
                      </div>
                    ))
                  ) : (
                    <EmptyState title="Your calendar is open." body="Save an event or register for something with a point of view." />
                  )}
                </div>
              </div>
            </>
          )}
          {tab === 'schedule' && <ScheduleTab />}
          {tab === 'networking' && <NetworkingTab />}
          {tab === 'saved-events' && <EventCollection events={savedEvents} emptyTitle="Your shortlist is empty." emptyBody="Tap the heart on an event you want to remember." />}
          {tab === 'recommendations' && <EventCollection events={data?.recommended ?? fallbackEvents} emptyTitle="We are still learning your taste." />}
          {tab === 'registrations' && <RegistrationsTab registrations={registrations} onOpenPass={(p) => setSelectedPass(p)} />}
          {tab === 'notifications' && (
            <div className="space-y-3">
              {notifications.length ? (
                notifications.map((n) => (
                  <div key={n.id} className="rounded-2xl border border-foreground/10 bg-card p-5">
                    <div className="flex gap-3">
                      <Bell size={17} className="mt-1 text-accent" />
                      <div>
                        <p className="font-semibold">{n.title}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{n.message}</p>
                        <p className="mt-3 font-mono-face text-[10px] uppercase tracking-[.12em] text-muted-foreground">{fmtDate(n.createdAt)}</p>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <EmptyState title="You are all caught up." />
              )}
            </div>
          )}
          {tab === 'settings' && <SettingsPanel />}
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

function EventCollection({ events, emptyTitle, emptyBody }: { events: EventCard[]; emptyTitle: string; emptyBody?: string }) {
  return events.length ? (
    <div className="grid gap-5 md:grid-cols-2">
      {events.map((e) => (
        <EventCardView event={e} key={e.id} />
      ))}
    </div>
  ) : (
    <EmptyState title={emptyTitle} body={emptyBody} />
  );
}

function OrganizerPage({ view = 'overview' }: { view?: string }) {
  const dash = useGetOrganizerDashboard();
  const events = useGetOrganizerEvents();
  const analytics = useGetOrganizerAnalytics();
  if (dash.isLoading) return <LoadingState label="Loading organizer studio" />;
  if (dash.isError) return <ErrorState retry={() => dash.refetch()} />;
  const data = dash.data;
  const list = events.data ?? data?.recentEvents ?? [];
  return (
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-12 lg:px-10 lg:py-16">
      <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Organizer studio / {view}</p>
          <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em]">
            {view === 'analytics' ? 'See what is moving.' : view === 'events' ? 'Your event desk.' : 'Make a room people remember.'}
          </h1>
        </div>
        <Link href="/organizer/events/create" className="inline-flex items-center justify-center gap-2 rounded-full bg-accent px-5 py-3 text-sm font-bold text-accent-foreground" data-testid="link-create-organizer-event">
          <Plus size={17} /> Create an event
        </Link>
      </div>
      <div className="mt-10 grid gap-3 sm:grid-cols-4">
        <Metric label="Total events" value={data?.totalEvents ?? 0} icon={CalendarDays} />
        <Metric label="Published" value={data?.publishedEvents ?? 0} icon={Check} />
        <Metric label="Registrations" value={data?.registrations ?? 0} icon={Users} />
        <Metric label="Views" value={data?.views ?? 0} icon={TrendingUp} />
      </div>
      {view === 'analytics' ? (
        <AnalyticsPanel data={analytics.data} />
      ) : (
        <div className="mt-12">
          <SectionHeading kicker="Your calendar" title="Recent events" action="Event desk" href="/organizer/events" />
          <div className="space-y-3">
            {list.length ? (
              list.map((event) => (
                <Link href={`/events/${event.slug}`} key={event.id} className="flex items-center justify-between rounded-2xl border border-foreground/10 bg-card p-5 hover:border-accent" data-testid={`row-organizer-event-${event.id}`}>
                  <div>
                    <p className="font-display text-xl font-bold">{event.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{fmtDate(event.startDate)} · {event.location}</p>
                  </div>
                  <span className="rounded-full bg-secondary px-2.5 py-1 font-mono-face text-[9px] uppercase text-secondary-foreground">{event.status}</span>
                </Link>
              ))
            ) : (
              <EmptyState title="Your event desk is empty." body="Give your next gathering a place on the calendar." />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function AnalyticsPanel({ data }: { data?: { views: number[]; registrations: number[]; conversion: number[]; ticketDistribution: Record<string, number> } }) {
  const values = data?.views ?? [32, 48, 40, 67, 59, 82, 74];
  return (
    <div className="mt-12 rounded-2xl border border-foreground/10 bg-card p-6 sm:p-8">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-mono-face text-[10px] uppercase tracking-[.17em] text-accent">Last 7 weeks</p>
          <h2 className="mt-2 font-display text-2xl font-bold">Audience momentum</h2>
        </div>
        <LineChart className="text-accent" />
      </div>
      <div className="mt-10 flex h-48 items-end gap-2 border-b border-foreground/10">
        {values.map((v, i) => (
          <div key={i} className="group relative flex-1 rounded-t-md bg-accent/75 transition-all hover:bg-accent" style={{ height: `${Math.max(10, Math.min(100, v))}%` }}>
            <span className="absolute -top-6 left-1/2 hidden -translate-x-1/2 font-mono-face text-[9px] group-hover:block">{v}</span>
          </div>
        ))}
      </div>
      <div className="mt-5 flex justify-between font-mono-face text-[9px] uppercase text-muted-foreground">
        <span>7 weeks ago</span>
        <span>This week</span>
      </div>
    </div>
  );
}

function CreateEventPage() {
  const create = useCreateOrganizerEvent();
  const queryClient = useQueryClient();
  const [, setLocation] = useLocation();
  const [error, setError] = useState('');
  const [form, setForm] = useState<EventInput>({
    title: '',
    description: '',
    eventType: 'Conference',
    category: 'artificial-intelligence',
    startDate: '',
    endDate: '',
    startTime: '09:30 AM',
    location: 'Bengaluru',
    format: 'in-person',
    price: 0,
  });

  const set = (key: keyof EventInput, value: string | number) => {
    setForm((f) => {
      const updated = { ...f, [key]: value };
      if (key === 'startDate' && (!f.endDate || f.endDate < (value as string))) {
        updated.endDate = value as string;
      }
      return updated;
    });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError('');
    const payload = {
      ...form,
      title: form.title.trim(),
      description: form.description.trim(),
      endDate: form.endDate || form.startDate,
      location: form.location.trim() || 'Bengaluru',
      price: Number(form.price) || 0,
    };

    create.mutate(
      { data: payload },
      {
        onSuccess: (event) => {
          queryClient.invalidateQueries();
          setLocation(`/events/${event.slug}`);
        },
        onError: (err: unknown) => {
          const msg = (err as { message?: string })?.message || 'Could not create the event. Check the required details.';
          setError(msg);
        },
      }
    );
  };
  return (
    <div className="page-enter mx-auto max-w-[1000px] px-5 py-12 lg:px-10 lg:py-16">
      <Link href="/organizer/events" className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-accent" data-testid="link-back-organizer-events">
        <ArrowLeft size={15} /> Event desk
      </Link>
      <div className="mt-10 max-w-2xl">
        <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Organizer studio / New event</p>
        <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em]">Put something<br />good on the calendar.</h1>
      </div>
      <form onSubmit={submit} className="mt-12 rounded-3xl border border-foreground/10 bg-card p-6 sm:p-9">
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="Event title" value={form.title} onChange={(v) => set('title', v)} required testId="input-event-title" />
          </div>
          <div className="sm:col-span-2">
            <label className="block text-xs font-semibold text-muted-foreground">
              Description
              <textarea required minLength={10} value={form.description} onChange={(e) => set('description', e.target.value)} className="mt-2 min-h-32 w-full rounded-lg border border-foreground/15 bg-background px-3 py-3 text-sm outline-none focus:border-accent" data-testid="input-event-description" />
            </label>
          </div>
          <Field label="Event type" value={form.eventType} onChange={(v) => set('eventType', v)} required testId="input-event-type" />
          <label className="block text-xs font-semibold text-muted-foreground">
            Category
            <select value={form.category} onChange={(e) => set('category', e.target.value)} className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-3 text-sm" data-testid="select-event-category">
              {fallbackCategories.map((c) => (
                <option key={c.slug} value={c.slug}>{c.name}</option>
              ))}
            </select>
          </label>
          <Field label="Start date" type="date" value={form.startDate} onChange={(v) => set('startDate', v)} required testId="input-event-start-date" />
          <Field label="End date" type="date" value={form.endDate} onChange={(v) => set('endDate', v)} required testId="input-event-end-date" />
          <Field label="Start time" type="time" value={form.startTime} onChange={(v) => set('startTime', v)} required testId="input-event-start-time" />
          <Field label="Location" value={form.location} onChange={(v) => set('location', v)} required testId="input-event-location" />
          <label className="block text-xs font-semibold text-muted-foreground">
            Format
            <select value={form.format} onChange={(e) => set('format', e.target.value as EventInput['format'])} className="mt-2 w-full rounded-lg border border-foreground/15 bg-background px-3 py-3 text-sm" data-testid="select-event-format">
              <option value="in-person">In person</option>
              <option value="online">Online</option>
            </select>
          </label>
          <Field label="Price (INR)" type="number" value={String(form.price)} onChange={(v) => set('price', Number(v))} testId="input-event-price" />
        </div>
        {error && <p className="mt-5 text-sm text-destructive" data-testid="status-create-event-error">{error}</p>}
        <button disabled={create.isPending} className="mt-8 inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground hover:bg-accent" data-testid="button-create-event">
          {create.isPending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Publish event
        </button>
      </form>
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
    <div className="page-enter mx-auto max-w-[1440px] px-5 py-12 lg:px-10 lg:py-16">
      <div className="flex items-end justify-between">
        <div>
          <p className="font-mono-face text-xs uppercase tracking-[.18em] text-accent">Admin / {view}</p>
          <h1 className="mt-4 font-display text-5xl font-extrabold tracking-[-.07em]">
            {view === 'overview' ? 'Keep the signal clean.' : `Manage ${view}.`}
          </h1>
        </div>
        <ShieldCheck className="hidden text-accent sm:block" size={30} />
      </div>
      <div className="mt-10 grid gap-3 sm:grid-cols-4">
        {cards.map(([label, value, Icon]) => (
          <Metric key={label as string} label={label as string} value={value as number} icon={Icon as typeof Heart} />
        ))}
      </div>
      {view === 'overview' ? (
        <div className="mt-12 grid gap-5 lg:grid-cols-2">
          <div className="rounded-2xl border border-foreground/10 bg-card p-6">
            <div className="flex items-center justify-between">
              <p className="font-mono-face text-[10px] uppercase tracking-[.15em] text-accent">Popular categories</p>
              <Link href="/admin" className="font-mono-face text-[10px] text-accent hover:underline flex items-center gap-1">
                Operations console <ArrowRight size={10} />
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
      ) : (
        <EmptyState title={`The ${view} workspace is ready.`} body="Connect the next moderation workflow here when your operations team is ready." />
      )}
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
        <Route path="/events/:slug/register" component={RegisterPage} />
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
        <Route path="/dashboard" component={() => <DashboardPage tab="overview" />} />
        <Route path="/dashboard/schedule" component={() => <DashboardPage tab="schedule" />} />
        <Route path="/dashboard/networking" component={() => <DashboardPage tab="networking" />} />
        <Route path="/dashboard/registrations" component={() => <DashboardPage tab="registrations" />} />
        <Route path="/dashboard/saved-events" component={() => <DashboardPage tab="saved-events" />} />
        <Route path="/dashboard/recommendations" component={() => <DashboardPage tab="recommendations" />} />
        <Route path="/dashboard/notifications" component={() => <DashboardPage tab="notifications" />} />
        <Route path="/dashboard/settings" component={() => <DashboardPage tab="settings" />} />

        {/* Organizer Desk */}
        <Route path="/organizer" component={() => <OrganizerPage />} />
        <Route path="/organizer/events" component={() => <OrganizerPage view="events" />} />
        <Route path="/organizer/events/create" component={CreateEventPage} />
        <Route path="/organizer/analytics" component={() => <OrganizerPage view="analytics" />} />

        {/* Admin Console — Organizer Discovery & Organizer Outreach operations */}
        <Route path="/admin" component={() => <OpsLayout><OpsDashboardPage /></OpsLayout>} />
        <Route path="/admin/acquisition" component={() => <Redirect to="/admin" />} />
        <Route path="/acquisition-agent" component={() => <Redirect to="/admin" />} />
        <Route path="/admin/discovery" component={() => <OpsLayout><DiscoveryPage mode="new" /></OpsLayout>} />
        <Route path="/admin/discovery/events" component={() => <OpsLayout><DiscoveryPage mode="events" /></OpsLayout>} />
        <Route path="/admin/discovery/organizers" component={() => <OpsLayout><OrganizersPage /></OpsLayout>} />
        <Route path="/admin/discovery/organizers/:id" component={() => <OpsLayout><OrganizerProfilePage /></OpsLayout>} />
        <Route path="/admin/discovery/contacts" component={() => <OpsLayout><ContactsPage /></OpsLayout>} />
        <Route path="/admin/outreach" component={() => <OpsLayout><OutreachPage /></OpsLayout>} />
        <Route path="/admin/outreach/:tab" component={() => <OpsLayout><OutreachPage /></OpsLayout>} />
        <Route path="/admin/activity" component={() => <OpsLayout><ActivityPage /></OpsLayout>} />
        <Route path="/admin/settings" component={() => <OpsLayout><SettingsPage /></OpsLayout>} />
        {/* Platform data workspaces (unchanged placeholders) */}
        <Route path="/admin/events" component={() => <AdminPage view="events" />} />
        <Route path="/admin/users" component={() => <AdminPage view="users" />} />
        <Route path="/admin/organizers" component={() => <AdminPage view="organizers" />} />
        <Route path="/admin/categories" component={() => <AdminPage view="categories" />} />
        <Route path="/admin/venues" component={() => <AdminPage view="venues" />} />
        <Route path="/admin/reviews" component={() => <AdminPage view="reviews" />} />

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
