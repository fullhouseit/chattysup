/**
 * Click-triggered popover menu.
 *
 * The trigger is supplied as a render prop so callers keep full control of its
 * markup; the panel closes on outside click, Escape and item activation.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { cn } from "@/lib/cn";

export type DropdownAlign = "left" | "right";

export interface DropdownProps {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  children: ReactNode | ((props: { close: () => void }) => ReactNode);
  align?: DropdownAlign;
  /** Position the panel above the trigger instead of below it. */
  above?: boolean;
  className?: string;
  panelClassName?: string;
  width?: string;
}

export function Dropdown({
  trigger,
  children,
  align = "left",
  above = false,
  className,
  panelClassName,
  width = "w-56",
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((value) => !value), []);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  return (
    <div ref={root} className={cn("relative", className)}>
      {trigger({ open, toggle })}
      {open && (
        <div
          className={cn(
            "absolute z-40 animate-scale-in rounded-xl border border-line bg-white p-1 shadow-pop",
            "dark:border-slate-700 dark:bg-slate-900",
            width,
            align === "right" ? "right-0" : "left-0",
            above ? "bottom-full mb-1.5" : "top-full mt-1.5",
            panelClassName,
          )}
          role="menu"
        >
          {typeof children === "function" ? children({ close }) : children}
        </div>
      )}
    </div>
  );
}

export interface DropdownItemProps {
  icon?: ReactNode;
  children: ReactNode;
  onClick?: (event: ReactMouseEvent<HTMLButtonElement>) => void;
  danger?: boolean;
  disabled?: boolean;
  active?: boolean;
  trailing?: ReactNode;
  className?: string;
}

export function DropdownItem({
  icon,
  children,
  onClick,
  danger,
  disabled,
  active,
  trailing,
  className,
}: DropdownItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
        "text-ink-soft hover:bg-surface-muted dark:text-slate-300 dark:hover:bg-slate-800",
        active && "bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200",
        danger &&
          "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40",
        disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
        className,
      )}
    >
      {icon && <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4">{icon}</span>}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {trailing}
    </button>
  );
}

export function DropdownSeparator() {
  return <div className="my-1 h-px bg-line dark:bg-slate-800" />;
}

export function DropdownLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-2.5 pb-1 pt-2 text-2xs font-semibold uppercase tracking-wide text-ink-faint">
      {children}
    </div>
  );
}

export default Dropdown;
