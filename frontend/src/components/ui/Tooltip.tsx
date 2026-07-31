/** Lightweight CSS-only tooltip wrapper. */
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface TooltipProps {
  label: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
}

const SIDES = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-1.5",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-1.5",
  left: "right-full top-1/2 -translate-y-1/2 mr-1.5",
  right: "left-full top-1/2 -translate-y-1/2 ml-1.5",
};

export function Tooltip({ label, children, side = "top", className }: TooltipProps) {
  if (!label) return <>{children}</>;
  return (
    <span className={cn("group/tooltip relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 whitespace-nowrap rounded-md bg-slate-900 px-2 py-1 text-2xs font-medium text-white opacity-0 shadow-pop transition-opacity",
          "group-hover/tooltip:opacity-100 dark:bg-slate-700",
          SIDES[side],
        )}
      >
        {label}
      </span>
    </span>
  );
}

export default Tooltip;
