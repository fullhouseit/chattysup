/** Per-agent email notification preferences, shown on the profile screen. */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Mail } from "lucide-react";
import { notifications as api, type NotificationPrefs } from "@/lib/api";
import { Select, Spinner, Switch, useToast } from "@/components/ui";

const ROWS: { key: keyof NotificationPrefs; label: string; hint: string }[] = [
  {
    key: "assigned",
    label: "Conversations assigned to me",
    hint: "Every new message in a conversation I own.",
  },
  {
    key: "unassigned",
    label: "Unassigned conversations",
    hint: "New messages nobody has picked up yet.",
  },
  {
    key: "participating",
    label: "Conversations I follow",
    hint: "Threads I was added to as a participant.",
  },
  {
    key: "others",
    label: "Everyone else's conversations",
    hint: "Off by default — this is every message in the whole workspace.",
  },
  {
    key: "private_notes",
    label: "Private notes from teammates",
    hint: "Internal notes left on conversations I would be emailed about.",
  },
  {
    key: "skip_when_online",
    label: "Skip while I have the app open",
    hint: "Do not email me about something I can already see.",
  },
];

const INTERVALS = [
  { value: "0", label: "Every message" },
  { value: "300", label: "At most one per 5 minutes" },
  { value: "900", label: "At most one per 15 minutes" },
  { value: "3600", label: "At most one per hour" },
];

export function NotificationPreferences() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ["notifications", "status"],
    queryFn: api.status,
  });
  const prefsQuery = useQuery({
    queryKey: ["notifications", "preferences"],
    queryFn: api.preferences,
  });

  const [enabled, setEnabled] = useState(false);
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);

  useEffect(() => {
    if (prefsQuery.data) {
      setEnabled(prefsQuery.data.email_notifications);
      setPrefs(prefsQuery.data.preferences);
    }
  }, [prefsQuery.data]);

  const save = useMutation({
    mutationFn: api.updatePreferences,
    onSuccess: (data) => {
      setEnabled(data.email_notifications);
      setPrefs(data.preferences);
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (prefsQuery.isLoading || !prefs) {
    return (
      <section className="rounded-xl border border-line bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
        <Spinner />
      </section>
    );
  }

  const status = statusQuery.data;
  const inactive = status && !status.operational;

  return (
    <section className="rounded-xl border border-line bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-slate-100">
            <Mail className="h-4 w-4" /> Email notifications
          </h3>
          <p className="mt-1 text-xs text-ink-muted dark:text-slate-400">
            Get an email with the message text and a link straight to the chat.
          </p>
        </div>
        <Switch
          checked={enabled}
          onChange={(value) => {
            setEnabled(value);
            save.mutate({ email_notifications: value });
          }}
        />
      </div>

      {inactive ? (
        <div className="mt-4 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {status?.reason} Your preferences are saved and will apply once it is on.
          </span>
        </div>
      ) : null}

      <div
        className={
          enabled ? "mt-4 space-y-3" : "mt-4 space-y-3 opacity-50 pointer-events-none"
        }
      >
        {ROWS.map((row) => (
          <div key={row.key} className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-sm text-ink dark:text-slate-200">{row.label}</div>
              <div className="text-xs text-ink-muted dark:text-slate-400">{row.hint}</div>
            </div>
            <Switch
              checked={Boolean(prefs[row.key])}
              onChange={(value) => {
                setPrefs({ ...prefs, [row.key]: value });
                save.mutate({ [row.key]: value });
              }}
            />
          </div>
        ))}

        <div className="flex items-center justify-between gap-4 border-t border-line pt-3 dark:border-slate-800">
          <div>
            <div className="text-sm text-ink dark:text-slate-200">Frequency</div>
            <div className="text-xs text-ink-muted dark:text-slate-400">
              How often a single conversation may email me.
            </div>
          </div>
          <Select
            className="w-56"
            value={String(prefs.min_interval_seconds)}
            onChange={(event) => {
              const value = Number(event.target.value);
              setPrefs({ ...prefs, min_interval_seconds: value });
              save.mutate({ min_interval_seconds: value });
            }}
          >
            {INTERVALS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
      </div>
    </section>
  );
}

export default NotificationPreferences;
