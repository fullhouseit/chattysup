/**
 * Standard heading block for the settings and contacts screens: a title, an
 * optional one-line explanation and a right-aligned actions slot.
 */
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** Optional breadcrumb / back link rendered above the title. */
  above?: ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  description,
  actions,
  above,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("mb-5", className)}>
      {above && <div className="mb-2">{above}</div>}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-ink dark:text-slate-100">{title}</h1>
          {description && (
            <p className="mt-1 max-w-2xl text-sm text-ink-muted dark:text-slate-400">
              {description}
            </p>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

export default PageHeader;
