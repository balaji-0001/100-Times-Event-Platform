import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customFetch } from '@workspace/api-client-react';
import { CheckCircle2, ShieldAlert, ShieldCheck, XCircle, RefreshCw, AlertTriangle, History } from 'lucide-react';
import { Badge, Kicker, LoadingState } from './ui';
import { Link } from 'wouter';

interface TrustAuditEntry {
  id: number;
  actorType: string;
  actorId?: number | null;
  decision: string;
  previousStatus?: string | null;
  newStatus: string;
  notes?: string | null;
  createdAt: string;
}

interface DuplicateCandidateItem {
  candidate_event_id?: number | null;
  candidate_discovered_event_id?: number | null;
  title: string;
  similarity_score: number;
  reason: string;
}

interface TrustReviewItem {
  id: number;
  eventId: number;
  eventTitle: string;
  eventSlug: string;
  eventLifecycleState: string;
  organizerId?: number | null;
  organizerName: string;
  organizerEmail: string;
  status: 'APPROVED' | 'NEEDS_REVIEW' | 'REJECTED' | 'DUPLICATE';
  score: number;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  reasons: string[];
  warnings: string[];
  duplicateCandidates: DuplicateCandidateItem[];
  missingFields: string[];
  recommendedAction: string;
  checksSummary: Record<string, boolean>;
  createdAt: string;
  auditHistory: TrustAuditEntry[];
}

