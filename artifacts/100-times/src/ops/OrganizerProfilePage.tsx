import { useState } from 'react';
import { Link, useParams } from 'wouter';
import { ArrowLeft } from 'lucide-react';
import { type DiscoveredEvent, type OutreachMessage, contactStatus, contactSummary, eventsForOrganizer, messagesForEvent, messagesForOrganizer, useDiscoveredEvents, useDiscoveredOrganizers, useOutreachMessages } from './api';
import { buildActivity } from './activity';
import { AdminTable, Badge, Btn, ConfidenceBar, DL, ErrorState, ExtLink, LoadingState, NA, Notice, PageHeader, Panel, Section, StatCard, StatusBadge, cell, cellMuted, fmtDate, fmtDateTime, fmtTime, val, verificationTone } from './ui';
import { EventDrawer } from './EventDrawer';
import { OutreachDrawer } from './OutreachDrawer';

export function OrganizerProfilePage() {
  const { id } = useParams<{ id: string }>();
  const organizerId = Number(id);
  const organizers = useDiscoveredOrganizers();
  const events = useDiscoveredEvents();
  const messages = useOutreachMessages();
  const [openEvent, setOpenEvent] = useState<DiscoveredEvent | null>(null);
  const [openMessage, setOpenMessage] = useState<OutreachMessage | null>(null);

  if (organizers.isLoading || events.isLoading || messages.isLoading) return <LoadingState label="Loading organizer profile" />;
  if (organizers.isError) return <ErrorState error={organizers.error} retry={() => organizers.refetch()} />;
  const o = organizers.data?.find((x) => x.id === organizerId);
  if (!o) return <ErrorState title="Organizer not found." retry={() => organizers.refetch()} />;

  const orgEvents = eventsForOrganizer(events.data, o.id).sort((a, b) => (b.discoveredAt ?? '').localeCompare(a.discoveredAt ?? ''));
  const orgMessages = messagesForOrganizer(messages.data, o.id).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const summary = contactSummary(orgMessages);
  const status = o.blocked ? 'Do not contact' : contactStatus(orgMessages);
  const activity = buildActivity({ events: events.data, organizers: organizers.data, messages: messages.data, organizerId: o.id });
  // Keep the live message object in sync with the drawer after mutations.
  const liveMessage = openMessage ? messages.data?.find((m) => m.id === openMessage.id) ?? null : null;

  return (
    <div>
      <Link href="/admin/discovery/organizers" className="inline-flex items-center gap-1 font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground hover:text-accent"><ArrowLeft size={11} /> All organizers</Link>
      <div className="mt-3">
        <PageHeader kicker={`Organizer profile · #${o.id}`} title={o.name} subtitle={[o.organizerType, [o.city, o.state].filter(Boolean).join(', ')].filter(Boolean).join(' · ') || undefined}
          actions={<Badge tone={status === 'Do not contact' ? 'danger' : status === 'Not contacted' ? 'neutral' : status === 'Pending approval' ? 'warn' : 'good'}>{status}</Badge>} />
      </div>
      {o.blocked && <div className="mt-4"><Notice tone="danger">This organizer is restricted from all future outreach.</Notice></div>}

      <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_320px]">
        <Panel className="p-6">
          <Section title="Organizer">
            <DL rows={[
              ['Name', o.name],
              ['Organizer type', val(o.organizerType)],
              ['Website', <ExtLink href={o.website} />],
              ['Email', o.email ? <a href={`mailto:${o.email}`} className="text-accent hover:underline">{o.email}</a> : NA],
              ['Phone', val(o.phone)],
              ['Location', [o.city, o.state].filter(Boolean).join(', ') || NA],
              ['LinkedIn', <ExtLink href={o.linkedin} />],
              ['Source URL', <ExtLink href={o.sourceUrl} />],
              ['Confidence', <ConfidenceBar value={o.confidenceScore} />],
              ['Verified', fmtDateTime(o.verifiedAt)],
              ['Last updated', fmtDateTime(o.lastUpdatedAt)],
            ]} />
          </Section>
          <Section title={`Contact channels found (${o.contacts.length})`}>
            {o.contacts.length === 0 ? <p className="text-sm text-muted-foreground">No public contact details were found.</p> : (
              <AdminTable columns={['Type', 'Value', 'Found on', 'Confidence', '']} minWidth={600}>
                {o.contacts.map((c) => (
                  <tr key={c.id}>
                    <td className={cellMuted}><span className="uppercase">{c.contactType}</span></td>
                    <td className={cell}><span className="break-all">{c.value}</span></td>
                    <td className={cell}><ExtLink href={c.sourceUrl}>{safeHost(c.sourceUrl)}</ExtLink></td>
                    <td className={cell}><ConfidenceBar value={c.confidenceScore} /></td>
                    <td className={cell}>{c.isPrimary && <Badge tone="accent">Primary</Badge>}</td>
                  </tr>
                ))}
              </AdminTable>
            )}
          </Section>
        </Panel>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
          <StatCard label="Total events" value={orgEvents.length} />
          <StatCard label="Contacted" value={summary.sent > 0 ? 'Yes' : 'No'} sub={summary.sent > 0 ? `${summary.sent} email${summary.sent === 1 ? '' : 's'} sent` : orgMessages.length ? `${orgMessages.length} awaiting approval` : undefined} tone={summary.sent > 0 ? 'good' : 'accent'} />
          <StatCard label="Delivered" value={summary.delivered} tone="good" />
          <StatCard label="Replies" value={summary.replies} />
          <StatCard label="Last contact" value={summary.lastContact ? fmtDate(summary.lastContact) : '—'} />
        </div>
      </div>

      <Panel className="mt-6 p-6">
        <Section title={`Events by this organizer (${orgEvents.length})`}>
          {orgEvents.length === 0 ? <p className="text-sm text-muted-foreground">No events are linked to this organizer.</p> : (
            <AdminTable columns={['Event', 'Category', 'Date', 'City', 'Status', 'Discovered', '']} minWidth={800}>
              {orgEvents.map((e) => (
                <tr key={e.id} className="cursor-pointer hover:bg-muted/20" onClick={() => setOpenEvent(e)}>
                  <td className={cell}><span className="block max-w-[320px] truncate font-semibold">{e.name ?? NA}</span></td>
                  <td className={cellMuted}>{e.category ?? NA}</td>
                  <td className={cellMuted}>{e.date ?? NA}</td>
                  <td className={cellMuted}>{e.city ?? NA}</td>
                  <td className={cell}><Badge tone={verificationTone(e.verificationStatus)}>{e.verificationStatus.replace('_', ' ')}</Badge></td>
                  <td className={cellMuted}>{fmtDate(e.discoveredAt)}</td>
                  <td className={cell}><Btn size="sm" onClick={(ev) => { ev.stopPropagation(); setOpenEvent(e); }}>View</Btn></td>
                </tr>
              ))}
            </AdminTable>
          )}
        </Section>
      </Panel>

      <Panel className="mt-6 p-6">
        <Section title={`Outreach history (${orgMessages.length})`}>
          {orgMessages.length === 0 ? (
            <div className="rounded-xl border border-dashed border-foreground/15 p-6 text-center text-sm"><span className="font-semibold">Not contacted.</span><span className="ml-1 text-muted-foreground">Agent 2 has not generated any outreach for this organizer.</span></div>
          ) : (
            <ol className="space-y-3">
              {orgMessages.map((m, i) => (
                <li key={m.id} className="rounded-xl border border-foreground/10 bg-background p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-xs"><span className="font-mono-face text-[10px] uppercase text-muted-foreground">{fmtDate(m.sentAt ?? m.createdAt)} · Email #{i + 1}{m.followUpSentAt ? ' · follow-up sent' : ''}</span><p className="mt-1 font-semibold">{m.subject ?? 'Email not generated'}</p><p className="text-muted-foreground">Event: {m.event.name ?? NA} · To: {m.recipient ?? NA}</p></div>
                    <div className="flex items-center gap-2"><StatusBadge status={m.status} /><Btn size="sm" onClick={() => setOpenMessage(m)}>View email</Btn></div>
                  </div>
                  <div className="mt-3 grid gap-1 font-mono-face text-[10px] text-muted-foreground sm:grid-cols-4">
                    <span>Generated {fmtDateTime(m.createdAt)}</span><span>Sent {fmtDateTime(m.sentAt)}</span><span>Follow-up {fmtDateTime(m.followUpSentAt)}</span><span>Replied {fmtDateTime(m.responseAt)}</span>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Section>
      </Panel>

      <Panel className="mt-6 p-6">
        <Section title="Agent activity">
          {activity.length === 0 ? <p className="text-sm text-muted-foreground">No activity recorded for this organizer.</p> : (
            <ol className="divide-y divide-foreground/10 text-sm">
              {activity.map((a) => (
                <li key={a.id} className="flex items-start gap-4 py-2.5"><span className="w-[7.5rem] shrink-0 font-mono-face text-[10px] leading-5 text-muted-foreground">{fmtDate(a.at)}<br />{fmtTime(a.at)}</span><Badge tone={a.agent === 'discovery' ? 'info' : 'accent'}>{a.agent === 'discovery' ? 'Agent 1' : 'Agent 2'}</Badge><div className="min-w-0"><p className="font-semibold">{a.title}</p>{a.detail && <p className="text-xs text-muted-foreground">{a.detail}</p>}</div></li>
              ))}
            </ol>
          )}
        </Section>
      </Panel>

      <EventDrawer event={openEvent} organizer={o} messages={openEvent ? messagesForEvent(messages.data, openEvent.id) : []} onClose={() => setOpenEvent(null)} />
      <OutreachDrawer message={liveMessage} onClose={() => setOpenMessage(null)} />
    </div>
  );
}

function safeHost(url?: string | null) { try { return url ? new URL(url).host.replace(/^www\./, '') : undefined; } catch { return url ?? undefined; } }
