/**
 * `/admin/inboxes` — the grid of connected channels.
 *
 * Each card shows the channel glyph, delivery mode, live connection status and
 * the number of open conversations, plus a menu with the per-inbox actions.
 */
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox as InboxIcon, MoreVertical, Plus, Settings2, Trash2, Zap } from "lucide-react";
import { adminStats as adminStatsApi, inboxes as inboxesApi } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { AdminStats, Inbox } from "@/lib/types";
import { queryKeys } from "@/store/app";
import {
  Badge,
  Button,
  ConfirmDialog,
  Dropdown,
  DropdownItem,
  DropdownSeparator,
  EmptyState,
  IconButton,
  PageSpinner,
  useToast,
} from "@/components/ui";
import { channelStyle } from "@/components/conversations/ChannelIcon";
import { Card } from "./components/Card";
import { ConnectionDot } from "./components/ConnectionDot";
import { PageHeader } from "./components/PageHeader";

export function InboxesPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [pendingDelete, setPendingDelete] = useState<Inbox | null>(null);
  const [testing, setTesting] = useState<number | null>(null);

  const inboxesQuery = useQuery({ queryKey: queryKeys.inboxes, queryFn: inboxesApi.list });
  const statsQuery = useQuery<AdminStats>({
    queryKey: ["admin", "stats"],
    queryFn: adminStatsApi.get,
    staleTime: 30_000,
  });

  const openCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const entry of statsQuery.data?.inboxes ?? []) {
      counts.set(entry.id, entry.open_conversations);
    }
    return counts;
  }, [statsQuery.data]);

  const testMutation = useMutation({
    mutationFn: (id: number) => inboxesApi.test(id),
    onMutate: (id: number) => setTesting(id),
    onSettled: () => setTesting(null),
    onSuccess: (result: Record<string, any>) => {
      const ok = result?.ok ?? result?.success ?? result?.status === "ok";
      const detail = result?.error ?? result?.message ?? result?.detail;
      if (ok === false) toast.error("Connection failed", detail ? String(detail) : undefined);
      else toast.success("Connection is healthy");
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxes });
    },
    onError: (error: Error) => toast.error("Connection failed", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => inboxesApi.remove(id),
    onSuccess: () => {
      toast.success("Inbox deleted");
      setPendingDelete(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxes });
      queryClient.invalidateQueries({ queryKey: ["admin", "stats"] });
    },
    onError: (error: Error) => toast.error("Could not delete the inbox", error.message),
  });

  if (inboxesQuery.isLoading) return <PageSpinner />;

  const inboxes = inboxesQuery.data ?? [];

  return (
    <>
      <PageHeader
        title="Inboxes"
        description="Every channel your team answers from. Connect as many as you like."
        actions={
          <Link to="/admin/inboxes/new">
            <Button variant="primary" size="sm" leftIcon={<Plus className="h-3.5 w-3.5" />}>
              New inbox
            </Button>
          </Link>
        }
      />

      {inboxes.length === 0 ? (
        <Card className="py-10">
          <EmptyState
            icon={<InboxIcon />}
            title="No inboxes yet"
            description="Connect a channel to start receiving conversations."
            action={
              <Button variant="primary" onClick={() => navigate("/admin/inboxes/new")}>
                Connect a channel
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {inboxes.map((inbox) => {
            const { Icon, color } = channelStyle(inbox.channel_type);
            return (
              <Card key={inbox.id} className="flex flex-col gap-3">
                <div className="flex items-start gap-3">
                  <span
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white"
                    style={{ backgroundColor: color }}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/admin/inboxes/${inbox.id}`}
                      className="block truncate text-sm font-semibold text-ink hover:text-primary dark:text-slate-100"
                    >
                      {inbox.name}
                    </Link>
                    <p className="truncate text-xs capitalize text-ink-muted dark:text-slate-400">
                      {inbox.channel_type} · {inbox.mode}
                    </p>
                  </div>
                  <Dropdown
                    align="right"
                    trigger={({ toggle }) => (
                      <IconButton label="Inbox actions" onClick={toggle}>
                        <MoreVertical className="h-4 w-4" />
                      </IconButton>
                    )}
                  >
                    {({ close }) => (
                      <>
                        <DropdownItem
                          icon={<Settings2 className="h-3.5 w-3.5" />}
                          onClick={() => {
                            close();
                            navigate(`/admin/inboxes/${inbox.id}`);
                          }}
                        >
                          Settings
                        </DropdownItem>
                        <DropdownItem
                          icon={<Zap className="h-3.5 w-3.5" />}
                          onClick={() => {
                            close();
                            testMutation.mutate(inbox.id);
                          }}
                        >
                          Test connection
                        </DropdownItem>
                        <DropdownItem
                          icon={<InboxIcon className="h-3.5 w-3.5" />}
                          onClick={() => {
                            close();
                            navigate(`/conversations?inbox_id=${inbox.id}`);
                          }}
                        >
                          View conversations
                        </DropdownItem>
                        <DropdownSeparator />
                        <DropdownItem
                          danger
                          icon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => {
                            close();
                            setPendingDelete(inbox);
                          }}
                        >
                          Delete inbox
                        </DropdownItem>
                      </>
                    )}
                  </Dropdown>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <ConnectionDot status={inbox.connection_status} />
                  {!inbox.is_active && <Badge tone="warning">Disabled</Badge>}
                  {inbox.greeting_enabled && <Badge tone="neutral">Greeting</Badge>}
                  {inbox.auto_assignment_enabled && <Badge tone="neutral">Auto-assign</Badge>}
                </div>

                {inbox.connection_error && (
                  <p className="rounded-lg bg-red-50 px-2.5 py-1.5 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-300">
                    {inbox.connection_error}
                  </p>
                )}

                <div className="mt-auto flex items-center justify-between border-t border-line pt-3 text-xs text-ink-muted dark:border-slate-800 dark:text-slate-400">
                  <span className="tabular-nums">
                    {openCounts.get(inbox.id) ?? 0} open conversations
                  </span>
                  <span>
                    {inbox.last_polled_at
                      ? `Polled ${relativeTime(inbox.last_polled_at)} ago`
                      : "Never polled"}
                  </span>
                </div>

                <Button
                  size="sm"
                  variant="secondary"
                  block
                  loading={testing === inbox.id}
                  onClick={() => testMutation.mutate(inbox.id)}
                >
                  Test connection
                </Button>
              </Card>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Delete ${pendingDelete?.name ?? "inbox"}?`}
        description="Its conversations and messages are removed with it. This cannot be undone."
        confirmLabel="Delete inbox"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default InboxesPage;
