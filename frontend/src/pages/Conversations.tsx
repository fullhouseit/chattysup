/**
 * The main four-pane inbox screen (`/conversations` and `/conversations/:id`).
 *
 * PANE 1 comes from the app shell; this page owns panes 2–4: the conversation
 * list, the chat transcript with its composer, and the contact sidebar.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox as InboxIcon, MessagesSquare, Plus, Tag, X } from "lucide-react";
import { conversations as conversationsApi } from "@/lib/api";
import { humanize } from "@/lib/format";
import type {
  Conversation,
  ConversationPriority,
  ConversationStatus,
} from "@/lib/types";
import { queryKeys, useAppData, useRealtime } from "@/store/app";
import {
  Dropdown,
  DropdownItem,
  EmptyState,
  IconButton,
  Spinner,
  Tooltip,
  useToast,
} from "@/components/ui";
import { ChatHeader, type ChatTab } from "@/components/conversations/ChatHeader";
import { Composer } from "@/components/conversations/Composer";
import { ContactPanel } from "@/components/conversations/ContactPanel";
import { ConversationList } from "@/components/conversations/ConversationList";
import {
  DEFAULT_FILTERS,
  type ConversationFilterState,
} from "@/components/conversations/ConversationFilters";
import { MessageList } from "@/components/conversations/MessageList";
import type { Message } from "@/lib/types";

/** Build the filter state from the URL so links and folders are shareable. */
function filtersFromParams(params: URLSearchParams): ConversationFilterState {
  const view = params.get("view");
  const labels = (params.get("labels") ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  return {
    ...DEFAULT_FILTERS,
    status: (params.get("status") as ConversationFilterState["status"]) ?? "open",
    assignee:
      (params.get("assignee") as ConversationFilterState["assignee"]) ??
      (view === "unattended" ? "unassigned" : view === "mentions" ? "me" : "all"),
    inboxId: params.get("inbox_id") ? Number(params.get("inbox_id")) : null,
    labels,
    priority:
      (params.get("priority") as ConversationFilterState["priority"]) ?? "all",
    sort: (params.get("sort") as ConversationFilterState["sort"]) ?? "latest",
    q: params.get("q") ?? "",
  };
}

function paramsFromFilters(
  filters: ConversationFilterState,
  view: string | null,
): URLSearchParams {
  const params = new URLSearchParams();
  if (view) params.set("view", view);
  if (filters.status !== "open") params.set("status", filters.status);
  if (filters.assignee !== "all") params.set("assignee", filters.assignee);
  if (filters.inboxId) params.set("inbox_id", String(filters.inboxId));
  if (filters.labels.length) params.set("labels", filters.labels.join(","));
  if (filters.priority !== "all") params.set("priority", filters.priority);
  if (filters.sort !== "latest") params.set("sort", filters.sort);
  if (filters.q) params.set("q", filters.q);
  return params;
}

export function ConversationsPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { labels: allLabels } = useAppData();

  const view = params.get("view");
  const teamId = params.get("team_id");
  const filters = useMemo(() => filtersFromParams(params), [params]);

  const selectedId = id ? Number(id) : null;
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [tab, setTab] = useState<ChatTab>("messages");
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [scrollSignal, setScrollSignal] = useState(0);
  const composerInsert = useRef<((text: string) => void) | null>(null);

  /* ------------------------------------------------------------- filters */

  const updateFilters = useCallback(
    (patch: Partial<ConversationFilterState>) => {
      const next = { ...filters, ...patch };
      setParams(paramsFromFilters(next, view), { replace: true });
    },
    [filters, setParams, view],
  );

  /**
   * `Mentions` and `Unattended` are UI-level views layered on the REST filters:
   * mentions = my conversations with something unread, unattended = unassigned
   * conversations still waiting for a first agent reply.
   */
  const clientFilter = useMemo(() => {
    if (view === "mentions") {
      return (conversation: Conversation) => conversation.unread_count > 0;
    }
    if (view === "unattended") {
      return (conversation: Conversation) =>
        !conversation.assignee_id && conversation.status !== "resolved";
    }
    if (teamId) {
      return (conversation: Conversation) => conversation.team_id === Number(teamId);
    }
    return undefined;
  }, [view, teamId]);

  const notice =
    view === "mentions"
      ? "Conversations assigned to you with unread activity."
      : view === "unattended"
        ? "Unassigned conversations still waiting for a first reply."
        : undefined;

  /* ---------------------------------------------------- selected details */

  const conversationQuery = useQuery({
    queryKey: queryKeys.conversation(selectedId ?? 0),
    queryFn: () => conversationsApi.get(selectedId!),
    enabled: Boolean(selectedId),
  });
  const conversation = conversationQuery.data ?? null;

  // Mark as read whenever a conversation with unread activity is opened.
  useEffect(() => {
    if (!conversation || conversation.unread_count === 0) return;
    void conversationsApi
      .markRead(conversation.id)
      .then(() => {
        queryClient.invalidateQueries({ queryKey: ["conversations"] });
        queryClient.invalidateQueries({
          queryKey: queryKeys.conversation(conversation.id),
        });
      })
      .catch(() => undefined);
  }, [conversation, queryClient]);

  useRealtime<{ conversation: Conversation }>(
    "conversation.updated",
    useCallback(
      (payload) => {
        if (payload.conversation?.id !== selectedId) return;
        queryClient.setQueryData(
          queryKeys.conversation(payload.conversation.id),
          payload.conversation,
        );
      },
      [queryClient, selectedId],
    ),
  );

  const selectConversation = useCallback(
    (conversationId: number) => {
      setReplyTo(null);
      setTab("messages");
      navigate({
        pathname: `/conversations/${conversationId}`,
        search: params.toString(),
      });
    },
    [navigate, params],
  );

  /* ------------------------------------------------------------ mutations */

  const patchConversation = useCallback(
    async (patch: Record<string, unknown>) => {
      if (!conversation) return;
      try {
        const updated = await conversationsApi.update(conversation.id, patch);
        queryClient.setQueryData(queryKeys.conversation(conversation.id), updated);
        queryClient.invalidateQueries({ queryKey: ["conversations"] });
      } catch (error) {
        toast.error("Could not update the conversation", (error as Error).message);
      }
    },
    [conversation, queryClient, toast],
  );

  const setLabels = useCallback(
    async (titles: string[]) => {
      if (!conversation) return;
      try {
        const updated = await conversationsApi.setLabels(conversation.id, titles);
        queryClient.setQueryData(queryKeys.conversation(conversation.id), updated);
        queryClient.invalidateQueries({ queryKey: ["conversations"] });
      } catch (error) {
        toast.error("Could not update labels", (error as Error).message);
      }
    },
    [conversation, queryClient, toast],
  );

  /* --------------------------------------------------------------- render */

  return (
    <div className="flex h-full w-full min-w-0">
      {!listCollapsed && (
        <ConversationList
          filters={filters}
          onFiltersChange={updateFilters}
          selectedId={selectedId}
          onSelect={selectConversation}
          onCollapse={() => setListCollapsed(true)}
          clientFilter={clientFilter}
          notice={notice}
        />
      )}

      <section className="flex min-w-0 flex-1 flex-col bg-surface-muted dark:bg-[#0F141A]">
        {!selectedId ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={<MessagesSquare />}
              title="Select a conversation"
              description="Pick a conversation from the list to read the history and reply."
            />
          </div>
        ) : conversationQuery.isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Spinner size="lg" />
          </div>
        ) : !conversation ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={<InboxIcon />}
              title="Conversation not found"
              description="It may have been deleted or you no longer have access to its inbox."
            />
          </div>
        ) : (
          <>
            <ChatHeader
              conversation={conversation}
              detailsOpen={detailsOpen}
              onToggleDetails={() => setDetailsOpen((value) => !value)}
              listCollapsed={listCollapsed}
              onExpandList={() => setListCollapsed(false)}
              tab={tab}
              onTabChange={setTab}
              onStatusChange={(status: ConversationStatus, snoozedUntil) =>
                void patchConversation(
                  snoozedUntil === undefined
                    ? { status }
                    : { status, snoozed_until: snoozedUntil },
                )
              }
              onToggleMute={() => void patchConversation({ muted: !conversation.muted })}
              onCopyLink={() => {
                void navigator.clipboard
                  .writeText(`${window.location.origin}/conversations/${conversation.id}`)
                  .then(() => toast.success("Link copied"))
                  .catch(() => undefined);
              }}
            />

            {tab === "messages" ? (
              <>
                {/* Label bar */}
                <div className="flex flex-wrap items-center gap-1.5 border-b border-line bg-white px-4 py-1.5 dark:border-slate-800 dark:bg-slate-900">
                  <Tag className="h-3.5 w-3.5 text-ink-faint" />
                  {conversation.labels.map((label) => (
                    <span
                      key={label.id}
                      className="group inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-2xs font-medium text-ink-soft dark:bg-slate-800 dark:text-slate-300"
                    >
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ backgroundColor: label.color }}
                      />
                      {label.title}
                      <button
                        type="button"
                        aria-label={`Remove ${label.title}`}
                        onClick={() =>
                          void setLabels(
                            conversation.labels
                              .filter((item) => item.id !== label.id)
                              .map((item) => item.title),
                          )
                        }
                        className="text-ink-faint opacity-0 transition group-hover:opacity-100 hover:text-red-500"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  <Dropdown
                    width="w-52"
                    trigger={({ toggle }) => (
                      <Tooltip label="Add label">
                        <IconButton
                          label="Add label"
                          onClick={toggle}
                          className="h-5 w-5"
                        >
                          <Plus className="h-3 w-3" />
                        </IconButton>
                      </Tooltip>
                    )}
                  >
                    {({ close }) => (
                      <div className="max-h-64 overflow-y-auto scroll-thin">
                        {allLabels
                          .filter(
                            (label) =>
                              !conversation.labels.some((item) => item.id === label.id),
                          )
                          .map((label) => (
                            <DropdownItem
                              key={label.id}
                              icon={
                                <span
                                  className="block h-2.5 w-2.5 rounded-full"
                                  style={{ backgroundColor: label.color }}
                                />
                              }
                              onClick={() => {
                                void setLabels([
                                  ...conversation.labels.map((item) => item.title),
                                  label.title,
                                ]);
                                close();
                              }}
                            >
                              {label.title}
                            </DropdownItem>
                          ))}
                        {allLabels.length === conversation.labels.length && (
                          <p className="px-2.5 py-2 text-xs text-ink-faint">
                            All labels applied
                          </p>
                        )}
                      </div>
                    )}
                  </Dropdown>
                </div>

                <MessageList
                  key={conversation.id}
                  conversationId={conversation.id}
                  contact={conversation.contact}
                  onReply={setReplyTo}
                  scrollSignal={scrollSignal}
                />

                <Composer
                  key={`composer-${conversation.id}`}
                  conversationId={conversation.id}
                  replyTo={replyTo}
                  onClearReply={() => setReplyTo(null)}
                  onSent={() => setScrollSignal((value) => value + 1)}
                  insertRef={composerInsert}
                />
              </>
            ) : (
              <CustomerDashboard conversation={conversation} />
            )}
          </>
        )}
      </section>

      {conversation && detailsOpen && (
        <ContactPanel
          conversation={conversation}
          onUpdateConversation={(patch) => void patchConversation(patch)}
          onInsertCanned={(content) => composerInsert.current?.(content)}
          onSelectConversation={selectConversation}
          onClose={() => setDetailsOpen(false)}
        />
      )}
    </div>
  );
}

