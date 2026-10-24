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
  roles?: string[];
  emailVerified?: boolean;
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
  country?: string | null;
  countries?: string[];
  cities?: string[];
  states?: string[];
  categories?: string[];
  sources?: string[];
  searchDepth?: number | null;
  dailyLimit?: number | null;
  eventsPerRun?: number | null;
  targetValidEvents?: number | null;
  // Event rejection rules
  rejectNoOrganizer?: boolean;
  requireOrganizerEmail?: boolean;
  requireOrganizerPhone?: boolean;
  requireOrganizerWebsite?: boolean;
  rejectPastEvents?: boolean;
  rejectUnparseableDates?: boolean;
  rejectMissingLocation?: boolean;
  rejectMissingTicketUrl?: boolean;
  rejectUnmatchedCategory?: boolean;
  fallbackToOtherSector?: boolean;
  minTitleLength?: number;
  minDescriptionLength?: number;
  minConfidenceScore?: number;
  blacklistedKeywords?: string[];
  excludedDomains?: string[];
}

export interface OutreachAutoStatus {
  enabled: boolean;
  draftIntervalMinutes: number;
  followupIntervalMinutes: number;
  country?: string | null;
  countries?: string[];
  cities?: string[];
  states?: string[];
  categories?: string[];
  maxCandidates?: number;
  dailyLimit?: number;
  followupWaitDays?: number;
  maxFollowupAttempts?: number;
  senderName?: string;
  templateStyle?: string;
}

/** Real database counts — never derived by counting the (200-row-capped)
 * events/organizers lists client-side. Those lists are for browsing a page
 * at a time; once discovery finds more than 200, a count computed from
 * `.length` on that list silently stops growing. These numbers don't. */
export interface DiscoveryStats {
  eventsTotal: number;
  organizersTotal: number;
  contactsTotal: number;
  organizersWithEmailTotal: number;
  needsReviewTotal: number;
  newEventsTotal: number;
  onlineTotal: number;
  offlineTotal: number;
  hybridTotal: number;
  formatUnknownTotal: number;
  venueMissingTotal: number;
  venueMissingSample: Array<{ id: number; name: string | null; city: string | null }>;
}

export type AutomationRequestStatus = 'NEW' | 'IN_PROGRESS' | 'DONE' | 'DECLINED';

export interface AutomationRequest {
  id: number;
  description: string;
  status: AutomationRequestStatus;
  requestedBy: string | null;
  note: string | null;
  createdAt: string;
  updatedAt: string;
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
// SMTP Delivery & Outbox Types
// ---------------------------------------------------------------------------

export interface SmtpConfig {
  configured: boolean;
  status: 'REAL' | 'NOT_CONFIGURED';
  provider: string;
  host: string;
  port: number;
  username: string;
  fromEmail: string;
  useTls: boolean;
  hasPassword: boolean;
}

export interface SmtpConfigRequest {
  host: string;
  port: number;
  username?: string;
  password?: string;
  fromEmail: string;
  useTls: boolean;
}

export interface SmtpTestRequest {
  recipient: string;
  subject?: string;
  body?: string;
}

export interface SmtpTestResult {
  success: boolean;
  message: string;
  messageId?: string;
  provider: string;
  bounced: boolean;
}

export interface OutboxItem {
  id: string;
  timestamp: string;
  recipient: string;
  subject: string;
  body: string;
  html?: string | null;
  provider: string;
  status: string;
  messageId?: string | null;
  error?: string | null;
}

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
  outreachAuto: ['ops', 'outreach-auto'] as const,
  discoveryStats: ['ops', 'discovery-stats'] as const,
  automationRequests: ['ops', 'automation-requests'] as const,
  smtpConfig: ['ops', 'smtp-config'] as const,
  emailOutbox: ['ops', 'email-outbox'] as const,
  categories: ['ops', 'categories'] as const,
};

export const PLATFORM_CATEGORIES = [
  'Construction',
  'Energy and Power Generation',
  'Finance',
  'Healthcare',
  'Manufacturing',
  'Mining',
  'Oil and Gas',
  'Packaging',
  'Pharmaceuticals',
  'Telecommunications',
  'Textiles',
  'Transport and Logistics',
] as const;

