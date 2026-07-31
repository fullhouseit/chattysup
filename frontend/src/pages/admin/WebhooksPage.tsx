/**
 * `/admin/webhooks` — outgoing HTTP callbacks.
 *
 * Every event the server can emit is offered as a subscription checkbox, and
 * the last delivery status is surfaced so a broken endpoint is obvious.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2, Webhook as WebhookIcon } from "lucide-react";
import { webhooks as webhooksApi } from "@/lib/api";
import { humanize, relativeTime } from "@/lib/format";
import { SECRET_MASK, type Webhook } from "@/lib/types";
import { useAppData } from "@/store/app";
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  Input,
  Modal,
  PageSpinner,
  Select,
  Switch,
  useToast,
} from "@/components/ui";
import { Card } from "./components/Card";
import { MultiSelect } from "./components/MultiSelect";
import { PageHeader } from "./components/PageHeader";
import { TableMessage, TableWrap, Td, Th, Tr } from "./components/DataTable";

interface WebhookDraft {
  name: string;
  url: string;
  secret: string;
  subscriptions: string[];
  inbox_id: number | null;
  active: boolean;
}

const EMPTY: WebhookDraft = {
  name: "",
  url: "",
  secret: "",
  subscriptions: [],
  inbox_id: null,
  active: true,
};

/** Colour the last HTTP status: 2xx green, 4xx/5xx red, nothing yet neutral. */
function statusTone(status: number | null): "success" | "danger" | "neutral" {
  if (status === null || status === undefined) return "neutral";
  return status >= 200 && status < 300 ? "success" : "danger";
}

