import { useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Instagram,
  Facebook,
  Linkedin,
  MessageSquare,
  Play,
  RefreshCw,
  Send,
  Share2,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  X,
  XCircle,
} from 'lucide-react';
import {
  type PlatformPromotionSetting,
  type PromotionJob,
  useApprovePromotionJob,
  usePromotionJobs,
  usePromotionSettings,
  usePromotionStats,
  useRejectPromotionJob,
  useRetryPromotionJob,
  useTriggerEventPromotion,
  useUpdatePlatformSetting,
  useUpdatePromotionJobContent,
} from './api';
import { Btn, Drawer, EmptyState, ErrorState, Kicker, LoadingState, cx, fmtDateTime } from './ui';

const errText = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');

const PLATFORM_ICONS: Record<string, typeof Share2> = {
  instagram: Instagram,
  facebook: Facebook,
  linkedin: Linkedin,
  telegram: Send,
  discord: MessageSquare,
};

const PLATFORM_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  instagram: { bg: 'bg-pink-500/10', text: 'text-pink-400', border: 'border-pink-500/20' },
  facebook: { bg: 'bg-blue-600/10', text: 'text-blue-400', border: 'border-blue-600/20' },
  linkedin: { bg: 'bg-sky-600/10', text: 'text-sky-400', border: 'border-sky-600/20' },
  telegram: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/20' },
  discord: { bg: 'bg-indigo-500/10', text: 'text-indigo-400', border: 'border-indigo-500/20' },
};

