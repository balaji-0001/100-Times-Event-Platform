// Data layer for the 100Times operations admin (Organizer Discovery + Organizer Outreach).
// Every type here mirrors a backend response schema in artifacts/api-server/backend/schemas.py,
// and every hook binds to an endpoint that already exists — nothing is mocked.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customFetch } from '@workspace/api-client-react';

// ---------------------------------------------------------------------------
// Types (camelCase, exactly as serialized by the API)
// ---------------------------------------------------------------------------

export interface Me {
  id: number;
  name: string;
  email: string;
  role: 'USER' | 'ORGANIZER' | 'ADMIN';
}

export interface EventSource {
  id: number;
  sourceWebsite?: string | null;
  sourceUrl: string;
  sourceType: string;
  fetchedAt: string;
}

export interface DiscoveredEvent {
  id: number;
  name?: string | null;
  date?: string | null;
  eventDate?: string | null;
  location?: string | null;
  category?: string | null;
  subcategory?: string | null;
  eventDescription?: string | null;
  venue?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  url?: string | null;
  ticketUrl?: string | null;
  eventFormat?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  sourceUrl?: string | null;
  sourceWebsite?: string | null;
  matchScore: number;
  confidenceScore: number;
  organizerId?: number | null;
  organizerStatus: 'PENDING' | 'FOUND' | 'NOT_FOUND';
  verificationStatus: 'UNVERIFIED' | 'VERIFIED' | 'NEEDS_REVIEW' | 'REJECTED';
  discoveryStatus: 'NEW' | 'DUPLICATE' | 'PROMOTED';
  discoveredBy: 'social_pipeline' | 'web_discovery_agent';
  verificationNotes: string[];
  discoveredAt?: string | null;
  lastUpdatedAt?: string | null;
  sources: EventSource[];
}

export interface OrganizerContact {
  id: number;
  contactType: 'email' | 'phone' | 'linkedin' | 'website' | 'other' | string;
  value: string;
  sourceUrl?: string | null;
  confidenceScore: number;
  isPrimary: boolean;
}

export interface DiscoveredOrganizer {
  id: number;
  name: string;
  email?: string | null;
  website?: string | null;
  linkedin?: string | null;
  sourceUrl?: string | null;
  organizerType?: string | null;
  city?: string | null;
  state?: string | null;
  phone?: string | null;
  confidenceScore: number;
  blocked?: boolean;
  verifiedAt?: string | null;
  lastUpdatedAt?: string | null;
  contacts: OrganizerContact[];
}

export const OUTREACH_STATUSES = [
  'NEW', 'RESEARCHED', 'EMAIL_GENERATED', 'PENDING_APPROVAL', 'APPROVED',
  'SENT', 'DELIVERED', 'BOUNCED', 'REPLIED', 'OPTED_OUT', 'FOLLOW_UP_DUE',
  'COMPLETED', 'REJECTED',
] as const;
export type OutreachStatus = (typeof OUTREACH_STATUSES)[number];

export interface OutreachMessage {
  id: number;
  event: DiscoveredEvent;
  organizer?: DiscoveredOrganizer | null;
  campaignId?: number | null;
  recipient?: string | null;
  subject?: string | null;
  message?: string | null;
  generatedBy: 'ai' | 'deterministic_fallback';
  status: OutreachStatus;
  failureReason?: string | null;
  sendAttemptCount: number;
  sentAt?: string | null;
  lastContactedAt?: string | null;
  responseAt?: string | null;
  followUpSentAt?: string | null;
  messageId?: string | null;
  createdAt: string;
}

export interface OutreachStats {
  eventsFound: number;
  qualifiedEvents: number;
  organizersFound: number;
  messagesSent: number;
  followUpsSent: number;
  responses: number;
  failedMessages: number;
  emailProviderStatus: 'REAL' | 'NOT_CONFIGURED';
}

export interface AgentRun {
  id: number;
  agentType: 'discovery' | 'outreach';
  status: 'running' | 'completed' | 'failed';
  startedAt: string;
  completedAt?: string | null;
  configSnapshot?: Record<string, unknown> | null;
  summary: Record<string, number>;
  error?: string | null;
}

export interface DiscoveryAutoStatus {
  enabled: boolean;
  intervalMinutes: number;
}

export type OutreachAction =
  | 'approve' | 'reject' | 'send' | 'retry' | 'opt_out' | 'ignore' | 'restrict_organizer' | 'mark_replied';

