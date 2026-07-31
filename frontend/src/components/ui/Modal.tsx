/** Accessible centred dialog rendered in a portal. */
import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { IconButton } from "./Button";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  description?: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
  children?: ReactNode;
  className?: string;
}

const SIZES = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

export function Modal({
  open,
  onClose,
  title,
  description,
  footer,
  size = "md",
  children,
  className,
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 animate-fade-in bg-slate-900/40 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "relative w-full animate-scale-in overflow-hidden rounded-xl bg-white shadow-pop dark:bg-slate-900",
          SIZES[size],
          className,
        )}
      >
        {(title || description) && (
          <header className="flex items-start gap-3 border-b border-line px-5 py-4 dark:border-slate-800">
            <div className="min-w-0 flex-1">
              {title && (
                <h2 className="truncate text-md font-semibold text-ink dark:text-slate-100">
                  {title}
                </h2>
              )}
              {description && (
                <p className="mt-0.5 text-sm text-ink-muted dark:text-slate-400">
                  {description}
                </p>
              )}
            </div>
            <IconButton label="Close" onClick={onClose} className="-mr-1 -mt-1">
              <X className="h-4 w-4" />
            </IconButton>
          </header>
        )}
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4 scroll-thin">{children}</div>
        {footer && (
          <footer className="flex items-center justify-end gap-2 border-t border-line bg-surface-muted px-5 py-3 dark:border-slate-800 dark:bg-slate-900/60">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body,
  );
}

export default Modal;
