/** Per-channel glyph + brand colour, used in the rail, list rows and headers. */
import { Globe, Mail, MessageCircle, Send, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

interface ChannelStyle {
  Icon: LucideIcon;
  color: string;
  label: string;
}

const CHANNELS: Record<string, ChannelStyle> = {
  telegram: { Icon: Send, color: "#229ED9", label: "Telegram" },
  web: { Icon: Globe, color: "#1F93FF", label: "Website" },
  email: { Icon: Mail, color: "#EA4335", label: "Email" },
};

const FALLBACK: ChannelStyle = {
  Icon: MessageCircle,
  color: "#6B7280",
  label: "Channel",
};

export function channelStyle(channelType: string | null | undefined): ChannelStyle {
  return CHANNELS[(channelType ?? "").toLowerCase()] ?? FALLBACK;
}

export interface ChannelIconProps {
  channelType: string | null | undefined;
  className?: string;
  /** Paint the glyph in the channel's brand colour. */
  colored?: boolean;
}

export function ChannelIcon({ channelType, className, colored = true }: ChannelIconProps) {
  const { Icon, color, label } = channelStyle(channelType);
  return (
    <Icon
      aria-label={label}
      className={cn("h-3.5 w-3.5 shrink-0", className)}
      style={colored ? { color } : undefined}
    />
  );
}

/** Round badge overlaid on an avatar to show which channel a chat came from. */
export function ChannelBadge({
  channelType,
  className,
}: {
  channelType: string | null | undefined;
  className?: string;
}) {
  const { Icon, color } = channelStyle(channelType);
  return (
    <span
      className={cn(
        "flex h-4 w-4 items-center justify-center rounded-full text-white",
        className,
      )}
      style={{ backgroundColor: color }}
    >
      <Icon className="h-2.5 w-2.5" />
    </span>
  );
}

export default ChannelIcon;