export interface CategoryItem {
  id: number;
  name: string;
  slug: string;
  description?: string;
  icon?: string;
  eventCount?: number;
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useCategories() {
  return useQuery({
    queryKey: keys.categories,
    queryFn: () => customFetch<CategoryItem[]>('/api/categories'),
  });
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => customFetch<Me>('/api/auth/me'),
    enabled,
    retry: false,
  });
}

// Fetches the full discovered-events/organizers list in one request so client-side
// filtering/search/sort/pagination always works against everything, not a stale slice —
// discovery hit the old 200-row cap for real and the overview silently stopped growing.
// The backend caps this at 5000; true totals for headline numbers come from `/stats`
// (`useDiscoveryStats`) instead of counting this list, so those stay correct either way.
const LIST_LIMIT = 5000;

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

export function useDiscoveryStats() {
  return useQuery({
    queryKey: keys.discoveryStats,
    queryFn: () => customFetch<DiscoveryStats>('/api/discovery/stats'),
    // The automatic discovery scan (every 60 min, when its switch is on) finds and stores
    // events entirely server-side — no mutation in this tab to invalidate the cache off of.
    // Poll so the overview reflects what the background automation just did without a manual refresh.
    refetchInterval: 60_000,
  });
}

export function useOutreachAutoStatus() {
  return useQuery({
    queryKey: keys.outreachAuto,
    queryFn: () => customFetch<OutreachAutoStatus>('/api/acquisition/outreach/auto'),
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
    mutationFn: (
      payload:
        | boolean
        | (Partial<DiscoveryAutoStatus> & {
            enabled?: boolean;
          })
    ) => {
      const body = typeof payload === 'boolean' ? { enabled: payload } : payload;
      return customFetch<DiscoveryAutoStatus>('/api/discovery/auto', {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
    },
    onSuccess: (data) => qc.setQueryData(keys.discoveryAuto, data),
  });
}

export function useSetOutreachAuto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (
      payload:
        | boolean
        | {
            enabled?: boolean;
            country?: string | null;
            countries?: string[];
            cities?: string[];
            states?: string[];
            categories?: string[];
            maxCandidates?: number;
            dailyLimit?: number;
            followupWaitDays?: number;
            maxFollowupAttempts?: number;
            senderName?: string;
            templateStyle?: string;
            draftIntervalMinutes?: number;
            followupIntervalMinutes?: number;
          }
    ) => {
      const body = typeof payload === 'boolean' ? { enabled: payload } : payload;
      return customFetch<OutreachAutoStatus>('/api/acquisition/outreach/auto', {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
    },
    onSuccess: (data) => qc.setQueryData(keys.outreachAuto, data),
  });
}

export function useAutomationRequests() {
  return useQuery({
    queryKey: keys.automationRequests,
    queryFn: () => customFetch<AutomationRequest[]>('/api/automations/requests'),
  });
}

export function useCreateAutomationRequest() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (description: string) =>
      customFetch<AutomationRequest>('/api/automations/requests', { method: 'POST', body: JSON.stringify({ description }) }),
    onSuccess: () => invalidate(keys.automationRequests),
  });
}

export interface DiscoveryRunPayload {
  cities?: string[];
  states?: string[];
  categories?: string[];
  country?: string | null;
  countries?: string[];
  sources?: string[];
  eventsPerRun?: number;
  targetValidEvents?: number;
  searchDepth?: number;
  sourcesPerQuery?: number;
  dailyLimit?: number;
  dateFrom?: string;
  dateTo?: string;
  fallbackToOtherSector?: boolean;
  rejectNoOrganizer?: boolean;
  requireOrganizerEmail?: boolean;
  requireOrganizerPhone?: boolean;
  requireOrganizerWebsite?: boolean;
  rejectPastEvents?: boolean;
  rejectUnparseableDates?: boolean;
  rejectMissingLocation?: boolean;
  rejectMissingTicketUrl?: boolean;
  rejectUnmatchedCategory?: boolean;
  minTitleLength?: number;
  minDescriptionLength?: number;
  minConfidenceScore?: number;
  blacklistedKeywords?: string[];
  excludedDomains?: string[];
}

