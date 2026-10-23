import { useEffect, useState } from 'react';
import { Check, Layers, Settings, Sliders } from 'lucide-react';
import { useCategories, useDiscoveryAutoStatus, useSetDiscoveryAuto } from './api';
import { GeoChecklistSelector } from './GeoChecklistSelector';
import { Btn, Drawer, ErrorState, Notice, inputClass } from './ui';

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

  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [depth, setDepth] = useState('20');
  const [dailyLimit, setDailyLimit] = useState('200');
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
        country: selectedCountries.length ? selectedCountries[0] : null,
        countries: selectedCountries,
        states: selectedStates,
        cities: selectedCities,
        categories: selectedCategories.length ? selectedCategories : allAvailableCategories,
        searchDepth: Number(depth) || 20,
        dailyLimit: Number(dailyLimit) || 200,
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
      title="Automatic Discovery Settings"
      width="max-w-2xl"
    >
      <p className="mb-4 text-xs text-muted-foreground">
        Configure the geographic checklists (countries, states, cities) and sectors used by the background discovery loop before turning on Automatic Discovery.
      </p>

      <div className="grid gap-4 text-xs">
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

        {saveSuccess && (
          <Notice tone="info">
            Settings saved successfully! The automatic discovery loop will use these target settings.
          </Notice>
        )}

        {setAuto.isError && (
          <ErrorState
            error={setAuto.error}
            title="Failed to save automatic discovery settings"
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
