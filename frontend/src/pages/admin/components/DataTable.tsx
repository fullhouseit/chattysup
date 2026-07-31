/**
 * Thin, unopinionated table primitives.
 *
 * The screens keep full control of their cells; these components only carry the
 * shared chrome — sticky bordered header, hover rows, dense 13px type and the
 * horizontal scroll container that keeps narrow viewports usable.
 */
import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/cn";

export function TableWrap({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto scroll-thin">
      <table className="w-full min-w-[640px] border-collapse text-sm">{children}</table>
    </div>
  );
}

export function Th({
  children,
  className,
  align = "left",
}: {
  children?: ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
}) {
  return (
    <th
      scope="col"
      className={cn(
        "border-b border-line bg-surface-muted px-4 py-2.5 text-2xs font-semibold uppercase tracking-wide text-ink-muted dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-400",
        align === "right" && "text-right",
        align === "center" && "text-center",
        align === "left" && "text-left",
        className,
      )}
    >
      {children}
    </th>
  );
}

export interface SortableThProps {
  children: ReactNode;
  /** The sort key this column emits. */
  sortKey: string;
  active: string | null;
  direction: "asc" | "desc";
  onSort: (key: string) => void;
  className?: string;
}

/** Header cell that toggles the table's sort key / direction when clicked. */
export function SortableTh({
  children,
  sortKey,
  active,
  direction,
  onSort,
  className,
}: SortableThProps) {
  const isActive = active === sortKey;
  const Icon = !isActive ? ArrowUpDown : direction === "asc" ? ArrowUp : ArrowDown;
  return (
    <Th className={className}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          "inline-flex items-center gap-1 transition-colors hover:text-ink dark:hover:text-slate-200",
          isActive && "text-ink dark:text-slate-100",
        )}
      >
        {children}
        <Icon className="h-3 w-3" />
      </button>
    </Th>
  );
}

export function Td({
  children,
  className,
  align = "left",
  colSpan,
  title,
}: {
  children?: ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
  colSpan?: number;
  /** Native tooltip, handy when the cell truncates. */
  title?: string;
}) {
  return (
    <td
      colSpan={colSpan}
      title={title}
      className={cn(
        "border-b border-line px-4 py-2.5 align-middle text-ink-soft dark:border-slate-800 dark:text-slate-300",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      {children}
    </td>
  );
}

export function Tr({
  children,
  onClick,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <tr
      onClick={onClick}
      className={cn(
        "transition-colors last:[&>td]:border-b-0",
        onClick && "cursor-pointer hover:bg-primary-50/60 dark:hover:bg-slate-800/50",
        className,
      )}
    >
      {children}
    </tr>
  );
}

/** Full-width message row used for empty and loading states. */
export function TableMessage({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <Td colSpan={colSpan} className="py-10 text-center text-sm text-ink-muted">
        {children}
      </Td>
    </tr>
  );
}
