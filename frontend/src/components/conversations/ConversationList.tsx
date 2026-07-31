/**
 * PANE 2 — the paginated, filterable conversation list.
 *
 * Data comes from `GET /conversations` through an infinite query; realtime
 * events invalidate it so new and updated conversations appear without a
 * refresh. Scrolling near the bottom loads the next page automatically.
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox as InboxIcon } from "lucide-react";
import { conversations as conversationsApi } from "@/lib/api";
import type { Conversation, ConversationQuery, Paginated } from "@/lib/types";
import { useAppData, useRealtime } from "@/store/app";
import { Button, EmptyState, Spinner, Tabs } from "@/components/ui";
import {
  ConversationFilters,
  type ConversationFilterState,
} from "./ConversationFilters";
import { ConversationListItem } from "./ConversationListItem";

const PER_PAGE = 25;

export interface ConversationListProps {
  filters: ConversationFilterState;
  onFiltersChange: (patch: Partial<ConversationFilterState>) => void;
  selectedId: number | null;
  onSelect: (id: number) => void;
  onCollapse?: () => void;
  /** Extra client-side predicate for the pseudo views (Mentions, Unattended). */
  clientFilter?: (conversation: Conversation) => boolean;
  /** Banner explaining an active pseudo view. */
  notice?: string;
}

/** Translate the UI filter state into the REST query parameters. */
export function toQuery(
  filters: ConversationFilterState,
  page: number,
): ConversationQuery {
  return {
    status: filters.status,
    assignee: filters.assignee,
    inbox_id: filters.inboxId ?? undefined,
    labels: filters.labels.length ? filters.labels.join(",") : undefined,
    priority: filters.priority === "all" ? undefined : filters.priority,
    q: filters.q || undefined,
    sort: filters.sort,
    page,
    per_page: PER_PAGE,
  };
}

export function ConversationList({
  filters,
  onFiltersChange,
  selectedId,
  onSelect,
  onCollapse,
  clientFilter,
  notice,
}: ConversationListProps) {
  const queryClient = useQueryClient();
  const { connection } = useAppData();
  const scroller = useRef<HTMLDivElement>(null);

  const key = useMemo(
    () => ["conversations", { ...filters, labels: filters.labels.join(",") }] as const,
    [filters],
  );

  const query = useInfiniteQuery({
    queryKey: key,
    initialPageParam: 1,
    queryFn: ({ pageParam }) => conversationsApi.list(toQuery(filters, pageParam)),
    getNextPageParam: (last: Paginated<Conversation>) => {
      const loaded = last.meta.page * last.meta.per_page;
      return loaded < last.meta.total ? last.meta.page + 1 : undefined;
    },
  });

  const pages = query.data?.pages ?? [];
  const meta = pages[pages.length - 1]?.meta;
  const counts = meta?.counts ?? { mine: 0, unassigned: 0, all: 0 };

  const items = useMemo(() => {
    const flat = pages.flatMap((page) => page.data);
    const seen = new Set<number>();
    const unique = flat.filter((conversation) => {
      if (seen.has(conversation.id)) return false;
      seen.add(conversation.id);
      return true;
    });
    return clientFilter ? unique.filter(clientFilter) : unique;
  }, [pages, clientFilter]);

  /* --------------------------------------------------------- live updates */

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
  }, [queryClient]);

  useRealtime("conversation.created", invalidate);
  useRealtime("conversation.updated", invalidate);
  useRealtime("message.created", invalidate);

  // Refetch as soon as the socket comes back — we may have missed events.
  useEffect(() => {
    if (connection === "open") invalidate();
  }, [connection, invalidate]);

  /* ------------------------------------------------------ infinite scroll */

  function handleScroll() {
    const node = scroller.current;
    if (!node || query.isFetchingNextPage || !query.hasNextPage) return;
    if (node.scrollHeight - node.scrollTop - node.clientHeight < 320) {
      void query.fetchNextPage();
    }
  }

  return (
    <section className="flex h-full w-[380px] shrink-0 flex-col border-r border-line bg-white dark:border-slate-800 dark:bg-slate-900">
      <ConversationFilters
        filters={filters}
        onChange={onFiltersChange}
        onCollapse={onCollapse}
        total={meta?.total}
      />

      <Tabs
        value={filters.assignee}
        onChange={(value) =>
          onFiltersChange({ assignee: value as ConversationFilterState["assignee"] })
        }
        items={[
          { key: "me", label: "Mine", count: counts.mine },
          { key: "unassigned", label: "Unassigned", count: counts.unassigned },
          { key: "all", label: "All", count: counts.all },
        ]}
        size="sm"
        fill
      />

      {notice && (
        <p className="border-b border-line bg-surface-muted px-3 py-1.5 text-2xs text-ink-muted dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-400">
          {notice}
        </p>
      )}

      <div
        ref={scroller}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-y-auto scroll-thin"
      >
        {query.isLoading ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : query.isError ? (
          <EmptyState
            icon={<InboxIcon />}
            title="Could not load conversations"
            description={(query.error as Error)?.message}
            action={
              <Button size="sm" onClick={() => void query.refetch()}>
                Try again
              </Button>
            }
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<InboxIcon />}
            title="No conversations here"
            description="Try a different status, inbox or assignee filter."
          />
        ) : (
          <>
            {items.map((conversation) => (
              <ConversationListItem
                key={conversation.id}
                conversation={conversation}
                selected={conversation.id === selectedId}
                onSelect={onSelect}
              />
            ))}
            <div className="flex justify-center p-3">
              {query.hasNextPage ? (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={query.isFetchingNextPage}
                  onClick={() => void query.fetchNextPage()}
                >
                  Load more
                </Button>
              ) : (
                <span className="text-2xs text-ink-faint">
                  {items.length} conversation{items.length === 1 ? "" : "s"}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

export default ConversationList;
