/** Circular avatar with initials fallback, presence dot and badge slot. */
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { avatarColor, initials as toInitials } from "@/lib/format";
import type { Availability } from "@/lib/types";

export type AvatarSize = "xs" | "sm" | "md" | "lg" | "xl" | "2xl";

const SIZES: Record<AvatarSize, string> = {
  xs: "h-5 w-5 text-[9px]",
  sm: "h-7 w-7 text-[10px]",
  md: "h-9 w-9 text-xs",
  lg: "h-10 w-10 text-sm",
  xl: "h-14 w-14 text-base",
  "2xl": "h-20 w-20 text-xl",
};

const DOT_SIZES: Record<AvatarSize, string> = {
  xs: "h-1.5 w-1.5",
  sm: "h-2 w-2",
  md: "h-2.5 w-2.5",
  lg: "h-2.5 w-2.5",
  xl: "h-3.5 w-3.5",
  "2xl": "h-4 w-4",
};

const PRESENCE: Record<Availability, string> = {
  online: "bg-emerald-500",
  busy: "bg-amber-500",
  offline: "bg-slate-400",
};

export interface AvatarProps {
  name?: string | null;
  src?: string | null;
  size?: AvatarSize;
  /** Show a presence dot in the bottom-right corner. */
  status?: Availability | null;
  /** Small channel badge rendered bottom-right (mutually exclusive with dot). */
  badge?: ReactNode;
  seed?: string | number;
  className?: string;
  square?: boolean;
}

export function Avatar({
  name,
  src,
  size = "md",
  status,
  badge,
  seed,
  className,
  square,
}: AvatarProps) {
  const [broken, setBroken] = useState(false);
  const palette = avatarColor(seed ?? name ?? "?");
  const showImage = Boolean(src) && !broken;

  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      {showImage ? (
        <img
          src={src as string}
          alt={name ?? ""}
          onError={() => setBroken(true)}
          className={cn(
            "object-cover ring-1 ring-black/5",
            square ? "rounded-lg" : "rounded-full",
            SIZES[size],
          )}
        />
      ) : (
        <span
          aria-hidden
          style={{ backgroundColor: palette.bg, color: palette.fg }}
          className={cn(
            "inline-flex items-center justify-center font-semibold uppercase leading-none ring-1 ring-black/5",
            square ? "rounded-lg" : "rounded-full",
            SIZES[size],
          )}
        >
          {toInitials(name)}
        </span>
      )}

      {badge ? (
        <span className="absolute -bottom-0.5 -right-0.5 flex items-center justify-center rounded-full bg-white ring-2 ring-white dark:bg-slate-900 dark:ring-slate-900">
          {badge}
        </span>
      ) : status ? (
        <span
          aria-label={status}
          className={cn(
            "absolute bottom-0 right-0 rounded-full ring-2 ring-white dark:ring-slate-900",
            DOT_SIZES[size],
            PRESENCE[status] ?? PRESENCE.offline,
          )}
        />
      ) : null}
    </span>
  );
}

export default Avatar;
