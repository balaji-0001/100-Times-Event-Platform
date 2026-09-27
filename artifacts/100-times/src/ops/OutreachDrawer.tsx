import { useEffect, useState } from 'react';
import { Link } from 'wouter';
import { Ban, Check, Edit3, MailCheck, MessageSquareReply, Send, ShieldAlert, XCircle } from 'lucide-react';
import { type OutreachMessage, APPROVABLE_STATUSES, PRE_SEND_STATUSES, TERMINAL_STATUSES, useEditOutreachMessage, useOutreachAction } from './api';
import { Badge, Btn, DL, Drawer, ErrorState, ExtLink, Kicker, NA, Notice, Section, StatusBadge, fmtDate, fmtDateTime, inputClass, val } from './ui';
import { TimelineRow } from './EventDrawer';

function providerFor(m: OutreachMessage) {
  if (!m.sentAt) return NA;
  return m.messageId?.startsWith('mock-') ? 'Mock provider (SMTP not configured — no real email was delivered)' : 'SMTP';
}

export function OutreachDrawer({ message: m, onClose }: { message: OutreachMessage | null; onClose: () => void }) {
  const action = useOutreachAction();
  const edit = useEditOutreachMessage();
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [reasonFor, setReasonFor] = useState<'reject' | 'opt_out' | 'restrict_organizer' | null>(null);
  const [reason, setReason] = useState('');

  useEffect(() => { if (m) { setSubject(m.subject ?? ''); setBody(m.message ?? ''); setEditing(false); setReasonFor(null); setReason(''); action.reset(); } }, [m?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!m) return null;
  const isMock = m.messageId?.startsWith('mock-');
  const canEdit = PRE_SEND_STATUSES.includes(m.status);
  const canApprove = APPROVABLE_STATUSES.includes(m.status);
  const canSend = m.status === 'APPROVED';
  const isTerminal = TERMINAL_STATUSES.includes(m.status) || m.status === 'OPTED_OUT';
  const canMarkReplied = ['DELIVERED', 'SENT'].includes(m.status);
  const run = (a: Parameters<typeof action.mutate>[0]) => action.mutate(a);

  const footer = (
    <div className="space-y-3">
      {action.isError && <ErrorState error={action.error} title="Action failed" />}
      {reasonFor && (
        <div className="rounded-xl border border-foreground/10 bg-background p-3">
          <p className="text-xs font-semibold">{reasonFor === 'reject' ? 'Reject this email' : reasonFor === 'opt_out' ? 'Mark recipient as opted out (do not contact)' : 'Restrict this organizer from all future outreach'}</p>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Reason (optional, recorded in the audit log)" className={`${inputClass} mt-2`} />
          <div className="mt-2 flex gap-2">
            <Btn variant={reasonFor === 'reject' ? 'secondary' : 'danger'} size="sm" loading={action.isPending} onClick={() => { run({ id: m.id, action: reasonFor, reason: reason || undefined }); setReasonFor(null); }}>Confirm</Btn>
            <Btn variant="ghost" size="sm" onClick={() => setReasonFor(null)}>Cancel</Btn>
          </div>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {canApprove && <Btn variant="primary" loading={action.isPending} onClick={() => run({ id: m.id, action: 'approve' })}><Check size={13} /> Approve</Btn>}
        {canSend && <Btn variant="primary" loading={action.isPending} onClick={() => run({ id: m.id, action: m.failureReason ? 'retry' : 'send' })}><Send size={13} /> {m.failureReason ? 'Retry send' : 'Send email'}</Btn>}
        {canEdit && !editing && <Btn onClick={() => setEditing(true)}><Edit3 size={13} /> Edit email</Btn>}
        {canMarkReplied && <Btn onClick={() => run({ id: m.id, action: 'mark_replied' })} loading={action.isPending}><MessageSquareReply size={13} /> Mark replied</Btn>}
        {canEdit && <Btn onClick={() => setReasonFor('reject')}><XCircle size={13} /> Reject</Btn>}
        {!isTerminal && <Btn variant="danger" onClick={() => setReasonFor('opt_out')}><Ban size={13} /> Do not contact</Btn>}
        {!isTerminal && <Btn variant="ghost" onClick={() => setReasonFor('restrict_organizer')}><ShieldAlert size={13} /> Restrict organizer</Btn>}
      </div>
      {canApprove && <p className="text-[11px] text-muted-foreground">Approving does not send. After approval a separate “Send email” step delivers it — nothing goes out without both.</p>}
    </div>
  );

  return (
    <Drawer open onClose={onClose} kicker={`Outreach #${m.id}`} title={m.subject ?? 'Email not yet generated'} footer={footer} width="max-w-3xl">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={m.status} />
        <Badge tone={m.generatedBy === 'ai' ? 'info' : 'neutral'}>{m.generatedBy === 'ai' ? 'AI generated' : 'Template fallback'}</Badge>
        {isMock && <Badge tone="warn">Mock send</Badge>}
      </div>
      {m.failureReason && <div className="mt-4"><Notice tone="danger"><strong>Last send attempt failed:</strong> {m.failureReason}</Notice></div>}
      {isMock && <div className="mt-4"><Notice tone="warn">This message was processed by the mock email provider because SMTP is not configured. No real email reached the recipient.</Notice></div>}

      <Section title="Recipient">
        <DL rows={[
          ['Organizer', m.organizer ? <Link href={`/admin/discovery/organizers/${m.organizer.id}`} className="font-semibold text-accent hover:underline">{m.organizer.name}</Link> : NA],
          ['Contact name', NA],
          ['Email', m.recipient ? <a href={`mailto:${m.recipient}`} className="text-accent hover:underline">{m.recipient}</a> : NA],
          ['Phone', val(m.organizer?.phone)],
          ['Website', <ExtLink href={m.organizer?.website} />],
        ]} />
      </Section>

      <Section title="Event" aside={<Link href={`/admin/discovery/events?event=${m.event.id}`} className="font-mono-face text-[10px] uppercase tracking-wider text-accent hover:underline">Open event →</Link>}>
        <DL rows={[
          ['Event', val(m.event.name)],
          ['Date', val(m.event.date)],
          ['City', [m.event.city, m.event.state].filter(Boolean).join(', ') || NA],
          ['Category', val(m.event.category)],
          ['Event URL', <ExtLink href={m.event.url} />],
          ['Registration URL', <ExtLink href={m.event.ticketUrl} />],
        ]} />
      </Section>

      <Section title="Email" aside={<Kicker className="text-muted-foreground">{m.sentAt ? 'Exact message sent' : 'Exact draft awaiting approval'}</Kicker>}>
        {editing ? (
          <div className="space-y-2">
            <input value={subject} onChange={(e) => setSubject(e.target.value)} className={`${inputClass} font-semibold`} placeholder="Subject" />
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={14} className={inputClass} placeholder="Message body" />
            {edit.isError && <ErrorState error={edit.error} title="Could not save" />}
            <div className="flex gap-2">
              <Btn variant="primary" size="sm" loading={edit.isPending} onClick={() => edit.mutate({ id: m.id, subject, message: body }, { onSuccess: () => setEditing(false) })}>Save</Btn>
              <Btn variant="ghost" size="sm" onClick={() => { setEditing(false); setSubject(m.subject ?? ''); setBody(m.message ?? ''); }}>Cancel</Btn>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-foreground/10 bg-background p-5 text-sm">
            <div className="grid gap-1 border-b border-foreground/10 pb-3 font-mono-face text-[11px] text-muted-foreground">
              <p><span className="inline-block w-16">To</span>{m.recipient ?? NA}</p>
              <p><span className="inline-block w-16">Subject</span><span className="text-foreground">{m.subject ?? NA}</span></p>
            </div>
            {m.message ? <p className="mt-4 whitespace-pre-wrap leading-relaxed text-foreground/90">{m.message}</p> : <p className="mt-4 text-muted-foreground">The email body has not been generated yet.</p>}
          </div>
        )}
        <DL rows={[
          ['Generated by', m.generatedBy === 'ai' ? 'Promotion agent (AI model)' : 'Promotion agent (deterministic template)'],
          ['Generated at', fmtDateTime(m.createdAt)],
          ['Approved at', NA],
          ['Sent at', fmtDateTime(m.sentAt)],
          ['Email provider', providerFor(m)],
          ['Message ID', val(m.messageId)],
          ['Send attempts', String(m.sendAttemptCount)],
        ]} />
        <p className="mt-2 text-[11px] text-muted-foreground">Approval time is not stored by the backend; the audit log records the approval action without a timestamp field on the message.</p>
      </Section>

      <Section title="Status">
        <DL rows={[
          ['Current status', <StatusBadge status={m.status} />],
          ['Generated', fmtDateTime(m.createdAt)],
          ['Sent', fmtDateTime(m.sentAt)],
          ['Last contact', fmtDateTime(m.lastContactedAt)],
          ['Follow-up sent', fmtDateTime(m.followUpSentAt)],
          ['Replied', fmtDateTime(m.responseAt)],
          ['Opened', NA],
          ['Bounced', m.status === 'BOUNCED' ? fmtDateTime(m.lastContactedAt) : 'No'],
        ]} />
      </Section>

      <Section title="Agent activity">
        <ol className="space-y-2 text-xs">
          <TimelineRow at={m.createdAt} label="Organizer selected and email generated" sub={m.organizer?.name ?? undefined} />
          {m.status !== 'NEW' && m.status !== 'RESEARCHED' && m.status !== 'EMAIL_GENERATED' && !m.sentAt && m.status !== 'REJECTED' && <TimelineRow at={m.createdAt} label="Added to approval queue" />}
          {m.sentAt && <TimelineRow at={m.sentAt} label={isMock ? 'Email handed to mock provider' : 'Email sent'} sub={m.recipient ?? undefined} tone={isMock ? 'warn' : 'good'} />}
          {m.status === 'BOUNCED' && <TimelineRow at={m.lastContactedAt} label="Bounced — recipient suppressed" tone="danger" />}
          {m.followUpSentAt && <TimelineRow at={m.followUpSentAt} label="Follow-up sent" tone="good" />}
          {m.responseAt && <TimelineRow at={m.responseAt} label="Reply received" tone="good" />}
          {m.status === 'REJECTED' && <TimelineRow at={m.lastContactedAt ?? m.createdAt} label="Rejected by admin" tone="warn" />}
          {m.status === 'OPTED_OUT' && <TimelineRow at={m.lastContactedAt ?? m.createdAt} label="Recipient opted out" tone="danger" />}
        </ol>
      </Section>
      <p className="mt-6 text-[11px] text-muted-foreground"><MailCheck size={11} className="mr-1 inline" />Drafted {fmtDate(m.createdAt)}. Previous outreach records for this organizer are kept permanently and listed on the organizer profile.</p>
    </Drawer>
  );
}
