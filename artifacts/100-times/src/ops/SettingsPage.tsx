import { useEffect, useState } from 'react';
import { Link, useLocation, useSearch } from 'wouter';
import {
  ArrowRight,
  CheckCircle2,
  Compass,
  Database,
  Eye,
  EyeOff,
  Globe,
  Mail,
  Play,
  RefreshCw,
  Send,
  Sliders,
  Trash2,
  XCircle,
} from 'lucide-react';
import {
  OutboxItem,
  useClearEmailOutbox,
  useEmailOutbox,
  useMe,
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
import { SourceRegistryView } from './SourceRegistryView';
import { Breadcrumbs } from './OpsLayout';

type SettingsTab = 'registry' | 'smtp' | 'system';
const TABS: SettingsTab[] = ['registry', 'smtp', 'system'];

/** A batch/follow-up result as label/value rows (all values come from the API response). */
function ResultRows({ data }: { data: object }) {
  return <DL rows={Object.entries(data).map(([k, v]) => [k.replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').toLowerCase(), v === null || v === undefined ? 'â€”' : typeof v === 'object' ? JSON.stringify(v) : String(v)])} />;
}

export function SettingsPage() {
  const me = useMe();
  const runBatch = useRunOutreachBatch();
  const followups = useProcessFollowups();
  // The open tab is in the URL (?tab=smtp) so other pages can link straight to it.
  const search = useSearch();
  const [, setLocation] = useLocation();
  const tabParam = new URLSearchParams(search).get('tab');
  const activeTab: SettingsTab | 'sources' = tabParam === 'sources' ? 'sources' : (TABS as string[]).includes(tabParam ?? '') ? (tabParam as SettingsTab) : 'registry';
  const setActiveTab = (tab: SettingsTab) => setLocation(tab === 'registry' ? '/admin/settings' : `/admin/settings?tab=${tab}`, { replace: true });
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
    saveSmtp.mutate(
      {
        host,
        port: Number(port) || 587,
        username: username || undefined,
        password: password || undefined,
        fromEmail,
        useTls,
      },
      // The form re-reads the saved config (the hook invalidates it); the password is never sent back, so clear it.
      { onSuccess: () => setPassword('') },
    );
  };

  const handleSendTest = (e: React.FormEvent) => {
    e.preventDefault();
    if (!testRecipient) return;
    testSmtp.mutate({ recipient: testRecipient });
  };

  const isReal = smtpConfigQuery.data?.status === 'REAL';

  return (
    <div>
      <Breadcrumbs items={[{ label: 'Administration' }, { label: 'Providers & API keys' }]} />
      <PageHeader
        kicker="Administration"
        title="Providers & API keys"
        subtitle="The source registry (which discovery sources may run at all), outgoing e-mail (SMTP) and account details. What a discovery run searches is set in Discovery configuration."
      />

      {/* Settings Navigation Tabs */}
      <div className="mt-6 flex flex-wrap gap-2 border-b border-foreground/10 pb-4">
        <button
          type="button"
          onClick={() => setActiveTab('registry')}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition-all ${
            activeTab === 'registry'
              ? 'bg-accent text-accent-foreground shadow-sm ring-1 ring-accent/30'
              : 'border border-foreground/10 bg-card text-muted-foreground hover:bg-muted/40 hover:text-foreground'
          }`}
        >
          <Database size={14} /> Source registry
        </button>

        <Link
          href="/admin/discover/configuration#sources"
          title="Search providers, channels, listing websites and the Ticketmaster key are edited in Discovery configuration"
          className="flex items-center gap-2 rounded-xl border border-foreground/10 bg-card px-4 py-2.5 text-xs font-bold text-muted-foreground transition-all hover:bg-muted/40 hover:text-foreground"
        >
          <Globe size={14} /> Discovery sources & providers <ArrowRight size={12} />
        </Link>

        <button
          type="button"
          onClick={() => setActiveTab('smtp')}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition-all ${
            activeTab === 'smtp'
              ? 'bg-accent text-accent-foreground shadow-sm ring-1 ring-accent/30'
              : 'border border-foreground/10 bg-card text-muted-foreground hover:bg-muted/40 hover:text-foreground'
          }`}
        >
          <Mail size={14} /> Outgoing e-mail (SMTP)
          {smtpConfigQuery.data && <Badge tone={isReal ? 'good' : 'warn'}>{isReal ? 'Live SMTP' : 'Not configured'}</Badge>}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('system')}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition-all ${
            activeTab === 'system'
              ? 'bg-accent text-accent-foreground shadow-sm ring-1 ring-accent/30'
              : 'border border-foreground/10 bg-card text-muted-foreground hover:bg-muted/40 hover:text-foreground'
          }`}
        >
          <Sliders size={14} /> Agent runs & account
        </button>
      </div>

      {/* Tab 0: Source registry */}
      {activeTab === 'registry' && (
        <div className="mt-6">
          <SourceRegistryView />
        </div>
      )}

      {/* Old "Discovery Channels & Custom Websites" tab (?tab=sources): moved to Discovery configuration. */}
      {activeTab === 'sources' && (
        <div className="mt-6">
          <Panel className="p-6">
            <h3 className="font-display text-lg font-bold flex items-center gap-2"><Globe size={18} className="text-accent" /> Discovery sources & providers have moved</h3>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              Search providers, directories and aggregators, listing websites, source health checks and the Ticketmaster key are now edited
              together with the rest of the saved discovery settings, in one place.
            </p>
            <Link href="/admin/discover/configuration#sources" className="button-press mt-4 inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground">
              Open Discovery configuration â†’ Sources & providers <ArrowRight size={12} />
            </Link>
          </Panel>
        </div>
      )}

      {/* Tab 3: Agent runs & account */}
      {activeTab === 'system' && (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          {/* Account & Platform Info */}
          <Panel className="p-6">
            <Section title="Signed in as">
              <DL rows={[['Name', me.data?.name ?? 'â€”'], ['Email', me.data?.email ?? 'â€”'], ['Role', me.data?.role ?? 'â€”']]} />
            </Section>

            <Section title="Schedules & Automation">
              <p className="text-sm text-muted-foreground">
                Automatic discovery is switched on or off on its own page, <Link href="/admin/discover/automatic" className="text-accent hover:underline">Automatic discovery</Link>.
                Outreach drafting has its switch under <Link href="/admin/automations" className="text-accent hover:underline">Automations</Link>, and every e-mail waits for human approval before delivery.
              </p>
            </Section>
          </Panel>

          {/* Manual Runs Panel */}
          <Panel className="p-6">
            <Section title="Run event discovery">
              <p className="text-sm text-muted-foreground">Discovery runs are started from the guided Run discovery page; their progress and reports are under Run history &amp; reports.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Link href="/admin/discover" className="button-press inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-xs font-bold text-accent-foreground hover:bg-primary hover:text-primary-foreground"><Compass size={13} /> Run discovery</Link>
                <Link href="/admin/discover/runs" className="button-press inline-flex items-center gap-1.5 rounded-full border border-foreground/15 bg-background px-4 py-2 text-xs font-bold hover:border-accent hover:text-accent">Run history &amp; reports</Link>
              </div>
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
                <p className="text-[11px] text-muted-foreground">Drafts land in <Link href="/admin/outreach/pending" className="text-accent hover:underline">Outreach â†’ Pending</Link>. Nothing is sent until approved.</p>
                {runBatch.isError && <ErrorState error={runBatch.error} title="Batch failed" />}
                {runBatch.isSuccess && (
                  <Notice tone="good">
                    <p className="mb-2 font-semibold">Outreach batch finished.</p>
                    <ResultRows data={runBatch.data} />
                  </Notice>
                )}
                {followups.isError && <ErrorState error={followups.error} title="Processing follow-ups failed" />}
                {followups.isSuccess && (
                  <Notice tone="good">
                    <p className="mb-2 font-semibold">Follow-ups processed.</p>
                    <ResultRows data={followups.data} />
                  </Notice>
                )}
              </div>
            </Section>
          </Panel>
        </div>
      )}

      {/* Tab 2: Outgoing Email & SMTP Relay */}
      {activeTab === 'smtp' && (
        <div className="mt-6 space-y-8">
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
                  placeholder={smtpConfigQuery.data?.hasPassword ? 'â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢ (leave blank to keep)' : 'Enter SMTP password'}
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

        {/* Outgoing Email Outbox (Live Log) */}
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
                  onClick={() => { if (window.confirm('Clear the outbox log? This only removes the log entries shown here; no e-mail is recalled.')) clearOutbox.mutate(); }}
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
      )}

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
