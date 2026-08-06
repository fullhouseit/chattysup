/** Installation-wide email switch, SMTP health and a test send. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Send } from "lucide-react";
import type { NotificationStatus } from "@/lib/api";
import { Button, Switch, useToast } from "@/components/ui";
import { Card, CardHeader } from "./Card";

interface Props {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  statusQuery: () => Promise<NotificationStatus>;
  sendTest: () => Promise<{ status: string; to: string }>;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-1">
      <span className="text-ink-muted dark:text-slate-400">{label}</span>
      <span className="truncate font-mono text-ink dark:text-slate-200">{value}</span>
    </div>
  );
}

export function EmailNotificationsCard({
  enabled,
  onToggle,
  statusQuery,
  sendTest,
}: Props) {
  const toast = useToast();
  const [sending, setSending] = useState(false);

  const status = useQuery({
    queryKey: ["notifications", "status"],
    queryFn: statusQuery,
  });
  const smtp = status.data?.smtp;
  const configured = Boolean(status.data?.smtp_configured);

  async function test() {
    setSending(true);
    try {
      const result = await sendTest();
      toast.success(`Test email sent to ${result.to}`);
    } catch (error) {
      toast.error((error as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <Card flush>
      <CardHeader
        title="Email notifications"
        description="Email agents when a customer writes, with a link to the conversation."
      />
      <div className="max-w-xl space-y-4 p-5">
        {configured ? (
          <div className="flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 className="h-4 w-4" />
            SMTP is configured.
          </div>
        ) : (
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              No mail server configured. Set <code>SMTP_HOST</code> and{" "}
              <code>SMTP_FROM_EMAIL</code> in the environment and restart —
              these are deliberately not editable from the UI.
            </span>
          </div>
        )}

        <Switch
          checked={enabled}
          disabled={!configured}
          onChange={onToggle}
          label="Send email notifications"
          description="Each agent still controls what reaches their own inbox, on their profile."
        />

        {smtp ? (
          <div className="rounded-lg border border-line p-3 text-xs dark:border-slate-800">
            <Row label="Host" value={`${smtp.host ?? "—"}:${smtp.port}`} />
            <Row label="Security" value={smtp.security} />
            <Row label="Username" value={smtp.username ?? "—"} />
            <Row label="Password" value={smtp.has_password ? "set" : "not set"} />
            <Row label="From" value={`${smtp.from_name} <${smtp.from_email ?? "—"}>`} />
          </div>
        ) : null}

        <div className="flex justify-end">
          <Button
            variant="secondary"
            disabled={!configured || sending}
            onClick={() => void test()}
          >
            <Send className="mr-1.5 h-4 w-4" />
            {sending ? "Sending…" : "Send test email"}
          </Button>
        </div>
      </div>
    </Card>
  );
}

export default EmailNotificationsCard;
