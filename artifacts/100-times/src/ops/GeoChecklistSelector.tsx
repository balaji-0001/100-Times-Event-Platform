import { useMemo, useState } from 'react';
import { Globe, MapPin, Plus, Search, X } from 'lucide-react';
import {
  ALL_WORLD_COUNTRIES,
  COUNTRY_HIERARCHY,
  getReferenceCitiesForCountriesAndStates,
  getReferenceStatesForCountries,
} from '@/lib/countries';
import { inputClass } from './ui';

/** Drop the states/cities that belong only to removed countries (custom cities are kept). */
function pruneForCountries(remaining: string[], removed: string[], states: string[], cities: string[]) {
  const keptStates = new Set(remaining.flatMap((c) => Object.keys(COUNTRY_HIERARCHY[c] ?? {})));
  const keptCities = new Set(remaining.flatMap((c) => Object.values(COUNTRY_HIERARCHY[c] ?? {}).flat()));
  const removedStates = new Set(removed.flatMap((c) => Object.keys(COUNTRY_HIERARCHY[c] ?? {})));
  const removedCities = new Set(removed.flatMap((c) => Object.values(COUNTRY_HIERARCHY[c] ?? {}).flat()));
  return {
    states: states.filter((s) => !removedStates.has(s) || keptStates.has(s)),
    cities: cities.filter((c) => !removedCities.has(c) || keptCities.has(c)),
  };
}

export interface GeoChecklistSelectorProps {
  /** Optional single country (for backwards compatibility) */
  country?: string;
  onCountryChange?: (country: string) => void;
  /** Primary multi-country list */
  selectedCountries?: string[];
  onCountriesChange?: (countries: string[]) => void;
  selectedStates: string[];
  onStatesChange: (states: string[]) => void;
  selectedCities: string[];
  onCitiesChange: (cities: string[]) => void;
  disabled?: boolean;
  /** Whether "no country ticked" means a worldwide search (true, the default — Automatic settings).
   *  The run wizard passes false: there, Worldwide is its own explicit choice. */
  emptyMeansWorldwide?: boolean;
}

const POPULAR_COUNTRIES = [
  'India',
  'Dubai',
  'United Arab Emirates',
  'United States',
  'United Kingdom',
  'Germany',
  'Canada',
  'Singapore',
  'Australia',
  'France',
  'Saudi Arabia',
  'Netherlands',
];