export function WebhooksPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { inboxes } = useAppData();

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Webhook | null>(null);
  const [draft, setDraft] = useState<WebhookDraft>(EMPTY);
  const [pendingDelete, setPendingDelete] = useState<Webhook | null>(null);

  const listQuery = useQuery({ queryKey: ["webhooks"], queryFn: webhooksApi.list });
  const eventsQuery = useQuery({
    queryKey: ["webhooks", "events"],
    queryFn: webhooksApi.events,
    staleTime: Infinity,
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["webhooks"] });
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload: Partial<Webhook> = {
        name: draft.name.trim() || null,
        url: draft.url.trim(),
        subscriptions: draft.subscriptions,
        inbox_id: draft.inbox_id,
        active: draft.active,
      };
      // An untouched mask means "keep the stored secret".
      if (draft.secret !== SECRET_MASK) payload.secret = draft.secret.trim() || null;
      return editing ? webhooksApi.update(editing.id, payload) : webhooksApi.create(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Webhook updated" : "Webhook created");
      setOpen(false);
      setEditing(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not save the webhook", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => webhooksApi.remove(id),
    onSuccess: () => {
      toast.success("Webhook deleted");
      setPendingDelete(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not delete the webhook", error.message),
  });

  function startCreate() {
    setEditing(null);
    setDraft(EMPTY);
    setOpen(true);
  }

  function startEdit(webhook: Webhook) {
    setEditing(webhook);
    setDraft({
      name: webhook.name ?? "",
      url: webhook.url,
      secret: webhook.secret ?? "",
      subscriptions: [...(webhook.subscriptions ?? [])],
      inbox_id: webhook.inbox_id,
      active: webhook.active,
    });
    setOpen(true);
  }

  const list = listQuery.data ?? [];
  const events = eventsQuery.data ?? [];

  return (
    <>
      <PageHeader
        title="Webhooks"
        description="Push conversation events to your own services as they happen."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            onClick={startCreate}
          >
            New webhook
          </Button>
        }
      />

      <Card flush>
        {listQuery.isLoading ? (
          <PageSpinner />
        ) : list.length === 0 ? (
          <div className="py-10">
            <EmptyState
              icon={<WebhookIcon />}
              title="No webhooks yet"
              description="Point one at your CRM, a Slack relay or an internal dashboard."
              action={
                <Button variant="primary" onClick={startCreate}>
                  New webhook
                </Button>
              }
            />
          </div>
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <Th>Endpoint</Th>
                <Th>Events</Th>
                <Th>Last delivery</Th>
                <Th align="right" />
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <TableMessage colSpan={4}>No webhooks.</TableMessage>
              ) : (
                list.map((webhook) => (
                  <Tr key={webhook.id}>
                    <Td>
                      <span className="block truncate font-medium text-ink dark:text-slate-100">
                        {webhook.name || webhook.url}
                      </span>
                      <span className="block max-w-md truncate text-2xs text-ink-muted">
                        {webhook.url}
                      </span>
                      {!webhook.active && <Badge tone="warning">Paused</Badge>}
                    </Td>
                    <Td>
                      {webhook.subscriptions?.length ? (
                        <span className="flex flex-wrap gap-1">
                          {webhook.subscriptions.slice(0, 3).map((event) => (
                            <Badge key={event} tone="neutral">
                              {event}
                            </Badge>
                          ))}
                          {webhook.subscriptions.length > 3 && (
                            <span className="text-2xs text-ink-muted">
                              +{webhook.subscriptions.length - 3}
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-xs text-ink-muted">All events</span>
                      )}
                    </Td>
                    <Td>
                      <span className="flex flex-col gap-0.5">
                        <span className="flex items-center gap-1.5">
                          <Badge tone={statusTone(webhook.last_status)}>
                            {webhook.last_status ?? "never"}
                          </Badge>
                          {webhook.last_delivered_at && (
                            <span className="text-2xs text-ink-muted">
                              {relativeTime(webhook.last_delivered_at)} ago
                            </span>
                          )}
                        </span>
                        {webhook.last_error && (
                          <span className="max-w-xs truncate text-2xs text-red-600 dark:text-red-400">
                            {webhook.last_error}
                          </span>
                        )}
                      </span>
                    </Td>
                    <Td align="right">
                      <span className="inline-flex gap-1">
                        <IconButton label="Edit webhook" onClick={() => startEdit(webhook)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </IconButton>
                        <IconButton
                          label="Delete webhook"
                          onClick={() => setPendingDelete(webhook)}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-red-500" />
                        </IconButton>
                      </span>
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </TableWrap>
        )}
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        size="lg"
        title={editing ? "Edit webhook" : "New webhook"}
        description="We POST a JSON envelope — {event, data} — to this URL."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={saveMutation.isPending}
              disabled={!draft.url.trim()}
              onClick={() => saveMutation.mutate()}
            >
              {editing ? "Save webhook" : "Create webhook"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={draft.name}
            placeholder="CRM sync"
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <Input
            label="Endpoint URL"
            type="url"
            value={draft.url}
            placeholder="https://example.com/hooks/chattysup"
            onChange={(event) => setDraft({ ...draft, url: event.target.value })}
          />
          <Input
            label="Signing secret"
            type="password"
            value={draft.secret}
            hint="Optional. Sent as an HMAC signature header so you can verify the payload."
            onChange={(event) => setDraft({ ...draft, secret: event.target.value })}
            onFocus={() => {
              if (draft.secret === SECRET_MASK) setDraft({ ...draft, secret: "" });
            }}
          />
          <MultiSelect
            label="Events"
            hint="Leave empty to receive everything."
            options={events.map((event) => ({
              value: event,
              label: event,
              description: humanize(event.replace(".", " ")),
            }))}
            value={draft.subscriptions}
            onChange={(subscriptions) => setDraft({ ...draft, subscriptions })}
          />
          <Select
            label="Limit to an inbox"
            value={draft.inbox_id === null ? "" : String(draft.inbox_id)}
            placeholder="All inboxes"
            options={inboxes.map((inbox) => ({ value: inbox.id, label: inbox.name }))}
            onChange={(event) =>
              setDraft({
                ...draft,
                inbox_id: event.target.value === "" ? null : Number(event.target.value),
              })
            }
          />
          <Switch
            checked={draft.active}
            onChange={(active) => setDraft({ ...draft, active })}
            label="Deliver events"
            description="Turn off to pause deliveries without deleting the endpoint."
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete this webhook?"
        description={pendingDelete?.url}
        confirmLabel="Delete webhook"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default WebhooksPage;
