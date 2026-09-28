import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customFetch } from '@workspace/api-client-react';
import { Bot, Play, Sparkles, CheckCircle2, ExternalLink } from 'lucide-react';
import { Badge, Kicker, LoadingState } from './ui';

interface SourceStatus {
  platform: string;
  enabled: boolean;
  usedToday: number;
  dailyLimit: number;
  rateLimitStatus: string;
}

interface MatchedEventItem {
  id: number;
  eventId: number;
  eventTitle: string;
  eventSlug: string;
  matchScore: number;
  matchReasons: string[];
  recommendationText: string;
  trackingUrl: string;
  status: string;
  converted: boolean;
}

interface IntentRecord {
  id: number;
  sourcePlatform: string;
  sourceUrl: string;
  authorHandle: string;
  rawText: string;
  location: string;
  eventCategory: string;
  eventType: string;
  datePreference: string;
  pricePreference: string;
  formatPreference: string;
  keywords: string[];
  inferredInterests: string[];
  confidence: number;
  status: string;
  createdAt: string;
  matches: MatchedEventItem[];
}

interface AttendeeAgentDashboardData {
  sources: SourceStatus[];
  metrics: {
    discoveredConversations: number;
    detectedIntents: number;
    matchingEvents: number;
    recommendationsSent: number;
    responses: number;
    conversions: number;
    registrationsGenerated: number;
    errors: number;
  };
  intents: IntentRecord[];
  activityLogs: Array<{
    id: number;
    status: string;
    startedAt: string;
    completedAt: string;
    summary: Record<string, unknown>;
    error?: string | null;
  }>;
}

