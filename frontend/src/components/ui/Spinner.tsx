/** Indeterminate loading indicators. */
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

export interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
  label?: string;
}

const SIZES = { sm: "h-4 w-4", md: "h-5 w-5", lg: "h-8 w-8" };

export function Spinner({ size = "md", className, label }: SpinnerProps) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-ink-muted", className)}>
      <Loader2 className={cn("animate-spin", SIZES[size])} aria-hidden />
      {label && <span className="text-sm">{label}</span>}
    </span>
  );
}

/** Centred spinner filling its parent — used for route/pane suspense. */
export function PageSpinner({ label }: { label?: string }) {
  return (
    <div className="flex h-full w-full items-center justify-center py-16">
      <Spinner size="lg" label={label} />
    </div>
  );
}

export default Spinner;
