/** Reaction chips under a bubble plus the hover "add reaction" picker. */
import { useState } from "react";
import { SmilePlus } from "lucide-react";
import { cn } from "@/lib/cn";
import type { Reaction } from "@/lib/types";
import { Dropdown } from "@/components/ui";
import { EmojiPicker, QUICK_REACTIONS } from "./EmojiPicker";

export interface ReactionBarProps {
  reactions: Reaction[];
  onToggle: (emoji: string) => void;
  align?: "left" | "right";
  disabled?: boolean;
}

export function ReactionBar({
  reactions,
  onToggle,
  align = "left",
  disabled,
}: ReactionBarProps) {
  if (!reactions.length) return null;
  return (
    <div
      className={cn(
        "mt-1 flex flex-wrap items-center gap-1",
        align === "right" && "justify-end",
      )}
    >
      {reactions.map((reaction) => (
        <button
          key={reaction.emoji}
          type="button"
          disabled={disabled}
          onClick={() => onToggle(reaction.emoji)}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-xs transition",
            reaction.by_me
              ? "border-primary-200 bg-primary-50 text-primary-700 dark:border-primary-700 dark:bg-primary-900/40 dark:text-primary-200"
              : "border-line bg-white text-ink-soft hover:bg-surface-muted dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300",
          )}
        >
          <span className="text-sm leading-none">{reaction.emoji}</span>
          {reaction.count > 1 && (
            <span className="tabular-nums">{reaction.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

/** Hover affordance: six quick reactions plus the full emoji picker. */
export function AddReactionButton({
  onSelect,
  align = "left",
}: {
  onSelect: (emoji: string) => void;
  align?: "left" | "right";
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Dropdown
      align={align === "right" ? "right" : "left"}
      width="w-auto"
      panelClassName="p-1"
      trigger={({ toggle }) => (
        <button
          type="button"
          aria-label="Add reaction"
          onClick={() => {
            setExpanded(false);
            toggle();
          }}
          className="rounded-full p-1 text-ink-faint opacity-0 transition group-hover/message:opacity-100 hover:bg-slate-100 hover:text-ink dark:hover:bg-slate-800"
        >
          <SmilePlus className="h-4 w-4" />
        </button>
      )}
    >
      {({ close }) =>
        expanded ? (
          <EmojiPicker
            compact
            className="border-0 p-0 shadow-none"
            onSelect={(emoji) => {
              onSelect(emoji);
              close();
            }}
          />
        ) : (
          <div className="flex items-center gap-0.5">
            {QUICK_REACTIONS.map((emoji) => (
              <button
                key={emoji}
                type="button"
                onClick={() => {
                  onSelect(emoji);
                  close();
                }}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-lg transition hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                {emoji}
              </button>
            ))}
            <button
              type="button"
              aria-label="More emoji"
              onClick={() => setExpanded(true)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-faint transition hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <SmilePlus className="h-4 w-4" />
            </button>
          </div>
        )
      }
    </Dropdown>
  );
}

export default ReactionBar;
