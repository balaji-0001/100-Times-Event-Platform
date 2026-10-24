import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Building2,
  CalendarX,
  Check,
  FilterX,
  Globe,
  Layers,
  MapPin,
  Mail,
  Phone,
  Settings,
  Shield,
  ShieldAlert,
  Sliders,
  Tag,
} from 'lucide-react';
import { useCategories, useDiscoveryAutoStatus, useSetDiscoveryAuto } from './api';
import { GeoChecklistSelector } from './GeoChecklistSelector';
import { Btn, Drawer, ErrorState, Notice, inputClass } from './ui';

function ToggleSwitch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
        checked ? 'bg-accent' : 'bg-foreground/20'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

function FilterRuleRow({
  icon: Icon,
  title,
  description,
  checked,
  onChange,
  badge,
  disabled,
}: {
  icon: any;
  title: string;
  description: string;
  checked: boolean;
  onChange: (val: boolean) => void;
  badge?: string;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3 p-3 rounded-lg border border-foreground/10 bg-card/60 hover:bg-card/90 transition-colors">
      <div className="flex items-start gap-2.5">
        <div className="p-1.5 rounded-md bg-accent/10 text-accent mt-0.5 shrink-0">
          <Icon size={14} />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground text-xs">{title}</span>
            {badge && (
              <span className="px-1.5 py-0.2 text-[9px] font-medium tracking-wide uppercase rounded bg-foreground/10 text-muted-foreground">
                {badge}
              </span>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{description}</p>
        </div>
      </div>
      <div className="pt-0.5 shrink-0">
        <ToggleSwitch checked={checked} onChange={onChange} disabled={disabled} />
      </div>
    </div>
  );
}

export function DiscoverySettingsDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const auto = useDiscoveryAutoStatus();
  const setAuto = useSetDiscoveryAuto();
  const categoriesQuery = useCategories();

  const [activeTab, setActiveTab] = useState<'scope' | 'rejection'>('scope');

  // Geographic and sector scope state
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [depth, setDepth] = useState('20');
  const [dailyLimit, setDailyLimit] = useState('200');

  // Rejection rules state
  const [rejectNoOrganizer, setRejectNoOrganizer] = useState(true);
  const [requireOrganizerEmail, setRequireOrganizerEmail] = useState(true);
  const [requireOrganizerPhone, setRequireOrganizerPhone] = useState(false);
  const [requireOrganizerWebsite, setRequireOrganizerWebsite] = useState(false);
  const [rejectPastEvents, setRejectPastEvents] = useState(true);
  const [rejectUnparseableDates, setRejectUnparseableDates] = useState(true);
  const [rejectMissingLocation, setRejectMissingLocation] = useState(false);
  const [rejectMissingTicketUrl, setRejectMissingTicketUrl] = useState(false);
  const [rejectUnmatchedCategory, setRejectUnmatchedCategory] = useState(true);
  const [minTitleLength, setMinTitleLength] = useState('8');
  const [minDescriptionLength, setMinDescriptionLength] = useState('20');
  const [minConfidenceScore, setMinConfidenceScore] = useState('50');
  const [blacklistedKeywords, setBlacklistedKeywords] = useState('');
  const [excludedDomains, setExcludedDomains] = useState('');

  const [saveSuccess, setSaveSuccess] = useState(false);

  // Sync state from server on open or query success
  useEffect(() => {
    if (auto.data) {
      const serverCountries =
        auto.data.countries && auto.data.countries.length > 0
          ? auto.data.countries
          : auto.data.country
          ? [auto.data.country]
          : [];
      setSelectedCountries(serverCountries);
      setSelectedStates(auto.data.states || []);
      setSelectedCities(auto.data.cities || []);
      setSelectedCategories(auto.data.categories || []);
      setDepth(auto.data.searchDepth ? String(auto.data.searchDepth) : '20');
      setDailyLimit(auto.data.dailyLimit ? String(auto.data.dailyLimit) : '200');

      // Sync rejection rules
      setRejectNoOrganizer(auto.data.rejectNoOrganizer ?? true);
      setRequireOrganizerEmail(auto.data.requireOrganizerEmail ?? true);
      setRequireOrganizerPhone(auto.data.requireOrganizerPhone ?? false);
      setRequireOrganizerWebsite(auto.data.requireOrganizerWebsite ?? false);
      setRejectPastEvents(auto.data.rejectPastEvents ?? true);
      setRejectUnparseableDates(auto.data.rejectUnparseableDates ?? true);
      setRejectMissingLocation(auto.data.rejectMissingLocation ?? false);
      setRejectMissingTicketUrl(auto.data.rejectMissingTicketUrl ?? false);
      setRejectUnmatchedCategory(auto.data.rejectUnmatchedCategory ?? true);
      setMinTitleLength(String(auto.data.minTitleLength ?? 8));
      setMinDescriptionLength(String(auto.data.minDescriptionLength ?? 20));
      setMinConfidenceScore(String(auto.data.minConfidenceScore ?? 50));
      setBlacklistedKeywords((auto.data.blacklistedKeywords || []).join(', '));
      setExcludedDomains((auto.data.excludedDomains || []).join(', '));
    }
  }, [auto.data, open]);

  const allAvailableCategories = categoriesQuery.data?.map((c) => c.name) || [
    'Construction',
    'Energy and Power Generation',
    'Finance',
    'Healthcare',
    'Manufacturing',
    'Mining',
    'Oil and Gas',
    'Packaging',
    'Pharmaceuticals',
    'Telecommunications',
    'Textiles',
    'Transport and Logistics',
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

    const parsedKeywords = blacklistedKeywords
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean);

    const parsedDomains = excludedDomains
      .split(',')
      .map((d) => d.trim().replace(/^https?:\/\//i, '').replace(/\/.*$/, ''))
      .filter(Boolean);

    setAuto.mutate(
      {
        country: selectedCountries.length ? selectedCountries[0] : null,
        countries: selectedCountries,
        states: selectedStates,
        cities: selectedCities,
        categories: selectedCategories.length ? selectedCategories : allAvailableCategories,
        searchDepth: Number(depth) || 20,
        dailyLimit: Number(dailyLimit) || 200,
        // Rejection settings
        rejectNoOrganizer,
        requireOrganizerEmail,
        requireOrganizerPhone,
        requireOrganizerWebsite,
        rejectPastEvents,
        rejectUnparseableDates,
        rejectMissingLocation,
        rejectMissingTicketUrl,
        rejectUnmatchedCategory,
        minTitleLength: Number(minTitleLength) || 0,
        minDescriptionLength: Number(minDescriptionLength) || 0,
        minConfidenceScore: Number(minConfidenceScore) || 0,
        blacklistedKeywords: parsedKeywords,
        excludedDomains: parsedDomains,
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
      kicker="Organizer Discovery · Automation Settings"
      title="Discovery Agent Configuration"
      width="max-w-3xl"
    >
      <div className="flex items-center gap-2 border-b border-foreground/10 pb-3 mb-4">
        <button
          type="button"
          onClick={() => setActiveTab('scope')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            activeTab === 'scope'
              ? 'bg-accent text-accent-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-foreground/5 hover:text-foreground'
          }`}
        >
          <Globe size={13} /> Scope & Geographic Targets
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('rejection')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
            activeTab === 'rejection'
              ? 'bg-accent text-accent-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-foreground/5 hover:text-foreground'
          }`}
        >
          <ShieldAlert size={13} /> Event Rejection & Quality Rules
        </button>
      </div>

      {activeTab === 'scope' && (
        <div className="grid gap-4 text-xs">
          <p className="text-xs text-muted-foreground">
            Configure the geographic checklists (countries, states, cities) and sectors used by the background discovery loop before turning on Automatic Discovery.
          </p>

          <GeoChecklistSelector
            selectedCountries={selectedCountries}
            onCountriesChange={setSelectedCountries}
            selectedStates={selectedStates}
            onStatesChange={setSelectedStates}
            selectedCities={selectedCities}
            onCitiesChange={setSelectedCities}
            disabled={setAuto.isPending}
          />

          <div>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <Layers size={13} className="text-accent" /> Target Sectors
              </span>
              <div className="flex gap-2 text-[10px]">
                <button
                  type="button"
                  onClick={selectAllCategories}
                  className="text-accent hover:underline"
                >
                  Select all
                </button>
                <span>•</span>
                <button
                  type="button"
                  onClick={clearCategories}
                  className="text-muted-foreground hover:underline"
                >
                  Clear
                </button>
              </div>
            </div>
            <span className="block text-[11px] text-muted-foreground mt-0.5 mb-2">
              Click to toggle which 100 TIMES sectors are discovered
            </span>
            <div className="flex flex-wrap gap-1.5">
              {allAvailableCategories.map((cat) => {
                const active = selectedCategories.includes(cat);
                return (
                  <button
                    type="button"
                    key={cat}
                    onClick={() => toggleCategory(cat)}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium border transition-colors ${
                      active
                        ? 'border-accent bg-accent/15 text-accent font-semibold'
                        : 'border-foreground/15 bg-card text-muted-foreground hover:border-foreground/30'
                    }`}
                  >
                    {active && <Check size={11} />}
                    {cat}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label>
              <span className="font-semibold text-foreground">Search queries per cycle</span>
              <input
                type="number"
                min={1}
                max={200}
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
                className={`${inputClass} mt-1`}
                disabled={setAuto.isPending}
              />
            </label>
            <label>
              <span className="font-semibold text-foreground">Daily event limit</span>
              <input
                type="number"
                min={1}
                max={2000}
                value={dailyLimit}
                onChange={(e) => setDailyLimit(e.target.value)}
                className={`${inputClass} mt-1`}
                disabled={setAuto.isPending}
              />
            </label>
          </div>
        </div>
      )}

      {activeTab === 'rejection' && (
        <div className="grid gap-4 text-xs">
          <div className="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 text-amber-600 dark:text-amber-400">
            <div className="flex items-center gap-1.5 font-semibold text-xs mb-1">
              <Shield size={13} /> Automated Quality & Rejection Gate
            </div>
            <p className="text-[11px] leading-relaxed">
              Discovered events that violate any enabled rejection criteria will be automatically rejected by the Discovery Agent and recorded in audit logs with a clear reason.
            </p>
          </div>

          {/* Organizer Criteria */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <Building2 size={13} className="text-accent" /> Organizer Requirements
            </h4>
            <div className="grid gap-2">
              <FilterRuleRow
                icon={Building2}
                title="Reject Events with No Organizer"
                description="Immediately rejects candidate pages where no verified organizer or company was identified."
                checked={rejectNoOrganizer}
                onChange={setRejectNoOrganizer}
                badge="Recommended"
                disabled={setAuto.isPending}
              />
              <FilterRuleRow
                icon={Mail}
                title="Require Verified Public Organizer Email"
                description="Rejects events if no valid organizer email could be located and deliverability-verified on public pages."
                checked={requireOrganizerEmail}
                onChange={setRequireOrganizerEmail}
                badge="Mandatory"
                disabled={setAuto.isPending}
              />
              <FilterRuleRow
                icon={Phone}
                title="Require Organizer Phone Number"
                description="Rejects events that do not contain an official phone number on the organizer profile."
                checked={requireOrganizerPhone}
                onChange={setRequireOrganizerPhone}
                disabled={setAuto.isPending}
              />
              <FilterRuleRow
                icon={Globe}
                title="Require Official Organizer Website"
                description="Rejects events where the organizer lacks an official web domain or homepage link."
                checked={requireOrganizerWebsite}
                onChange={setRequireOrganizerWebsite}
                disabled={setAuto.isPending}
              />
            </div>
          </div>

          {/* Dates & Schedule */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <CalendarX size={13} className="text-accent" /> Date & Schedule Validation
            </h4>
            <div className="grid gap-2">
              <FilterRuleRow
                icon={CalendarX}
                title="Reject Past or Expired Events"
                description="Rejects events whose event date has already passed prior to the current discovery scan."
                checked={rejectPastEvents}
                onChange={setRejectPastEvents}
                badge="Active"
                disabled={setAuto.isPending}
              />
              <FilterRuleRow
                icon={AlertTriangle}
                title="Reject Ambiguous / Unparseable Dates"
                description="Rejects events where the date could not be parsed into a definitive calendar date (e.g. 'Coming soon', 'Late 2026')."
                checked={rejectUnparseableDates}
                onChange={setRejectUnparseableDates}
                badge="Recommended"
                disabled={setAuto.isPending}
              />
            </div>
          </div>

          {/* Location & Ticket Links */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <MapPin size={13} className="text-accent" /> Location & Ticket Links
            </h4>
            <div className="grid gap-2">
              <FilterRuleRow
                icon={MapPin}
                title="Reject Missing Location (Offline/Hybrid)"
                description="Rejects in-person or hybrid events that lack both venue name and city information."
                checked={rejectMissingLocation}
                onChange={setRejectMissingLocation}
                disabled={setAuto.isPending}
              />
              <FilterRuleRow
                icon={Tag}
                title="Require Ticket or Registration URL"
                description="Rejects events that do not have a working ticket, booking, or registration URL."
                checked={rejectMissingTicketUrl}
                onChange={setRejectMissingTicketUrl}
                disabled={setAuto.isPending}
              />
              <FilterRuleRow
                icon={FilterX}
                title="Reject Unmatched Categories / Sectors"
                description="Rejects events whose sector does not match the 100 TIMES supported categories or is marked 'Other'."
                checked={rejectUnmatchedCategory}
                onChange={setRejectUnmatchedCategory}
                badge="Active"
                disabled={setAuto.isPending}
              />
            </div>
          </div>

          {/* Thresholds */}
          <div className="grid grid-cols-3 gap-2">
            <label>
              <span className="font-semibold text-foreground text-[11px]">Min Title Length</span>
              <input
                type="number"
                min={0}
                max={50}
                value={minTitleLength}
                onChange={(e) => setMinTitleLength(e.target.value)}
                className={`${inputClass} mt-1`}
                placeholder="8 chars"
                disabled={setAuto.isPending}
              />
              <span className="text-[10px] text-muted-foreground mt-0.5 block">Shortest allowed title</span>
            </label>
            <label>
              <span className="font-semibold text-foreground text-[11px]">Min Description Length</span>
              <input
                type="number"
                min={0}
                max={200}
                value={minDescriptionLength}
                onChange={(e) => setMinDescriptionLength(e.target.value)}
                className={`${inputClass} mt-1`}
                placeholder="20 chars"
                disabled={setAuto.isPending}
              />
              <span className="text-[10px] text-muted-foreground mt-0.5 block">Rejects empty stubs</span>
            </label>
            <label>
              <span className="font-semibold text-foreground text-[11px]">Min AI Confidence (0-100)</span>
              <input
                type="number"
                min={0}
                max={100}
                value={minConfidenceScore}
                onChange={(e) => setMinConfidenceScore(e.target.value)}
                className={`${inputClass} mt-1`}
                placeholder="50"
                disabled={setAuto.isPending}
              />
              <span className="text-[10px] text-muted-foreground mt-0.5 block">Rejects low-score extractions</span>
            </label>
          </div>

          {/* Blocklists */}
          <div>
            <h4 className="text-xs font-semibold text-foreground mb-2 flex items-center gap-1.5">
              <FilterX size={13} className="text-accent" /> Spam & Domain Blocklists
            </h4>
            <div className="grid gap-2">
              <label>
                <span className="font-semibold text-foreground text-[11px]">Blacklisted Spam Keywords</span>
                <textarea
                  rows={2}
                  value={blacklistedKeywords}
                  onChange={(e) => setBlacklistedKeywords(e.target.value)}
                  className={`${inputClass} mt-1`}
                  placeholder="e.g. airdrop, crypto giveaway, casino, betting, get rich quick, mlm"
                  disabled={setAuto.isPending}
                />
                <span className="text-[10px] text-muted-foreground mt-0.5 block">
                  Comma-separated keywords. Any event matching these in title or description will be rejected.
                </span>
              </label>

              <label>
                <span className="font-semibold text-foreground text-[11px]">Excluded Domains</span>
                <textarea
                  rows={2}
                  value={excludedDomains}
                  onChange={(e) => setExcludedDomains(e.target.value)}
                  className={`${inputClass} mt-1`}
                  placeholder="e.g. spam-listings.com, scam-events.org, bit.ly"
                  disabled={setAuto.isPending}
                />
                <span className="text-[10px] text-muted-foreground mt-0.5 block">
                  Comma-separated domains to block from being extracted as source or ticket links.
                </span>
              </label>
            </div>
          </div>
        </div>
      )}

      {saveSuccess && (
        <div className="mt-4">
          <Notice tone="info">
            Discovery settings and rejection rules saved successfully! They are now active in the automated agent loop.
          </Notice>
        </div>
      )}

      {setAuto.isError && (
        <div className="mt-4">
          <ErrorState
            error={setAuto.error}
            title="Failed to save discovery settings"
          />
        </div>
      )}

      <div className="flex items-center justify-end gap-2 pt-3 mt-4 border-t border-foreground/10">
        <Btn variant="ghost" onClick={onClose} disabled={setAuto.isPending}>
          Close
        </Btn>
        <Btn
          variant="primary"
          loading={setAuto.isPending}
          onClick={handleSave}
        >
          <Sliders size={13} /> Save All Settings
        </Btn>
      </div>
    </Drawer>
  );
}

export function DiscoverySettingsButton({ size = 'sm' }: { size?: 'sm' | 'md' }) {
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
      <DiscoverySettingsDrawer open={open} onClose={() => setOpen(false)} />
    </>
  );
}
