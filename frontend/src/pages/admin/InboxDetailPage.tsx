/**
 * `/admin/inboxes/:id` — settings for one connected channel.
 *
 * Four tabs: the dynamic connection form, behaviour options, the collaborator
 * roster and a danger zone. Secrets come back masked and are posted back
 * untouched unless the administrator actually types a replacement.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Zap } from "lucide-react";
import { channels as channelsApi, inboxes as inboxesApi, users as usersApi } from "@/lib/api";
import { fullTimestamp } from "@/lib/format";
import type { Inbox } from "@/lib/types";
import { queryKeys } from "@/store/app";
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  PageSpinner,
  Switch,
  Tabs,
  useToast,
} from "@/components/ui";
import { channelStyle } from "@/components/conversations/ChannelIcon";
import { Card, CardHeader } from "./components/Card";
import { ConnectionDot } from "./components/ConnectionDot";
import { CopyButton } from "./components/CopyButton";
import { MultiSelect } from "./components/MultiSelect";
import { PageHeader } from "./components/PageHeader";
import {
  BehaviourFields,
  ConfigurationFields,
  inboxFormFromInbox,
  toInboxPayload,
  type InboxFormState,
} from "./components/InboxForm";

type TabKey = "configuration" | "behaviour" | "collaborators" | "danger";

export function InboxDetailPage() {
  const { id } = useParams();
  const inboxId = Number(id);
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<TabKey>("configuration");
  const [form, setForm] = useState<InboxFormState | null>(null);
  const [memberIds, setMemberIds] = useState<number[] | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const inboxQuery = useQuery({
    queryKey: ["inbox", inboxId],
    queryFn: () => inboxesApi.get(inboxId),
    enabled: Number.isFinite(inboxId),
  });
  const channelsQuery = useQuery({ queryKey: ["channels"], queryFn: channelsApi.list });
  const agentsQuery = useQuery({ queryKey: queryKeys.agents, queryFn: usersApi.list });
  const membersQuery = useQuery({
    queryKey: ["inbox", inboxId, "members"],
    queryFn: () => inboxesApi.members(inboxId),
    enabled: Number.isFinite(inboxId),
  });

  const inbox: Inbox | undefined = inboxQuery.data;
  const channel = useMemo(
    () => channelsQuery.data?.find((item) => item.key === inbox?.channel_type) ?? null,
    [channelsQuery.data, inbox],
  );

  // Hydrate the editable copies once each source query settles.
  useEffect(() => {
    if (inbox) setForm(inboxFormFromInbox(inbox));
  }, [inbox]);
  useEffect(() => {
    if (membersQuery.data) setMemberIds(membersQuery.data.user_ids ?? []);
  }, [membersQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => inboxesApi.update(inboxId, toInboxPayload(form!)),
    onSuccess: (next) => {
      toast.success("Inbox saved");
      queryClient.setQueryData(["inbox", inboxId], next);
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxes });
    },
    onError: (error: Error) => toast.error("Could not save the inbox", error.message),
  });

  const activeMutation = useMutation({
    mutationFn: (is_active: boolean) => inboxesApi.update(inboxId, { is_active }),
    onSuccess: (next) => {
      queryClient.setQueryData(["inbox", inboxId], next);
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxes });
      toast.success(next.is_active ? "Inbox enabled" : "Inbox disabled");
    },
    onError: (error: Error) => toast.error("Could not update the inbox", error.message),
  });

  const membersMutation = useMutation({
    mutationFn: (userIds: number[]) => inboxesApi.setMembers(inboxId, userIds),
    onSuccess: () => {
      toast.success("Collaborators updated");
      queryClient.invalidateQueries({ queryKey: ["inbox", inboxId, "members"] });
    },
    onError: (error: Error) => toast.error("Could not update collaborators", error.message),
  });

  const testMutation = useMutation({
    mutationFn: () => inboxesApi.test(inboxId),
    onSuccess: (result: Record<string, any>) => {
      const ok = result?.ok ?? result?.success ?? result?.status === "ok";
      const detail = result?.error ?? result?.message ?? result?.detail;
      if (ok === false) toast.error("Connection failed", detail ? String(detail) : undefined);
      else toast.success("Connection is healthy", detail ? String(detail) : undefined);
      queryClient.invalidateQueries({ queryKey: ["inbox", inboxId] });
    },
    onError: (error: Error) => toast.error("Connection failed", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => inboxesApi.remove(inboxId),
    onSuccess: () => {
      toast.success("Inbox deleted");
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxes });
      navigate("/admin/inboxes");
    },
    onError: (error: Error) => toast.error("Could not delete the inbox", error.message),
  });

  if (inboxQuery.isLoading || !form) return <PageSpinner />;

  if (inboxQuery.isError || !inbox) {
    return (
      <EmptyState
        title="Inbox not found"
        description="It may have been deleted."
        action={
          <Link to="/admin/inboxes">
            <Button variant="secondary">Back to inboxes</Button>
          </Link>
        }
      />
    );
  }

  const { Icon, color } = channelStyle(inbox.channel_type);
  const patch = (next: Partial<InboxFormState>) =>
    setForm((state) => (state ? { ...state, ...next } : state));

  const webhookBlock =
    inbox.mode === "webhook" && inbox.webhook_url ? (
      <div className="rounded-lg border border-line bg-surface-muted p-3 dark:border-slate-700 dark:bg-slate-800/60">
        <p className="text-xs font-medium text-ink-soft dark:text-slate-300">Webhook URL</p>
        <div className="mt-1.5 flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate rounded bg-white px-2 py-1 text-xs text-ink dark:bg-slate-900 dark:text-slate-200">
            {inbox.webhook_url}
          </code>
          <CopyButton value={inbox.webhook_url} label="Copy webhook URL" />
        </div>
        <p className="mt-1.5 text-2xs text-ink-muted dark:text-slate-400">
          Register this address with the provider so it can push updates to ChattySup.
        </p>
      </div>
    ) : null;

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
        title={
          <span className="flex items-center gap-2.5">
            <span
              className="flex h-8 w-8 items-center justify-center rounded-lg text-white"
              style={{ backgroundColor: color }}
            >
              <Icon className="h-4 w-4" />
            </span>
            {inbox.name}
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span className="capitalize">
              {inbox.channel_type} · {inbox.mode}
            </span>
            <ConnectionDot status={inbox.connection_status} />
            {!inbox.is_active && <Badge tone="warning">Disabled</Badge>}
          </span>
        }
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<Zap className="h-3.5 w-3.5" />}
              loading={testMutation.isPending}
              onClick={() => testMutation.mutate()}
            >
              Test connection
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              Save changes
            </Button>
          </>
        }
      />

      {inbox.connection_error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-300">
          {inbox.connection_error}
        </p>
      )}

      <Card flush>
        <Tabs
          value={tab}
          onChange={(key) => setTab(key as TabKey)}
          items={[
            { key: "configuration", label: "Configuration" },
            { key: "behaviour", label: "Behaviour" },
            { key: "collaborators", label: "Collaborators" },
            { key: "danger", label: "Danger zone" },
          ]}
        />

        <div className="p-5">
          {tab === "configuration" && (
            <div className="max-w-xl space-y-4">
              <ConfigurationFields
                channel={channel}
                state={form}
                onChange={patch}
                footer={webhookBlock}
              />
              <dl className="grid grid-cols-2 gap-3 border-t border-line pt-4 text-xs dark:border-slate-800">
                <div>
                  <dt className="text-ink-muted dark:text-slate-400">Created</dt>
                  <dd className="text-ink dark:text-slate-200">
                    {fullTimestamp(inbox.created_at) || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-muted dark:text-slate-400">Last polled</dt>
                  <dd className="text-ink dark:text-slate-200">
                    {fullTimestamp(inbox.last_polled_at) || "Never"}
                  </dd>
                </div>
              </dl>
            </div>
          )}

          {tab === "behaviour" && (
            <div className="max-w-xl">
              <BehaviourFields channel={channel} state={form} onChange={patch} />
            </div>
          )}

          {tab === "collaborators" && (
            <div className="max-w-xl space-y-3">
              <MultiSelect
                label="Agents who can answer this inbox"
                hint="Leave empty to let every agent see it."
                options={(agentsQuery.data ?? []).map((agent) => ({
                  value: agent.id,
                  label: agent.display_name || agent.name,
                  description: agent.email,
                }))}
                value={memberIds ?? []}
                onChange={setMemberIds}
              />
              <Button
                variant="primary"
                size="sm"
                loading={membersMutation.isPending}
                onClick={() => membersMutation.mutate(memberIds ?? [])}
              >
                Save collaborators
              </Button>
            </div>
          )}

          {tab === "danger" && (
            <div className="max-w-xl space-y-5">
              <Switch
                checked={inbox.is_active}
                onChange={(next) => activeMutation.mutate(next)}
                label="Inbox is active"
                description="Disabling stops polling and rejects new inbound messages while keeping history."
              />
              <div className="rounded-lg border border-red-200 p-4 dark:border-red-900/50">
                <p className="text-sm font-semibold text-red-700 dark:text-red-300">
                  Delete this inbox
                </p>
                <p className="mt-1 text-xs text-ink-muted dark:text-slate-400">
                  All of its conversations, messages and attachments are deleted too. This
                  cannot be undone.
                </p>
                <Button
                  variant="danger"
                  size="sm"
                  className="mt-3"
                  onClick={() => setConfirmDelete(true)}
                >
                  Delete inbox
                </Button>
              </div>
            </div>
          )}
        </div>
      </Card>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${inbox.name}?`}
        description="Every conversation from this channel will be removed. This cannot be undone."
        confirmLabel="Delete inbox"
        tone="danger"
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => deleteMutation.mutate()}
      />
    </>
  );
}

export default InboxDetailPage;