export function AttendeeAgentPage() {
  const qc = useQueryClient();
  const [testText, setTestText] = useState('I want AI conferences in Hyderabad next month.');
  const [testPlatform, setTestPlatform] = useState('telegram');
  const [testHandle, setTestHandle] = useState('@arjun_hyd_ai');

  const dashQuery = useQuery({
    queryKey: ['ops', 'attendee-agent-dashboard'],
    queryFn: () => customFetch<AttendeeAgentDashboardData>('/api/attendee-agent/dashboard'),
  });

  const scanMutation = useMutation({
    mutationFn: () => customFetch('/api/attendee-agent/scan', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ops', 'attendee-agent-dashboard'] }),
  });

  const matchMutation = useMutation({
    mutationFn: (payload: { text: string; platform: string; authorHandle: string }) =>
      customFetch('/api/attendee-agent/match', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ops', 'attendee-agent-dashboard'] }),
  });

  const toggleSourceMutation = useMutation({
    mutationFn: ({ source, enabled, dailyLimit }: { source: string; enabled: boolean; dailyLimit?: number }) =>
      customFetch(`/api/attendee-agent/sources/${source}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled, dailyLimit }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ops', 'attendee-agent-dashboard'] }),
  });

  if (dashQuery.isLoading) return <LoadingState label="Loading Attendee Agent telemetry" />;

  const data = dashQuery.data;
  const m = data?.metrics;

  const handleTestSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!testText.trim()) return;
    matchMutation.mutate({ text: testText.trim(), platform: testPlatform, authorHandle: testHandle });
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <Kicker>Attendee Agent · Demand Matching</Kicker>
          <h1 className="mt-2 font-display text-3xl font-extrabold tracking-tight">
            Attendee Intent & Event Matching Engine
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Detects high-intent event seekers across permitted community channels, extracts structured preferences, and matches them with published 100 TIMES events.
          </p>
        </div>
        <button
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
          className="inline-flex items-center gap-2 rounded-full bg-accent px-4 py-2.5 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
          data-testid="button-run-attendee-agent-scan"
        >
          <Play size={14} /> {scanMutation.isPending ? 'Scanning Community Signals…' : 'Run Attendee Discovery Scan'}
        </button>
      </div>

      {/* Metrics Grid */}
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-2xl border border-foreground/10 bg-card p-4">
          <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Discovered Intents</p>
          <p className="mt-2 font-display text-3xl font-bold">{m?.detectedIntents ?? 0}</p>
        </div>
        <div className="rounded-2xl border border-foreground/10 bg-card p-4">
          <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Event Matches & Recs Sent</p>
          <p className="mt-2 font-display text-3xl font-bold">{m?.recommendationsSent ?? 0}</p>
        </div>
        <div className="rounded-2xl border border-foreground/10 bg-card p-4">
          <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Responses</p>
          <p className="mt-2 font-display text-3xl font-bold">{m?.responses ?? 0}</p>
        </div>
        <div className="rounded-2xl border border-foreground/10 bg-card p-4">
          <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Conversions / Registrations</p>
          <p className="mt-2 font-display text-3xl font-bold">{m?.registrationsGenerated ?? 0}</p>
        </div>
      </div>

      {/* Per-Source Enable/Disable & Rate Limit Controls */}
      <div className="rounded-2xl border border-foreground/10 bg-card p-6">
        <h2 className="font-display text-lg font-bold">Permitted Community Sources & Rate Limits</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Enable or pause individual sources and enforce strict daily signal ingestion & anti-spam caps.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {(data?.sources ?? []).map((src) => (
            <div key={src.platform} className="rounded-xl border border-foreground/10 bg-background p-4">
              <div className="flex items-center justify-between">
                <span className="font-display text-base font-bold capitalize">{src.platform}</span>
                <Badge tone={src.enabled ? 'good' : 'neutral'}>{src.enabled ? 'ENABLED' : 'DISABLED'}</Badge>
              </div>
              <p className="mt-2 font-mono-face text-xs text-muted-foreground">
                Used today: {src.usedToday} / {src.dailyLimit} ({src.rateLimitStatus})
              </p>
              <button
                onClick={() => toggleSourceMutation.mutate({ source: src.platform, enabled: !src.enabled })}
                className="mt-3 w-full rounded-lg border border-foreground/15 px-3 py-1.5 text-xs font-semibold hover:border-accent"
                data-testid={`button-toggle-source-${src.platform}`}
              >
                {src.enabled ? 'Disable Source' : 'Enable Source'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Interactive Intent Extraction & Event Matching Tester */}
      <form onSubmit={handleTestSubmit} className="rounded-2xl border border-foreground/10 bg-card p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Bot className="text-accent" size={18} />
          <h2 className="font-display text-lg font-bold">Live Intent Extractor & Event Matcher</h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="sm:col-span-2">
            <label className="block text-xs font-semibold text-muted-foreground">
              Community Post / Seeker Message
              <input
                value={testText}
                onChange={(e) => setTestText(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs outline-none focus:border-accent"
                data-testid="input-attendee-intent-text"
              />
            </label>
          </div>
          <div>
            <label className="block text-xs font-semibold text-muted-foreground">
              Source Channel
              <select
                value={testPlatform}
                onChange={(e) => setTestPlatform(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs"
              >
                <option value="telegram">Telegram</option>
                <option value="discord">Discord</option>
                <option value="reddit">Reddit</option>
                <option value="community">Community Forum</option>
              </select>
            </label>
          </div>
          <div>
            <label className="block text-xs font-semibold text-muted-foreground">
              Author Handle
              <input
                value={testHandle}
                onChange={(e) => setTestHandle(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs outline-none focus:border-accent"
              />
            </label>
          </div>
        </div>
        <button
          type="submit"
          disabled={matchMutation.isPending}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-xs font-bold text-primary-foreground hover:bg-accent"
          data-testid="button-extract-and-match"
        >
          <Sparkles size={14} /> {matchMutation.isPending ? 'Extracting & Matching…' : 'Extract Intent & Match Events'}
        </button>
      </form>

      {/* Detected Intents & Event Matches List */}
      <div className="space-y-4">
        <h2 className="font-display text-xl font-bold">Discovered Conversations & Matched Events</h2>
        {(data?.intents ?? []).length === 0 ? (
          <div className="rounded-2xl border border-foreground/10 bg-card p-8 text-center text-xs text-muted-foreground">
            Click &ldquo;Run Attendee Discovery Scan&rdquo; or test a query above to see structured intents and matched events.
          </div>
        ) : (
          (data?.intents ?? []).map((intent) => (
            <div key={intent.id} className="rounded-2xl border border-foreground/10 bg-card p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Badge tone="good">{intent.sourcePlatform.toUpperCase()}</Badge>
                  <span className="font-mono-face text-xs font-semibold">{intent.authorHandle}</span>
                  <span className="text-xs text-muted-foreground">
                    Confidence: {Math.round(intent.confidence * 100)}%
                  </span>
                </div>
                <span className="font-mono-face text-[11px] text-muted-foreground">
                  {new Date(intent.createdAt).toLocaleString()}
                </span>
              </div>

              <p className="text-sm font-medium">&ldquo;{intent.rawText}&rdquo;</p>

              <div className="flex flex-wrap gap-2 text-xs">
                <span className="rounded-lg bg-muted px-2.5 py-1 font-mono-face">
                  category: <strong>{intent.eventCategory}</strong>
                </span>
                <span className="rounded-lg bg-muted px-2.5 py-1 font-mono-face">
                  location: <strong>{intent.location}</strong>
                </span>
                <span className="rounded-lg bg-muted px-2.5 py-1 font-mono-face">
                  time_range: <strong>{intent.datePreference}</strong>
                </span>
                <span className="rounded-lg bg-muted px-2.5 py-1 font-mono-face">
                  event_type: <strong>{intent.eventType}</strong>
                </span>
              </div>

              {intent.matches.length > 0 && (
                <div className="space-y-2 border-t border-foreground/10 pt-3">
                  <p className="font-mono-face text-[10px] uppercase text-accent">
                    Top Matched Events ({intent.matches.length})
                  </p>
                  {intent.matches.map((match) => (
                    <div key={match.id} className="rounded-xl border border-foreground/10 bg-background p-3 text-xs space-y-1.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-display text-sm font-bold">{match.eventTitle}</span>
                        <div className="flex items-center gap-2">
                          <Badge tone={match.matchScore >= 70 ? 'good' : 'warn'}>
                            Match Score: {match.matchScore}/100
                          </Badge>
                          {match.converted && (
                            <span className="inline-flex items-center gap-1 text-emerald-400 font-bold">
                              <CheckCircle2 size={12} /> Converted to Registration
                            </span>
                          )}
                        </div>
                      </div>
                      <p className="text-muted-foreground">{match.recommendationText}</p>
                      <div className="flex flex-wrap items-center justify-between gap-2 pt-1 font-mono-face text-[10px] text-muted-foreground">
                        <span>Reasons: {match.matchReasons.join(' · ')}</span>
                        <a
                          href={`/events/${match.eventSlug}`}
                          className="inline-flex items-center gap-1 text-accent hover:underline"
                        >
                          Open Event <ExternalLink size={10} />
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