export function useRunDiscovery() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: DiscoveryRunPayload = {}) =>
      customFetch<Record<string, unknown>>('/api/discovery/run', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidate(keys.events, keys.organizers, keys.discoveryRuns, keys.outreachStats, keys.discoveryStats),
  });
}

/** Excel file of discovered events (and their organizers) with an event date in [from, to]; either bound may be blank. */
export function useDownloadDiscoveredEvents() {
  return useMutation({
    mutationFn: async ({ from, to }: { from: string; to: string }) => {
      const params = new URLSearchParams();
      if (from) params.set('from', from);
      if (to) params.set('to', to);
      const blob = await customFetch<Blob>(`/api/discovery/export.xlsx${params.size ? `?${params}` : ''}`, { responseType: 'blob' });
      const label = from || to ? `${from || 'start'}_to_${to || 'latest'}` : 'all';
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `discovered-events_${label}.xlsx`;
      link.click();
      URL.revokeObjectURL(link.href);
    },
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

export function useSmtpConfig() {
  return useQuery({
    queryKey: keys.smtpConfig,
    queryFn: () => customFetch<SmtpConfig>('/api/acquisition/outreach/smtp/config'),
  });
}

export function useSaveSmtpConfig() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: SmtpConfigRequest) =>
      customFetch<SmtpConfig>('/api/acquisition/outreach/smtp/config', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidate(keys.smtpConfig, keys.outreachStats),
  });
}

export function useTestSmtp() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: SmtpTestRequest) =>
      customFetch<SmtpTestResult>('/api/acquisition/outreach/smtp/test', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidate(keys.emailOutbox),
  });
}

export function useEmailOutbox() {
  return useQuery({
    queryKey: keys.emailOutbox,
    queryFn: () => customFetch<OutboxItem[]>('/api/acquisition/outreach/smtp/outbox'),
    refetchInterval: 5000,
  });
}

export function useClearEmailOutbox() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => customFetch<{ status: string }>('/api/acquisition/outreach/smtp/outbox/clear', { method: 'POST' }),
    onSuccess: () => invalidate(keys.emailOutbox),
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

// ---------------------------------------------------------------------------
// Community Discovery (Agent 5) + Community Promotion (Agent 4 extension)
// ---------------------------------------------------------------------------

export interface CommunitySource {
  id: number;
  sourceUrl: string;
  sourceType: string;
  fetchedAt: string;
}

/** DISCOVERED | NEEDS_REVIEW | APPROVED | REJECTED | CONNECTION_REQUIRED | CONNECTED | PERMISSION_MISSING | PROMOTION_RESTRICTED */
export type CommunityApprovalStatus = 'DISCOVERED' | 'NEEDS_REVIEW' | 'APPROVED' | 'REJECTED' | 'CONNECTION_REQUIRED' | 'CONNECTED' | 'PERMISSION_MISSING' | 'PROMOTION_RESTRICTED';

export interface DiscoveredCommunity {
  id: number;
  platform: 'telegram' | 'discord';
  name: string;
  canonicalUrl: string;
  inviteUrl: string | null;
  description: string | null;
  category: string | null;
  subcategory: string | null;
  topics: string[];
  language: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  memberCount: number | null;
  rulesText: string | null;
  promotionAllowed: boolean | null;
  automationAllowed: boolean;
  riskLevel: string;
  confidenceScore: number;
  discoveryStatus: string;
  verificationNotes: string[];
  approvalStatus: CommunityApprovalStatus;
  rejectionReason: string | null;
  connectionStatus: string;
  communityId: number | null;
  discoveredAt: string;
  lastCheckedAt: string | null;
  sources: CommunitySource[];
}

export interface CommunityDiscoveryStats {
  communitiesTotal: number;
  needsReviewTotal: number;
  approvedTotal: number;
  connectedTotal: number;
  telegramTotal: number;
  discordTotal: number;
}

