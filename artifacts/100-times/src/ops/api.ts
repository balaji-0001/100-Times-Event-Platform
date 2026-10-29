// Data layer for the 100Times operations admin (Organizer Discovery + Organizer Outreach).
// Every type here mirrors a backend response schema in artifacts/api-server/backend/schemas.py,
// and every hook binds to an endpoint that already exists — nothing is mocked.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customFetch } from '@workspace/api-client-react';
import type { DiscoveryLocation } from '@/lib/countries';

// ---------------------------------------------------------------------------
// Types (camelCase, exactly as serialized by the API)
// ---------------------------------------------------------------------------

export interface Me {
  id: number;
  name: string;
  email: string;
  role: 'USER' | 'ORGANIZER' | 'ADMIN';
  roles?: string[];
  accountType?: 'attendee' | 'organiser' | 'admin';
  emailVerified?: boolean;
  // Profile fields returned by GET /api/auth/me (UserOut).
  country?: string | null;
  company?: string | null;
  jobTitle?: string | null;
  bio?: string | null;
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
  discoveryStatus: 'NEW' | 'DUPLICATE' | 'PROMOTED' | 'REJECTED';
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
  status: 'running' | 'completed' | 'failed' | 'stopped';
  startedAt: string;
  completedAt?: string | null;
  configSnapshot?: Record<string, unknown> | null;
  // Mostly counters; also `stop_reason`, `target_shortfall` and a `timings` object (see RunSummary).
  summary: Record<string, any>;
  error?: string | null;
}

export interface DiscoveryAutoStatus {
  enabled: boolean;
  intervalMinutes: number;
  country?: string | null;
  countries?: string[];
  /** Structured country -> state -> city selection (see buildDiscoveryLocations). */
  locations?: DiscoveryLocation[];
  /** State -> cities lists for countries where a whole state is ticked (see buildRegionCities). */
  regionCities?: Record<string, Record<string, string[]>>;
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
  /** Store events a run rejects (with the reason) so they can be reviewed and restored. */
  keepRejectedEvents?: boolean;
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
  listingUrls?: string[];
  /** Whether a Ticketmaster key is saved (and its last 4 characters) — the key itself never reaches the browser. */
  ticketmasterApiKeySet?: boolean;
  ticketmasterApiKeyHint?: string | null;
  ticketmasterEnabled?: boolean;
  /** Web-search providers runs may call; null/undefined = every configured provider. */
  searchProviders?: string[] | null;
}

/** PATCH /api/discovery/auto body: a new key to save ("" removes it), or omit to keep it. */
export type DiscoveryAutoUpdate = Partial<DiscoveryAutoStatus> & {
  enabled?: boolean;
  ticketmasterApiKey?: string | null;
  resetSearchProviders?: boolean;
};

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
  rejectedTotal?: number;
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
  outreachBacklog: ['ops', 'outreach-backlog'] as const,
  discoveryRuns: ['ops', 'runs', 'discovery'] as const,
  outreachRuns: ['ops', 'runs', 'outreach'] as const,
  discoveryAuto: ['ops', 'discovery-auto'] as const,
  outreachAuto: ['ops', 'outreach-auto'] as const,
  discoveryStats: ['ops', 'discovery-stats'] as const,
  discoveryActiveRun: ['ops', 'discovery-active-run'] as const,
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

