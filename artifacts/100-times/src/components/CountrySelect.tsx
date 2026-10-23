import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Globe, Search, X } from 'lucide-react';
import { ALL_WORLD_COUNTRIES } from '@/lib/countries';

interface CountrySelectProps {
  value?: string;
  onChange: (country: string | undefined) => void;
  className?: string;
}

export function CountrySelect({ value, onChange, className = '' }: CountrySelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      // Focus search input on open
      setTimeout(() => searchInputRef.current?.focus(), 50);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  const filteredCountries = search.trim()
    ? ALL_WORLD_COUNTRIES.filter((c) => c.toLowerCase().includes(search.trim().toLowerCase()))
    : ALL_WORLD_COUNTRIES;

  const isAllSelected = !value || value === '' || value.toLowerCase() === 'all';
  const displayLabel = isAllSelected ? 'All Countries' : value;

  const handleSelect = (countryName: string | undefined) => {
    onChange(countryName);
    setIsOpen(false);
    setSearch('');
  };

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      {/* Dropdown Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="mt-2 flex w-full items-center justify-between gap-2 rounded-lg border border-foreground/15 bg-background px-3 py-2.5 text-left text-sm font-medium transition hover:border-foreground/30 focus:border-accent focus:outline-none"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        data-testid="select-filter-country"
      >
        <span className="flex items-center gap-2 truncate">
          <Globe size={15} className="shrink-0 text-accent" />
          <span className="truncate">{displayLabel}</span>
        </span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-muted-foreground transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Dropdown Popover */}
      {isOpen && (
        <div
          className="absolute left-0 top-full z-50 mt-1.5 w-full min-w-[240px] max-w-[320px] rounded-xl border border-foreground/15 bg-card p-2 shadow-2xl backdrop-blur-md animate-in fade-in-0 zoom-in-95"
          role="listbox"
        >
          {/* Search Input Box */}
          <div className="relative mb-2">
            <Search size={14} className="absolute left-2.5 top-2.5 text-muted-foreground" />
            <input
              ref={searchInputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search 195+ countries..."
              className="w-full rounded-lg border border-foreground/15 bg-background py-1.5 pl-8 pr-7 text-xs outline-none placeholder:text-muted-foreground focus:border-accent"
              data-testid="input-country-search"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
                aria-label="Clear search"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Options List */}
          <div className="max-h-60 overflow-y-auto overscroll-contain pr-1 text-xs">
            {/* "All Countries" Option */}
            {(!search || 'all countries'.includes(search.toLowerCase())) && (
              <button
                type="button"
                onClick={() => handleSelect(undefined)}
                className={`flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left transition ${
                  isAllSelected ? 'bg-accent/15 font-semibold text-accent' : 'hover:bg-muted text-foreground'
                }`}
                role="option"
                aria-selected={isAllSelected}
                data-testid="option-all-countries"
              >
                <span className="flex items-center gap-2">
                  <Globe size={13} className="text-accent" />
                  All Countries (Worldwide)
                </span>
                {isAllSelected && <Check size={14} className="text-accent" />}
              </button>
            )}

            {/* Separator */}
            {(!search || 'all countries'.includes(search.toLowerCase())) && (
              <div className="my-1 border-t border-foreground/10" />
            )}

            {/* Filtered Country Items */}
            {filteredCountries.length > 0 ? (
              filteredCountries.map((country) => {
                const isSelected = value?.toLowerCase() === country.toLowerCase();
                return (
                  <button
                    key={country}
                    type="button"
                    onClick={() => handleSelect(country)}
                    className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left transition ${
                      isSelected ? 'bg-accent/15 font-semibold text-accent' : 'hover:bg-muted text-foreground'
                    }`}
                    role="option"
                    aria-selected={isSelected}
                    data-testid={`option-country-${country.toLowerCase().replace(/\s+/g, '-')}`}
                  >
                    <span className="truncate">{country}</span>
                    {isSelected && <Check size={14} className="text-accent shrink-0 ml-2" />}
                  </button>
                );
              })
            ) : (
              <div className="py-4 text-center text-xs text-muted-foreground">
                No countries match "{search}"
              </div>
            )}
          </div>

          {/* Footer note showing count */}
          <div className="mt-1.5 border-t border-foreground/10 pt-1.5 px-1 text-[10px] text-muted-foreground flex justify-between">
            <span>{filteredCountries.length} countries available</span>
            {!isAllSelected && (
              <button
                type="button"
                onClick={() => handleSelect(undefined)}
                className="text-accent hover:underline font-semibold"
              >
                Reset to All
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