export type CommunityAction = 'approve' | 'reject' | 'mark_connection_required' | 'mark_connected' | 'mark_permission_missing' | 'mark_promotion_restricted';

export interface PromotedEventSummary {
  id: number;
  title: string;
  slug: string;
}

export interface TargetCommunitySummary {
  id: number;
  name: string;
  platform: string;
  connected: boolean;
}

/** A drafted event<->community promotion post (Agent 4 extension). Reuses the
 * existing acquisition-opportunity pipeline under the hood — `sourceKind`
 * distinguishes this from the original discussion-reply flow, which this
 * console doesn't surface (kept out of the UI since the 2026 redesign). */
export interface CommunityPromotionOpportunity {
  id: number;
  sourceKind: 'discussion_reply' | 'community_promotion';
  promotedEvent: PromotedEventSummary | null;
  targetCommunity: TargetCommunitySummary | null;
  matchExplanation: string | null;
  relevanceScore: number;
  generatedResponse: string;
  contentPayload: { subject?: string } | null;
  contentGeneratedBy: 'ai' | 'deterministic_fallback' | null;
  approvalStatus: 'pending' | 'approved' | 'rejected' | 'scheduled' | 'ready_for_manual_publishing' | 'published';
  referralUrl: string;
  clicksCount: number;
  registrationsCount: number;
  scheduledAt: string | null;
  publishedAt: string | null;
  publishedUrl: string | null;
  reviewedAt: string | null;
  createdAt: string;
}

const COMMUNITY_LIST_LIMIT = 5000;

const communityKeys = {
  communities: ['ops', 'discovered-communities'] as const,
  communityStats: ['ops', 'community-discovery-stats'] as const,
  communityAuto: ['ops', 'community-discovery-auto'] as const,
  communityRuns: ['ops', 'runs', 'community-discovery'] as const,
  promotionOpportunities: ['ops', 'community-promotion-opportunities'] as const,
  promotionAuto: ['ops', 'community-promotion-auto'] as const,
  promotionRuns: ['ops', 'runs', 'community-promotion'] as const,
};

export function useDiscoveredCommunities() {
  return useQuery({
    queryKey: communityKeys.communities,
    queryFn: () => customFetch<DiscoveredCommunity[]>(`/api/community-discovery/communities?limit=${COMMUNITY_LIST_LIMIT}`),
  });
}

export function useCommunityDiscoveryStats() {
  return useQuery({
    queryKey: communityKeys.communityStats,
    queryFn: () => customFetch<CommunityDiscoveryStats>('/api/community-discovery/stats'),
    refetchInterval: 60_000, // the background scan (when on) finds communities with no tab open to invalidate off of
  });
}

export function useCommunityDiscoveryAutoStatus() {
  return useQuery({
    queryKey: communityKeys.communityAuto,
    queryFn: () => customFetch<DiscoveryAutoStatus>('/api/community-discovery/auto'),
  });
}

export function useSetCommunityDiscoveryAuto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      customFetch<DiscoveryAutoStatus>('/api/community-discovery/auto', { method: 'PATCH', body: JSON.stringify({ enabled }) }),
    onSuccess: (data) => qc.setQueryData(communityKeys.communityAuto, data),
  });
}

export function useCommunityDiscoveryRuns() {
  return useQuery({
    queryKey: communityKeys.communityRuns,
    queryFn: () => customFetch<AgentRun[]>('/api/community-discovery/runs?limit=100'),
  });
}

export function useRunCommunityDiscovery() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { cities?: string[]; states?: string[]; categories?: string[]; country?: string; countries?: string[]; searchDepth?: number; sourcesPerQuery?: number; dateFrom?: string; dateTo?: string } = {}) =>
      customFetch<Record<string, unknown>>('/api/community-discovery/run', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidate(communityKeys.communities, communityKeys.communityStats, communityKeys.communityRuns),
  });
}

export function useCommunityAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, reason }: { id: number; action: CommunityAction; reason?: string }) =>
      customFetch<DiscoveredCommunity>(`/api/community-discovery/communities/${id}/action`, {
        method: 'POST', body: JSON.stringify(reason ? { action, reason } : { action }),
      }),
    onSuccess: () => invalidate(communityKeys.communities, communityKeys.communityStats),
  });
}