// `live` = the run is still executing: events are stored the moment they're
// verified, so poll to show them as they arrive.
export function useDiscoveryRunEvents(runId: number | null, live = false) {
  return useQuery({
    queryKey: ['discoveryRunEvents', runId],
    queryFn: () => customFetch<DiscoveredEvent[]>(`/api/discovery/runs/${runId}/events`),
    enabled: Boolean(runId),
    refetchInterval: live ? 3000 : false,
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

export interface ActiveDiscoveryRunResponse {
  active: boolean;
  run: AgentRun | null;
}

export function useActiveDiscoveryRun() {
  return useQuery({
    queryKey: keys.discoveryActiveRun,
    queryFn: () => customFetch<ActiveDiscoveryRunResponse>('/api/discovery/runs/active'),
    refetchInterval: (query) => (query.state.data?.active ? 2000 : 8000),
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

// --- Discovery provider registry (GET /api/discovery/catalog) ---------------

export type SourceHealthStatus = 'ok' | 'no_events' | 'failed' | 'untested' | 'not_implemented' | 'not_configured';

export interface CatalogProvider {
  id: string;
  name: string;
  full_name: string;
  tier: 'free' | 'paid' | 'last_resort';
  cost_rank: number;
  configured: boolean;
  unavailable_reason: string | null;
  setup_env: string[];
  docs_url: string | null;
  cooling_down_seconds: number;
  cooldown_reason: string | null;
  last_call: { status: string | null; error: string | null; results: number | null; at: string | null };
}

export interface CatalogSource {
  id: string;
  name: string;
  url: string;
  events_page: string | null;
  category: string;
  channel: 'directories' | 'aggregators' | 'apis';
  access_method: string;
  countries: string[];
  implemented: boolean;
  configured: boolean;
  enabled_by_admin: boolean;
  default_selected: boolean;
  health: { status: SourceHealthStatus; detail: string | null; checked_at: string | null; last_success_at: string | null };
}

export interface DiscoveryCatalog {
  channels: { id: 'web' | 'directories' | 'aggregators' | 'apis'; token: string | null; name: string; description: string }[];
  providers: CatalogProvider[];
  web_options: { id: string; name: string; description: string }[];
  sources: CatalogSource[];
  default_sources: string[];
  default_listing_urls: string[];
  strategy: string;
  paid_search_budget_per_run: number;
}

export function useDiscoveryCatalog() {
  return useQuery({
    queryKey: ['discoveryCatalog'],
    queryFn: () => customFetch<DiscoveryCatalog>('/api/discovery/catalog'),
    refetchInterval: 60_000,
  });
}

export interface CatalogCheckResult {
  sources: { id: string; ok: boolean; events: number; error: string | null; note?: string | null }[];
  skipped: { id: string; reason: string }[];
  providers: { id: string; status: string; error?: string; results?: number; cost_usd?: number | null }[];
}

/** Live probe of sources (and, only when listed, providers — paid ones are billed for the probe). */
export function useCheckDiscoveryCatalog() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { sourceIds?: string[]; providerIds?: string[] }) =>
      customFetch<CatalogCheckResult>('/api/discovery/catalog/check', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['discoveryCatalog'] });
      qc.invalidateQueries({ queryKey: ['discoverySearchProviders'] });
    },
  });
}

/** One row of a run's per-source execution report (RunSummary.sources). */
export interface RunSourceRow {
  id: string;
  name: string;
  channel: string;
  kind: 'search_provider' | 'adapter' | 'aggregator' | 'custom_website' | 'api';
  configured: boolean;
  available: boolean;
  status: 'pending' | 'skipped' | 'succeeded' | 'failed';
  reason: string | null;
  jobs: number;
  jobs_ok: number;
  jobs_failed: number;
  candidates: number;
  off_sector: number;
  duplicates: number;
  rejected: number;
  verified: number;
  needs_review: number;
  duration_ms: number;
  errors: string[];
  calls: number;
  results: number;
  zero_result_calls: number;
  rate_limited: number;
  cost_usd: number | null;
  skipped_reasons: Record<string, number>;
  purposes: Record<string, number>;
}

export interface RunSourceReport {
  counts: {
    selected: number;
    configured: number;
    available: number;
    executed: number;
    successful: number;
    returned_candidates: number;
    sources_with_candidates: number;
    succeeded_zero_results: number;
    failed: number;
    skipped: number;
    verified: number;
  };
  sources: RunSourceRow[];
}