export function GeoChecklistSelector({
  country = '',
  onCountryChange,
  selectedCountries,
  onCountriesChange,
  selectedStates,
  onStatesChange,
  selectedCities,
  onCitiesChange,
  disabled = false,
  emptyMeansWorldwide = true,
}: GeoChecklistSelectorProps) {
  const [countrySearch, setCountrySearch] = useState('');
  const [stateSearch, setStateSearch] = useState('');
  const [citySearch, setCitySearch] = useState('');
  const [customCity, setCustomCity] = useState('');

  // 1. Resolve active countries (supports both multi-select selectedCountries and legacy single country)
  const activeCountries = useMemo(() => {
    if (selectedCountries !== undefined) {
      return selectedCountries;
    }
    return country ? [country] : [];
  }, [selectedCountries, country]);

  const updateCountries = (newCountries: string[]) => {
    if (disabled) return;
    if (onCountriesChange) {
      onCountriesChange(newCountries);
    }
    if (onCountryChange) {
      onCountryChange(newCountries.length > 0 ? newCountries[0] : '');
    }
  };

  const toggleCountry = (c: string) => {
    if (disabled) return;
    if (activeCountries.includes(c)) {
      const remaining = activeCountries.filter((item) => item !== c);
      updateCountries(remaining);
      // A removed country takes its states and cities with it — otherwise they
      // stayed selected and were still searched (without their country).
      const { states, cities } = pruneForCountries(remaining, [c], selectedStates, selectedCities);
      if (states.length !== selectedStates.length) onStatesChange(states);
      if (cities.length !== selectedCities.length) onCitiesChange(cities);
    } else {
      updateCountries([...activeCountries, c]);
    }
  };

  const selectAllCountries = () => {
    if (disabled) return;
    updateCountries([...ALL_WORLD_COUNTRIES]);
  };

  const clearAllCountries = () => {
    if (disabled) return;
    updateCountries([]);
    onStatesChange([]);
    onCitiesChange([]);
  };

  // Filtered countries by search query
  const filteredCountries = useMemo(() => {
    if (!countrySearch.trim()) return ALL_WORLD_COUNTRIES;
    const q = countrySearch.trim().toLowerCase();
    return ALL_WORLD_COUNTRIES.filter((c) => c.toLowerCase().includes(q));
  }, [countrySearch]);

  // 2. Available states for all active countries
  const availableStatesData = useMemo(() => {
    if (activeCountries.length === 0) return [];
    return getReferenceStatesForCountries(activeCountries);
  }, [activeCountries]);

  const availableStateNames = useMemo(() => {
    return Array.from(new Set(availableStatesData.map((s) => s.state)));
  }, [availableStatesData]);

  // Filtered states by search query
  const filteredStates = useMemo(() => {
    if (!stateSearch.trim()) return availableStatesData;
    const q = stateSearch.trim().toLowerCase();
    return availableStatesData.filter(
      (s) => s.state.toLowerCase().includes(q) || s.country.toLowerCase().includes(q)
    );
  }, [availableStatesData, stateSearch]);

  // State handlers
  const toggleState = (s: string) => {
    if (disabled) return;
    if (selectedStates.includes(s)) {
      const remainingStates = selectedStates.filter((item) => item !== s);
      onStatesChange(remainingStates);
      // ...and a removed state takes its cities with it (unless another selected state has them).
      const stillCovered = new Set(getReferenceCitiesForCountriesAndStates(activeCountries, remainingStates).map((x) => x.city));
      const ofState = new Set(activeCountries.flatMap((country) => COUNTRY_HIERARCHY[country]?.[s] ?? []));
      const cities = selectedCities.filter((city) => !ofState.has(city) || (remainingStates.length > 0 && stillCovered.has(city)));
      if (cities.length !== selectedCities.length) onCitiesChange(cities);
    } else {
      onStatesChange([...selectedStates, s]);
    }
  };

  const selectAllStates = () => {
    if (disabled) return;
    onStatesChange(Array.from(new Set([...selectedStates, ...availableStateNames])));
  };

  const clearAllStates = () => {
    if (disabled) return;
    onStatesChange([]);
  };

  // 3. Available cities based on active countries and selected states
  const availableCitiesData = useMemo(() => {
    if (activeCountries.length === 0) return [];
    return getReferenceCitiesForCountriesAndStates(activeCountries, selectedStates);
  }, [activeCountries, selectedStates]);

  const availableCityNames = useMemo(() => {
    return Array.from(new Set(availableCitiesData.map((item) => item.city)));
  }, [availableCitiesData]);

  // Filtered cities by search query
  const filteredCities = useMemo(() => {
    const q = citySearch.trim().toLowerCase();
    const all = Array.from(new Set([...availableCityNames, ...selectedCities]));
    if (!q) return all;
    return all.filter((c) => c.toLowerCase().includes(q));
  }, [availableCityNames, selectedCities, citySearch]);

  // City handlers
  const toggleCity = (c: string) => {
    if (disabled) return;
    if (selectedCities.includes(c)) {
      onCitiesChange(selectedCities.filter((item) => item !== c));
    } else {
      onCitiesChange([...selectedCities, c]);
    }
  };

  const selectAllCities = () => {
    if (disabled) return;
    onCitiesChange(Array.from(new Set([...selectedCities, ...availableCityNames])));
  };

  const clearAllCities = () => {
    if (disabled) return;
    onCitiesChange([]);
  };

  const addCustomCity = () => {
    const trimmed = customCity.trim();
    if (!trimmed || selectedCities.includes(trimmed)) return;
    onCitiesChange([...selectedCities, trimmed]);
    setCustomCity('');
  };

  return (
    <div className="space-y-4">
      {/* ========================================================================= */}
      {/* --- 1. Target Countries Checklist Section --- */}
      {/* ========================================================================= */}
      <div className="rounded-xl border border-foreground/10 bg-background/50 p-3 space-y-2.5">
        <div className="flex items-center justify-between">
          <div>
            <span className="font-semibold text-foreground flex items-center gap-1.5 text-xs">
              <Globe size={13} className="text-accent" /> Target Countries Checklist
              {activeCountries.length > 0 && (
                <span className="rounded-full bg-accent/15 px-2 py-0.2 text-[10px] font-medium text-accent">
                  {activeCountries.length} selected
                </span>
              )}
            </span>
            <span className="block text-[10px] text-muted-foreground mt-0.5">
              {activeCountries.length === 0
                ? emptyMeansWorldwide
                  ? 'Worldwide mode (All Countries active) · Select one or more countries to filter'
                  : 'No country selected yet · tick one or more countries'
                : `${activeCountries.length} of ${ALL_WORLD_COUNTRIES.length} countries selected`}
            </span>
          </div>

          <div className="flex items-center gap-2 text-[10px]">
            {activeCountries.length > 0 ? (
              <button
                type="button"
                onClick={clearAllCountries}
                className="text-accent hover:underline font-medium"
                disabled={disabled}
              >
                {emptyMeansWorldwide ? 'Reset to Worldwide' : 'Clear countries'}
              </button>
            ) : (
              <button
                type="button"
                onClick={selectAllCountries}
                className="text-accent hover:underline font-medium"
                disabled={disabled}
              >
                Select all
              </button>
            )}
          </div>
        </div>

        {/* Popular Quick Pills */}
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[10px] text-muted-foreground mr-1">Quick select:</span>
          {POPULAR_COUNTRIES.map((c) => {
            const isSelected = activeCountries.includes(c);
            return (
              <button
                type="button"
                key={c}
                onClick={() => toggleCountry(c)}
                disabled={disabled}
                className={`rounded-md px-2 py-0.5 text-[10px] font-medium transition-colors border ${
                  isSelected
                    ? 'border-accent bg-accent/20 text-accent font-semibold'
                    : 'border-foreground/10 bg-card/60 text-foreground/80 hover:border-foreground/20'
                }`}
              >
                {isSelected ? '✓ ' : '+ '}
                {c}
              </button>
            );
          })}
        </div>

        {/* Country Search */}
        <div className="relative">
          <Search size={11} className="absolute left-2.5 top-2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search 200+ countries (e.g. India, Dubai, United States, Germany)..."
            value={countrySearch}
            onChange={(e) => setCountrySearch(e.target.value)}
            className={`${inputClass} w-full pl-7 py-1 text-[11px]`}
            disabled={disabled}
          />
        </div>

        {/* Countries Checklist Grid */}
        <div className="max-h-36 overflow-y-auto pr-1 grid grid-cols-2 sm:grid-cols-3 gap-1.5 rounded-lg border border-foreground/10 p-2 bg-card/60">
          {filteredCountries.map((c) => {
            const checked = activeCountries.includes(c);
            return (
              <label
                key={c}
                className={`flex items-center gap-1.5 p-1 rounded-md text-[11px] cursor-pointer transition-colors ${
                  checked
                    ? 'bg-accent/10 text-accent font-semibold'
                    : 'text-foreground/80 hover:bg-muted/40'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleCountry(c)}
                  disabled={disabled}
                  className="rounded border-foreground/20 text-accent focus:ring-accent"
                />
                <span className="truncate" title={c}>
                  {c}
                </span>
              </label>
            );
          })}
          {filteredCountries.length === 0 && (
            <div className="col-span-full py-2 text-center text-[10px] text-muted-foreground">
              No countries matching &ldquo;{countrySearch}&rdquo;
            </div>
          )}
        </div>

        {/* Selected Countries Chips */}
        {activeCountries.length > 0 && (
          <div className="pt-1">
            <span className="text-[10px] font-semibold text-muted-foreground block mb-1">
              Selected Countries ({activeCountries.length}):
            </span>
            <div className="flex flex-wrap gap-1 max-h-16 overflow-y-auto">
              {activeCountries.map((c) => (
                <span
                  key={c}
                  className="inline-flex items-center gap-1 rounded-md bg-accent/15 px-2 py-0.5 text-[10px] font-medium text-accent"
                >
                  {c}
                  <button
                    type="button"
                    onClick={() => toggleCountry(c)}
                    disabled={disabled}
                    className="hover:text-red-400"
                    title={`Remove ${c}`}
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* --- 2. States / Regions Checklist Section --- */}
      {/* ========================================================================= */}
      <div className="rounded-xl border border-foreground/10 bg-background/50 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <span className="font-semibold text-foreground flex items-center gap-1 text-xs">
              <MapPin size={12} className="text-accent" /> States / Regions Checklist
              {activeCountries.length > 0 && (
                <span className="text-[10px] text-muted-foreground">
                  ({activeCountries.length} countr{activeCountries.length > 1 ? 'ies' : 'y'})
                </span>
              )}
            </span>
            <span className="block text-[10px] text-muted-foreground">
              {activeCountries.length > 0
                ? `${selectedStates.length} of ${availableStateNames.length} selected`
                : emptyMeansWorldwide
                  ? 'Worldwide mode — all states/regions worldwide eligible'
                  : 'Select a country first'}
            </span>
          </div>
          {availableStatesData.length > 0 && (
            <div className="flex items-center gap-2 text-[10px]">
              <button
                type="button"
                onClick={selectAllStates}
                className="text-accent hover:underline font-medium"
                disabled={disabled}
              >
                Select all
              </button>
              <span>•</span>
              <button
                type="button"
                onClick={clearAllStates}
                className="text-muted-foreground hover:underline font-medium"
                disabled={disabled}
              >
                Clear
              </button>
            </div>
          )}
        </div>

        {availableStatesData.length > 0 && (
          <div className="relative">
            <Search size={11} className="absolute left-2.5 top-2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search states / regions..."
              value={stateSearch}
              onChange={(e) => setStateSearch(e.target.value)}
              className={`${inputClass} w-full pl-7 py-1 text-[11px]`}
              disabled={disabled}
            />
          </div>
        )}

        {activeCountries.length > 0 ? (
          availableStatesData.length > 0 ? (
            <div className="max-h-36 overflow-y-auto pr-1 grid grid-cols-2 sm:grid-cols-3 gap-1.5 rounded-lg border border-foreground/10 p-2 bg-card/60">
              {filteredStates.map((st) => {
                const checked = selectedStates.includes(st.state);
                return (
                  <label
                    key={`${st.country}-${st.state}`}
                    className={`flex items-center gap-1.5 p-1 rounded-md text-[11px] cursor-pointer transition-colors ${
                      checked
                        ? 'bg-accent/10 text-accent font-semibold'
                        : 'text-foreground/80 hover:bg-muted/40'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleState(st.state)}
                      disabled={disabled}
                      className="rounded border-foreground/20 text-accent focus:ring-accent"
                    />
                    <div className="truncate" title={`${st.state} (${st.country})`}>
                      <span className="block truncate">{st.state}</span>
                      {activeCountries.length > 1 && (
                        <span className="block text-[9px] text-muted-foreground truncate font-normal">
                          {st.country}
                        </span>
                      )}
                    </div>
                  </label>
                );
              })}
              {filteredStates.length === 0 && (
                <div className="col-span-full py-2 text-center text-[10px] text-muted-foreground">
                  No states matching &ldquo;{stateSearch}&rdquo;
                </div>
              )}
            </div>
          ) : (
            <div className="py-2 text-center text-[11px] text-muted-foreground">
              No regional state list configured for selected countries. You can specify cities directly below.
            </div>
          )
        ) : (
          <div className="py-2 text-center text-[11px] text-muted-foreground">
            {emptyMeansWorldwide
              ? 'Worldwide mode active — select one or more countries above to filter by specific states/regions.'
              : 'Select one or more countries above to choose states or regions.'}
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* --- 3. Cities Checklist Section --- */}
      {/* ========================================================================= */}
      <div className="rounded-xl border border-foreground/10 bg-background/50 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div>
            <span className="font-semibold text-foreground flex items-center gap-1 text-xs">
              <MapPin size={12} className="text-accent" /> Cities Checklist
              {selectedStates.length > 0 && (
                <span className="text-[10px] text-muted-foreground">
                  (filtered to {selectedStates.length} state{selectedStates.length > 1 ? 's' : ''})
                </span>
              )}
            </span>
            <span className="block text-[10px] text-muted-foreground">
              {activeCountries.length > 0
                ? `${selectedCities.length} selected`
                : emptyMeansWorldwide
                  ? 'Worldwide mode active · Add custom cities or select countries above'
                  : 'Select countries above to list their cities'}
            </span>
          </div>
          {filteredCities.length > 0 && (
            <div className="flex items-center gap-2 text-[10px]">
              <button
                type="button"
                onClick={selectAllCities}
                className="text-accent hover:underline font-medium"
                disabled={disabled}
              >
                Select all
              </button>
              <span>•</span>
              <button
                type="button"
                onClick={clearAllCities}
                className="text-muted-foreground hover:underline font-medium"
                disabled={disabled}
              >
                Clear
              </button>
            </div>
          )}
        </div>

        {/* City search filter */}
        <div className="relative">
          <Search size={11} className="absolute left-2.5 top-2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search cities in checklist..."
            value={citySearch}
            onChange={(e) => setCitySearch(e.target.value)}
            className={`${inputClass} w-full pl-7 py-1 text-[11px]`}
            disabled={disabled}
          />
        </div>

        {/* Cities checklist grid */}
        {filteredCities.length > 0 ? (
          <div className="max-h-40 overflow-y-auto pr-1 grid grid-cols-2 sm:grid-cols-3 gap-1.5 rounded-lg border border-foreground/10 p-2 bg-card/60">
            {filteredCities.map((ct) => {
              const checked = selectedCities.includes(ct);
              return (
                <label
                  key={ct}
                  className={`flex items-center gap-1.5 p-1 rounded-md text-[11px] cursor-pointer transition-colors ${
                    checked
                      ? 'bg-accent/10 text-accent font-semibold'
                      : 'text-foreground/80 hover:bg-muted/40'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleCity(ct)}
                    disabled={disabled}
                    className="rounded border-foreground/20 text-accent focus:ring-accent"
                  />
                  <span className="truncate" title={ct}>
                    {ct}
                  </span>
                </label>
              );
            })}
          </div>
        ) : (
          <div className="py-2 text-center text-[11px] text-muted-foreground">
            {activeCountries.length > 0
              ? 'No standard cities listed for this filter. Add custom cities below.'
              : emptyMeansWorldwide
                ? 'Worldwide mode active. Select countries above to view standard cities, or add custom cities below.'
                : 'Select countries above to view standard cities, or add custom cities below.'}
          </div>
        )}

        {/* Custom city adder */}
        <div className="flex items-center gap-1.5 pt-1">
          <input
            type="text"
            placeholder="Add custom city (e.g. Nashik, Solapur, Dubai Marina)..."
            value={customCity}
            onChange={(e) => setCustomCity(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addCustomCity();
              }
            }}
            className={`${inputClass} flex-1 py-1 text-[11px]`}
            disabled={disabled}
          />
          <button
            type="button"
            onClick={addCustomCity}
            disabled={disabled || !customCity.trim()}
            className="inline-flex items-center gap-1 rounded-lg border border-foreground/15 bg-background px-2.5 py-1 text-[11px] font-semibold hover:border-accent disabled:opacity-50"
          >
            <Plus size={11} /> Add
          </button>
        </div>

        {/* Selected cities chips preview */}
        {selectedCities.length > 0 && (
          <div className="pt-1">
            <span className="text-[10px] font-semibold text-muted-foreground block mb-1">
              Currently Selected Cities ({selectedCities.length}):
            </span>
            <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
              {selectedCities.map((ct) => (
                <span
                  key={ct}
                  className="inline-flex items-center gap-1 rounded-md bg-accent/15 px-2 py-0.5 text-[10px] font-medium text-accent"
                >
                  {ct}
                  <button
                    type="button"
                    onClick={() => toggleCity(ct)}
                    disabled={disabled}
                    className="hover:text-red-400"
                    title={`Remove ${ct}`}
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
