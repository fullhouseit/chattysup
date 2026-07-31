/** Text input / textarea with an optional label, icon, hint and error slot. */
import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from "react";
import { cn } from "@/lib/cn";

const FIELD = cn(
  "w-full rounded-lg border border-line bg-white px-3 text-sm text-ink shadow-card transition",
  "placeholder:text-ink-faint focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100",
  "disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-muted",
  "dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500",
  "dark:focus:border-primary-600 dark:focus:ring-primary-900/40",
);

interface FieldShellProps {
  id: string;
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: ReactNode;
}

function FieldShell({ id, label, hint, error, className, children }: FieldShellProps) {
  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <label
          htmlFor={id}
          className="block text-xs font-medium text-ink-soft dark:text-slate-300"
        >
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      ) : hint ? (
        <p className="text-xs text-ink-muted dark:text-slate-400">{hint}</p>
      ) : null}
    </div>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  icon?: ReactNode;
  trailing?: ReactNode;
  wrapperClassName?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, icon, trailing, className, wrapperClassName, id, ...rest },
  ref,
) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <FieldShell
      id={fieldId}
      label={label}
      hint={hint}
      error={error}
      className={wrapperClassName}
    >
      <div className="relative">
        {icon && (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint">
            {icon}
          </span>
        )}
        <input
          ref={ref}
          id={fieldId}
          className={cn(
            FIELD,
            "h-9",
            icon && "pl-9",
            trailing && "pr-9",
            error && "border-red-300 focus:border-red-400 focus:ring-red-100",
            className,
          )}
          {...rest}
        />
        {trailing && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-faint">
            {trailing}
          </span>
        )}
      </div>
    </FieldShell>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  wrapperClassName?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, className, wrapperClassName, id, rows = 4, ...rest },
  ref,
) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <FieldShell
      id={fieldId}
      label={label}
      hint={hint}
      error={error}
      className={wrapperClassName}
    >
      <textarea
        ref={ref}
        id={fieldId}
        rows={rows}
        className={cn(
          FIELD,
          "resize-y py-2 leading-relaxed",
          error && "border-red-300 focus:border-red-400 focus:ring-red-100",
          className,
        )}
        {...rest}
      />
    </FieldShell>
  );
});

export default Input;
