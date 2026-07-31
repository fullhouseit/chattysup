/**
 * `/admin` — the workspace overview.
 *
 * Stat cards summarising `GET /admin/stats`, a per-inbox connection health
 * table with an on-demand "Test connection" probe, and a compact activity feed.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Clock,
  Inbox as InboxIcon,
  MessageSquare,
  PlugZap,
  RefreshCw,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import { adminStats as adminStatsApi, inboxes as inboxesApi } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { AdminStats } from "@/lib/types";
import { queryKeys } from "@/store/app";
import { Button, EmptyState, PageSpinner, useToast } from "@/components/ui";
import { ChannelIcon } from "@/components/conversations/ChannelIcon";
import { Card, CardHeader } from "./components/Card";
import { ConnectionDot } from "./components/ConnectionDot";
import { PageHeader } from "./components/PageHeader";
import { TableWrap, Td, Th, Tr } from "./components/DataTable";

interface StatCardProps {
  label: string;
  value: number | string;
  icon: LucideIcon;
  tone: string;
  to?: string;
  hint?: string;
}

function StatCard({ label, value, icon: Icon, tone, to, hint }: StatCardProps) {
  const body = (
    <Card className="h-full transition-shadow hover:shadow-pop">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted dark:text-slate-400">
            {label}
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-ink dark:text-slate-100">
            {value}
          </p>
          {hint && <p className="mt-0.5 text-xs text-ink-muted dark:text-slate-400">{hint}</p>}
        </div>
        <span className={`rounded-lg p-2 ${tone}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
    </Card>
  );
  return to ? (
    <Link to={to} className="focus-ring block rounded-xl">
      {body}
    </Link>
  ) : (
    body
  );
}

/** Human sentence for one `recent_activity` entry, whatever keys it carries. */
function activityLine(entry: Record<string, any>): string {
  if (typeof entry.text === "string") return entry.text;
  if (typeof entry.message === "string") return entry.message;
  const contact = entry.contact_name ?? entry.contact ?? "Someone";
  const inbox = entry.inbox_name ?? entry.inbox;
  return inbox ? `${contact} — ${inbox}` : String(contact);
}

