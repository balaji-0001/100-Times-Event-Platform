// Data layer for the attendee experience. Every type mirrors a response from
// artifacts/api-server/backend/routes/attendee.py, and every hook binds to a
// real endpoint — nothing here is mocked or defaulted to sample data.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customFetch } from '@workspace/api-client-react';

export type EventKind = 'platform' | 'discovered';
export type RegistrationStatus =
  | 'NOT_REGISTERED'
  | 'REGISTRATION_PAGE_OPENED'
  | 'REGISTERED'
  | 'WAITLISTED'
  | 'CANCELLED'
  | 'NOT_ATTENDING';

export interface MatchCriterion {
  key: string;
  label: string;
  weight: number;
  earned: number;
  status: 'matched' | 'partial' | 'missed' | 'not_checked';
  detail: string;
}

export interface MatchInfo {
  percent: number;
  earned: number;
  possible: number;
  reasons: string[];
  gaps: string[];
  criteria: MatchCriterion[];
  criteriaChecked: number;
}

export interface EventState {
  saved: boolean;
  registrationStatus: RegistrationStatus;
  registrationSource: 'platform' | 'self_reported' | null;
  registrationConfirmedAt: string | null;
  registrationPageOpenedAt: string | null;
  lastViewedAt: string | null;
  ticketCode: string | null;
}

export interface AttendeeEvent {
  ref: string;
  kind: EventKind;
  id: number;
  title: string;
  description: string | null;
  startDate: string;
  endDate: string | null;
  startTime: string | null;
  city: string | null;
  country: string | null;
  venue: string | null;
  location: string | null;
  sector: string | null;
  eventType: string | null;
  attendanceMode: 'online' | 'offline' | 'hybrid' | null;
  price: { isFree: boolean | null; min: number | null; max: number | null; currency: string | null; display: string };
  registrationDeadline: string | null;
  officialUrl: string | null;
  registrationUrl: string | null;
  internalUrl: string | null;
  registerOnPlatform: boolean;
  organizer: { name: string | null; website: string | null; email: string | null; phone: string | null; verified: boolean };
  verification: { status: string; score: number | null; basis: string; sourceUrl?: string; sourceCount?: number };
  eligible: boolean;
  ineligibleReason: string | null;
  match: MatchInfo | null;
  state: EventState | null;
}

export interface AttendeePreferences {
  saved?: boolean;
  interests: string[];
  industries: string[];
  countries: string[];
  eventTypes: string[];
  budgetMax: number | null;
  budgetCurrency: string | null;
  freeOnly: boolean;
  dateFrom: string | null;
  dateTo: string | null;
  attendanceMode: 'any' | 'online' | 'offline' | 'hybrid';
  notifyConsent: boolean;
  notifyConsentAt?: string | null;
  notifyEventReminders: boolean;
  notifyDeadlines: boolean;
  notifyEventChanges: boolean;
  notifyNewMatches: boolean;
  notifyByEmail: boolean;
  updatedAt?: string | null;
}

export interface CountOption {
  value: string;
  count: number;
}

export interface AttendeeOptions {
  catalogSize: number;
  industries: CountOption[];
  countries: CountOption[];
  allCountries: string[];
  eventTypes: CountOption[];
  attendanceModes: CountOption[];
  currencies: CountOption[];
  interestSuggestions: string[];
  weights: Record<string, number>;
  emailDelivery: { provider: string; status: 'REAL' | 'NOT_CONFIGURED' };
}

export interface MatchResponse {
  hasPreferences: boolean;
  catalogSize: number;
  totalRanked: number;
  weights?: Record<string, number>;
  results: AttendeeEvent[];
  generatedAt?: string;
}

export interface AttendeeDashboardData {
  user: { id: number; name: string; email: string };
  hasPreferences: boolean;
  catalogSize: number;
  recommended: AttendeeEvent[];
  saved: AttendeeEvent[];
  registered: AttendeeEvent[];
  upcoming: AttendeeEvent[];
  deadlines: AttendeeEvent[];
  savedWithoutPublishedDeadline: number;
  recentlyViewed: AttendeeEvent[];
  counts: { saved: number; registered: number; upcoming: number; unreadNotifications: number };
  notificationsEnabled: boolean;
}

export interface AssistantResponse {
  reply: string;
  notes: string[];
  appliedFilters: string[];
  requestedCount: number;
  totalMatching: number;
  results: AttendeeEvent[];
  examples: string[];
  catalogSize: number;
  filters: { parser: 'rules' | 'rules+ai' } & Record<string, unknown>;
}

export interface AttendeeNotification {
  id: number;
  title: string;
  message: string;
  kind: string | null;
  isRead: boolean;
  emailStatus: string | null;
  createdAt: string | null;
}

