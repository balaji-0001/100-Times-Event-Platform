// Activity timeline derived from real record timestamps. The agents do not write
// per-step audit rows, so every entry here corresponds to a stored timestamp on an
// event, outreach message, or agent run — nothing is synthesized.

import type { AgentRun, DiscoveredEvent, DiscoveredOrganizer, OutreachMessage } from './api';

export type Agent = 'discovery' | 'outreach';

export interface ActivityEntry {
  id: string;
  at: string;
  agent: Agent;
  title: string;
  detail?: string;
  href?: string;
  tone?: 'good' | 'warn' | 'danger' | 'neutral';
}

export function buildActivity(input: {
  events?: DiscoveredEvent[];
  organizers?: DiscoveredOrganizer[];
  messages?: OutreachMessage[];
  runs?: AgentRun[];
  organizerId?: number;
}): ActivityEntry[] {
  const out: ActivityEntry[] = [];
  const orgName = (id?: number | null) => input.organizers?.find((o) => o.id === id)?.name;

  for (const e of input.events ?? []) {
    if (input.organizerId !== undefined && e.organizerId !== input.organizerId) continue;
    if (e.discoveredAt) {
      const org = orgName(e.organizerId);
      out.push({
        id: `event-${e.id}`,
        at: e.discoveredAt,
        agent: 'discovery',
        title: `Found ${e.name ?? `event #${e.id}`}`,
        detail: [org ? `Organizer: ${org}` : e.organizerStatus === 'NOT_FOUND' ? 'No organizer email found' : 'Organizer pending', e.city, `Saved as ${e.verificationStatus.replace('_', ' ').toLowerCase()}`].filter(Boolean).join(' → '),
        href: `/admin/discovery/events?event=${e.id}`,
        tone: e.verificationStatus === 'VERIFIED' ? 'good' : e.verificationStatus === 'REJECTED' ? 'danger' : 'neutral',
      });
    }
  }

  for (const m of input.messages ?? []) {
    if (input.organizerId !== undefined && m.organizer?.id !== input.organizerId) continue;
    const who = m.organizer?.name ?? m.recipient ?? `outreach #${m.id}`;
    const href = `/admin/outreach/all?message=${m.id}`;
    out.push({ id: `msg-${m.id}-drafted`, at: m.createdAt, agent: 'outreach', title: `Drafted email to ${who}`, detail: [m.event?.name ? `Event: ${m.event.name}` : null, m.recipient ? `To: ${m.recipient}` : null].filter(Boolean).join(' → '), href, tone: 'neutral' });
    if (m.sentAt) out.push({ id: `msg-${m.id}-sent`, at: m.sentAt, agent: 'outreach', title: `Sent email to ${who}`, detail: [m.recipient ? `To: ${m.recipient}` : null, `Status: ${m.status.replace(/_/g, ' ').toLowerCase()}`].filter(Boolean).join(' → '), href, tone: m.status === 'BOUNCED' ? 'danger' : 'good' });
    if (m.followUpSentAt) out.push({ id: `msg-${m.id}-followup`, at: m.followUpSentAt, agent: 'outreach', title: `Follow-up sent to ${who}`, href, tone: 'good' });
    if (m.responseAt) out.push({ id: `msg-${m.id}-reply`, at: m.responseAt, agent: 'outreach', title: `Reply received from ${who}`, href, tone: 'good' });
    if (m.status === 'BOUNCED' && m.failureReason) out.push({ id: `msg-${m.id}-bounce`, at: m.lastContactedAt ?? m.createdAt, agent: 'outreach', title: `Email to ${who} bounced`, detail: m.failureReason, href, tone: 'danger' });
  }

  if (input.organizerId === undefined) {
    for (const r of input.runs ?? []) {
      const label = r.agentType === 'discovery' ? 'Discovery agent' : 'Outreach agent';
      out.push({ id: `run-${r.id}-start`, at: r.startedAt, agent: r.agentType, title: `${label} run #${r.id} started`, href: '/admin/activity', tone: 'neutral' });
      if (r.completedAt) {
        const s = r.summary ?? {};
        const detail = r.agentType === 'discovery'
          ? `${s.events_discovered ?? 0} discovered, ${s.new_events ?? 0} new, ${s.duplicate_events ?? 0} duplicates, ${s.organizers_found ?? 0} organizers`
          : `${s.candidates_considered ?? 0} considered, ${s.drafted ?? 0} drafted`;
        out.push({ id: `run-${r.id}-end`, at: r.completedAt, agent: r.agentType, title: `${label} run #${r.id} ${r.status}`, detail: r.status === 'failed' ? (r.error ?? 'Failed') : detail, href: '/admin/activity', tone: r.status === 'failed' ? 'danger' : 'good' });
      }
    }
  }

  return out.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}
