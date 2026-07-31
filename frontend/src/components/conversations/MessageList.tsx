/**
 * PANE 3 body — the scrolling message transcript.
 *
 * History is paged backwards with `before_id`; live messages arrive over the
 * WebSocket and are merged in place. The view keeps itself pinned to the bottom
 * unless the agent has scrolled up to read older messages.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, MessagesSquare } from "lucide-react";
import { conversations as conversationsApi, messages as messagesApi } from "@/lib/api";
import { dayLabel } from "@/lib/format";
import type { Contact, Message, User } from "@/lib/types";
import { useAppData, useRealtime } from "@/store/app";
import { useAuth } from "@/store/auth";
import { Button, EmptyState, Spinner, useToast } from "@/components/ui";
import { MessageBubble } from "./MessageBubble";

const PAGE_SIZE = 50;

export interface MessageListProps {
  conversationId: number;
  contact: Contact | null;
  onReply: (message: Message) => void;
  /** Bumped by the composer after a successful send to force a scroll down. */
  scrollSignal?: number;
}

/** Merge a message into a sorted list, replacing any existing entry. */
function upsert(list: Message[], message: Message): Message[] {
  const index = list.findIndex((item) => item.id === message.id);
  if (index >= 0) {
    const next = list.slice();
    next[index] = message;
    return next;
  }
  return [...list, message].sort((a, b) => a.id - b.id);
}