export function useTestTicketmaster() {
  return useMutation({
    mutationFn: (body?: { apiKey?: string }) =>
      customFetch<{ success: boolean; message: string; totalEvents?: number }>(
        '/api/discovery/ticketmaster/test',
        {
          method: 'POST',
          body: body ? JSON.stringify(body) : undefined,
        }
      ),
  });
}

export function useSetDiscoveryAuto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: boolean | DiscoveryAutoUpdate) => {
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
    onSuccess: (data) => {
      qc.setQueryData(keys.outreachAuto, data);
      qc.invalidateQueries({ queryKey: keys.outreachBacklog }); // sectors/places decide what's waiting
    },
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
  locations?: DiscoveryLocation[];
  regionCities?: Record<string, Record<string, string[]>>;
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
  /** Store events a run rejects (with the reason) so they can be reviewed and restored. */
  keepRejectedEvents?: boolean;
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
  listingUrls?: string[];
  /** Only to try a new key; when omitted the saved key is used server-side. */
  ticketmasterApiKey?: string | null;
  ticketmasterEnabled?: boolean;
  /** Web-search providers this run may call; omit for every configured provider. */
  searchProviders?: string[];
}

export function useRunDiscovery() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: DiscoveryRunPayload = {}) =>
      customFetch<Record<string, unknown>>('/api/discovery/run', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidate(keys.events, keys.organizers, keys.discoveryRuns, keys.outreachStats, keys.discoveryStats, keys.discoveryActiveRun),
  });
}

export function useStopDiscoveryRun() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (runId?: number) =>
      customFetch<{ stopped: boolean; runId?: number; message?: string }>(
        runId ? `/api/discovery/runs/${runId}/stop` : '/api/discovery/runs/stop',
        { method: 'POST' }
      ),
    onSuccess: () =>
      invalidate(keys.discoveryActiveRun, keys.discoveryRuns, keys.events, keys.discoveryStats),
  });
}

export type EventReviewAction = 'restore' | 'approve' | 'reject';

/** An admin's decision on one discovered event: restore (rejected -> Needs review), approve (-> Verified) or reject. */
export function useReviewDiscoveredEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, note }: { id: number; action: EventReviewAction; note?: string }) =>
      customFetch<DiscoveredEvent>(`/api/discovery/events/${id}/review`, { method: 'POST', body: JSON.stringify({ action, note }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.events });
      qc.invalidateQueries({ queryKey: keys.discoveryStats });
    },
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
      customFetch<OutreachBatchResult>('/api/acquisition/outreach/batch-run', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidate(keys.outreach, keys.outreachStats, keys.outreachRuns, keys.outreachBacklog),
  });
}

export interface OutreachBatchResult {
  runId: number | null;
  status: string;
  drafted: number;
  candidates_considered: number;
  skipped_duplicate: number;
  skipped_suppressed: number;
  skipped_past_event?: number;
}

/** Discovered events that have an organizer e-mail but no outreach draft yet, and why. */
export interface OutreachBacklog {
  waiting: number;
  ready: number;
  past_event: number;
  outside_sectors: number;
  outside_locations: number;
  suppressed: number;
  sectors: string[];
  countries: string[];
  states: string[];
  cities: string[];
  autoEnabled: boolean;
}