export function SocialPromotionsPage() {
  const [selectedPlatform, setSelectedPlatform] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [activeJob, setActiveJob] = useState<PromotionJob | null>(null);
  const [editingJob, setEditingJob] = useState<PromotionJob | null>(null);
  const [manualEventId, setManualEventId] = useState<string>('');
  const [showManualModal, setShowManualModal] = useState<boolean>(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  const stats = usePromotionStats();
  const settings = usePromotionSettings();
  const jobs = usePromotionJobs({
    platform: selectedPlatform === 'all' ? undefined : selectedPlatform,
    status: selectedStatus === 'all' ? undefined : selectedStatus,
  });

  const approveMutation = useApprovePromotionJob();
  const rejectMutation = useRejectPromotionJob();
  const retryMutation = useRetryPromotionJob();
  const updateContentMutation = useUpdatePromotionJobContent();
  const updateSettingMutation = useUpdatePlatformSetting();
  const triggerPromotionMutation = useTriggerEventPromotion();

  // Surface every failed action instead of failing silently.
  const actionErrors = [
    { label: 'Approve / publish', m: approveMutation },
    { label: 'Reject', m: rejectMutation },
    { label: 'Retry', m: retryMutation },
    { label: 'Update platform setting', m: updateSettingMutation },
  ].filter((x) => x.m.isError);

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopyFeedback(label);
    setTimeout(() => setCopyFeedback(null), 2000);
  };

  const handleApprove = (job: PromotionJob, dryRun: boolean) => {
    approveMutation.mutate({ id: job.id, dryRun });
  };

  const handleRetry = (job: PromotionJob) => {
    retryMutation.mutate(job.id);
  };

  const handleReject = (job: PromotionJob) => {
    rejectMutation.mutate(job.id);
  };

  const handleSaveEdit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!editingJob) return;
    updateContentMutation.mutate(
      {
        id: editingJob.id,
        title: editingJob.title || undefined,
        content: editingJob.content,
        destinationRef: editingJob.destinationRef || undefined,
      },
      {
        onSuccess: () => {
          setEditingJob(null);
        },
      }
    );
  };

  const handleManualTrigger = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const id = parseInt(manualEventId, 10);
    if (!id || isNaN(id)) return;
    triggerPromotionMutation.mutate(
      { eventId: id, force: true },
      {
        onSuccess: () => {
          setShowManualModal(false);
          setManualEventId('');
        },
      }
    );
  };

  return (
    <div className="space-y-8 page-enter">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Kicker>Automatic Event Distribution</Kicker>
          <h1 className="text-3xl font-bold tracking-tight">Social Event Promotions</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Multi-platform automated promotion across Instagram, Facebook Pages, LinkedIn, Telegram, and Discord with UTM tracking.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Btn
            onClick={() => { triggerPromotionMutation.reset(); setShowManualModal(true); }}
            className="flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-accent-foreground shadow hover:opacity-90"
          >
            <Sparkles size={14} /> Promote Event
          </Btn>
          <Btn
            onClick={() => {
              stats.refetch();
              settings.refetch();
              jobs.refetch();
            }}
            variant="secondary"
            size="sm"
            className="flex items-center gap-1.5"
          >
            <RefreshCw size={13} className={cx((jobs.isFetching || stats.isFetching) && 'animate-spin')} /> Refresh
          </Btn>
        </div>
      </div>

      {actionErrors.length > 0 && (
        <div className="space-y-2">
          {actionErrors.map(({ label, m }) => (
            <div key={label} className="flex items-start justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/5 px-4 py-3 text-xs text-red-600 dark:text-red-300">
              <span><strong>{label} failed:</strong> {errText(m.error)}</span>
              <button onClick={() => m.reset()} className="shrink-0 text-muted-foreground hover:text-foreground" aria-label="Dismiss error">
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Metrics Banner */}
      {stats.isError && (
        <p className="text-xs text-red-600 dark:text-red-300">Could not load promotion stats: {errText(stats.error)}</p>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div className="rounded-2xl border border-foreground/10 bg-card p-4">
          <p className="font-mono-face text-[10px] uppercase text-muted-foreground">Total Jobs</p>
          <p className="mt-1 text-2xl font-bold">{stats.data?.totalJobs ?? '—'}</p>
        </div>
        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
          <p className="font-mono-face text-[10px] uppercase text-emerald-400">Live Published</p>
          <p className="mt-1 text-2xl font-bold text-emerald-400">{stats.data?.published ?? '—'}</p>
        </div>
        <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/5 p-4">
          <p className="font-mono-face text-[10px] uppercase text-cyan-400">Dry-Run Simulated</p>
          <p className="mt-1 text-2xl font-bold text-cyan-400">{stats.data?.dryRun ?? '—'}</p>
        </div>
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
          <p className="font-mono-face text-[10px] uppercase text-amber-400">Pending Approval</p>
          <p className="mt-1 text-2xl font-bold text-amber-400">{stats.data?.pendingApproval ?? '—'}</p>
        </div>
        <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-4">
          <p className="font-mono-face text-[10px] uppercase text-rose-400">Failed / Retrying</p>
          <p className="mt-1 text-2xl font-bold text-rose-400">{stats.data?.failed ?? '—'}</p>
        </div>
      </div>

      {/* Platform Controls & Channel Settings */}
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Platform Configuration & Health</h2>
        <p className="text-xs text-muted-foreground">Toggle platform enablement, safety dry-run defaults, and auto-publishing rules.</p>
        {settings.isError && (
          <div className="mt-4">
            <ErrorState title="Could not load platform settings." error={settings.error} retry={() => settings.refetch()} />
          </div>
        )}
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {settings.data?.map((setting) => {
            const Icon = PLATFORM_ICONS[setting.platform] || Share2;
            const style = PLATFORM_COLORS[setting.platform] || { bg: 'bg-card', text: 'text-foreground', border: 'border-foreground/10' };
            return (
              <div key={setting.platform} className={cx('rounded-2xl border p-4 transition', style.border, style.bg)}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon size={18} className={style.text} />
                    <span className="font-bold capitalize">{setting.platform}</span>
                  </div>
                  <span
                    className={cx(
                      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold',
                      setting.isConnected ? 'bg-emerald-500/20 text-emerald-400' : 'bg-muted text-muted-foreground'
                    )}
                  >
                    {setting.isConnected ? 'Connected' : 'Dry-Run / Unconfigured'}
                  </span>
                </div>

                <div className="mt-4 space-y-2 text-xs">
                  {/* Enabled Toggle */}
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Enabled:</span>
                    <button
                      onClick={() =>
                        updateSettingMutation.mutate({
                          platform: setting.platform,
                          updates: { enabled: !setting.enabled },
                        })
                      }
                      className="font-semibold text-foreground hover:underline"
                    >
                      {setting.enabled ? (
                        <span className="flex items-center gap-1 text-emerald-400">
                          <ToggleRight size={18} /> Active
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-muted-foreground">
                          <ToggleLeft size={18} /> Paused
                        </span>
                      )}
                    </button>
                  </div>

                  {/* Dry Run Toggle */}
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Mode:</span>
                    <button
                      onClick={() =>
                        updateSettingMutation.mutate({
                          platform: setting.platform,
                          updates: { dryRun: !setting.dryRun },
                        })
                      }
                      className="font-semibold hover:underline"
                    >
                      {setting.dryRun ? (
                        <span className="text-cyan-400">Dry-Run (Safe)</span>
                      ) : (
                        <span className="text-rose-400 font-bold">LIVE API</span>
                      )}
                    </button>
                  </div>

                  {/* Auto Publish vs Approval Toggle */}
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Workflow:</span>
                    <button
                      onClick={() =>
                        updateSettingMutation.mutate({
                          platform: setting.platform,
                          updates: { autoPublish: !setting.autoPublish },
                        })
                      }
                      className="font-semibold text-foreground hover:underline"
                    >
                      {setting.autoPublish ? (
                        <span className="text-purple-400">Auto-Publish</span>
                      ) : (
                        <span className="text-amber-400">Require Approval</span>
                      )}
                    </button>
                  </div>
                </div>

                <p className="mt-3 truncate text-[10px] text-muted-foreground" title={setting.connectionMessage}>
                  {setting.connectionMessage || '—'}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-foreground/10 pb-4">
        {/* Platform Selector */}
        <div className="flex flex-wrap items-center gap-1.5">
          {['all', 'instagram', 'facebook', 'linkedin', 'telegram', 'discord'].map((p) => (
            <button
              key={p}
              onClick={() => setSelectedPlatform(p)}
              className={cx(
                'rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition',
                selectedPlatform === p ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:bg-muted'
              )}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Status Selector */}
        <div className="flex items-center gap-1.5">
          {['all', 'PENDING_APPROVAL', 'PUBLISHED', 'DRY_RUN', 'FAILED'].map((st) => (
            <button
              key={st}
              onClick={() => setSelectedStatus(st)}
              className={cx(
                'rounded-lg px-2.5 py-1 text-xs font-medium transition',
                selectedStatus === st ? 'bg-muted text-accent font-semibold' : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {st === 'all' ? 'All Statuses' : st.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Promotion Jobs Table */}
      <div className="rounded-2xl border border-foreground/10 bg-card overflow-hidden">
        {jobs.isLoading ? (
          <div className="p-12">
            <LoadingState label="Loading promotion jobs..." />
          </div>
        ) : jobs.isError ? (
          <div className="p-12">
            <ErrorState title="Could not load promotion jobs." error={jobs.error} retry={() => jobs.refetch()} />
          </div>
        ) : !jobs.data?.items || jobs.data.items.length === 0 ? (
          <div className="p-12">
            <EmptyState
              title="No promotion jobs found"
              body="When events transition to Published, promotion jobs across Instagram, Facebook, LinkedIn, Telegram, and Discord will automatically queue here."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-foreground/10 bg-muted/40 font-mono-face text-[10px] uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Event</th>
                  <th className="px-4 py-3">Platform</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Copy Preview</th>
                  <th className="px-4 py-3">Tracking & Live Links</th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-foreground/10">
                {jobs.data.items.map((job) => {
                  const Icon = PLATFORM_ICONS[job.platform] || Share2;
                  const style = PLATFORM_COLORS[job.platform] || { bg: '', text: 'text-foreground', border: '' };

                  return (
                    <tr key={job.id} className="hover:bg-muted/30 transition">
                      {/* Event Column */}
                      <td className="px-4 py-3.5 max-w-xs">
                        <div className="font-semibold text-foreground truncate" title={job.event?.title || `Event #${job.eventId}`}>
                          {job.event?.title || `Event #${job.eventId}`}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          {[job.event?.city, job.event?.category].filter(Boolean).join(' • ') || '—'}
                        </div>
                      </td>

                      {/* Platform Column */}
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        <span className={cx('inline-flex items-center gap-1.5 rounded-md px-2 py-1 font-semibold capitalize', style.text, style.bg)}>
                          <Icon size={14} />
                          {job.platform}
                        </span>
                      </td>

                      {/* Status Column */}
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        {job.status === 'PUBLISHED' && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                            <CheckCircle2 size={12} /> Live Published
                          </span>
                        )}
                        {job.status === 'DRY_RUN' && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold text-cyan-400">
                            <Play size={12} /> Dry-Run Sim
                          </span>
                        )}
                        {job.status === 'PENDING_APPROVAL' && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                            <Clock size={12} /> Pending Approval
                          </span>
                        )}
                        {job.status === 'FAILED' && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2 py-0.5 text-[10px] font-semibold text-rose-400" title={job.lastError || 'Error'}>
                            <AlertCircle size={12} /> Failed ({job.retryCount}/{job.maxRetries})
                          </span>
                        )}
                        {job.status === 'CANCELLED' && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                            <XCircle size={12} /> Cancelled
                          </span>
                        )}
                      </td>

                      {/* Copy Preview */}
                      <td className="px-4 py-3.5 max-w-sm">
                        <div
                          onClick={() => setActiveJob(job)}
                          className="cursor-pointer line-clamp-2 text-muted-foreground hover:text-foreground hover:underline transition"
                          title="Click to view full promotional text"
                        >
                          {job.content}
                        </div>
                      </td>

                      {/* Links */}
                      <td className="px-4 py-3.5 space-y-1">
                        {job.trackingUrl && (
                          <button
                            onClick={() => handleCopy(job.trackingUrl!, `utm_${job.id}`)}
                            className="flex items-center gap-1 text-[11px] text-accent hover:underline"
                          >
                            <Copy size={11} /> {copyFeedback === `utm_${job.id}` ? 'Copied UTM Link!' : 'Copy UTM Link'}
                          </button>
                        )}
                        {job.publishedUrl && (
                          <a
                            href={job.publishedUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                          >
                            <ExternalLink size={11} /> View Post
                          </a>
                        )}
                      </td>

                      {/* Date */}
                      <td className="px-4 py-3.5 whitespace-nowrap text-[11px] text-muted-foreground">
                        {fmtDateTime(job.createdAt)}
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3.5 text-right whitespace-nowrap space-x-1.5">
                        {job.status === 'PENDING_APPROVAL' && (
                          <>
                            <button
                              onClick={() => handleApprove(job, false)}
                              disabled={approveMutation.isPending}
                              className="rounded-lg bg-emerald-500/20 px-2.5 py-1 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/30 transition"
                            >
                              Publish Live
                            </button>
                            <button
                              onClick={() => handleApprove(job, true)}
                              disabled={approveMutation.isPending}
                              className="rounded-lg bg-cyan-500/20 px-2.5 py-1 text-xs font-semibold text-cyan-400 hover:bg-cyan-500/30 transition"
                            >
                              Dry-Run
                            </button>
                            <button
                              onClick={() => { updateContentMutation.reset(); setEditingJob(job); }}
                              className="rounded-lg bg-muted px-2.5 py-1 text-xs font-semibold text-foreground hover:bg-muted/80 transition"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleReject(job)}
                              disabled={rejectMutation.isPending}
                              className="rounded-lg bg-rose-500/10 px-2 py-1 text-xs font-semibold text-rose-400 hover:bg-rose-500/20 transition"
                            >
                              Reject
                            </button>
                          </>
                        )}

                        {job.status === 'FAILED' && (
                          <button
                            onClick={() => handleRetry(job)}
                            disabled={retryMutation.isPending || job.retryCount >= job.maxRetries}
                            className="rounded-lg bg-amber-500/20 px-2.5 py-1 text-xs font-semibold text-amber-400 hover:bg-amber-500/30 transition disabled:opacity-50"
                          >
                            Retry Post
                          </button>
                        )}

                        <button
                          onClick={() => setActiveJob(job)}
                          className="rounded-lg border border-foreground/10 px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                        >
                          Details
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Drawer */}
      <Drawer
        open={Boolean(activeJob)}
        title={`Promotion Job #${activeJob?.id} Details`}
        onClose={() => setActiveJob(null)}
      >
        {activeJob && (
          <div className="space-y-6 text-sm">
            <div>
              <Kicker>{activeJob.platform.toUpperCase()} PROMOTION</Kicker>
              <h3 className="mt-1 text-xl font-bold">{activeJob.title || activeJob.event?.title || `Event #${activeJob.eventId}`}</h3>
              <p className="text-xs text-muted-foreground mt-0.5">Status: <span className="font-semibold text-foreground">{activeJob.status}</span> &bull; Mode: <span className="font-semibold text-foreground">{activeJob.isDryRun ? 'Dry-Run Simulation' : 'Live API'}</span></p>
            </div>

            {/* Generated Content Box */}
            <div className="rounded-xl border border-foreground/10 bg-muted/40 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono-face text-[10px] uppercase text-muted-foreground">Generated Post Copy</span>
                <button
                  onClick={() => handleCopy(activeJob.content, 'drawer_copy')}
                  className="flex items-center gap-1 text-xs text-accent hover:underline"
                >
                  <Copy size={12} /> {copyFeedback === 'drawer_copy' ? 'Copied!' : 'Copy Copy'}
                </button>
              </div>
              <pre className="whitespace-pre-wrap font-sans text-xs text-foreground/90 leading-relaxed">
                {activeJob.content}
              </pre>
            </div>

            {/* UTM Parameters */}
            <div className="rounded-xl border border-foreground/10 bg-card p-4 space-y-2">
              <span className="font-mono-face text-[10px] uppercase text-muted-foreground">Attribution & Tracking</span>
              <div className="text-xs space-y-1">
                <div><span className="text-muted-foreground">Destination Tracking URL:</span> <span className="font-mono text-accent break-all">{activeJob.trackingUrl}</span></div>
                {activeJob.externalPostId && <div><span className="text-muted-foreground">External Post ID:</span> <span className="font-mono text-foreground">{activeJob.externalPostId}</span></div>}
                {activeJob.publishedUrl && <div><span className="text-muted-foreground">Published Link:</span> <a href={activeJob.publishedUrl} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline break-all">{activeJob.publishedUrl}</a></div>}
                {activeJob.lastError && (
                  <div className="mt-2 rounded-lg bg-rose-500/10 p-2 text-rose-400 text-xs">
                    <strong>Error:</strong> {activeJob.lastError}
                  </div>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 pt-4 border-t border-foreground/10">
              {activeJob.status === 'PENDING_APPROVAL' && (
                <>
                  <Btn
                    onClick={() => {
                      handleApprove(activeJob, false);
                      setActiveJob(null);
                    }}
                    className="flex-1 bg-emerald-500 text-black font-semibold"
                  >
                    Approve & Publish Live
                  </Btn>
                  <Btn
                    onClick={() => {
                      handleApprove(activeJob, true);
                      setActiveJob(null);
                    }}
                    className="flex-1 bg-cyan-500 text-black font-semibold"
                  >
                    Simulate (Dry-Run)
                  </Btn>
                </>
              )}
              {activeJob.status === 'FAILED' && (
                <Btn
                  onClick={() => {
                    handleRetry(activeJob);
                    setActiveJob(null);
                  }}
                  className="flex-1 bg-amber-500 text-black font-semibold"
                >
                  Retry Job
                </Btn>
              )}
            </div>
          </div>
        )}
      </Drawer>

      {/* Edit Content Modal */}
      <Drawer
        open={Boolean(editingJob)}
        title={`Edit Copy — #${editingJob?.id} (${editingJob?.platform})`}
        onClose={() => setEditingJob(null)}
      >
        {editingJob && (
          <form onSubmit={handleSaveEdit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">Headline / Subject</label>
              <input
                type="text"
                value={editingJob.title || ''}
                onChange={(e) => setEditingJob({ ...editingJob, title: e.target.value })}
                className="w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs text-foreground focus:border-accent focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">Destination ID / Ref (e.g. Page ID, Channel ID)</label>
              <input
                type="text"
                value={editingJob.destinationRef || ''}
                onChange={(e) => setEditingJob({ ...editingJob, destinationRef: e.target.value })}
                className="w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs text-foreground focus:border-accent focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-foreground mb-1">Post Text / Caption</label>
              <textarea
                rows={10}
                value={editingJob.content}
                onChange={(e) => setEditingJob({ ...editingJob, content: e.target.value })}
                className="w-full rounded-xl border border-foreground/15 bg-background p-3 text-xs text-foreground focus:border-accent focus:outline-none"
                required
              />
            </div>

            {updateContentMutation.isError && (
              <p className="rounded-lg bg-red-500/10 p-2 text-xs text-red-600 dark:text-red-300">
                Could not save changes: {errText(updateContentMutation.error)}
              </p>
            )}

            <div className="flex items-center gap-2 pt-2">
              <Btn type="submit" disabled={updateContentMutation.isPending} className="flex-1 bg-primary text-primary-foreground font-semibold">
                {updateContentMutation.isPending ? 'Saving…' : 'Save Changes'}
              </Btn>
              <Btn type="button" variant="secondary" onClick={() => setEditingJob(null)}>
                Cancel
              </Btn>
            </div>
          </form>
        )}
      </Drawer>

      {/* Manual Promotion Trigger Modal */}
      <Drawer
        open={showManualModal}
        title="Promote Event Across Social Platforms"
        onClose={() => setShowManualModal(false)}
      >
        <form onSubmit={handleManualTrigger} className="space-y-4 text-xs">
          <p className="text-muted-foreground">
            Enter the numeric ID of any published event to generate tailored promotions across Instagram, Facebook Pages, LinkedIn, Telegram, and Discord.
          </p>

          <div>
            <label className="block font-semibold text-foreground mb-1">Event ID (e.g. 1, 2, 5)</label>
            <input
              type="number"
              value={manualEventId}
              onChange={(e) => setManualEventId(e.target.value)}
              placeholder="Enter event ID"
              className="w-full rounded-xl border border-foreground/15 bg-background px-3 py-2 text-xs text-foreground focus:border-accent focus:outline-none"
              required
              min={1}
            />
          </div>

          <div className="rounded-xl border border-foreground/10 bg-muted/40 p-3 space-y-1 text-muted-foreground">
            <p className="font-semibold text-foreground">What happens next:</p>
            <ul className="list-disc list-inside space-y-0.5">
              <li>Platform-tailored copy will be generated for each enabled platform.</li>
              <li>Tracking links will be created with UTM attribution parameters.</li>
              <li>Jobs will land in <span className="font-semibold text-foreground">Pending Approval</span> (or auto-publish if enabled).</li>
            </ul>
          </div>

          {triggerPromotionMutation.isError && (
            <p className="rounded-lg bg-red-500/10 p-2 text-xs text-red-600 dark:text-red-300">
              Could not generate promotions: {errText(triggerPromotionMutation.error)}
            </p>
          )}

          <div className="flex items-center gap-2 pt-2">
            <Btn
              type="submit"
              disabled={triggerPromotionMutation.isPending || !manualEventId}
              className="flex-1 bg-accent text-accent-foreground font-semibold"
            >
              {triggerPromotionMutation.isPending ? 'Generating...' : 'Generate Promotions'}
            </Btn>
            <Btn type="button" variant="secondary" onClick={() => setShowManualModal(false)}>
              Cancel
            </Btn>
          </div>
        </form>
      </Drawer>
    </div>
  );
}
