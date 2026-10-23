import { useState } from 'react';
import { Ban, Check, PlugZap, ShieldAlert, XCircle } from 'lucide-react';
import { type DiscoveredCommunity, useCommunityAction, useUpdateCommunityPolicy } from './api';
import { Badge, Btn, DL, Drawer, ErrorState, ExtLink, NA, Notice, Section, fmtDateTime, inputClass, val } from './ui';
import { TimelineRow } from './EventDrawer';

const STATUS_TONE: Record<string, 'neutral' | 'good' | 'warn' | 'danger' | 'accent' | 'info'> = {
  DISCOVERED: 'accent', NEEDS_REVIEW: 'warn', APPROVED: 'good', REJECTED: 'danger',
  CONNECTION_REQUIRED: 'warn', CONNECTED: 'good', PERMISSION_MISSING: 'danger', PROMOTION_RESTRICTED: 'danger',
};

function ConnectForm({ community, onDone }: { community: DiscoveredCommunity; onDone: () => void }) {
  const policy = useUpdateCommunityPolicy();
  const action = useCommunityAction();
  const [chatId, setChatId] = useState('');
  const [guildId, setGuildId] = useState('');
  const [channelId, setChannelId] = useState('');

  const platformRef = community.platform === 'telegram' ? (chatId.trim() ? `telegram_${chatId.trim()}` : '') : (guildId.trim() && channelId.trim() ? `discord_${guildId.trim()}_${channelId.trim()}` : '');
  const canSave = Boolean(platformRef) && Boolean(community.communityId);

  const save = () => {
    if (!canSave || !community.communityId) return;
    policy.mutate({ communityId: community.communityId, platformRef }, {
      onSuccess: () => action.mutate({ id: community.id, action: 'mark_connected' }, { onSuccess: onDone }),
    });
  };

  return (
    <div className="rounded-xl border border-foreground/10 bg-background p-3">
      <p className="text-xs font-semibold">Connect this community</p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        The bot has to already be a member — add <strong>@HundredTimesAgentBot</strong> to it in Telegram/Discord first, then send one message there so the real ID becomes knowable, and enter it below.
      </p>
      {community.platform === 'telegram' ? (
        <input value={chatId} onChange={(e) => setChatId(e.target.value)} placeholder="Chat ID (e.g. -1001234567890)" className={`${inputClass} mt-2`} />
      ) : (
        <div className="mt-2 grid grid-cols-2 gap-2">
          <input value={guildId} onChange={(e) => setGuildId(e.target.value)} placeholder="Guild (server) ID" className={inputClass} />
          <input value={channelId} onChange={(e) => setChannelId(e.target.value)} placeholder="Channel ID" className={inputClass} />
        </div>
      )}
      {policy.isError && <ErrorState error={policy.error} title="Could not save" />}
      {action.isError && <ErrorState error={action.error} title="Could not mark connected" />}
      <div className="mt-2 flex gap-2">
        <Btn variant="primary" size="sm" loading={policy.isPending || action.isPending} disabled={!canSave} onClick={save}>Save connection</Btn>
        <Btn variant="ghost" size="sm" onClick={onDone}>Cancel</Btn>
      </div>
    </div>
  );
}

