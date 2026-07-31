/** Friendly placeholder for empty lists and unselected panes. */
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  compact,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-2 px-4 py-8" : "gap-3 px-6 py-14",
        className,
      )}
    >
      {icon && (
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-ink-faint dark:bg-slate-800 [&>svg]:h-5 [&>svg]:w-5">
          {icon}
        </span>
      )}
      <div>
        <p className="text-sm font-medium text-ink dark:text-slate-200">{title}</p>
        {description && (
          <p className="mx-auto mt-1 max-w-xs text-xs leading-relaxed text-ink-muted dark:text-slate-400">
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  );
}

export default EmptyState;
