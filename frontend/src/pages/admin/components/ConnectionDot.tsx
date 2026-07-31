/**
 * Coloured dot + label for `Inbox.connection_status`.
 *
 * The backend is free to invent new statuses, so anything unrecognised falls
 * back to a neutral slate dot rather than disappearing.
 */
import { cn } from "@/lib/cn";
import { humanize } from "@/lib/format";

const TONES: Record<string, string> = {
  connected: "bg-emerald-500",
  ok: "bg-emerald-500",
  active: "bg-emerald-500",
  connecting: "bg-amber-500",
  pending: "bg-amber-500",
  configuring: "bg-amber-500",
  error: "bg-red-500",
  failed: "bg-red-500",
  disconnected: "bg-slate-400",
  inactive: "bg-slate-400",
  unknown: "bg-slate-300",
};

export function connectionTone(status: string | null | undefined): string {
  return TONES[(status ?? "unknown").toLowerCase()] ?? "bg-slate-400";
}

export interface ConnectionDotProps {
  status: string | null | undefined;
  /** Append the humanised status text next to the dot. */
  withLabel?: boolean;
  title?: string;
  className?: string;
}

export function ConnectionDot({ status, withLabel = true, title, className }: ConnectionDotProps) {
  const label = humanize(status || "unknown");
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-xs", className)}
      title={title ?? label}
    >
      <span className={cn("h-2 w-2 shrink-0 rounded-full", connectionTone(status))} />
      {withLabel && <span className="text-ink-soft dark:text-slate-300">{label}</span>}
    </span>
  );
}

export default ConnectionDot;
