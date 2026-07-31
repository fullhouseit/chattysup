/** Native select styled to match {@link Input}. */
import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

export interface SelectOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  options?: SelectOption[];
  placeholder?: string;
  wrapperClassName?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  {
    label,
    hint,
    error,
    options,
    placeholder,
    className,
    wrapperClassName,
    id,
    children,
    ...rest
  },
  ref,
) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <div className={cn("space-y-1.5", wrapperClassName)}>
      {label && (
        <label
          htmlFor={fieldId}
          className="block text-xs font-medium text-ink-soft dark:text-slate-300"
        >
          {label}
        </label>
      )}
      <div className="relative">
        <select
          ref={ref}
          id={fieldId}
          className={cn(
            "h-9 w-full appearance-none rounded-lg border border-line bg-white pl-3 pr-8 text-sm text-ink shadow-card transition",
            "focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100",
            "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-muted",
            "dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-primary-600 dark:focus:ring-primary-900/40",
            error && "border-red-300 focus:border-red-400 focus:ring-red-100",
            className,
          )}
          {...rest}
        >
          {placeholder && <option value="">{placeholder}</option>}
          {options?.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
          {children}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
      </div>
      {error ? (
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      ) : hint ? (
        <p className="text-xs text-ink-muted dark:text-slate-400">{hint}</p>
      ) : null}
    </div>
  );
});

export default Select;
