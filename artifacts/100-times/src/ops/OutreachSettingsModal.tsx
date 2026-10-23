import { useEffect, useState } from 'react';
import { Check, Layers, Mail, Settings, Sliders } from 'lucide-react';
import { useCategories, useOutreachAutoStatus, useSetOutreachAuto } from './api';
import { Btn, Drawer, ErrorState, Notice, inputClass } from './ui';

export function OutreachSettingsDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const auto = useOutreachAutoStatus();
  const setAuto = useSetOutreachAuto();
  const categoriesQuery = useCategories();

  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [maxCandidates, setMaxCandidates] = useState('20');
  const [dailyLimit, setDailyLimit] = useState('100');
  const [followupWaitDays, setFollowupWaitDays] = useState('2');
  const [maxFollowupAttempts, setMaxFollowupAttempts] = useState('3');
  const [senderName, setSenderName] = useState('100 TIMES Partnerships');
  const [templateStyle, setTemplateStyle] = useState('invitational');
  const [draftInterval, setDraftInterval] = useState('60');
  const [followupInterval, setFollowupInterval] = useState('1440');
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Sync state from server on open or query success
  useEffect(() => {
    if (auto.data) {
      setSelectedCategories(auto.data.categories || []);
      setMaxCandidates(String(auto.data.maxCandidates || 20));
      setDailyLimit(String(auto.data.dailyLimit || 100));
      setFollowupWaitDays(String(auto.data.followupWaitDays || 2));
      setMaxFollowupAttempts(String(auto.data.maxFollowupAttempts || 3));
      setSenderName(auto.data.senderName || '100 TIMES Partnerships');
      setTemplateStyle(auto.data.templateStyle || 'invitational');
      setDraftInterval(String(auto.data.draftIntervalMinutes || 60));
      setFollowupInterval(String(auto.data.followupIntervalMinutes || 1440));
    }
  }, [auto.data, open]);

  const allAvailableCategories = categoriesQuery.data?.map((c) => c.name) || [
    'Construction', 'Energy and Power Generation', 'Finance', 'Healthcare',
    'Manufacturing', 'Mining', 'Oil and Gas', 'Packaging', 'Pharmaceuticals',
    'Telecommunications', 'Textiles', 'Transport and Logistics'
  ];

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );
  };

  const selectAllCategories = () => setSelectedCategories([...allAvailableCategories]);
  const clearCategories = () => setSelectedCategories([]);

  const handleSave = () => {
    setSaveSuccess(false);
    setAuto.mutate(
      {
        categories: selectedCategories.length ? selectedCategories : allAvailableCategories,
        maxCandidates: Number(maxCandidates) || 20,
        dailyLimit: Number(dailyLimit) || 100,
        followupWaitDays: Number(followupWaitDays) || 2,
        maxFollowupAttempts: Number(maxFollowupAttempts) || 3,
        senderName: senderName.trim() || '100 TIMES Partnerships',
        templateStyle: templateStyle || 'invitational',
        draftIntervalMinutes: Number(draftInterval) || 60,
        followupIntervalMinutes: Number(followupInterval) || 1440,
      },
      {
        onSuccess: () => {
          setSaveSuccess(true);
          setTimeout(() => setSaveSuccess(false), 3000);
        },
      }
    );
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      kicker="Organizer Outreach · Agent 2 Settings"
      title="Automatic Outreach Settings"
      width="max-w-2xl"
    >
      <p className="mb-4 text-xs text-muted-foreground">
        Configure targeted sectors, batch drafting sizes, daily limits, and follow-up cadence for Agent 2. Drafts are automatically generated per schedule and held in <strong>Pending Approval</strong> until confirmed by an admin.
      </p>

      <div className="grid gap-5 text-xs">
        {/* Sectors / Categories Targeting */}
        <div className="rounded-xl border border-foreground/15 bg-card p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="font-semibold text-foreground flex items-center gap-1.5">
              <Layers size={14} className="text-accent" /> Targeted Sectors ({selectedCategories.length === 0 ? 'All Sectors' : `${selectedCategories.length} selected`})
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={selectAllCategories}
                disabled={setAuto.isPending}
                className="text-[11px] font-medium text-accent hover:underline disabled:opacity-50"
              >
                Select all
              </button>
              <span className="text-muted-foreground/40 text-[10px]">·</span>
              <button
                type="button"
                onClick={clearCategories}
                disabled={setAuto.isPending}
                className="text-[11px] font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
              >
                Clear
              </button>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground mb-3">
            Agent 2 prioritizes drafting outreach to organizers who host events in these chosen sectors.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {allAvailableCategories.map((cat) => {
              const active = selectedCategories.includes(cat);
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => toggleCategory(cat)}
                  disabled={setAuto.isPending}
                  className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] border transition-colors ${
                    active
                      ? 'border-accent bg-accent/10 font-medium text-accent'
                      : 'border-foreground/15 bg-background text-muted-foreground hover:border-foreground/30 hover:text-foreground'
                  }`}
                >
                  {active && <Check size={11} />}
                  <span>{cat}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Batch & Cadence Settings */}
        <div className="grid grid-cols-2 gap-3 rounded-xl border border-foreground/15 bg-card p-4">
          <div className="col-span-2 font-semibold text-foreground flex items-center gap-1.5 mb-1">
            <Sliders size={14} className="text-accent" /> Batch & Cadence Limits
          </div>

          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">Drafts per run (Batch Size)</span>
            <input
              type="number"
              min={1}
              max={100}
              value={maxCandidates}
              onChange={(e) => setMaxCandidates(e.target.value)}
              disabled={setAuto.isPending}
              className={inputClass}
            />
          </label>

          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">Daily drafting cap</span>
            <input
              type="number"
              min={1}
              max={500}
              value={dailyLimit}
              onChange={(e) => setDailyLimit(e.target.value)}
              disabled={setAuto.isPending}
              className={inputClass}
            />
          </label>

          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">Follow-up wait period (Days)</span>
            <input
              type="number"
              min={1}
              max={14}
              value={followupWaitDays}
              onChange={(e) => setFollowupWaitDays(e.target.value)}
              disabled={setAuto.isPending}
              className={inputClass}
            />
          </label>

          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">Max follow-up attempts</span>
            <input
              type="number"
              min={1}
              max={5}
              value={maxFollowupAttempts}
              onChange={(e) => setMaxFollowupAttempts(e.target.value)}
              disabled={setAuto.isPending}
              className={inputClass}
            />
          </label>
        </div>

        {/* Sender & Style Customization */}
        <div className="grid grid-cols-2 gap-3 rounded-xl border border-foreground/15 bg-card p-4">
          <div className="col-span-2 font-semibold text-foreground flex items-center gap-1.5 mb-1">
            <Mail size={14} className="text-accent" /> Email Sender & Template Styling
          </div>

          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">Sender Signature Name</span>
            <input
              type="text"
              value={senderName}
              placeholder="e.g. 100 TIMES Partnerships"
              onChange={(e) => setSenderName(e.target.value)}
              disabled={setAuto.isPending}
              className={inputClass}
            />
          </label>

          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">Email Template Style</span>
            <select
              value={templateStyle}
              onChange={(e) => setTemplateStyle(e.target.value)}
              disabled={setAuto.isPending}
              className={inputClass}
            >
              <option value="invitational">Invitational & Welcoming</option>
              <option value="direct">Direct & Concise</option>
              <option value="partnership">Strategic Partnership</option>
              <option value="curator">Curator & Speaker Focus</option>
            </select>
          </label>

          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">Draft Interval (Minutes)</span>
            <input
              type="number"
              min={10}
              max={1440}
              value={draftInterval}
              onChange={(e) => setDraftInterval(e.target.value)}
              disabled={setAuto.isPending}
              className={inputClass}
            />
          </label>

          <label className="flex flex-col gap-1 text-[11px]">
            <span className="text-muted-foreground">Follow-up Sweep Interval (Minutes)</span>
            <input
              type="number"
              min={60}
              max={4320}
              value={followupInterval}
              onChange={(e) => setFollowupInterval(e.target.value)}
              disabled={setAuto.isPending}
              className={inputClass}
            />
          </label>
        </div>

        {saveSuccess && (
          <Notice tone="good">
            Settings saved successfully! Agent 2 will use these target criteria when generating drafts.
          </Notice>
        )}

        {setAuto.isError && (
          <ErrorState
            error={setAuto.error}
            title="Failed to save automatic outreach settings"
          />
        )}

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-foreground/10">
          <Btn variant="ghost" onClick={onClose} disabled={setAuto.isPending}>
            Close
          </Btn>
          <Btn
            variant="primary"
            loading={setAuto.isPending}
            onClick={handleSave}
          >
            <Sliders size={13} /> Save Settings
          </Btn>
        </div>
      </div>
    </Drawer>
  );
}

export function OutreachSettingsButton({ size = 'sm' }: { size?: 'sm' | 'md' }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Btn
        variant="ghost"
        size={size}
        onClick={() => setOpen(true)}
        className="flex items-center gap-1 text-[11px]"
      >
        <Settings size={12} /> Settings
      </Btn>
      <OutreachSettingsDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}

