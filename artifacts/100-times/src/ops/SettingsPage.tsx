import { useEffect, useState } from 'react';
import { CheckCircle2, Eye, EyeOff, Mail, Play, RefreshCw, Send, Trash2, XCircle } from 'lucide-react';
import {
  OutboxItem,
  useClearEmailOutbox,
  useEmailOutbox,
  useMe,
  useOutreachStats,
  useProcessFollowups,
  useRunOutreachBatch,
  useSaveSmtpConfig,
  useSmtpConfig,
  useTestSmtp,
} from './api';
import {
  AdminTable,
  Badge,
  Btn,
  DL,
  Drawer,
  ErrorState,
  Notice,
  PageHeader,
  Panel,
  Section,
  cell,
  cellMuted,
  fmtDateTime,
  inputClass,
} from './ui';
import { ManualResearchForm } from './ManualResearch';

export function SettingsPage() {
  const me = useMe();
  const stats = useOutreachStats();
  const runBatch = useRunOutreachBatch();
  const followups = useProcessFollowups();
  const [maxCandidates, setMaxCandidates] = useState('10');

  // SMTP Settings State
  const smtpConfigQuery = useSmtpConfig();
  const saveSmtp = useSaveSmtpConfig();
  const testSmtp = useTestSmtp();
  const outboxQuery = useEmailOutbox();
  const clearOutbox = useClearEmailOutbox();

  const [host, setHost] = useState('');
  const [port, setPort] = useState('587');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fromEmail, setFromEmail] = useState('');
  const [useTls, setUseTls] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [testRecipient, setTestRecipient] = useState('');
  const [selectedMail, setSelectedMail] = useState<OutboxItem | null>(null);

  // Sync form when config is loaded
  useEffect(() => {
    if (smtpConfigQuery.data) {
      const d = smtpConfigQuery.data;
      setHost(d.host || '');
      setPort(String(d.port || 587));
      setUsername(d.username || '');
      setFromEmail(d.fromEmail || '');
      setUseTls(d.useTls ?? true);
      if (me.data?.email && !testRecipient) {
        setTestRecipient(me.data.email);
      }
    }
  }, [smtpConfigQuery.data, me.data?.email]);

  const applyPreset = (presetHost: string, presetPort: number, presetTls: boolean, defaultFrom = '') => {
    setHost(presetHost);
    setPort(String(presetPort));
    setUseTls(presetTls);
    if (defaultFrom && !fromEmail) {
      setFromEmail(defaultFrom);
    }
  };

  const handleSaveSmtp = (e: React.FormEvent) => {
    e.preventDefault();
    saveSmtp.mutate({
      host,
      port: Number(port) || 587,
      username: username || undefined,
      password: password || undefined,
      fromEmail,
      useTls,
    });
  };

  const handleSendTest = (e: React.FormEvent) => {
    e.preventDefault();
    if (!testRecipient) return;
    testSmtp.mutate({ recipient: testRecipient });
  };

  const isReal = smtpConfigQuery.data?.status === 'REAL';

  return (
    <div>
      <PageHeader
        kicker="Settings"
        title="Console settings and agent controls"
        subtitle="Manage SMTP email delivery, organizer acquisition thresholds, and automated agent schedules."
      />

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        {/* Account & Platform Info */}
        <Panel className="p-6">
          <Section title="Signed in as">
            <DL rows={[['Name', me.data?.name ?? '—'], ['Email', me.data?.email ?? '—'], ['Role', me.data?.role ?? '—']]} />
          </Section>

          <Section title="Schedules & Automation">
            <p className="text-sm text-muted-foreground">
              The discovery automation's scan has its own on/off switch on the Dashboard. Outreach batches are drafted only via
              “Generate outreach batch”, and every email waits for human approval before delivery.
            </p>
          </Section>
        </Panel>

        {/* Manual Runs Panel */}
        <Panel className="p-6">
          <Section title="Run Organizer Discovery (automation) — manual research">
            <ManualResearchForm />
          </Section>
          <Section title="Run Organizer Outreach (Agent 2)">
            <div className="grid gap-2 text-xs">
              <label>
                Max organizers to draft for
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={maxCandidates}
                  onChange={(e) => setMaxCandidates(e.target.value)}
                  className={`${inputClass} mt-1`}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <Btn
                  variant="primary"
                  loading={runBatch.isPending}
                  onClick={() => runBatch.mutate({ maxCandidates: Number(maxCandidates) || undefined })}
                >
                  <Play size={13} /> Generate outreach batch
                </Btn>
                <Btn loading={followups.isPending} onClick={() => followups.mutate()}>
                  Process follow-ups
                </Btn>
              </div>
              <p className="text-[11px] text-muted-foreground">Drafts land in Outreach → Pending. Nothing is sent until approved.</p>
              {runBatch.isError && <ErrorState error={runBatch.error} title="Batch failed" />}
              {runBatch.isSuccess && (
                <Notice tone="info">
                  <pre className="whitespace-pre-wrap font-mono-face text-[11px]">{JSON.stringify(runBatch.data, null, 2)}</pre>
                </Notice>
              )}
              {followups.isSuccess && (
                <Notice tone="info">
                  <pre className="whitespace-pre-wrap font-mono-face text-[11px]">{JSON.stringify(followups.data, null, 2)}</pre>
                </Notice>
              )}
            </div>
          </Section>
        </Panel>
      </div>

      {/* SMTP Email Delivery Configuration */}
      <div className="mt-8">
        <Panel className="p-6">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-foreground/10 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <Mail size={18} className="text-accent" />
                <h3 className="font-display text-lg font-bold">Email Delivery & SMTP Configuration</h3>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Configure your SMTP relay to send approved organizer outreach emails, ticket confirmations, and attendee notifications to real inboxes.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={isReal ? 'good' : 'warn'}>
                {isReal ? 'SMTP Configured (REAL Delivery)' : 'Mock Mode (Not Configured)'}
              </Badge>
            </div>
          </div>

          {!isReal && (
            <div className="mt-4">
              <Notice tone="warn">
                <strong>Email sending is currently in mock mode.</strong> Approved emails are recorded in the Outbox below but not delivered to real inboxes. Enter your SMTP relay credentials below and click <strong>Save SMTP Settings</strong> to activate live delivery.
              </Notice>
            </div>
          )}

          {isReal && (
            <div className="mt-4">
              <Notice tone="info">
                <strong>Live SMTP Delivery is Active.</strong> All approved outreach messages and platform notifications are dispatched through <code>{smtpConfigQuery.data?.host}:{smtpConfigQuery.data?.port}</code>.
              </Notice>
            </div>
          )}

          {/* Quick Presets */}
          <div className="mt-6">
            <span className="font-mono-face text-[10px] uppercase tracking-wider text-muted-foreground">Quick Provider Presets:</span>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => applyPreset('smtp.gmail.com', 587, true)}
                className="rounded-full border border-foreground/10 bg-background px-3 py-1 text-xs font-medium hover:border-accent hover:text-accent"
              >
                Gmail (smtp.gmail.com:587)
              </button>
              <button
                type="button"
                onClick={() => applyPreset('smtp.sendgrid.net', 587, true)}
                className="rounded-full border border-foreground/10 bg-background px-3 py-1 text-xs font-medium hover:border-accent hover:text-accent"
              >
                SendGrid (smtp.sendgrid.net:587)
              </button>
              <button
                type="button"
                onClick={() => applyPreset('smtp-relay.brevo.com', 587, true)}
                className="rounded-full border border-foreground/10 bg-background px-3 py-1 text-xs font-medium hover:border-accent hover:text-accent"
              >
                Brevo / Sendinblue (:587)
              </button>
              <button
                type="button"
                onClick={() => applyPreset('localhost', 1025, false, 'dev@100times.local')}
                className="rounded-full border border-foreground/10 bg-background px-3 py-1 text-xs font-medium hover:border-accent hover:text-accent"
              >
                Local Dev / Mailpit (localhost:1025)
              </button>
            </div>
          </div>

          {/* SMTP Credentials Form */}
          <form onSubmit={handleSaveSmtp} className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="block text-xs font-medium">
                SMTP Host <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="e.g. smtp.gmail.com"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                className={`${inputClass} mt-1`}
              />
            </div>

            <div>
              <label className="block text-xs font-medium">
                Port <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                required
                value={port}
                onChange={(e) => setPort(e.target.value)}
                className={`${inputClass} mt-1`}
              />
              <span className="font-mono-face text-[10px] text-muted-foreground">587 (STARTTLS), 465 (SSL), or 1025 (Local)</span>
            </div>

            <div>
              <label className="block text-xs font-medium">
                From Email Address <span className="text-red-500">*</span>
              </label>
              <input
                type="email"
                required
                placeholder="e.g. notifications@100times.in"
                value={fromEmail}
                onChange={(e) => setFromEmail(e.target.value)}
                className={`${inputClass} mt-1`}
              />
            </div>

            <div>
              <label className="block text-xs font-medium">Username / Relay Login</label>
              <input
                type="text"
                placeholder="e.g. your-account@gmail.com or apikey"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className={`${inputClass} mt-1`}
              />
            </div>

            <div>
              <label className="block text-xs font-medium">
                Password / App Password {smtpConfigQuery.data?.hasPassword && !password && <span className="text-green-500">(Saved in .env)</span>}
              </label>
              <div className="relative mt-1">
                <input
                  type={showPassword ? 'text' : 'password'}
                  placeholder={smtpConfigQuery.data?.hasPassword ? '•••••••• (leave blank to keep)' : 'Enter SMTP password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={`${inputClass} pr-9`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <div className="flex flex-col justify-end">
              <label className="flex items-center gap-2 text-xs font-medium cursor-pointer mb-2">
                <input
                  type="checkbox"
                  checked={useTls}
                  onChange={(e) => setUseTls(e.target.checked)}
                  className="h-4 w-4 rounded border-foreground/20 text-accent focus:ring-accent"
                />
                <span>Enable TLS / STARTTLS Encryption</span>
              </label>
            </div>

            <div className="sm:col-span-2 lg:col-span-3 flex flex-wrap items-center gap-3 pt-2">
              <Btn variant="primary" type="submit" loading={saveSmtp.isPending}>
                <CheckCircle2 size={14} /> Save SMTP Settings
              </Btn>

              {saveSmtp.isSuccess && (
                <span className="font-mono-face text-xs text-green-500 flex items-center gap-1">
                  <CheckCircle2 size={13} /> Settings saved and activated in environment!
                </span>
              )}
              {saveSmtp.isError && (
                <span className="font-mono-face text-xs text-red-500 flex items-center gap-1">
                  <XCircle size={13} /> Failed to save settings: {(saveSmtp.error as Error)?.message}
                </span>
              )}
            </div>
          </form>

          {/* Test Email Section */}
          <div className="mt-8 border-t border-foreground/10 pt-6">
            <h4 className="font-display text-sm font-bold flex items-center gap-2">
              <Send size={14} className="text-accent" /> Send Verification / Test Email
            </h4>
            <p className="mt-1 text-xs text-muted-foreground">
              Verify your SMTP connection by dispatching an immediate test email to your inbox.
            </p>

            <form onSubmit={handleSendTest} className="mt-3 flex flex-wrap items-center gap-2 max-w-xl">
              <input
                type="email"
                required
                placeholder="recipient@example.com"
                value={testRecipient}
                onChange={(e) => setTestRecipient(e.target.value)}
                className={`${inputClass} flex-1 min-w-[240px]`}
              />
              <Btn variant="secondary" type="submit" loading={testSmtp.isPending}>
                <Send size={13} /> Send Test Email
              </Btn>
            </form>

            {testSmtp.isSuccess && (
              <div className="mt-3">
                <Notice tone={testSmtp.data.success ? 'info' : 'danger'}>
                  <strong>{testSmtp.data.success ? 'Test Email Delivered!' : 'Delivery Test Failed:'}</strong> {testSmtp.data.message}
                  {testSmtp.data.messageId && <span className="ml-2 font-mono-face text-[10px] opacity-80">(ID: {testSmtp.data.messageId})</span>}
                </Notice>
              </div>
            )}
            {testSmtp.isError && (
              <div className="mt-3">
                <Notice tone="danger">
                  <strong>Test Failed:</strong> {(testSmtp.error as Error)?.message}
                </Notice>
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* Outgoing Email Outbox (Live Log) */}
      <div className="mt-8">
        <Panel className="p-6">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-foreground/10 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <Mail size={16} className="text-accent" />
                <h3 className="font-display text-base font-bold">Email Outbox & Delivery Inspector</h3>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Real-time log of outgoing emails (organizer outreach, event confirmations, test messages).
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Btn
                variant="ghost"
                size="sm"
                onClick={() => outboxQuery.refetch()}
                loading={outboxQuery.isFetching}
              >
                <RefreshCw size={13} /> Refresh
              </Btn>
              {outboxQuery.data && outboxQuery.data.length > 0 && (
                <Btn
                  variant="ghost"
                  size="sm"
                  onClick={() => clearOutbox.mutate()}
                  loading={clearOutbox.isPending}
                >
                  <Trash2 size={13} /> Clear
                </Btn>
              )}
            </div>
          </div>

          <div className="mt-4">
            {outboxQuery.isLoading && <p className="text-xs text-muted-foreground py-4 text-center">Loading outbox records...</p>}
            {outboxQuery.data && outboxQuery.data.length === 0 && (
              <div className="py-8 text-center text-xs text-muted-foreground">
                <Mail size={24} className="mx-auto mb-2 opacity-40" />
                No outgoing emails recorded yet. Send a test email above or approve an outreach message to see delivery logs here.
              </div>
            )}
            {outboxQuery.data && outboxQuery.data.length > 0 && (
              <AdminTable
                columns={[
                  { label: 'Time' },
                  { label: 'Recipient' },
                  { label: 'Subject' },
                  { label: 'Provider' },
                  { label: 'Status' },
                  { label: '' },
                ]}
              >
                {outboxQuery.data.map((item) => (
                  <tr key={item.id} className="hover:bg-muted/40 transition">
                    <td className={cellMuted}>{fmtDateTime(item.timestamp)}</td>
                    <td className={cell}>
                      <span className="font-semibold text-accent">{item.recipient}</span>
                    </td>
                    <td className={cell}>
                      <div className="truncate max-w-md font-medium">{item.subject}</div>
                    </td>
                    <td className={cell}>
                      <Badge tone={item.provider === 'smtp' ? 'good' : 'warn'}>
                        {item.provider === 'smtp' ? 'SMTP' : 'MOCK'}
                      </Badge>
                    </td>
                    <td className={cell}>
                      <span
                        className={`font-mono-face text-[10px] uppercase font-bold ${
                          item.status === 'DELIVERED'
                            ? 'text-green-500'
                            : item.status === 'BOUNCED' || item.status === 'FAILED'
                            ? 'text-red-500'
                            : 'text-amber-500'
                        }`}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td className={cell}>
                      <button
                        onClick={() => setSelectedMail(item)}
                        className="font-mono-face text-[11px] text-accent hover:underline flex items-center gap-1"
                      >
                        <Eye size={12} /> View
                      </button>
                    </td>
                  </tr>
                ))}
              </AdminTable>
            )}
          </div>
        </Panel>
      </div>

      {/* Email Preview Drawer */}
      {selectedMail && (
        <Drawer
          open={Boolean(selectedMail)}
          onClose={() => setSelectedMail(null)}
          kicker={`Email ID: ${selectedMail.id}`}
          title={selectedMail.subject}
        >
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={selectedMail.provider === 'smtp' ? 'good' : 'warn'}>
                Provider: {selectedMail.provider.toUpperCase()}
              </Badge>
              <Badge tone={selectedMail.status === 'DELIVERED' ? 'good' : 'neutral'}>
                Status: {selectedMail.status}
              </Badge>
              {selectedMail.messageId && (
                <span className="font-mono-face text-[11px] text-muted-foreground">
                  ID: {selectedMail.messageId}
                </span>
              )}
            </div>

            <Section title="Delivery Details">
              <DL
                rows={[
                  ['Recipient', selectedMail.recipient],
                  ['Dispatched At', fmtDateTime(selectedMail.timestamp)],
                  ['Subject', selectedMail.subject],
                  ['Error Reason', selectedMail.error ?? 'None (Success)'],
                ]}
              />
            </Section>

            <Section title="Email Body Content">
              <div className="rounded-xl border border-foreground/10 bg-muted/30 p-4 font-mono-face text-xs whitespace-pre-wrap leading-relaxed">
                {selectedMail.body}
              </div>
            </Section>
          </div>
        </Drawer>
      )}
    </div>
  );
}