export function useOutreachBacklog() {
  return useQuery({
    queryKey: keys.outreachBacklog,
    queryFn: () => customFetch<OutreachBacklog>('/api/acquisition/outreach/backlog'),
    refetchInterval: 60_000,
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

// ---------------------------------------------------------------------------
// Global Discovery Source Registry (70+ Sources Catalog)
// ---------------------------------------------------------------------------

export interface EventDiscoverySource {
  id: string;
  name: string;
  website_url: string;
  source_category: string;
  supported_industries: string[];
  supported_countries: string[];
  supported_event_types: string[];
  access_method: string;
  api_docs_url: string | null;
  api_auth_requirements: string | null;
  permission_status: string;
  integration_status: string;
  last_successful_execution: string | null;
  last_error: string | null;
  events_discovered: number;
  events_extracted: number;
  unique_events_discovered: number;
  health_status: string;
  is_enabled: boolean;
  config: Record<string, any>;
  created_at: string | null;
  updated_at: string | null;
}

export interface SourceRegistryStats {
  total_sources: number;
  sources_evaluated: number;
  sources_approved: number;
  sources_integrated: number;
  sources_tested: number;
  operational_sources: number;
  awaiting_credentials: number;
  permission_review: number;
  temporarily_unavailable: number;
  unsupported: number;
  enabled_sources: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  by_health: Record<string, number>;
  by_access_method: Record<string, number>;
}

export const sourceRegistryKeys = {
  all: ['discovery_sources'] as const,
  list: (params?: Record<string, any>) => ['discovery_sources', 'list', params] as const,
  stats: ['discovery_sources', 'stats'] as const,
  detail: (id: string) => ['discovery_sources', 'detail', id] as const,
};

export function useDiscoverySources(params?: {
  category?: string;
  status?: string;
  access_method?: string;
  search?: string;
  enabled_only?: boolean;
}) {
  const qStr = new URLSearchParams();
  if (params?.category && params.category !== '__all__') qStr.set('category', params.category);
  if (params?.status && params.status !== '__all__') qStr.set('status', params.status);
  if (params?.access_method && params.access_method !== '__all__') qStr.set('access_method', params.access_method);
  if (params?.search) qStr.set('search', params.search);
  if (params?.enabled_only) qStr.set('enabled_only', 'true');
  const qs = qStr.toString();

  return useQuery({
    queryKey: sourceRegistryKeys.list(params),
    queryFn: () =>
      customFetch<{ total: number; sources: EventDiscoverySource[] }>(
        `/api/discovery/sources${qs ? `?${qs}` : ''}`
      ),
  });
}

export function useDiscoverySourceStats() {
  return useQuery({
    queryKey: sourceRegistryKeys.stats,
    queryFn: () => customFetch<SourceRegistryStats>('/api/discovery/sources/stats'),
  });
}

export function useUpdateDiscoverySource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceId,
      updates,
    }: {
      sourceId: string;
      updates: Partial<EventDiscoverySource>;
    }) =>
      customFetch<{ success: boolean; source: Partial<EventDiscoverySource> }>(
        `/api/discovery/sources/${sourceId}`,
        {
          method: 'PATCH',
          body: JSON.stringify(updates),
        }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: sourceRegistryKeys.all });
    },
  });
}

export function useProbeSourceHealth() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sourceId: string) =>
      customFetch<{
        status: string;
        latency_ms: number;
        error: string | null;
        details?: Record<string, any>;
      }>(`/api/discovery/sources/${sourceId}/health`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: sourceRegistryKeys.all });
    },
  });
}

export function useTestSourceExtraction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceId,
      sampleQueryOrUrl,
    }: {
      sourceId: string;
      sampleQueryOrUrl?: string;
    }) =>
      customFetch<{
        success: boolean;
        events_found: number;
        sample_events: any[];
        duration_ms: number;
        error: string | null;
      }>(`/api/discovery/sources/${sourceId}/test`, {
        method: 'POST',
        body: JSON.stringify({ sample_query_or_url: sampleQueryOrUrl }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: sourceRegistryKeys.all });
    },
  });
}

export function useSyncDiscoverySources() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      customFetch<{ success: boolean; result: any }>('/api/discovery/sources/sync', {
        method: 'POST',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: sourceRegistryKeys.all });
    },
  });
}


// --- Run wizard / run reports -------------------------------------------------------

