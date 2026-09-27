import { useState } from 'react';
import { Link } from 'wouter';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { type DiscoveredEvent, type DiscoveredOrganizer, type OutreachMessage, contactStatus } from './api';
import { Badge, Btn, DL, Drawer, ExtLink, Kicker, NA, Notice, Section, StatusBadge, ConfidenceBar, cx, fmtDate, fmtDateTime, fmtTime, val, verificationTone } from './ui';

const SOURCE_TYPE_LABEL: Record<string, string> = {
  event_listing: 'Event listing', conference_site: 'Conference site', college_page: 'College / university page',
  government: 'Government page', trade_association: 'Trade association', corporate: 'Corporate page',
  organizer_website: 'Organizer website', aggregator: 'Event aggregator', other: 'Other',
};
export const sourceTypeLabel = (t: string) => SOURCE_TYPE_LABEL[t] ?? t.replace(/_/g, ' ');

// What each source type contributes, by construction of the discovery pipeline: the primary
// page yields the event record; organizer_website hops yield organizer contact details.
function informationFound(type: string, isPrimary: boolean) {
  if (type === 'organizer_website') return 'Organizer information (contact page)';
  return isPrimary ? 'Event details, organizer identification' : 'Event details';
}

export function EventDrawer({ event, organizer, messages, onClose }: { event: DiscoveredEvent | null; organizer?: DiscoveredOrganizer; messages: OutreachMessage[]; onClose: () => void }) {
  const [showRaw, setShowRaw] = useState(false);
  if (!event) return null;
  const location = [event.venue, event.city, event.state].filter(Boolean).join(', ');
  const primaryUrl = event.sourceUrl ?? event.url;

  return (
    <Drawer open onClose={onClose} kicker={`Discovered event #${event.id}`} title={event.name ?? NA}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={verificationTone(event.verificationStatus)}>{event.verificationStatus.replace('_', ' ')}</Badge>
        <Badge tone={event.organizerStatus === 'FOUND' ? 'good' : event.organizerStatus === 'NOT_FOUND' ? 'danger' : 'neutral'}>Organizer {event.organizerStatus.replace('_', ' ')}</Badge>
        {event.discoveryStatus !== 'NEW' && <Badge tone="info">{event.discoveryStatus}</Badge>}
        <span className="ml-auto text-[11px] text-muted-foreground">Confidence <ConfidenceBar value={event.confidenceScore} /></span>
      </div>

      {event.verificationNotes.length > 0 && (
        <div className="mt-4"><Notice tone="warn">{event.verificationNotes.map((n, i) => <p key={i}>{n}</p>)}</Notice></div>
      )}

      <Section title="Event details">
        <DL rows={[
          ['Event name', val(event.name)],
          ['Description', event.eventDescription ? <span className="whitespace-pre-wrap leading-relaxed">{event.eventDescription}</span> : NA],
          ['Category', val(event.category)],
          ['Subcategory', val(event.subcategory)],
          ['Event date', event.date ? <span>{event.date}{event.eventDate && <span className="ml-2 text-muted-foreground">(parsed {fmtDate(event.eventDate)})</span>}</span> : NA],
          ['Start time', val(event.startTime)],
          ['End time', val(event.endTime)],
          ['Venue', val(event.venue)],
          ['City', val(event.city)],
          ['State', val(event.state)],
          ['Country', val(event.country)],
          ['Event type', val(event.eventFormat)],
          ['Event URL', <ExtLink href={event.url} />],
          ['Registration / ticket URL', <ExtLink href={event.ticketUrl} />],
        ]} />
      </Section>

      <Section title="Organizer" aside={organizer && <Link href={`/admin/discovery/organizers/${organizer.id}`} className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">Open profile →</Link>}>
        {organizer ? (
          <DL rows={[
            ['Organizer name', <Link href={`/admin/discovery/organizers/${organizer.id}`} className="font-semibold text-accent hover:underline">{organizer.name}</Link>],
            ['Organizer type', val(organizer.organizerType)],
            ['Website', <ExtLink href={organizer.website} />],
            ['Email', organizer.email ? <a href={`mailto:${organizer.email}`} className="text-accent hover:underline">{organizer.email}</a> : NA],
            ['Phone', val(organizer.phone)],
            ['City', val(organizer.city)],
            ['State', val(organizer.state)],
            ['LinkedIn', <ExtLink href={organizer.linkedin} />],
            ['Other contacts', organizer.contacts.filter((c) => !['email', 'phone', 'linkedin', 'website'].includes(c.contactType) || (c.contactType === 'email' && c.value !== organizer.email)).length
              ? <ul className="space-y-1">{organizer.contacts.filter((c) => !['email', 'phone', 'linkedin', 'website'].includes(c.contactType) || (c.contactType === 'email' && c.value !== organizer.email)).map((c) => <li key={c.id}><span className="font-mono-face text-[10px] uppercase text-muted-foreground">{c.contactType}</span> {c.value}</li>)}</ul>
              : NA],
            ['Contact status', <span>{contactStatus(messages)}</span>],
          ]} />
        ) : (
          <Notice tone="info">
            {event.organizerStatus === 'NOT_FOUND'
              ? 'The discovery agent could not find a publicly listed organizer email on this event’s pages, so no organizer record was created and it is not eligible for outreach.'
              : 'Organizer identification has not completed for this event yet.'}
          </Notice>
        )}
      </Section>

      <Section title={`Sources (${event.sources.length})`}>
        {event.sources.length === 0 ? <p className="text-sm text-muted-foreground">{NA}</p> : (
          <ol className="space-y-3">
            {event.sources.map((s, i) => {
              const isPrimary = s.sourceUrl === primaryUrl;
              return (
                <li key={s.id} className="rounded-xl border border-foreground/10 bg-background p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Kicker className="text-muted-foreground">Source {i + 1}{isPrimary && ' · primary'}</Kicker>
                    <Badge tone="info">{sourceTypeLabel(s.sourceType)}</Badge>
                  </div>
                  <DL rows={[
                    ['Website', val(s.sourceWebsite ?? safeHost(s.sourceUrl))],
                    ['URL', <ExtLink href={s.sourceUrl} />],
                    ['Fetched', fmtDateTime(s.fetchedAt)],
                    ['Information found', informationFound(s.sourceType, isPrimary)],
                  ]} />
                </li>
              );
            })}
          </ol>
        )}
      </Section>

      <Section title="Discovery details">
        <DL rows={[
          ['Discovered by', event.discoveredBy === 'web_discovery_agent' ? 'Organizer Discovery agent (web search)' : 'Social listening pipeline'],
          ['Discovered', fmtDateTime(event.discoveredAt)],
          ['Last updated', fmtDateTime(event.lastUpdatedAt)],
          ['Source website', val(event.sourceWebsite)],
          ['Source URL', <ExtLink href={event.sourceUrl} />],
          ['Organizer source URL', <ExtLink href={organizer?.sourceUrl} />],
          ['Verification status', <Badge tone={verificationTone(event.verificationStatus)}>{event.verificationStatus.replace('_', ' ')}</Badge>],
          ['Confidence score', <ConfidenceBar value={event.confidenceScore} />],
          ['Missing fields', missingFields(event).length ? missingFields(event).join(', ') : 'None'],
        ]} />
      </Section>

      <Section title={`Outreach for this event (${messages.length})`}>
        {messages.length === 0 ? <p className="text-sm text-muted-foreground">No outreach has been generated for this event.</p> : (
          <ul className="divide-y divide-foreground/10 rounded-xl border border-foreground/10 bg-background">
            {messages.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-3 p-3 text-xs">
                <Link href={`/admin/outreach/all?message=${m.id}`} className="min-w-0 hover:underline"><span className="block truncate font-semibold">{m.subject ?? `Outreach #${m.id}`}</span><span className="text-muted-foreground">{m.recipient ?? NA} · {fmtDate(m.sentAt ?? m.createdAt)}</span></Link>
                <StatusBadge status={m.status} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Agent activity">
        <ol className="space-y-2 text-xs">
          <TimelineRow at={event.discoveredAt} label="Event discovered and saved" sub={event.sourceWebsite ? `from ${event.sourceWebsite}` : undefined} />
          {event.sources.map((s) => <TimelineRow key={s.id} at={s.fetchedAt} label={s.sourceType === 'organizer_website' ? 'Organizer website researched' : `${sourceTypeLabel(s.sourceType)} fetched`} sub={safeHost(s.sourceUrl)} />)}
          {organizer?.email && <TimelineRow at={event.discoveredAt} label="Organizer email found" sub={organizer.email} />}
          {event.organizerStatus === 'NOT_FOUND' && <TimelineRow at={event.discoveredAt} label="No valid organizer email found" tone="warn" />}
          {messages.map((m) => <TimelineRow key={`d${m.id}`} at={m.createdAt} label="Outreach email drafted" sub={m.recipient ?? undefined} />)}
          {messages.filter((m) => m.sentAt).map((m) => <TimelineRow key={`s${m.id}`} at={m.sentAt} label="Outreach email sent" sub={m.recipient ?? undefined} />)}
        </ol>
        <p className="mt-3 text-[11px] text-muted-foreground">Timestamps come from the stored records; the agents do not log intermediate steps.</p>
      </Section>

      <Section title="Raw record">
        <Btn size="sm" onClick={() => setShowRaw((v) => !v)}>{showRaw ? <ChevronUp size={12} /> : <ChevronDown size={12} />} {showRaw ? 'Hide' : 'Show'} raw extraction</Btn>
        {showRaw && <pre className="mt-3 max-h-80 overflow-auto rounded-xl border border-foreground/10 bg-background p-4 font-mono-face text-[11px] leading-relaxed">{JSON.stringify(event, null, 2)}</pre>}
        <p className="mt-2 text-[11px] text-muted-foreground">This is the stored record exactly as the API returns it. The agent's page-level extraction payload is not exposed by the current API.</p>
      </Section>
    </Drawer>
  );
}

export function TimelineRow({ at, label, sub, tone }: { at?: string | null; label: string; sub?: string; tone?: 'warn' | 'good' | 'danger' }) {
  if (!at) return null;
  const dot = tone === 'warn' ? 'bg-amber-500' : tone === 'danger' ? 'bg-red-500' : tone === 'good' ? 'bg-emerald-500' : 'bg-accent';
  return (
    <li className="flex items-start gap-3">
      <span className="mt-1 font-mono-face text-[10px] text-muted-foreground">{fmtDate(at)} {fmtTime(at)}</span>
      <span className={cx('mt-1.5 h-2 w-2 shrink-0 rounded-full', dot)} />
      <span><span className="font-semibold">{label}</span>{sub && <span className="ml-1 text-muted-foreground">— {sub}</span>}</span>
    </li>
  );
}

function safeHost(url?: string | null) { try { return url ? new URL(url).host : undefined; } catch { return undefined; } }

function missingFields(e: DiscoveredEvent) {
  const checks: Array<[string, unknown]> = [['description', e.eventDescription], ['category', e.category], ['event date', e.date], ['start time', e.startTime], ['venue', e.venue], ['city', e.city], ['state', e.state], ['event URL', e.url], ['registration URL', e.ticketUrl]];
  return checks.filter(([, v]) => !v).map(([k]) => k);
}
