/** Underlined tab row used by the conversation list and the chat pane. */
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface TabItem {
  key: string;
  label: ReactNode;
  count?: number;
  disabled?: boolean;
}

export interface TabsProps {
  items: TabItem[];
  value: string;
  onChange: (key: string) => void;
  className?: string;
  size?: "sm" | "md";
  /** Stretch the tabs to fill the available width. */
  fill?: boolean;
}

export function Tabs({
  items,
  value,
  onChange,
  className,
  size = "md",
  fill = false,
}: TabsProps) {
  return (
    <div
      role="tablist"
      className={cn(
        "flex items-center gap-1 border-b border-line px-1 dark:border-slate-800",
        className,
      )}
    >
      {items.map((item) => {
        const active = item.key === value;
        return (
          <button
            key={item.key}
            role="tab"
            type="button"
            aria-selected={active}
            disabled={item.disabled}
            onClick={() => !item.disabled && onChange(item.key)}
            className={cn(
              "relative -mb-px whitespace-nowrap border-b-2 px-3 font-medium transition-colors",
              size === "sm" ? "py-1.5 text-xs" : "py-2.5 text-sm",
              fill && "flex-1",
              active
                ? "border-primary text-primary"
                : "border-transparent text-ink-muted hover:text-ink dark:text-slate-400 dark:hover:text-slate-200",
              item.disabled && "cursor-not-allowed opacity-50 hover:text-ink-muted",
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span
                className={cn(
                  "ml-1.5 text-xs tabular-nums",
                  active ? "text-primary" : "text-ink-faint",
                )}
              >
                ({item.count})
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export default Tabs;
