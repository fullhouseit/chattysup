/**
 * Dependency-free emoji picker: a categorised grid with a search box.
 *
 * The catalogue is intentionally curated rather than exhaustive — it covers the
 * emoji support agents actually reach for, and keeps the bundle tiny.
 */
import { useMemo, useState } from "react";
import { cn } from "@/lib/cn";

interface EmojiGroup {
  name: string;
  icon: string;
  emojis: [string, string][];
}

const GROUPS: EmojiGroup[] = [
  {
    name: "Frequent",
    icon: "🕐",
    emojis: [
      ["👍", "thumbs up"],
      ["❤️", "heart"],
      ["😂", "joy laugh"],
      ["🙏", "thanks pray"],
      ["🎉", "party tada"],
      ["🔥", "fire"],
      ["👏", "clap"],
      ["✅", "check done"],
    ],
  },
  {
    name: "Smileys",
    icon: "😀",
    emojis: [
      ["😀", "grin smile"],
      ["😃", "smiley"],
      ["😄", "happy"],
      ["😁", "beam"],
      ["😅", "sweat smile"],
      ["😂", "joy"],
      ["🙂", "slight smile"],
      ["😉", "wink"],
      ["😊", "blush"],
      ["😍", "heart eyes love"],
      ["😘", "kiss"],
      ["😎", "cool sunglasses"],
      ["🤔", "thinking"],
      ["😐", "neutral"],
      ["😴", "sleep"],
      ["😢", "cry sad"],
      ["😭", "sob"],
      ["😡", "angry"],
      ["🥳", "celebrate"],
      ["🤗", "hug"],
      ["😇", "innocent"],
      ["🤝", "handshake deal"],
      ["🙌", "raise hands"],
      ["💪", "strong"],
    ],
  },
  {
    name: "Gestures",
    icon: "👍",
    emojis: [
      ["👍", "thumbs up yes"],
      ["👎", "thumbs down no"],
      ["👌", "ok"],
      ["✌️", "peace"],
      ["🤞", "fingers crossed"],
      ["👋", "wave hello"],
      ["🙏", "pray thanks"],
      ["👏", "clap applause"],
      ["✍️", "writing"],
      ["👀", "eyes look"],
    ],
  },
  {
    name: "Objects",
    icon: "💡",
    emojis: [
      ["✅", "check"],
      ["❌", "cross no"],
      ["⚠️", "warning"],
      ["❓", "question"],
      ["❗", "exclamation"],
      ["💡", "idea bulb"],
      ["📌", "pin"],
      ["📎", "clip attachment"],
      ["📞", "phone call"],
      ["📧", "mail email"],
      ["💳", "card payment"],
      ["🧾", "receipt invoice"],
      ["⏰", "clock time"],
      ["🚀", "rocket launch"],
      ["🎁", "gift"],
      ["🏆", "trophy win"],
      ["🔥", "fire hot"],
      ["⭐", "star"],
      ["🎉", "party"],
      ["💬", "chat message"],
    ],
  },
];

export interface EmojiPickerProps {
  onSelect: (emoji: string) => void;
  className?: string;
  /** Compact layout used by the message hover reaction picker. */
  compact?: boolean;
}

export function EmojiPicker({ onSelect, className, compact = false }: EmojiPickerProps) {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState(0);

  const emojis = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (term) {
      return GROUPS.flatMap((item) => item.emojis).filter(
        ([emoji, keywords]) => keywords.includes(term) || emoji === term,
      );
    }
    return GROUPS[group]?.emojis ?? [];
  }, [query, group]);

  return (
    <div
      className={cn(
        "rounded-xl border border-line bg-white p-2 shadow-pop dark:border-slate-700 dark:bg-slate-900",
        compact ? "w-[212px]" : "w-[268px]",
        className,
      )}
    >
      {!compact && (
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search emoji"
          aria-label="Search emoji"
          className="mb-2 h-8 w-full rounded-lg border border-line bg-surface-muted px-2.5 text-sm placeholder:text-ink-faint focus:border-primary-300 focus:bg-white focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
      )}

      <div
        className={cn(
          "grid max-h-[196px] gap-0.5 overflow-y-auto scroll-thin",
          compact ? "grid-cols-6" : "grid-cols-7",
        )}
      >
        {emojis.map(([emoji], index) => (
          <button
            key={`${emoji}-${index}`}
            type="button"
            onClick={() => onSelect(emoji)}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-lg transition hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            {emoji}
          </button>
        ))}
        {emojis.length === 0 && (
          <p className="col-span-full py-4 text-center text-xs text-ink-faint">
            No emoji found
          </p>
        )}
      </div>

      {!compact && !query && (
        <div className="mt-2 flex items-center gap-1 border-t border-line pt-2 dark:border-slate-800">
          {GROUPS.map((item, index) => (
            <button
              key={item.name}
              type="button"
              title={item.name}
              onClick={() => setGroup(index)}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-lg text-base transition",
                index === group
                  ? "bg-primary-50 dark:bg-primary-900/40"
                  : "hover:bg-slate-100 dark:hover:bg-slate-800",
              )}
            >
              {item.icon}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** The six reactions offered on hover, before opening the full picker. */
export const QUICK_REACTIONS = ["👍", "❤️", "😂", "🎉", "🙏", "👀"];

export default EmojiPicker;
