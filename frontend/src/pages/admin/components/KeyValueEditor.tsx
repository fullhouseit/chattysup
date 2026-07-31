/**
 * Editable map of free-form key/value pairs — the contact "custom attributes"
 * and conversation metadata editors both use it.
 *
 * Values are stored as strings unless they parse cleanly as a number or a
 * boolean, which keeps round-tripping through the JSON column lossless enough
 * for the automation engine's comparisons.
 */
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { Dict, Json } from "@/lib/types";
import { Button, IconButton, Input } from "@/components/ui";

/** Coerce a typed-in value to a boolean/number when it obviously is one. */
export function coerceValue(raw: string): Json {
  const text = raw.trim();
  if (text === "true") return true;
  if (text === "false") return false;
  if (text !== "" && !Number.isNaN(Number(text)) && /^-?\d+(\.\d+)?$/.test(text)) {
    return Number(text);
  }
  return raw;
}

function display(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export interface KeyValueEditorProps {
  value: Dict;
  onChange: (next: Dict) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  addLabel?: string;
  emptyText?: string;
}

export function KeyValueEditor({
  value,
  onChange,
  keyPlaceholder = "Attribute",
  valuePlaceholder = "Value",
  addLabel = "Add attribute",
  emptyText = "No attributes yet.",
}: KeyValueEditorProps) {
  const entries = Object.entries(value ?? {});
  const [draft, setDraft] = useState({ key: "", value: "" });

  function rename(oldKey: string, newKey: string) {
    const next: Dict = {};
    for (const [key, item] of Object.entries(value ?? {})) {
      next[key === oldKey ? newKey : key] = item;
    }
    onChange(next);
  }

  function setValue(key: string, raw: string) {
    onChange({ ...(value ?? {}), [key]: coerceValue(raw) });
  }

  function remove(key: string) {
    const next = { ...(value ?? {}) };
    delete next[key];
    onChange(next);
  }

  function add() {
    const key = draft.key.trim();
    if (!key) return;
    onChange({ ...(value ?? {}), [key]: coerceValue(draft.value) });
    setDraft({ key: "", value: "" });
  }

  return (
    <div className="space-y-2">
      {entries.length === 0 && (
        <p className="text-xs text-ink-muted dark:text-slate-400">{emptyText}</p>
      )}
      {entries.map(([key, item]) => (
        <div key={key} className="flex items-center gap-2">
          <Input
            value={key}
            onChange={(event) => rename(key, event.target.value)}
            wrapperClassName="w-2/5"
            aria-label={`${key} name`}
          />
          <Input
            value={display(item)}
            onChange={(event) => setValue(key, event.target.value)}
            wrapperClassName="flex-1"
            aria-label={`${key} value`}
          />
          <IconButton label={`Remove ${key}`} onClick={() => remove(key)}>
            <Trash2 className="h-3.5 w-3.5 text-ink-muted" />
          </IconButton>
        </div>
      ))}
      <div className="flex items-center gap-2 pt-1">
        <Input
          value={draft.key}
          onChange={(event) => setDraft((state) => ({ ...state, key: event.target.value }))}
          placeholder={keyPlaceholder}
          wrapperClassName="w-2/5"
        />
        <Input
          value={draft.value}
          onChange={(event) => setDraft((state) => ({ ...state, value: event.target.value }))}
          placeholder={valuePlaceholder}
          wrapperClassName="flex-1"
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
        />
        <Button size="sm" variant="secondary" leftIcon={<Plus className="h-3.5 w-3.5" />} onClick={add}>
          {addLabel}
        </Button>
      </div>
    </div>
  );
}

export default KeyValueEditor;
