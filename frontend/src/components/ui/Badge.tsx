/** Small status pill / counter chip. */
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type BadgeTone =
  | "neutral"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "purple";

const TONES: Record<BadgeTone, string> = {
  neutral:
    "bg-slate-100 text-ink-soft dark:bg-slate-800 dark:text-slate-300",
  primary:
    "bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-200",
  success:
    "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  warning: "bg-amber-50 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  danger: "bg-red-50 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  purple: "bg-violet-50 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
};

export interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: string;
  className?: string;
  size?: "xs" | "sm";
}

export function Badge({ children, tone = "neutral", dot, className, size = "sm" }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-full font-medium",
        size === "xs" ? "px-1.5 py-0.5 text-2xs" : "px-2 py-0.5 text-xs",
        TONES[tone],
        className,
      )}
    >
      {dot && (
        <span
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: dot }}
          aria-hidden
        />
      )}
      <span className="truncate">{children}</span>
    </span>
  );
}

/** Blue unread counter used in the conversation list and the sidebar. */
export function CountBadge({ count, className }: { count: number; className?: string }) {
  if (!count) return null;
  return (
    <span
      className={cn(
        "inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-primary px-1.5 text-2xs font-semibold tabular-nums text-white",
        className,
      )}
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}

export default Badge;
