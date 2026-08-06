/** Accessible on/off toggle. */
import { useId, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  className?: string;
  size?: "sm" | "md";
}

export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
  className,
  size = "md",
}: SwitchProps) {
  const id = useId();
  const small = size === "sm";
  return (
    <div className={cn("flex items-start gap-3", className)}>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "focus-ring relative shrink-0 rounded-full transition-colors",
          small ? "h-4 w-7" : "h-5 w-9",
          checked ? "bg-primary" : "bg-slate-300 dark:bg-slate-700",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        {/*
          `left-0.5` is load-bearing: without an explicit inset the knob is laid
          out at its browser-decided static position (a centred one inside the
          button), so the translate below started from the wrong origin and the
          knob overflowed the track by 14px when on.

          Off  = the 2px inset.  On = track − knob − 2×inset, i.e. 36−16−4 = 16px
          (`translate-x-4`) and 28−12−4 = 12px (`translate-x-3`), which leaves the
          same 2px gap on both ends.
        */}
        <span
          className={cn(
            "absolute left-0.5 top-0.5 rounded-full bg-white shadow transition-transform",
            small ? "h-3 w-3" : "h-4 w-4",
            checked ? (small ? "translate-x-3" : "translate-x-4") : "translate-x-0",
          )}
        />
      </button>
      {(label || description) && (
        <label htmlFor={id} className="min-w-0 cursor-pointer select-none">
          {label && (
            <span className="block text-sm font-medium text-ink dark:text-slate-200">
              {label}
            </span>
          )}
          {description && (
            <span className="mt-0.5 block text-xs text-ink-muted dark:text-slate-400">
              {description}
            </span>
          )}
        </label>
      )}
    </div>
  );
}

export default Switch;
