/** Collapsible section used throughout the right-hand contact sidebar. */
import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";

export interface AccordionProps {
  title: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  /** Controlled mode: supply both to drive the state from the parent. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  action?: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Accordion({
  title,
  children,
  defaultOpen = true,
  open,
  onOpenChange,
  action,
  className,
  bodyClassName,
}: AccordionProps) {
  const [internal, setInternal] = useState(defaultOpen);
  const isOpen = open ?? internal;

  function toggle() {
    const next = !isOpen;
    if (open === undefined) setInternal(next);
    onOpenChange?.(next);
  }

  return (
    <section className={cn("border-b border-line dark:border-slate-800", className)}>
      <div className="flex items-center gap-1 pr-3">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={isOpen}
          className="flex min-w-0 flex-1 items-center gap-1.5 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted transition-colors hover:text-ink dark:text-slate-400 dark:hover:text-slate-200"
        >
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 shrink-0 transition-transform",
              !isOpen && "-rotate-90",
            )}
          />
          <span className="truncate">{title}</span>
        </button>
        {action}
      </div>
      {isOpen && <div className={cn("px-3 pb-4 pt-0.5", bodyClassName)}>{children}</div>}
    </section>
  );
}

export default Accordion;
