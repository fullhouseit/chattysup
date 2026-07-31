/**
 * `/admin/inboxes/new` — the two-step "connect a channel" wizard.
 *
 * Step 1 lists everything `GET /channels` advertises; step 2 renders the
 * configuration form generated from that channel's `config_fields` together
 * with the behaviour options the channel supports.
 */
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { channels as channelsApi, inboxes as inboxesApi } from "@/lib/api";
import type { ChannelDescriptor } from "@/lib/types";
import { queryKeys } from "@/store/app";
import { Badge, Button, PageSpinner, useToast } from "@/components/ui";
import { channelStyle } from "@/components/conversations/ChannelIcon";
import { Card, CardHeader } from "./components/Card";
import { PageHeader } from "./components/PageHeader";
import {
  BehaviourFields,
  ConfigurationFields,
  emptyInboxForm,
  missingRequired,
  toInboxPayload,
  type InboxFormState,
} from "./components/InboxForm";

function StepDot({
  index,
  label,
  current,
}: {
  index: number;
  label: string;
  current: number;
}) {
  const done = current > index;
  const active = current === index;
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          "flex h-6 w-6 items-center justify-center rounded-full text-2xs font-semibold",
          done && "bg-emerald-500 text-white",
          active && "bg-primary text-white",
          !done && !active && "bg-slate-200 text-ink-muted dark:bg-slate-700 dark:text-slate-400",
        )}
      >
        {done ? <Check className="h-3 w-3" /> : index + 1}
      </span>
      <span
        className={cn(
          "text-sm",
          active
            ? "font-medium text-ink dark:text-slate-100"
            : "text-ink-muted dark:text-slate-400",
        )}
      >
        {label}
      </span>
    </div>
  );
}

export function InboxNewPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [step, setStep] = useState(0);
  const [channelKey, setChannelKey] = useState<string | null>(null);
  const [form, setForm] = useState<InboxFormState>(() => emptyInboxForm(null));

  const channelsQuery = useQuery({ queryKey: ["channels"], queryFn: channelsApi.list });
  const channel = useMemo(
    () => channelsQuery.data?.find((item) => item.key === channelKey) ?? null,
    [channelsQuery.data, channelKey],
  );

  const createMutation = useMutation({
    mutationFn: () => inboxesApi.create(toInboxPayload(form, channelKey ?? undefined)),
    onSuccess: (inbox) => {
      toast.success("Inbox created", `${inbox.name} is ready to receive messages.`);
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxes });
      queryClient.invalidateQueries({ queryKey: ["admin", "stats"] });
      navigate(`/admin/inboxes/${inbox.id}`);
    },
    onError: (error: Error) => toast.error("Could not create the inbox", error.message),
  });

  function pick(descriptor: ChannelDescriptor) {
    setChannelKey(descriptor.key);
    setForm(emptyInboxForm(descriptor));
    setStep(1);
  }

  function patch(next: Partial<InboxFormState>) {
    setForm((state) => ({ ...state, ...next }));
  }

  const missing = missingRequired(channel, form);
  const canSubmit = Boolean(channel) && form.name.trim().length > 0 && missing.length === 0;

  if (channelsQuery.isLoading) return <PageSpinner />;

  return (
    <>
      <PageHeader
        above={
          <Link
            to="/admin/inboxes"
            className="inline-flex items-center gap-1.5 text-sm text-ink-muted transition hover:text-ink dark:text-slate-400"
          >
            <ArrowLeft className="h-4 w-4" /> Back to inboxes
          </Link>
        }
        title="Connect a channel"
        description="Pick where the conversations will come from, then fill in its credentials."
      />

      <div className="mb-5 flex items-center gap-3">
        <StepDot index={0} label="Channel" current={step} />
        <ChevronRight className="h-4 w-4 text-ink-faint" />
        <StepDot index={1} label="Configuration" current={step} />
      </div>

      {step === 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {(channelsQuery.data ?? []).map((descriptor) => {
            const { Icon, color } = channelStyle(descriptor.key);
            return (
              <button
                key={descriptor.key}
                type="button"
                onClick={() => pick(descriptor)}
                className="focus-ring rounded-xl text-left"
              >
                <Card className="h-full transition-shadow hover:shadow-pop">
                  <div className="flex items-start gap-3">
                    <span
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white"
                      style={{ backgroundColor: descriptor.color || color }}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-ink dark:text-slate-100">
                        {descriptor.display_name}
                      </p>
                      <p className="mt-0.5 text-xs text-ink-muted dark:text-slate-400">
                        {descriptor.description}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {descriptor.supports_polling && <Badge tone="neutral">Polling</Badge>}
                    {descriptor.supports_webhook && <Badge tone="neutral">Webhook</Badge>}
                    {descriptor.supports_proxy && <Badge tone="neutral">Proxy</Badge>}
                  </div>
                </Card>
              </button>
            );
          })}
          {(channelsQuery.data ?? []).length === 0 && (
            <Card className="sm:col-span-2 xl:col-span-3">
              <p className="text-sm text-ink-muted dark:text-slate-400">
                No channels are registered on this server.
              </p>
            </Card>
          )}
        </div>
      )}

      {step === 1 && channel && (
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit) createMutation.mutate();
          }}
        >
          <Card flush>
            <CardHeader
              title={`${channel.display_name} connection`}
              description={channel.description}
              actions={
                <Button variant="ghost" size="xs" onClick={() => setStep(0)}>
                  Change channel
                </Button>
              }
            />
            <div className="p-5">
              <ConfigurationFields channel={channel} state={form} onChange={patch} />
            </div>
          </Card>

          <Card flush>
            <CardHeader
              title="Behaviour"
              description="Greetings, business hours and assignment rules for this inbox."
            />
            <div className="p-5">
              <BehaviourFields channel={channel} state={form} onChange={patch} />
            </div>
          </Card>

          {missing.length > 0 && (
            <p className="text-xs text-amber-700 dark:text-amber-300">
              Still required: {missing.join(", ")}.
            </p>
          )}

          <div className="flex items-center gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={!canSubmit}
              loading={createMutation.isPending}
            >
              Create inbox
            </Button>
            <Button variant="ghost" onClick={() => navigate("/admin/inboxes")}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </>
  );
}

export default InboxNewPage;