export function CommunityDrawer({ community, onClose }: { community: DiscoveredCommunity | null; onClose: () => void }) {
  const action = useCommunityAction();
  const policy = useUpdateCommunityPolicy();
  const [reasonFor, setReasonFor] = useState<'reject' | 'mark_permission_missing' | 'mark_promotion_restricted' | null>(null);
  const [reason, setReason] = useState('');
  const [connecting, setConnecting] = useState(false);

  if (!community) return null;
  const isTerminal = community.approvalStatus === 'REJECTED';
  const run = (a: Parameters<typeof action.mutate>[0]) => action.mutate(a);

  const footer = (
    <div className="space-y-3">
      {action.isError && <ErrorState error={action.error} title="Action failed" />}
      {reasonFor && (
        <div className="rounded-xl border border-foreground/10 bg-background p-3">
          <p className="text-xs font-semibold">
            {reasonFor === 'reject' ? 'Reject this community' : reasonFor === 'mark_permission_missing' ? 'Flag promotion permission as missing/unclear' : 'Flag this community as restricted from promotion'}
          </p>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Reason (optional, recorded in the audit log)" className={`${inputClass} mt-2`} />
          <div className="mt-2 flex gap-2">
            <Btn variant={reasonFor === 'reject' ? 'secondary' : 'danger'} size="sm" loading={action.isPending} onClick={() => { run({ id: community.id, action: reasonFor, reason: reason || undefined }); setReasonFor(null); }}>Confirm</Btn>
            <Btn variant="ghost" size="sm" onClick={() => setReasonFor(null)}>Cancel</Btn>
          </div>
        </div>
      )}
      {connecting && <ConnectForm community={community} onDone={() => setConnecting(false)} />}
      <div className="flex flex-wrap items-center gap-2">
        {community.approvalStatus !== 'APPROVED' && !isTerminal && <Btn variant="primary" loading={action.isPending} onClick={() => run({ id: community.id, action: 'approve' })}><Check size={13} /> Approve</Btn>}
        {community.approvalStatus === 'APPROVED' && community.connectionStatus !== 'CONNECTED' && !connecting && <Btn onClick={() => setConnecting(true)}><PlugZap size={13} /> Connect (set real chat/channel ID)</Btn>}
        {community.approvalStatus === 'APPROVED' && community.promotionAllowed === null && (
          <Btn variant="primary" loading={policy.isPending} disabled={!community.communityId} onClick={() => community.communityId && policy.mutate({ communityId: community.communityId, promotionAllowed: true })}>
            <Check size={13} /> Confirm promotion allowed
          </Btn>
        )}
        {!isTerminal && <Btn onClick={() => setReasonFor('reject')}><XCircle size={13} /> Reject</Btn>}
        {!isTerminal && <Btn variant="ghost" onClick={() => setReasonFor('mark_permission_missing')}><ShieldAlert size={13} /> Flag permission missing</Btn>}
        {!isTerminal && <Btn variant="danger" onClick={() => setReasonFor('mark_promotion_restricted')}><Ban size={13} /> Flag promotion restricted</Btn>}
      </div>
      {policy.isError && <ErrorState error={policy.error} title="Could not save" />}
      <p className="text-[11px] text-muted-foreground">Approving a lead never joins the community, invites a bot, or grants posting permission by itself — both "Connect" and "Confirm promotion allowed" are separate, explicit steps a human takes only after actually adding the bot and reading the community's rules.</p>
    </div>
  );

  return (
    <Drawer open onClose={onClose} kicker={`Discovered community #${community.id} · ${community.platform}`} title={community.name} footer={footer} width="max-w-3xl">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={STATUS_TONE[community.approvalStatus] ?? 'neutral'}>{community.approvalStatus.replace(/_/g, ' ')}</Badge>
        <Badge tone="neutral">{community.platform}</Badge>
        {community.connectionStatus !== 'NOT_CONNECTED' && <Badge tone={community.connectionStatus === 'CONNECTED' ? 'good' : 'warn'}>{community.connectionStatus.replace(/_/g, ' ')}</Badge>}
        <span className="ml-auto text-[11px] text-muted-foreground">Confidence {community.confidenceScore}</span>
      </div>

      {community.verificationNotes.length > 0 && (
        <div className="mt-4"><Notice tone="warn">{community.verificationNotes.map((n, i) => <p key={i}>{n}</p>)}</Notice></div>
      )}
      {community.rejectionReason && <div className="mt-3"><Notice tone="danger"><strong>Rejected:</strong> {community.rejectionReason}</Notice></div>}

      <Section title="Community details">
        <DL rows={[
          ['Name', val(community.name)],
          ['Platform', community.platform],
          ['Description', community.description ? <span className="whitespace-pre-wrap leading-relaxed">{community.description}</span> : NA],
          ['Sector', val(community.category)],
          ['Subsector', val(community.subcategory)],
          ['Topics', community.topics.length ? community.topics.join(', ') : NA],
          ['City', val(community.city)],
          ['State', val(community.state)],
          ['Country', val(community.country)],
          ['Member / subscriber count', community.memberCount != null ? community.memberCount.toLocaleString() : 'Not shown publicly'],
          ['Canonical URL', <ExtLink href={community.canonicalUrl} />],
          ['Invite URL', <ExtLink href={community.inviteUrl} />],
        ]} />
      </Section>

      <Section title="Promotion policy">
        <DL rows={[
          ['Rules text found', community.rulesText ? <span className="whitespace-pre-wrap leading-relaxed">{community.rulesText}</span> : 'None found on the page — check manually'],
          ['Promotion allowed', community.promotionAllowed === null ? 'Not yet confirmed' : community.promotionAllowed ? 'Yes' : 'No'],
          ['Automation allowed', 'No — never automatic, matches every other community in this platform'],
          ['Risk level', community.riskLevel],
        ]} />
        <p className="mt-2 text-[11px] text-muted-foreground">Approving this lead never sets promotion permission by itself — that still needs a separate, explicit confirmation once a human has actually read this community's rules.</p>
      </Section>

      <Section title={`Sources (${community.sources.length})`}>
        {community.sources.length === 0 ? <p className="text-sm text-muted-foreground">{NA}</p> : (
          <ol className="space-y-3">
            {community.sources.map((s) => (
              <li key={s.id} className="rounded-xl border border-foreground/10 bg-background p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground">{s.sourceType.replace(/_/g, ' ')}</span>
                </div>
                <DL rows={[
                  ['URL', <ExtLink href={s.sourceUrl} />],
                  ['Fetched', fmtDateTime(s.fetchedAt)],
                ]} />
              </li>
            ))}
          </ol>
        )}
      </Section>

      <Section title="Discovery details">
        <DL rows={[
          ['Discovered', fmtDateTime(community.discoveredAt)],
          ['Last checked', fmtDateTime(community.lastCheckedAt)],
          ['Discovery status', community.discoveryStatus],
        ]} />
      </Section>

      <Section title="Agent activity">
        <ol className="space-y-2 text-xs">
          <TimelineRow at={community.discoveredAt} label="Community discovered via public web search" sub={community.sources[0]?.sourceUrl ? new URL(community.sources[0].sourceUrl).host : undefined} />
          {community.sources.slice(1).map((s) => <TimelineRow key={s.id} at={s.fetchedAt} label={`${s.sourceType.replace(/_/g, ' ')} read`} sub={new URL(s.sourceUrl).host} />)}
          {community.approvalStatus !== 'DISCOVERED' && community.approvalStatus !== 'NEEDS_REVIEW' && (
            <TimelineRow at={community.lastCheckedAt ?? community.discoveredAt} label={`Marked ${community.approvalStatus.replace(/_/g, ' ').toLowerCase()} by admin`} tone={community.approvalStatus === 'REJECTED' ? 'danger' : 'good'} />
          )}
        </ol>
        <p className="mt-3 text-[11px] text-muted-foreground">Timestamps come from the stored records; the agent does not log intermediate steps.</p>
      </Section>
    </Drawer>
  );
}