// ---------------------------------------------------------------------------
// Status metadata
// ---------------------------------------------------------------------------

export const STATUS_LABEL: Record<OutreachStatus, string> = {
  NEW: 'New',
  RESEARCHED: 'Researched',
  EMAIL_GENERATED: 'Email generated',
  PENDING_APPROVAL: 'Awaiting approval',
  APPROVED: 'Approved',
  SENT: 'Sent',
  DELIVERED: 'Delivered',
  BOUNCED: 'Bounced',
  REPLIED: 'Replied',
  OPTED_OUT: 'Opted out',
  FOLLOW_UP_DUE: 'Follow-up due',
  COMPLETED: 'Completed',
  REJECTED: 'Rejected',
};

// Which resting statuses each Outreach tab shows. "Sent" means a send was attempted, so it
// includes DELIVERED and BOUNCED; with plain SMTP a successful send lands directly on DELIVERED.
export const OUTREACH_TABS = [
  { key: 'all', label: 'All', statuses: null },
  { key: 'pending', label: 'Pending', statuses: ['NEW', 'RESEARCHED', 'EMAIL_GENERATED', 'PENDING_APPROVAL', 'APPROVED'] },
  { key: 'sent', label: 'Sent', statuses: ['SENT', 'DELIVERED', 'BOUNCED'] },
  { key: 'delivered', label: 'Delivered', statuses: ['DELIVERED'] },
  { key: 'replies', label: 'Replies', statuses: ['REPLIED'] },
  { key: 'follow-ups', label: 'Follow-ups', statuses: ['FOLLOW_UP_DUE'] },
] as const;
export type OutreachTabKey = (typeof OUTREACH_TABS)[number]['key'];

// Statuses a message can still be edited/approved in (mirrors backend _PRE_SEND_STATUSES).
export const PRE_SEND_STATUSES: OutreachStatus[] = ['NEW', 'RESEARCHED', 'EMAIL_GENERATED', 'PENDING_APPROVAL', 'APPROVED', 'FOLLOW_UP_DUE'];
export const APPROVABLE_STATUSES: OutreachStatus[] = ['PENDING_APPROVAL', 'FOLLOW_UP_DUE'];
export const TERMINAL_STATUSES: OutreachStatus[] = ['COMPLETED', 'REJECTED'];

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const keys = {
  me: ['ops', 'me'] as const,
  events: ['ops', 'discovered-events'] as const,
  organizers: ['ops', 'discovered-organizers'] as const,
  outreach: ['ops', 'outreach-messages'] as const,
  outreachStats: ['ops', 'outreach-stats'] as const,
  discoveryRuns: ['ops', 'runs', 'discovery'] as const,
  outreachRuns: ['ops', 'runs', 'outreach'] as const,
  discoveryAuto: ['ops', 'discovery-auto'] as const,
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useMe(enabled = true) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => customFetch<Me>('/api/auth/me'),
    enabled,
    retry: false,
  });
}

// The list endpoints cap at limit=200. Current volumes (dozens of rows) fit in one request,
// so filtering/search/sort happen client-side; if the tables outgrow that, pagination goes here.
const LIST_LIMIT = 200;

export function useDiscoveredEvents() {
  return useQuery({
    queryKey: keys.events,
    queryFn: () => customFetch<DiscoveredEvent[]>(`/api/discovery/events?limit=${LIST_LIMIT}`),
  });
}

export function useDiscoveredOrganizers() {
  return useQuery({
    queryKey: keys.organizers,
    queryFn: () => customFetch<DiscoveredOrganizer[]>(`/api/discovery/organizers?limit=${LIST_LIMIT}`),
  });
}

export function useOutreachMessages() {
  return useQuery({
    queryKey: keys.outreach,
    queryFn: () => customFetch<OutreachMessage[]>('/api/acquisition/outreach'),
  });
}

export function useOutreachStats() {
  return useQuery({
    queryKey: keys.outreachStats,
    queryFn: () => customFetch<OutreachStats>('/api/acquisition/outreach/stats'),
  });
}

export function useDiscoveryRuns() {
  return useQuery({
    queryKey: keys.discoveryRuns,
    queryFn: () => customFetch<AgentRun[]>('/api/discovery/runs?limit=100'),
  });
}

export function useOutreachRuns() {
  return useQuery({
    queryKey: keys.outreachRuns,
    queryFn: () => customFetch<AgentRun[]>('/api/acquisition/outreach/runs?limit=100'),
  });
}

