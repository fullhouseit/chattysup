/**
 * The popup shown while the composer text starts with `/` — filters canned
 * responses by short code and inserts the selected body.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Zap } from "lucide-react";
import { cn } from "@/lib/cn";
import { truncate } from "@/lib/format";
import type { CannedResponse } from "@/lib/types";

export interface CannedResponsePickerProps {
  /** Text typed after the leading slash. */
  query: string;
  items: CannedResponse[];
  onSelect: (item: CannedResponse) => void;
  onClose: () => void;
}

export function CannedResponsePicker({
  query,
  items,
  onSelect,
  onClose,
}: CannedResponsePickerProps) {
  const [index, setIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    const filtered = term
      ? items.filter(
          (item) =>
            item.short_code.toLowerCase().includes(term) ||
            item.content.toLowerCase().includes(term),
        )
      : items;
    return filtered.slice(0, 8);
  }, [items, query]);

  useEffect(() => setIndex(0), [query]);

  // Keyboard navigation is captured at the document level so the textarea keeps
  // focus while the list is open.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!matches.length) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setIndex((value) => (value + 1) % matches.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setIndex((value) => (value - 1 + matches.length) % matches.length);
      } else if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        const item = matches[index];
        if (item) onSelect(item);
      } else if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [matches, index, onSelect, onClose]);

  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${index}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [index]);

  if (!matches.length) return null;

  return (
    <div className="absolute bottom-full left-0 right-0 z-30 mb-2 overflow-hidden rounded-xl border border-line bg-white shadow-pop dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center gap-1.5 border-b border-line px-3 py-1.5 text-2xs font-semibold uppercase tracking-wide text-ink-faint dark:border-slate-800">
        <Zap className="h-3 w-3" />
        Canned responses
      </div>
      <div ref={listRef} className="max-h-[240px] overflow-y-auto scroll-thin py-1">
        {matches.map((item, position) => (
          <button
            key={item.id}
            type="button"
            data-index={position}
            onMouseEnter={() => setIndex(position)}
            onClick={() => onSelect(item)}
            className={cn(
              "flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors",
              position === index
                ? "bg-primary-50 dark:bg-primary-900/30"
                : "hover:bg-surface-muted dark:hover:bg-slate-800",
            )}
          >
            <span className="text-sm font-medium text-primary">/{item.short_code}</span>
            <span className="text-xs text-ink-muted dark:text-slate-400">
              {truncate(item.content.replace(/\s+/g, " "), 90)}
            </span>
          </button>
        ))}
      </div>
      <p className="border-t border-line px-3 py-1.5 text-2xs text-ink-faint dark:border-slate-800">
        ↑↓ to navigate · Enter to insert · Esc to dismiss
      </p>
    </div>
  );
}

export default CannedResponsePicker;
