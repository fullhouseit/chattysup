/** PANE 2 row — one conversation in the list. */
import { memo } from "react";
import { CornerUpRight, Lock } from "lucide-react";
import { cn } from "@/lib/cn";
import { conversationAges, messagePreview } from "@/lib/format";
import type { Conversation, ConversationPriority } from "@/lib/types";
import { Avatar, CountBadge } from "@/components/ui";
import { ChannelBadge, ChannelIcon } from "./ChannelIcon";

/** Signal-strength style priority indicator drawn at the row's right edge. */
function PriorityBars({ priority }: { priority: ConversationPriority }) {
  if (priority === "none") return null;
  const levels: Record<Exclude<ConversationPriority, "none">, number> = {
    low: 1,
    medium: 2,
    high: 3,
    urgent: 4,
  };
  const filled = levels[priority];
  const hot = priority === "urgent" || priority === "high";
  return (
    <span
      className="flex items-end gap-[2px]"
      title={`${priority[0]!.toUpperCase()}${priority.slice(1)} priority`}
      aria-label={`${priority} priority`}
    >
      {[1, 2, 3, 4].map((level) => (
        <span
          key={level}
          className={cn(
            "w-[3px] rounded-sm",
            level <= filled
              ? hot
                ? "bg-red-500"
                : "bg-amber-500"
              : "bg-slate-200 dark:bg-slate-700",
          )}
          style={{ height: `${3 + level * 2.5}px` }}
        />
      ))}
    </span>
  );
}

export interface ConversationListItemProps {
  conversation: Conversation;
  selected: boolean;
  onSelect: (id: number) => void;
}

function ConversationListItemInner({
  conversation,
  selected,
  onSelect,
}: ConversationListItemProps) {
  const contact = conversation.contact;
  const last = conversation.last_message;
  const outgoing = last?.message_type === "outgoing";
  const preview = messagePreview(last?.content, last?.attachments?.[0]?.file_type);
  const unread = conversation.unread_count > 0;

  return (
    <button
      type="button"
      onClick={() => onSelect(conversation.id)}
      aria-current={selected}
      className={cn(
        "flex w-full items-start gap-3 border-b border-line px-3 py-3 text-left transition-colors",
        "dark:border-slate-800",
        selected
          ? "bg-primary-50 dark:bg-primary-900/25"
          : "hover:bg-surface-muted dark:hover:bg-slate-800/60",
      )}
    >
      <Avatar
        name={contact?.name}
        src={contact?.avatar_url}
        seed={contact?.id ?? conversation.id}
        size="lg"
        badge={<ChannelBadge channelType={conversation.inbox?.channel_type} />}
        className="mt-0.5"
      />

      <span className="min-w-0 flex-1">
        {/* inbox line */}
        <span className="flex items-center gap-1 text-2xs text-ink-faint">
          <ChannelIcon channelType={conversation.inbox?.channel_type} className="h-3 w-3" />
          <span className="truncate">{conversation.inbox?.name ?? "Inbox"}</span>
        </span>

        {/* name + age */}
        <span className="mt-0.5 flex items-baseline gap-2">
          <span
            className={cn(
              "min-w-0 flex-1 truncate text-sm",
              unread
                ? "font-semibold text-ink dark:text-white"
                : "font-semibold text-ink dark:text-slate-100",
            )}
          >
            {contact?.name || "Unknown contact"}
          </span>
          <span className="shrink-0 text-2xs tabular-nums text-ink-faint">
            {conversationAges(conversation.created_at, conversation.last_activity_at)}
          </span>
        </span>

        {/* preview */}
        <span className="mt-0.5 flex items-center gap-1">
          {last?.private ? (
            <Lock className="h-3 w-3 shrink-0 text-amber-500" />
          ) : outgoing ? (
            <CornerUpRight className="h-3 w-3 shrink-0 text-ink-faint" />
          ) : null}
          <span
            className={cn(
              "min-w-0 flex-1 truncate text-xs",
              unread
                ? "font-medium text-ink-soft dark:text-slate-200"
                : "text-ink-muted dark:text-slate-400",
            )}
          >
            {preview}
          </span>
          {unread && <CountBadge count={conversation.unread_count} className="ml-1" />}
        </span>

        {/* labels */}
        {conversation.labels.length > 0 && (
          <span className="mt-1.5 flex flex-wrap items-center gap-1">
            {conversation.labels.slice(0, 3).map((label) => (
              <span
                key={label.id}
                className="inline-flex max-w-[110px] items-center gap-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-2xs font-medium text-ink-soft dark:bg-slate-800 dark:text-slate-300"
              >
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ backgroundColor: label.color }}
                />
                <span className="truncate">{label.title}</span>
              </span>
            ))}
            {conversation.labels.length > 3 && (
              <span className="text-2xs text-ink-faint">
                +{conversation.labels.length - 3}
              </span>
            )}
          </span>
        )}
      </span>

      <span className="mt-1 flex shrink-0 flex-col items-end gap-1.5">
        <PriorityBars priority={conversation.priority} />
        {conversation.status === "snoozed" && (
          <span className="text-2xs text-amber-600">snoozed</span>
        )}
      </span>
    </button>
  );
}

export const ConversationListItem = memo(ConversationListItemInner);
export default ConversationListItem;