export function useDiscoveryAutoStatus() {
  return useQuery({
    queryKey: keys.discoveryAuto,
    queryFn: () => customFetch<DiscoveryAutoStatus>('/api/discovery/auto'),
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

function useInvalidate() {
  const qc = useQueryClient();
  return (...groups: Array<readonly string[]>) => groups.forEach((k) => qc.invalidateQueries({ queryKey: k }));
}

export function useOutreachAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, reason }: { id: number; action: OutreachAction; reason?: string }) =>
      customFetch<OutreachMessage>(`/api/acquisition/outreach/${id}/action`, {
        method: 'POST',
        body: JSON.stringify(reason ? { action, reason } : { action }),
      }),
    onSuccess: () => invalidate(keys.outreach, keys.outreachStats, keys.organizers),
  });
}

export function useEditOutreachMessage() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, subject, message }: { id: number; subject: string; message: string }) =>
      customFetch<OutreachMessage>(`/api/acquisition/outreach/${id}/edit`, {
        method: 'PATCH',
        body: JSON.stringify({ subject, message }),
      }),
    onSuccess: () => invalidate(keys.outreach),
  });
}

export function useSetDiscoveryAuto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      customFetch<DiscoveryAutoStatus>('/api/discovery/auto', { method: 'PATCH', body: JSON.stringify({ enabled }) }),
    onSuccess: (data) => qc.setQueryData(keys.discoveryAuto, data),
  });
}

export function useRunDiscovery() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { cities?: string[]; categories?: string[]; searchDepth?: number; sourcesPerQuery?: number } = {}) =>
      customFetch<Record<string, unknown>>('/api/discovery/run', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidate(keys.events, keys.organizers, keys.discoveryRuns, keys.outreachStats),
  });
}

export function useRunOutreachBatch() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { maxCandidates?: number } = {}) =>
      customFetch<Record<string, unknown>>('/api/acquisition/outreach/batch-run', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidate(keys.outreach, keys.outreachStats, keys.outreachRuns),
  });
}

export function useProcessFollowups() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => customFetch<Record<string, number>>('/api/acquisition/outreach/process-followups', { method: 'POST' }),
    onSuccess: () => invalidate(keys.outreach, keys.outreachStats),
  });
}

// ---------------------------------------------------------------------------
// Derived data helpers (pure functions over the loaded lists)
// ---------------------------------------------------------------------------

export function organizerById(organizers: DiscoveredOrganizer[] | undefined, id?: number | null) {
  if (!id || !organizers) return undefined;
  return organizers.find((o) => o.id === id);
}

export function eventsForOrganizer(events: DiscoveredEvent[] | undefined, organizerId: number) {
  return (events ?? []).filter((e) => e.organizerId === organizerId);
}

export function messagesForOrganizer(messages: OutreachMessage[] | undefined, organizerId: number) {
  return (messages ?? []).filter((m) => m.organizer?.id === organizerId);
}

export function messagesForEvent(messages: OutreachMessage[] | undefined, eventId: number) {
  return (messages ?? []).filter((m) => m.event?.id === eventId);
}

export function contactSummary(messages: OutreachMessage[]) {
  const sent = messages.filter((m) => Boolean(m.sentAt)).length;
  const delivered = messages.filter((m) => m.status === 'DELIVERED' || m.status === 'REPLIED' || m.status === 'FOLLOW_UP_DUE' || m.status === 'COMPLETED').length;
  const replies = messages.filter((m) => Boolean(m.responseAt)).length;
  const last = messages.map((m) => m.lastContactedAt ?? m.sentAt).filter(Boolean).sort().at(-1) ?? null;
  return { total: messages.length, sent, delivered, replies, lastContact: last };
}

/** Human-facing organizer contact status for tables: derived from real outreach rows. */
export function contactStatus(messages: OutreachMessage[]): 'Not contacted' | 'Pending approval' | 'Contacted' | 'Replied' | 'Do not contact' {
  if (messages.some((m) => m.status === 'OPTED_OUT')) return 'Do not contact';
  if (messages.some((m) => Boolean(m.responseAt))) return 'Replied';
  if (messages.some((m) => Boolean(m.sentAt))) return 'Contacted';
  if (messages.some((m) => PRE_SEND_STATUSES.includes(m.status))) return 'Pending approval';
  return 'Not contacted';
}
