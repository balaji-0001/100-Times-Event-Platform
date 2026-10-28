import { useEffect } from 'react';
import { Link, useLocation } from 'wouter';
import { SlidersHorizontal } from 'lucide-react';
import { cx } from './ui';

// The saved discovery configuration (places, sectors, sources & providers, rules,
// organizer requirements, limits) is edited in ONE place: /admin/discover/configuration
// (DiscoveryConfigPage). This drawer used to duplicate it; its exports stay so existing
// imports keep working, and both now lead to that page.

export const DISCOVERY_CONFIG_PATH = '/admin/discover/configuration';

/** Link to the discovery configuration page (formerly opened the settings drawer). */
export function DiscoverySettingsButton({ size = 'sm', label = 'Configuration' }: { size?: 'sm' | 'md'; label?: string }) {
  return (
    <Link
      href={DISCOVERY_CONFIG_PATH}
      className={cx(
        'button-press inline-flex items-center gap-1 whitespace-nowrap rounded-full font-bold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
        size === 'sm' ? 'px-3 py-1 text-[11px]' : 'px-4 py-2 text-xs',
      )}
    >
      <SlidersHorizontal size={12} /> {label}
    </Link>
  );
}

/** Former settings drawer: opening it now navigates to the configuration page. */
export function DiscoverySettingsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [, setLocation] = useLocation();
  useEffect(() => {
    if (!open) return;
    onClose();
    setLocation(DISCOVERY_CONFIG_PATH);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}