export function MessageList({
  conversationId,
  contact,
  onReply,
  scrollSignal = 0,
}: MessageListProps) {
  const { agents } = useAppData();
  const { user } = useAuth();
  const toast = useToast();

  const [items, setItems] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlder, setHasOlder] = useState(false);
  const [typing, setTyping] = useState(false);
  const [pinned, setPinned] = useState(true);

  const scroller = useRef<HTMLDivElement>(null);
  const anchorHeight = useRef(0);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ------------------------------------------------------------- loading */

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setItems([]);
    setPinned(true);
    conversationsApi
      .messages(conversationId, { limit: PAGE_SIZE })
      .then((page) => {
        if (cancelled) return;
        setItems(page);
        setHasOlder(page.length >= PAGE_SIZE);
      })
      .catch((error: Error) => !cancelled && toast.error("Could not load messages", error.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [conversationId, toast]);

  const loadOlder = useCallback(async () => {
    const first = items[0];
    if (!first || loadingOlder) return;
    setLoadingOlder(true);
    anchorHeight.current = scroller.current?.scrollHeight ?? 0;
    try {
      const page = await conversationsApi.messages(conversationId, {
        before_id: first.id,
        limit: PAGE_SIZE,
      });
      setItems((current) => [...page, ...current]);
      setHasOlder(page.length >= PAGE_SIZE);
    } catch (error) {
      toast.error("Could not load older messages", (error as Error).message);
    } finally {
      setLoadingOlder(false);
    }
  }, [conversationId, items, loadingOlder, toast]);

  /* ------------------------------------------------------------ realtime */

  useRealtime<{ message: Message; conversation_id: number }>(
    "message.created",
    useCallback(
      (payload) => {
        if (payload.conversation_id !== conversationId) return;
        setItems((current) => upsert(current, payload.message));
        setTyping(false);
      },
      [conversationId],
    ),
  );

  useRealtime<{ message: Message; conversation_id: number }>(
    "message.updated",
    useCallback(
      (payload) => {
        if (payload.conversation_id !== conversationId) return;
        setItems((current) => upsert(current, payload.message));
      },
      [conversationId],
    ),
  );

  useRealtime<{ message_id: number; conversation_id: number }>(
    "message.deleted",
    useCallback(
      (payload) => {
        if (payload.conversation_id !== conversationId) return;
        setItems((current) => current.filter((item) => item.id !== payload.message_id));
      },
      [conversationId],
    ),
  );

  useRealtime<{ conversation_id: number; actor: string }>(
    "conversation.typing",
    useCallback(
      (payload) => {
        if (payload.conversation_id !== conversationId || payload.actor !== "contact") return;
        setTyping(true);
        if (typingTimer.current) clearTimeout(typingTimer.current);
        typingTimer.current = setTimeout(() => setTyping(false), 6000);
      },
      [conversationId],
    ),
  );

  useEffect(
    () => () => {
      if (typingTimer.current) clearTimeout(typingTimer.current);
    },
    [],
  );

  /* -------------------------------------------------------------- scroll */

  useLayoutEffect(() => {
    const node = scroller.current;
    if (!node) return;
    if (loadingOlder) return;
    if (anchorHeight.current) {
      // Keep the viewport anchored after prepending history.
      node.scrollTop = node.scrollHeight - anchorHeight.current;
      anchorHeight.current = 0;
      return;
    }
    if (pinned) node.scrollTop = node.scrollHeight;
  }, [items, loadingOlder, pinned]);

  useEffect(() => {
    const node = scroller.current;
    if (node && scrollSignal) {
      setPinned(true);
      node.scrollTop = node.scrollHeight;
    }
  }, [scrollSignal]);

  function handleScroll() {
    const node = scroller.current;
    if (!node) return;
    const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
    setPinned(distance < 80);
    if (node.scrollTop < 120 && hasOlder && !loadingOlder) void loadOlder();
  }

  /* ------------------------------------------------------------- actions */

  const toggleReaction = useCallback(
    async (message: Message, emoji: string) => {
      try {
        const updated = await messagesApi.react(message.id, emoji);
        setItems((current) => upsert(current, updated));
      } catch (error) {
        toast.error("Could not react", (error as Error).message);
      }
    },
    [toast],
  );

  const retry = useCallback(
    async (message: Message) => {
      try {
        const updated = await messagesApi.retry(message.id);
        setItems((current) => upsert(current, updated));
      } catch (error) {
        toast.error("Retry failed", (error as Error).message);
      }
    },
    [toast],
  );

  const edit = useCallback(
    async (message: Message, content: string) => {
      try {
        const updated = await messagesApi.update(message.id, content);
        setItems((current) => upsert(current, updated));
      } catch (error) {
        toast.error("Could not edit the message", (error as Error).message);
      }
    },
    [toast],
  );

  const remove = useCallback(
    async (message: Message) => {
      try {
        await messagesApi.remove(message.id);
        setItems((current) => current.filter((item) => item.id !== message.id));
      } catch (error) {
        toast.error("Could not delete the message", (error as Error).message);
      }
    },
    [toast],
  );

  /* --------------------------------------------------------------- render */

  const senderFor = useCallback(
    (message: Message): User | null => {
      if (message.sender_type !== "user" || !message.sender_id) return null;
      if (user && message.sender_id === user.id) return user;
      return agents.find((agent) => agent.id === message.sender_id) ?? null;
    },
    [agents, user],
  );

  const rows = useMemo(() => {
    const output: { key: string; day?: string; message?: Message; grouped?: boolean }[] = [];
    let lastDay = "";
    items.forEach((message, index) => {
      const day = dayLabel(message.created_at);
      if (day && day !== lastDay) {
        output.push({ key: `day-${day}-${message.id}`, day });
        lastDay = day;
      }
      const previous = items[index - 1];
      const grouped =
        Boolean(previous) &&
        previous!.message_type === message.message_type &&
        previous!.private === message.private &&
        previous!.sender_id === message.sender_id &&
        previous!.message_type !== "activity" &&
        dayLabel(previous!.created_at) === day;
      output.push({ key: `m-${message.id}`, message, grouped });
    });
    return output;
  }, [items]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scroller}
        onScroll={handleScroll}
        className="h-full overflow-y-auto pb-4 scroll-thin"
      >
        {hasOlder && (
          <div className="flex justify-center py-3">
            <Button size="xs" variant="ghost" loading={loadingOlder} onClick={() => void loadOlder()}>
              Load earlier messages
            </Button>
          </div>
        )}

        {items.length === 0 ? (
          <EmptyState
            icon={<MessagesSquare />}
            title="No messages yet"
            description="Start the conversation with a reply below."
          />
        ) : (
          rows.map((row) =>
            row.day ? (
              <div key={row.key} className="sticky top-0 z-10 flex justify-center py-2">
                <span className="rounded-full bg-white/90 px-2.5 py-0.5 text-2xs font-medium text-ink-muted shadow-card backdrop-blur dark:bg-slate-800/90 dark:text-slate-400">
                  {row.day}
                </span>
              </div>
            ) : (
              <MessageBubble
                key={row.key}
                message={row.message!}
                contact={contact}
                sender={senderFor(row.message!)}
                grouped={row.grouped}
                canModerate={
                  row.message!.sender_id === user?.id || user?.role === "admin"
                }
                onToggleReaction={(message, emoji) => void toggleReaction(message, emoji)}
                onRetry={(message) => void retry(message)}
                onEdit={edit}
                onDelete={(message) => void remove(message)}
                onReply={onReply}
              />
            ),
          )
        )}

        {typing && (
          <div className="flex items-center gap-2 px-4 py-2 text-2xs text-ink-muted">
            <span className="flex gap-0.5">
              {[0, 1, 2].map((dot) => (
                <span
                  key={dot}
                  className="h-1.5 w-1.5 animate-blink rounded-full bg-ink-faint"
                  style={{ animationDelay: `${dot * 150}ms` }}
                />
              ))}
            </span>
            {contact?.name ?? "The customer"} is typing…
          </div>
        )}
      </div>

      {!pinned && (
        <button
          type="button"
          onClick={() => {
            setPinned(true);
            const node = scroller.current;
            if (node) node.scrollTop = node.scrollHeight;
          }}
          className="absolute bottom-4 right-6 flex h-9 w-9 items-center justify-center rounded-full bg-white text-ink-soft shadow-pop transition hover:text-primary dark:bg-slate-800 dark:text-slate-300"
          aria-label="Jump to latest"
        >
          <ArrowDown className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

export default MessageList;
