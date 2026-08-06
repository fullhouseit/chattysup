/**
 * Checkbox list used wherever a form picks several records at once — team
 * members, inbox collaborators, webhook event subscriptions.
 *
 * It is deliberately an inline scrolling list rather than a popover: the admin
 * forms are wide, and seeing every option at a glance beats a second click.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/cn";
import { Input } from "@/components/ui";

export interface MultiSelectOption<T extends string | number> {
  value: T;
  label: string;
  description?: string;
  icon?: ReactNode;
}

export interface MultiSelectProps<T extends string | number> {
  label?: ReactNode;
  hint?: ReactNode;
  options: MultiSelectOption<T>[];
  value: T[];
  onChange: (next: T[]) => void;
  /** Show a filter box once the list grows past this many options. */
  searchAfter?: number;
  emptyText?: string;
  className?: string;
  listClassName?: string;
}

export function MultiSelect<T extends string | number>({
  label,
  hint,
  options,
  value,
  onChange,
  searchAfter = 8,
  emptyText = "Nothing to choose from yet.",
  className,
  listClassName,
}: MultiSelectProps<T>) {
  const [query, setQuery] = useState("");
  const selected = useMemo(() => new Set<T>(value), [value]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return options;
    return options.filter(
      (option) =>
        option.label.toLowerCase().includes(needle) ||
        (option.description ?? "").toLowerCase().includes(needle),
    );
  }, [options, query]);

  function toggle(option: T) {
    if (selected.has(option)) onChange(value.filter((item) => item !== option));
    else onChange([...value, option]);
  }

  return (
    <div className={cn("space-y-1.5", className)}>
      {label && (
        <div className="flex items-baseline justify-between gap-2">
          <span className="block text-xs font-medium text-ink-soft dark:text-slate-300">
            {label}
          </span>
          {value.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-2xs text-ink-muted transition hover:text-ink dark:text-slate-400"
            >
              Clear ({value.length})
            </button>
          )}
        </div>
      )}
      {options.length > searchAfter && (
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter…"
          icon={<Search className="h-3.5 w-3.5" />}
        />
      )}
      <div
        className={cn(
          "max-h-56 divide-y divide-line overflow-y-auto rounded-lg border border-line scroll-thin dark:divide-slate-800 dark:border-slate-700",
          listClassName,
        )}
      >
        {visible.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-ink-muted dark:text-slate-400">
            {options.length === 0 ? emptyText : "No matches."}
          </p>
        ) : (
          visible.map((option) => (
            <label
              key={String(option.value)}
              className="flex cursor-pointer items-center gap-2.5 px-3 py-2 transition-colors hover:bg-surface-muted dark:hover:bg-slate-800/60"
            >
              <input
                type="checkbox"
                checked={selected.has(option.value)}
                onChange={() => toggle(option.value)}
                className="h-3.5 w-3.5 accent-primary"
              />
              {option.icon}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink dark:text-slate-200">
                  {option.label}
                </span>
                {option.description && (
                  <span className="block truncate text-2xs text-ink-muted dark:text-slate-400">
                    {option.description}
                  </span>
                )}
              </span>
            </label>
          ))
        )}
      </div>
      {hint && <p className="text-xs text-ink-muted dark:text-slate-400">{hint}</p>}
    </div>
  );
}

export default MultiSelect;