export function usePromotionOpportunities() {
  return useQuery({
    queryKey: communityKeys.promotionOpportunities,
    queryFn: () => customFetch<CommunityPromotionOpportunity[]>('/api/acquisition/opportunities?limit=100'),
    select: (rows) => rows.filter((r) => r.sourceKind === 'community_promotion'),
  });
}

export function useCommunityPromotionAutoStatus() {
  return useQuery({
    queryKey: communityKeys.promotionAuto,
    queryFn: () => customFetch<DiscoveryAutoStatus>('/api/community-promotion/auto'),
  });
}

export function useSetCommunityPromotionAuto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      customFetch<DiscoveryAutoStatus>('/api/community-promotion/auto', { method: 'PATCH', body: JSON.stringify({ enabled }) }),
    onSuccess: (data) => qc.setQueryData(communityKeys.promotionAuto, data),
  });
}

export function useCommunityPromotionRuns() {
  return useQuery({
    queryKey: communityKeys.promotionRuns,
    queryFn: () => customFetch<AgentRun[]>('/api/community-promotion/runs?limit=100'),
  });
}

export function useRunCommunityPromotion() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { maxCandidates?: number } = {}) =>
      customFetch<Record<string, unknown>>('/api/community-promotion/run', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidate(communityKeys.promotionOpportunities, communityKeys.promotionRuns),
  });
}

export type PromotionOpportunityAction = 'approve' | 'reject' | 'ignore' | 'approve_and_publish';

export function usePromotionOpportunityAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: PromotionOpportunityAction }) =>
      customFetch<CommunityPromotionOpportunity>(`/api/acquisition/opportunities/${id}/action`, { method: 'POST', body: JSON.stringify({ action }) }),
    onSuccess: () => invalidate(communityKeys.promotionOpportunities),
  });
}

export function usePublishPromotionOpportunity() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => customFetch<CommunityPromotionOpportunity>(`/api/acquisition/opportunities/${id}/publish`, { method: 'POST' }),
    onSuccess: () => invalidate(communityKeys.promotionOpportunities),
  });
}

/** Matches `routes/acquisition.py`'s `CommunityUpdateInput` — used to set a
 * community's `platformRef` once a human has actually connected the bot and
 * looked up its real chat/channel id, and/or confirming the separate,
 * explicit "promotion allowed" policy decision once a human has actually
 * read the community's rules. Neither is ever set by the agent itself. */
export function useUpdateCommunityPolicy() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ communityId, platformRef, promotionAllowed }: { communityId: number; platformRef?: string; promotionAllowed?: boolean }) =>
      customFetch<unknown>(`/api/acquisition/communities/${communityId}`, {
        method: 'PATCH',
        body: JSON.stringify({ ...(platformRef !== undefined && { platformRef }), ...(promotionAllowed !== undefined && { promotionAllowed }) }),
      }),
    onSuccess: () => invalidate(communityKeys.communities, communityKeys.promotionOpportunities),
  });
}

// ---------------------------------------------------------------------------
// Social Event Promotions (Instagram, Facebook, LinkedIn, Telegram, Discord)
// ---------------------------------------------------------------------------