/** The second chat tab — a read-only summary of the customer's context. */
function CustomerDashboard({ conversation }: { conversation: Conversation }) {
  const contact = conversation.contact;
  const priorityLabel: Record<ConversationPriority, string> = {
    none: "None",
    low: "Low",
    medium: "Medium",
    high: "High",
    urgent: "Urgent",
  };

  const cards = [
    { label: "Status", value: humanize(conversation.status) },
    { label: "Priority", value: priorityLabel[conversation.priority] },
    { label: "Assignee", value: conversation.assignee?.display_name ?? "Unassigned" },
    { label: "Inbox", value: conversation.inbox?.name ?? "—" },
    { label: "Unread", value: String(conversation.unread_count) },
    { label: "Labels", value: String(conversation.labels.length) },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6 scroll-thin">
      <div className="mx-auto max-w-2xl space-y-4">
        <div className="rounded-xl border border-line bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
          <h3 className="text-md font-semibold text-ink dark:text-slate-100">
            {contact?.name ?? "Unknown contact"}
          </h3>
          <p className="mt-0.5 text-sm text-ink-muted dark:text-slate-400">
            {[contact?.title, contact?.company].filter(Boolean).join(" @ ") ||
              "No company information"}
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {cards.map((card) => (
              <div
                key={card.label}
                className="rounded-lg bg-surface-muted p-3 dark:bg-slate-800"
              >
                <dt className="text-2xs uppercase tracking-wide text-ink-faint">
                  {card.label}
                </dt>
                <dd className="mt-0.5 truncate text-sm font-medium text-ink dark:text-slate-100">
                  {card.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        {Object.keys(contact?.custom_attributes ?? {}).length > 0 && (
          <div className="rounded-xl border border-line bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
            <h4 className="text-sm font-semibold text-ink dark:text-slate-100">
              Customer attributes
            </h4>
            <dl className="mt-3 space-y-1.5">
              {Object.entries(contact!.custom_attributes).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-4 text-sm">
                  <dt className="text-ink-muted dark:text-slate-400">{humanize(key)}</dt>
                  <dd className="truncate text-ink dark:text-slate-200">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}

export default ConversationsPage;