/** One discovery run with its live or final summary (GET /api/discovery/runs/:id). */
export function useDiscoveryRun(runId: number | null, live = false) {
  return useQuery({
    queryKey: ['ops', 'discovery-run', runId],
    queryFn: () => customFetch<AgentRun>(`/api/discovery/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: live ? 3000 : false,
  });
}

export interface RecommendedNotice {
  level: 'info' | 'warning';
  message: string;
  action: string;
}

/** Settings the system picks itself from real availability (GET /api/discovery/recommended-config). */
export interface RecommendedConfig {
  sources: string[];
  searchProviders: string[] | null; // null = every usable provider, free first (automatic)
  usableProviders: Array<{ id: string; name: string; tier: string }>;
  channels: {
    web: { available: boolean; providers: string[] };
    directories: { available: boolean; sources: number };
    aggregators: { available: boolean; sources: number };
  };
  targetValidEvents: number;
  dateFrom: string;
  dateTo: string;
  upcomingWindowDays: number;
  requireOrganizerEmail: boolean;
  rejectPastEvents: boolean;
  keepRejectedEvents: boolean;
  maxRunMinutes: number;
  paidSearchBudget: number | null;
  notices: RecommendedNotice[];
  blocker: string | null;
  listingUrls: string[];
  ticketmaster: { available: boolean };
}

export function useRecommendedConfig() {
  return useQuery({
    queryKey: ['ops', 'discovery-recommended-config'],
    queryFn: () => customFetch<RecommendedConfig>('/api/discovery/recommended-config'),
    staleTime: 30_000,
  });
}

// --- Navigation & configuration (agent B) ---

/** How a discovery run was started, from its stored config snapshot (`is_manual`); null when the run predates that flag. */
export type DiscoveryRunTrigger = 'manual' | 'automatic';

export function discoveryRunTrigger(run: Pick<AgentRun, 'configSnapshot'>): DiscoveryRunTrigger | null {
  const flag = run.configSnapshot?.is_manual;
  if (flag === true) return 'manual';
  if (flag === false) return 'automatic';
  return null;
}

/** A run's stored counter, or null when the summary doesn't carry it (render "—", never 0). */
export function runCount(run: Pick<AgentRun, 'summary'>, key: string): number | null {
  const v = run.summary?.[key];
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** eventId -> ids of the loaded runs whose summary.event_ids lists it (oldest first). Only covers the runs passed in. */
export function runsByEventId(runs: AgentRun[] | undefined): Map<number, number[]> {
  const index = new Map<number, number[]>();
  for (const run of [...(runs ?? [])].sort((a, b) => a.id - b.id)) {
    const ids = run.summary?.event_ids;
    if (!Array.isArray(ids)) continue;
    for (const id of ids) {
      if (typeof id !== 'number') continue;
      const list = index.get(id);
      if (list) { if (!list.includes(run.id)) list.push(run.id); } else index.set(id, [run.id]);
    }
  }
  return index;
}

/** Query keys the run-scoped event lists use (useDiscoveryRunEvents / useDiscoveryRun), for invalidation after a review. */
export const runScopedKeys = {
  runEvents: ['discoveryRunEvents'] as const,
  run: ['ops', 'discovery-run'] as const,
  catalog: ['discoveryCatalog'] as const,
};

// --- Run wizard (agent A) ---

/** The HTTP status of a failed API call, when the error carries one (ApiError does). */
export function apiErrorStatus(error: unknown): number | null {
  const status = (error as { status?: unknown } | null)?.status;
  return typeof status === 'number' ? status : null;
}

/** One run for its report page: shares useDiscoveryRun's cache entry, but a missing run (404) is reported at once instead of retried. */
export function useDiscoveryRunReport(runId: number | null) {
  return useQuery({
    queryKey: ['ops', 'discovery-run', runId],
    queryFn: () => customFetch<AgentRun>(`/api/discovery/runs/${runId}`),
    enabled: Boolean(runId),
    retry: (failures, error) => apiErrorStatus(error) !== 404 && failures < 2,
  });
}