export interface PromotionJob {
  id: number;
  eventId: number;
  event?: {
    id: number;
    title: string;
    slug: string;
    startDate?: string | null;
    format?: string | null;
    city?: string | null;
    category?: string | null;
    status: string;
    image?: string | null;
  } | null;
  platform: string;
  destinationRef?: string | null;
  status: string;
  isDryRun: boolean;
  title?: string | null;
  content: string;
  mediaUrls?: string[];
  utmParams?: Record<string, string>;
  trackingUrl?: string | null;
  externalPostId?: string | null;
  publishedUrl?: string | null;
  retryCount: number;
  maxRetries: number;
  lastError?: string | null;
  approvalRequired: boolean;
  approvedBy?: string | null;
  approvedAt?: string | null;
  publishedAt?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface PlatformPromotionSetting {
  id: number;
  platform: string;
  enabled: boolean;
  autoPublish: boolean;
  dryRun: boolean;
  defaultDestination?: string | null;
  rateLimitPerDay: number;
  customPromptTemplate?: string | null;
  isConnected: boolean;
  connectionMessage: string;
  updatedAt?: string | null;
}

export interface PromotionStats {
  totalJobs: number;
  published: number;
  dryRun: number;
  pendingApproval: number;
  failed: number;
  byPlatform: Record<string, number>;
}

export const promotionKeys = {
  jobs: ['promotions', 'jobs'] as const,
  settings: ['promotions', 'settings'] as const,
  stats: ['promotions', 'stats'] as const,
};

export function usePromotionJobs(filters?: { platform?: string; status?: string; page?: number; pageSize?: number }) {
  const params = new URLSearchParams();
  if (filters?.platform) params.set('platform', filters.platform);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.page) params.set('page', String(filters.page));
  if (filters?.pageSize) params.set('page_size', String(filters.pageSize));
  const qs = params.toString();

  return useQuery({
    queryKey: [...promotionKeys.jobs, filters],
    queryFn: () => customFetch<{ items: PromotionJob[]; total: number; page: number; pageSize: number; totalPages: number }>(`/api/promotions/jobs${qs ? `?${qs}` : ''}`),
  });
}

export function usePromotionSettings() {
  return useQuery({
    queryKey: promotionKeys.settings,
    queryFn: () => customFetch<PlatformPromotionSetting[]>('/api/promotions/settings'),
  });
}

export function usePromotionStats() {
  return useQuery({
    queryKey: promotionKeys.stats,
    queryFn: () => customFetch<PromotionStats>('/api/promotions/stats'),
  });
}

export function useApprovePromotionJob() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, dryRun }: { id: number; dryRun?: boolean }) =>
      customFetch<PromotionJob>(`/api/promotions/jobs/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ dry_run: dryRun }),
      }),
    onSuccess: () => invalidate(promotionKeys.jobs, promotionKeys.stats),
  });
}

export function useRejectPromotionJob() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) =>
      customFetch<PromotionJob>(`/api/promotions/jobs/${id}/reject`, { method: 'POST' }),
    onSuccess: () => invalidate(promotionKeys.jobs, promotionKeys.stats),
  });
}

export function useRetryPromotionJob() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) =>
      customFetch<PromotionJob>(`/api/promotions/jobs/${id}/retry`, { method: 'POST' }),
    onSuccess: () => invalidate(promotionKeys.jobs, promotionKeys.stats),
  });
}

export function useUpdatePromotionJobContent() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, content, title, destinationRef }: { id: number; content: string; title?: string; destinationRef?: string }) =>
      customFetch<PromotionJob>(`/api/promotions/jobs/${id}/content`, {
        method: 'PATCH',
        body: JSON.stringify({ content, title, destination_ref: destinationRef }),
      }),
    onSuccess: () => invalidate(promotionKeys.jobs),
  });
}

export function useUpdatePlatformSetting() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ platform, updates }: { platform: string; updates: Partial<PlatformPromotionSetting> }) =>
      customFetch<PlatformPromotionSetting>(`/api/promotions/settings/${platform}`, {
        method: 'PATCH',
        body: JSON.stringify({
          enabled: updates.enabled,
          auto_publish: updates.autoPublish,
          dry_run: updates.dryRun,
          default_destination: updates.defaultDestination,
          rate_limit_per_day: updates.rateLimitPerDay,
        }),
      }),
    onSuccess: () => invalidate(promotionKeys.settings),
  });
}

export function useTriggerEventPromotion() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ eventId, platforms, force }: { eventId: number; platforms?: string[]; force?: boolean }) =>
      customFetch<PromotionJob[]>(`/api/promotions/events/${eventId}/trigger`, {
        method: 'POST',
        body: JSON.stringify({ platforms, force }),
      }),
    onSuccess: () => invalidate(promotionKeys.jobs, promotionKeys.stats),
  });
}