export interface AttendeeAdminOverview {
  catalog: { total: number; platform: number; discovered: number };
  attendees: { withPreferences: number; notificationConsent: number };
  engagement: {
    savedPlatform: number;
    savedDiscovered: number;
    registrationPagesOpened: number;
    externalRegistrationsConfirmed: number;
    platformRegistrations: number;
    eventViews: number;
  };
  assistant: {
    questionsAsked: number;
    recent: Array<{ id: number; question: string; status: string; location: string | null; sector: string | null; eventType: string | null; createdAt: string | null }>;
  };
  notifications: {
    autoEnabled: boolean;
    sentByKind: Record<string, number>;
    emailByStatus: Record<string, number>;
    emailDelivery: { provider: string; status: string };
    lastSweep: { at: string | null; result: string | null; summary: Record<string, unknown> | null };
  };
}

export const attendeeKeys = {
  preferences: ['attendee', 'preferences'] as const,
  options: ['attendee', 'options'] as const,
  dashboard: ['attendee', 'dashboard'] as const,
  matches: ['attendee', 'matches'] as const,
  event: (kind: EventKind, id: number) => ['attendee', 'event', kind, id] as const,
  notifications: ['attendee', 'notifications'] as const,
  adminOverview: ['attendee', 'admin', 'overview'] as const,
};

const json = (body: unknown) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export function useAttendeePreferences() {
  return useQuery({ queryKey: attendeeKeys.preferences, queryFn: () => customFetch<AttendeePreferences>('/api/attendee/preferences') });
}

export function useAttendeeOptions() {
  return useQuery({ queryKey: attendeeKeys.options, queryFn: () => customFetch<AttendeeOptions>('/api/attendee/options'), staleTime: 60_000 });
}

export function useSavePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (prefs: AttendeePreferences) =>
      customFetch<AttendeePreferences>('/api/attendee/preferences', { ...json(prefs), method: 'PUT' }),
    onSuccess: (data) => {
      qc.setQueryData(attendeeKeys.preferences, data);
      qc.invalidateQueries({ queryKey: attendeeKeys.dashboard });
      qc.removeQueries({ queryKey: attendeeKeys.matches });
    },
  });
}

export function useMatchMyEvents() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (limit: number = 100) => customFetch<MatchResponse>('/api/attendee/match', json({ limit })),
    onSuccess: (data) => qc.setQueryData(attendeeKeys.matches, data),
  });
}

export function useAttendeeDashboard() {
  return useQuery({ queryKey: attendeeKeys.dashboard, queryFn: () => customFetch<AttendeeDashboardData>('/api/attendee/dashboard') });
}

export function useAttendeeEvent(kind: EventKind | null, id: number | null) {
  return useQuery({
    queryKey: attendeeKeys.event(kind ?? 'discovered', id ?? 0),
    queryFn: () => customFetch<AttendeeEvent>(`/api/attendee/events/${kind}/${id}`),
    enabled: Boolean(kind && id),
  });
}

function useEventAction<TVars, TOut>(fn: (vars: TVars) => Promise<TOut>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attendee'] });
    },
  });
}

export function useToggleSave() {
  return useEventAction(({ kind, id, saved }: { kind: EventKind; id: number; saved: boolean }) =>
    customFetch<EventState>(`/api/attendee/events/${kind}/${id}/save`, { method: saved ? 'POST' : 'DELETE' }),
  );
}

export function useRegistrationOpened() {
  return useEventAction(({ kind, id }: { kind: EventKind; id: number }) =>
    customFetch<{ registrationUrl: string | null; state: EventState }>(`/api/attendee/events/${kind}/${id}/registration-opened`, { method: 'POST' }),
  );
}

export function useSetExternalRegistration() {
  return useEventAction(({ id, status, confirm }: { id: number; status: 'REGISTERED' | 'NOT_ATTENDING' | 'NONE'; confirm: boolean }) =>
    customFetch<EventState>(`/api/attendee/events/discovered/${id}/registration`, json({ status, confirm })),
  );
}

export function useAskAssistant() {
  return useMutation({
    mutationFn: (message: string) => customFetch<AssistantResponse>('/api/attendee/assistant', json({ message })),
  });
}

export function useAttendeeNotifications() {
  return useQuery({
    queryKey: attendeeKeys.notifications,
    queryFn: () => customFetch<{ items: AttendeeNotification[]; unread: number }>('/api/attendee/notifications'),
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number | 'all') =>
      customFetch(id === 'all' ? '/api/attendee/notifications/read-all' : `/api/attendee/notifications/${id}/read`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['attendee'] }),
  });
}

export function useAttendeeAdminOverview() {
  return useQuery({ queryKey: attendeeKeys.adminOverview, queryFn: () => customFetch<AttendeeAdminOverview>('/api/attendee/admin/overview') });
}

export function useSetAttendeeNotificationsAuto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      customFetch<{ enabled: boolean }>('/api/attendee/admin/notifications/auto', { ...json({ enabled }), method: 'PATCH' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: attendeeKeys.adminOverview }),
  });
}

export function useRunAttendeeNotifications() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => customFetch<Record<string, unknown>>('/api/attendee/admin/notifications/run', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: attendeeKeys.adminOverview }),
  });
}
