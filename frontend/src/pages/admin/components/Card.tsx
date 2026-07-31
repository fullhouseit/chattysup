/** White rounded panel used for every settings section and table shell. */
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface CardProps {
  children: ReactNode;
  className?: string;
  /** Removes the inner padding so tables can bleed to the border. */
  flush?: boolean;
}

export function Card({ children, className, flush = false }: CardProps) {
  return (
    <section
      className={cn(
        "rounded-xl border border-line bg-white shadow-card dark:border-slate-800 dark:bg-slate-900",
        flush ? "overflow-hidden" : "p-5",
        className,
      )}
    >
      {children}
    </section>
  );
}

export interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/** Title row for a {@link Card}; pair with `flush` cards above a table. */
export function CardHeader({ title, description, actions, className }: CardHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-3 border-b border-line px-5 py-3.5 dark:border-slate-800",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-ink dark:text-slate-100">{title}</h2>
        {description && (
          <p className="mt-0.5 text-xs text-ink-muted dark:text-slate-400">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export default Card;
