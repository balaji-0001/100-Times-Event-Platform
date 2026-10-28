// The on/off rule row the run wizard's Goals step reuses (manual research itself
// is the guided wizard at /admin/discover — RunWizardPage).

import { type ComponentType, useId } from 'react';

function ToggleSwitch({
  checked,
  onChange,
  disabled,
  label,
  describedBy,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  describedBy?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
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

/** One on/off rejection rule (used by the run wizard's Goals step). */
export function FilterRuleRow({
  icon: Icon,
  title,
  description,
  checked,
  onChange,
  badge,
  disabled,
}: {
  icon: ComponentType<{ size?: number; className?: string }>;
  title: string;
  description: string;
  checked: boolean;
  onChange: (val: boolean) => void;
  badge?: string;
  disabled?: boolean;
}) {
  const descriptionId = useId();
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
          <p id={descriptionId} className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{description}</p>
        </div>
      </div>
      <div className="pt-0.5 shrink-0">
        <ToggleSwitch checked={checked} onChange={onChange} disabled={disabled} label={title} describedBy={descriptionId} />
      </div>
    </div>
  );
}
