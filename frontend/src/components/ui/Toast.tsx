/**
 * Toast notifications.
 *
 * `<ToastProvider>` sits at the app root; anything below it calls `useToast()`
 * and gets `{ toast, success, error, dismiss }`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/cn";

export type ToastTone = "info" | "success" | "warning" | "error";

export interface ToastOptions {
  title?: string;
  description?: string;
  tone?: ToastTone;
  duration?: number;
}

interface ToastRecord extends Required<Pick<ToastOptions, "tone">> {
  id: number;
  title: string;
  description?: string;
}

interface ToastContextValue {
  toast: (options: ToastOptions) => number;
  success: (title: string, description?: string) => number;
  error: (title: string, description?: string) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

const TONES: Record<ToastTone, string> = {
  info: "text-primary",
  success: "text-emerald-600",
  warning: "text-amber-600",
  error: "text-red-600",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastRecord[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const toast = useCallback(
    ({ title = "", description, tone = "info", duration = 4500 }: ToastOptions) => {
      const id = nextId.current++;
      setItems((current) => [...current, { id, title, description, tone }]);
      if (duration > 0) window.setTimeout(() => dismiss(id), duration);
      return id;
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      toast,
      dismiss,
      success: (title, description) => toast({ title, description, tone: "success" }),
      error: (title, description) =>
        toast({ title, description, tone: "error", duration: 7000 }),
    }),
    [toast, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[340px] max-w-[calc(100vw-2rem)] flex-col gap-2">
        {items.map((item) => {
          const Icon = ICONS[item.tone];
          return (
            <div
              key={item.id}
              role="status"
              className="pointer-events-auto flex animate-scale-in items-start gap-2.5 rounded-xl border border-line bg-white p-3 shadow-pop dark:border-slate-700 dark:bg-slate-900"
            >
              <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", TONES[item.tone])} />
              <div className="min-w-0 flex-1">
                {item.title && (
                  <p className="text-sm font-medium text-ink dark:text-slate-100">
                    {item.title}
                  </p>
                )}
                {item.description && (
                  <p className="mt-0.5 break-words text-xs text-ink-muted dark:text-slate-400">
                    {item.description}
                  </p>
                )}
              </div>
              <button
                type="button"
                aria-label="Dismiss"
                onClick={() => dismiss(item.id)}
                className="rounded p-0.5 text-ink-faint transition hover:text-ink dark:hover:text-slate-200"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

/** Access the toast API. Falls back to a no-op outside the provider. */
export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  return (
    context ?? {
      toast: () => 0,
      success: () => 0,
      error: () => 0,
      dismiss: () => undefined,
    }
  );
}

export default ToastProvider;