export function TrustReviewPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string>('ALL');
  const [notesByReview, setNotesByReview] = useState<Record<number, string>>({});

  const reviewsQuery = useQuery({
    queryKey: ['ops', 'trust-reviews', filter],
    queryFn: () =>
      customFetch<TrustReviewItem[]>(
        `/api/trust/reviews${filter !== 'ALL' ? `?status_filter=${encodeURIComponent(filter)}` : ''}`
      ),
  });

  const decisionMutation = useMutation({
    mutationFn: ({
      reviewId,
      decision,
      notes,
    }: {
      reviewId: number;
      decision: 'APPROVE' | 'REJECT' | 'REQUEST_CHANGES';
      notes?: string;
    }) =>
      customFetch(`/api/trust/reviews/${reviewId}/decision`, {
        method: 'POST',
        body: JSON.stringify({ decision, notes }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ops', 'trust-reviews'] });
      qc.invalidateQueries({ queryKey: ['organizer-events-full'] });
    },
  });

  if (reviewsQuery.isLoading) return <LoadingState label="Loading Trust Agent (Agent 3) reviews" />;

  const reviews = reviewsQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <Kicker>Trust Agent · Agent 3</Kicker>
          <h1 className="mt-2 font-display text-3xl font-extrabold tracking-tight">
            Trust & Safety Review Queue
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Automated completeness, organizer identity, duplicate detection, and risk scoring with human moderation gates.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(['ALL', 'NEEDS_REVIEW', 'APPROVED', 'REJECTED', 'DUPLICATE'] as const).map((st) => (
            <button
              key={st}
              onClick={() => setFilter(st)}
              className={`rounded-full px-3.5 py-1.5 font-mono-face text-xs font-semibold transition ${
                filter === st
                  ? 'bg-accent text-accent-foreground'
                  : 'border border-foreground/15 bg-card text-muted-foreground hover:border-accent'
              }`}
            >
              {st.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {reviews.length === 0 ? (
        <div className="rounded-2xl border border-foreground/10 bg-card p-10 text-center">
          <ShieldCheck className="mx-auto text-accent" size={32} />
          <p className="mt-3 font-display text-xl font-bold">No Trust Agent reviews in this filter.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Events submitted by organizers are automatically evaluated by Trust Agent (Agent 3) and logged here.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {reviews.map((item) => (
            <div
              key={item.id}
              className="rounded-2xl border border-foreground/10 bg-card p-6 space-y-4"
              data-testid={`trust-review-card-${item.id}`}
            >
              <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      tone={
                        item.status === 'APPROVED'
                          ? 'good'
                          : item.status === 'NEEDS_REVIEW'
                          ? 'warn'
                          : 'bad'
                      }
                    >
                      {item.status}
                    </Badge>
                    <Badge tone={item.confidence === 'HIGH' ? 'good' : item.confidence === 'MEDIUM' ? 'warn' : 'bad'}>
                      CONFIDENCE: {item.confidence}
                    </Badge>
                    <span className="rounded-full bg-muted px-2.5 py-0.5 font-mono-face text-xs font-bold">
                      Trust Score: {item.score}/100
                    </span>
                    <span className="font-mono-face text-xs text-muted-foreground">
                      Action: {item.recommendedAction}
                    </span>
                  </div>
                  <Link
                    href={`/events/${item.eventSlug || item.eventId}`}
                    className="mt-2 block font-display text-xl font-bold hover:text-accent"
                  >
                    {item.eventTitle}
                  </Link>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Organizer: <span className="font-semibold text-foreground">{item.organizerName}</span>{' '}
                    ({item.organizerEmail || 'verified profile'}) · Lifecycle: {item.eventLifecycleState}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() =>
                      decisionMutation.mutate({
                        reviewId: item.id,
                        decision: 'APPROVE',
                        notes: notesByReview[item.id] || 'Approved by Admin in Trust Review Console',
                      })
                    }
                    disabled={decisionMutation.isPending}
                    className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-emerald-500"
                    data-testid={`button-trust-approve-${item.id}`}
                  >
                    <CheckCircle2 size={14} /> Approve & Publish
                  </button>
                  <button
                    onClick={() =>
                      decisionMutation.mutate({
                        reviewId: item.id,
                        decision: 'REQUEST_CHANGES',
                        notes: notesByReview[item.id] || 'Please address missing fields and resubmit.',
                      })
                    }
                    disabled={decisionMutation.isPending}
                    className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-3.5 py-1.5 text-xs font-bold text-amber-400 hover:bg-amber-500/20"
                    data-testid={`button-trust-request-changes-${item.id}`}
                  >
                    <RefreshCw size={14} /> Request Changes
                  </button>
                  <button
                    onClick={() =>
                      decisionMutation.mutate({
                        reviewId: item.id,
                        decision: 'REJECT',
                        notes: notesByReview[item.id] || 'Rejected by moderation team.',
                      })
                    }
                    disabled={decisionMutation.isPending}
                    className="inline-flex items-center gap-1.5 rounded-full border border-rose-500/40 bg-rose-500/10 px-3.5 py-1.5 text-xs font-bold text-rose-400 hover:bg-rose-500/20"
                    data-testid={`button-trust-reject-${item.id}`}
                  >
                    <XCircle size={14} /> Reject
                  </button>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-xs">
                <div className="rounded-xl border border-foreground/10 bg-background/50 p-3">
                  <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Completeness</p>
                  <p className="mt-1 font-semibold">
                    {item.checksSummary?.information_complete ? '✓ Complete' : `Missing: ${item.missingFields.join(', ') || 'fields'}`}
                  </p>
                </div>
                <div className="rounded-xl border border-foreground/10 bg-background/50 p-3">
                  <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Organizer Verified</p>
                  <p className="mt-1 font-semibold">
                    {item.checksSummary?.organizer_verified ? '✓ Verified Identity' : '⚠ Unverified Organizer'}
                  </p>
                </div>
                <div className="rounded-xl border border-foreground/10 bg-background/50 p-3">
                  <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Duplicates</p>
                  <p className="mt-1 font-semibold">
                    {item.duplicateCandidates.length === 0
                      ? '✓ No duplicates'
                      : `${item.duplicateCandidates.length} candidate(s) found`}
                  </p>
                </div>
                <div className="rounded-xl border border-foreground/10 bg-background/50 p-3">
                  <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Safety & Spam Check</p>
                  <p className="mt-1 font-semibold">
                    {item.checksSummary?.no_major_risk_detected ? '✓ No major risk detected' : '⚠ Risk flags raised'}
                  </p>
                </div>
              </div>

              {(item.reasons.length > 0 || item.warnings.length > 0 || item.duplicateCandidates.length > 0) && (
                <div className="grid gap-3 md:grid-cols-2 text-xs">
                  {item.reasons.length > 0 && (
                    <div className="rounded-xl bg-muted/40 p-3">
                      <p className="font-mono-face text-[10px] uppercase text-accent">Trust Reasons</p>
                      <ul className="mt-1.5 space-y-1 text-muted-foreground">
                        {item.reasons.map((r, idx) => (
                          <li key={idx}>• {r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {item.warnings.length > 0 && (
                    <div className="rounded-xl bg-amber-500/10 p-3">
                      <p className="font-mono-face text-[10px] uppercase text-amber-400 flex items-center gap-1">
                        <AlertTriangle size={12} /> Warnings & Missing Info
                      </p>
                      <ul className="mt-1.5 space-y-1 text-amber-200/90">
                        {item.warnings.map((w, idx) => (
                          <li key={idx}>• {w}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {item.duplicateCandidates.length > 0 && (
                <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-3 text-xs">
                  <p className="font-mono-face text-[10px] uppercase text-rose-400 flex items-center gap-1">
                    <ShieldAlert size={12} /> Duplicate Candidates Detected
                  </p>
                  <div className="mt-2 space-y-1">
                    {item.duplicateCandidates.map((dup, i) => (
                      <p key={i}>
                        <span className="font-semibold">{dup.title}</span> — {dup.similarity_score}% match ({dup.reason})
                      </p>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:items-center">
                <input
                  value={notesByReview[item.id] ?? ''}
                  onChange={(e) => setNotesByReview((prev) => ({ ...prev, [item.id]: e.target.value }))}
                  placeholder="Optional moderation note for organizer & audit trail…"
                  className="flex-1 rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs outline-none focus:border-accent"
                />
              </div>

              {item.auditHistory.length > 0 && (
                <div className="border-t border-foreground/10 pt-3">
                  <p className="font-mono-face text-[10px] uppercase text-muted-foreground flex items-center gap-1">
                    <History size={11} /> Audit History ({item.auditHistory.length})
                  </p>
                  <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                    {item.auditHistory.map((h) => (
                      <div key={h.id} className="flex flex-wrap items-center justify-between gap-2">
                        <span>
                          <strong className="text-foreground">{h.actorType}</strong> → {h.decision} ({h.previousStatus} →{' '}
                          {h.newStatus}) {h.notes ? `· "${h.notes}"` : ''}
                        </span>
                        <span className="font-mono-face text-[10px]">{new Date(h.createdAt).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