export function DashboardPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [testing, setTesting] = useState<number | null>(null);

  const statsQuery = useQuery<AdminStats>({
    queryKey: ["admin", "stats"],
    queryFn: adminStatsApi.get,
    refetchInterval: 60_000,
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => inboxesApi.test(id),
    onMutate: (id: number) => setTesting(id),
    onSettled: () => setTesting(null),
    onSuccess: (result: Record<string, any>) => {
      const ok = result?.ok ?? result?.success ?? result?.status === "ok";
      const detail =
        result?.error ?? result?.message ?? result?.detail ?? result?.status ?? undefined;
      if (ok === false) toast.error("Connection failed", detail ? String(detail) : undefined);
      else toast.success("Connection is healthy", detail ? String(detail) : undefined);
      queryClient.invalidateQueries({ queryKey: ["admin", "stats"] });
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxes });
    },
    onError: (error: Error) => toast.error("Connection failed", error.message),
  });

  if (statsQuery.isLoading) return <PageSpinner />;

  if (statsQuery.isError) {
    return (
      <EmptyState
        icon={<PlugZap />}
        title="Could not load the dashboard"
        description={(statsQuery.error as Error).message}
        action={
          <Button variant="secondary" onClick={() => statsQuery.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  const stats = statsQuery.data!;
  const conversations = stats.conversations;

  return (
    <>
      <PageHeader
        title="Overview"
        description="How your workspace is doing right now."
        actions={
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            onClick={() => statsQuery.refetch()}
            loading={statsQuery.isFetching}
          >
            Refresh
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Open"
          value={conversations.open}
          icon={MessageSquare}
          tone="bg-primary-50 text-primary dark:bg-primary-900/30 dark:text-primary-300"
          to="/conversations?status=open"
        />
        <StatCard
          label="Pending"
          value={conversations.pending}
          icon={Clock}
          tone="bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-300"
          to="/conversations?status=pending"
        />
        <StatCard
          label="Resolved"
          value={conversations.resolved}
          icon={CheckCircle2}
          tone="bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300"
          to="/conversations?status=resolved"
        />
        <StatCard
          label="Snoozed"
          value={conversations.snoozed}
          icon={Clock}
          tone="bg-violet-50 text-violet-600 dark:bg-violet-900/30 dark:text-violet-300"
          to="/conversations?status=snoozed"
          hint={`${conversations.total} conversations in total`}
        />
        <StatCard
          label="Messages today"
          value={stats.messages_today}
          icon={MessageSquare}
          tone="bg-sky-50 text-sky-600 dark:bg-sky-900/30 dark:text-sky-300"
        />
        <StatCard
          label="Contacts"
          value={stats.contacts}
          icon={Users}
          tone="bg-slate-100 text-ink-soft dark:bg-slate-800 dark:text-slate-300"
          to="/contacts"
        />
        <StatCard
          label="Agents online"
          value={`${stats.agents_online} / ${stats.agents}`}
          icon={UserCheck}
          tone="bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-300"
          to="/admin/agents"
        />
        <StatCard
          label="Inboxes"
          value={stats.inboxes.length}
          icon={InboxIcon}
          tone="bg-primary-50 text-primary dark:bg-primary-900/30 dark:text-primary-300"
          to="/admin/inboxes"
        />
      </div>

      <Card flush className="mt-5">
        <CardHeader
          title="Channel health"
          description="Live connection status for every inbox."
          actions={
            <Link to="/admin/inboxes">
              <Button variant="secondary" size="xs">
                Manage inboxes
              </Button>
            </Link>
          }
        />
        <TableWrap>
          <thead>
            <tr>
              <Th>Inbox</Th>
              <Th>Channel</Th>
              <Th>Status</Th>
              <Th align="right">Open</Th>
              <Th align="right" />
            </tr>
          </thead>
          <tbody>
            {stats.inboxes.length === 0 ? (
              <tr>
                <Td colSpan={5} className="py-10 text-center">
                  <span className="text-sm text-ink-muted">
                    No inboxes yet.{" "}
                    <Link to="/admin/inboxes/new" className="text-primary hover:underline">
                      Connect your first channel
                    </Link>
                    .
                  </span>
                </Td>
              </tr>
            ) : (
              stats.inboxes.map((inbox) => (
                <Tr key={inbox.id}>
                  <Td>
                    <Link
                      to={`/admin/inboxes/${inbox.id}`}
                      className="font-medium text-ink hover:text-primary dark:text-slate-100"
                    >
                      {inbox.name}
                    </Link>
                  </Td>
                  <Td>
                    <span className="inline-flex items-center gap-1.5">
                      <ChannelIcon channelType={inbox.channel_type} />
                      <span className="capitalize">{inbox.channel_type}</span>
                    </span>
                  </Td>
                  <Td>
                    <ConnectionDot status={inbox.connection_status} />
                  </Td>
                  <Td align="right" className="tabular-nums">
                    {inbox.open_conversations}
                  </Td>
                  <Td align="right">
                    <Button
                      size="xs"
                      variant="secondary"
                      loading={testing === inbox.id}
                      onClick={() => testMutation.mutate(inbox.id)}
                    >
                      Test connection
                    </Button>
                  </Td>
                </Tr>
              ))
            )}
          </tbody>
        </TableWrap>
      </Card>

      <Card flush className="mt-5">
        <CardHeader title="Recent activity" />
        {stats.recent_activity.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-ink-muted dark:text-slate-400">
            Nothing has happened yet today.
          </p>
        ) : (
          <ul className="divide-y divide-line dark:divide-slate-800">
            {stats.recent_activity.slice(0, 12).map((entry, index) => (
              <li
                key={(entry.id as number) ?? index}
                className="flex items-center gap-3 px-5 py-2.5 text-sm"
              >
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                <span className="min-w-0 flex-1 truncate text-ink-soft dark:text-slate-300">
                  {entry.conversation_id ? (
                    <Link
                      to={`/conversations/${entry.conversation_id}`}
                      className="hover:text-primary"
                    >
                      {activityLine(entry)}
                    </Link>
                  ) : (
                    activityLine(entry)
                  )}
                </span>
                <span className="shrink-0 text-xs text-ink-faint">
                  {relativeTime((entry.created_at as string) ?? null)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

export default DashboardPage;
