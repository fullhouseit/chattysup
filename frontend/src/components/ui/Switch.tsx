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
        <span
          className={cn(
            "absolute top-0.5 rounded-full bg-white shadow transition-transform",
            small ? "h-3 w-3" : "h-4 w-4",
            checked
              ? small
                ? "translate-x-3.5"
                : "translate-x-4"
              : "translate-x-0.5",
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
