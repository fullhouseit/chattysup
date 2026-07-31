/**
 * Editor for `Inbox.working_hours`.
 *
 * The shape matches what `services/automation.py` reads back:
 *
 * ```json
 * { "enabled": true, "days": { "0": { "enabled": true, "start": "09:00", "end": "17:00" } } }
 * ```
 *
 * Keys are Python `date.weekday()` indices, i.e. `0` = Monday … `6` = Sunday.
 */
import type { Dict } from "@/lib/types";
import { Switch } from "@/components/ui";

const DAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

interface DayHours {
  enabled: boolean;
  start: string;
  end: string;
}

function readDay(hours: Dict, index: number): DayHours {
  const day = (hours?.days ?? {})[String(index)] ?? {};
  return {
    enabled: Boolean(day.enabled),
    start: typeof day.start === "string" ? day.start : "09:00",
    end: typeof day.end === "string" ? day.end : "17:00",
  };
}

export interface WorkingHoursEditorProps {
  value: Dict;
  onChange: (next: Dict) => void;
}

export function WorkingHoursEditor({ value, onChange }: WorkingHoursEditorProps) {
  const hours = value ?? {};
  const enabled = Boolean(hours.enabled);

  function patchDay(index: number, patch: Partial<DayHours>) {
    const current = readDay(hours, index);
    onChange({
      ...hours,
      enabled,
      days: {
        ...(hours.days ?? {}),
        [String(index)]: { ...current, ...patch },
      },
    });
  }

  return (
    <div className="space-y-3">
      <Switch
        checked={enabled}
        onChange={(next) => onChange({ ...hours, enabled: next, days: hours.days ?? {} })}
        label="Enable business hours"
        description="Outside these hours new conversations get the out-of-office reply."
      />
      {enabled && (
        <div className="divide-y divide-line rounded-lg border border-line dark:divide-slate-800 dark:border-slate-700">
          {DAYS.map((name, index) => {
            const day = readDay(hours, index);
            return (
              <div key={name} className="flex items-center gap-3 px-3 py-2">
                <label className="flex w-32 shrink-0 cursor-pointer items-center gap-2 text-sm text-ink dark:text-slate-200">
                  <input
                    type="checkbox"
                    checked={day.enabled}
                    onChange={(event) => patchDay(index, { enabled: event.target.checked })}
                    className="h-3.5 w-3.5 rounded border-line text-primary focus:ring-primary-200 dark:border-slate-600 dark:bg-slate-800"
                  />
                  {name}
                </label>
                <input
                  type="time"
                  value={day.start}
                  disabled={!day.enabled}
                  onChange={(event) => patchDay(index, { start: event.target.value })}
                  className="h-8 rounded-lg border border-line bg-white px-2 text-sm text-ink disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                />
                <span className="text-xs text-ink-muted">to</span>
                <input
                  type="time"
                  value={day.end}
                  disabled={!day.enabled}
                  onChange={(event) => patchDay(index, { end: event.target.value })}
                  className="h-8 rounded-lg border border-line bg-white px-2 text-sm text-ink disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default WorkingHoursEditor;
