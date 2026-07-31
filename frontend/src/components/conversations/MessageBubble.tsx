/**
 * A single message row.
 *
 * Incoming messages sit on the left with an avatar, outgoing replies on the
 * right in blue, private notes in amber with a lock, and activity entries as a
 * centred pill. Stickers render bare — no bubble at all.
 */
import { useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCheck,
  Clock,
  CornerUpLeft,
  Lock,
  MoreHorizontal,
  Pencil,
  RotateCw,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { fullTimestamp, messageTimestamp, renderMessageHtml } from "@/lib/format";
import type { Contact, Message, User } from "@/lib/types";
import {
  Avatar,
  Dropdown,
  DropdownItem,
  IconButton,
  Textarea,
  Tooltip,
} from "@/components/ui";
import { Attachments, StickerAttachment } from "./Attachments";
import { AddReactionButton, ReactionBar } from "./ReactionBar";

export interface MessageBubbleProps {
  message: Message;
  contact: Contact | null;
  sender: User | null;
  /** Hide the avatar/name when the previous bubble had the same author. */
  grouped?: boolean;
  onToggleReaction: (message: Message, emoji: string) => void;
  onRetry: (message: Message) => void;
  onEdit: (message: Message, content: string) => Promise<void> | void;
  onDelete: (message: Message) => void;
  onReply: (message: Message) => void;
  canModerate: boolean;
}

function DeliveryTicks({ message }: { message: Message }) {
  if (message.message_type !== "outgoing") return null;
  switch (message.status) {
    case "pending":
      return <Clock className="h-3 w-3 text-ink-faint" aria-label="Sending" />;
    case "sent":
      return <Check className="h-3 w-3 text-ink-faint" aria-label="Sent" />;
    case "delivered":
      return <CheckCheck className="h-3 w-3 text-ink-faint" aria-label="Delivered" />;
    case "read":
      return <CheckCheck className="h-3 w-3 text-primary" aria-label="Read" />;
    case "failed":
      return <AlertCircle className="h-3 w-3 text-red-500" aria-label="Failed" />;
    default:
      return null;
  }
}

/** Centred grey pill for `message_type === "activity"`. */
function ActivityPill({ message }: { message: Message }) {
  return (
    <div className="flex justify-center py-1.5">
      <span
        title={fullTimestamp(message.created_at)}
        className="rounded-full bg-slate-100 px-2.5 py-1 text-2xs text-ink-muted dark:bg-slate-800 dark:text-slate-400"
      >
        {message.content}
      </span>
    </div>
  );
}

function ReplyQuote({ message }: { message: Message }) {
  const preview = message.content_attributes?.reply_to_preview as
    | { id: number; content: string; sender_type: string }
    | undefined;
  if (!preview) return null;
  return (
    <div className="mb-1.5 flex gap-2 rounded-md border-l-2 border-primary bg-black/[0.03] px-2 py-1 dark:bg-white/5">
      <div className="min-w-0">
        <p className="text-2xs font-medium text-primary">
          {preview.sender_type === "contact" ? "Customer" : "Agent"}
        </p>
        <p className="truncate text-xs text-ink-muted dark:text-slate-400">
          {preview.content || "Attachment"}
        </p>
      </div>
    </div>
  );
}

export function MessageBubble({
  message,
  contact,
  sender,
  grouped = false,
  onToggleReaction,
  onRetry,
  onEdit,
  onDelete,
  onReply,
  canModerate,
}: MessageBubbleProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content ?? "");

  if (message.message_type === "activity") {
    return <ActivityPill message={message} />;
  }

  if (message.deleted_at) {
    return (
      <div className="flex justify-center py-1">
        <span className="text-2xs italic text-ink-faint">This message was deleted</span>
      </div>
    );
  }

  const outgoing = message.message_type === "outgoing";
  const isNote = message.private;
  const alignRight = outgoing || isNote;
  const sticker =
    message.content_type === "sticker" ||
    (message.attachments.length === 1 && message.attachments[0]!.file_type === "sticker");
  const authorName = outgoing
    ? (sender?.display_name ?? sender?.name ?? "You")
    : (contact?.name ?? "Customer");

  async function saveEdit() {
    await onEdit(message, draft);
    setEditing(false);
  }

  return (
    <div
      className={cn(
        "group/message flex w-full gap-2 px-4",
        grouped ? "pt-0.5" : "pt-3",
        alignRight ? "flex-row-reverse" : "flex-row",
      )}
    >
      {!alignRight &&
        (grouped ? (
          <span className="w-7 shrink-0" />
        ) : (
          <Avatar
            name={contact?.name}
            src={contact?.avatar_url}
            seed={contact?.id}
            size="sm"
            className="mt-4"
          />
        ))}

      <div
        className={cn(
          "flex min-w-0 max-w-[min(560px,78%)] flex-col",
          alignRight ? "items-end" : "items-start",
        )}
      >
        {!grouped && (
          <span className="px-1 pb-0.5 text-2xs font-medium text-ink-faint">
            {isNote ? `${authorName} · private note` : authorName}
          </span>
        )}

        <div className={cn("flex items-center gap-1", alignRight && "flex-row-reverse")}>
          {sticker ? (
            <StickerAttachment attachment={message.attachments[0]!} />
          ) : (
            <div
              className={cn(
                "relative rounded-lg border px-3 py-2 shadow-card",
                isNote
                  ? "border-amber-200 bg-note text-amber-950 dark:border-amber-700/60 dark:bg-amber-900/30 dark:text-amber-100"
                  : outgoing
                    ? "border-primary-100 bg-primary-50 text-ink dark:border-primary-900 dark:bg-primary-900/30 dark:text-slate-100"
                    : "border-line bg-white text-ink dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100",
              )}
            >
              <ReplyQuote message={message} />

              {isNote && (
                <Lock className="absolute -left-1.5 -top-1.5 h-3.5 w-3.5 rounded-full bg-amber-200 p-0.5 text-amber-800" />
              )}

              {editing ? (
                <div className="w-[320px] max-w-full space-y-2">
                  <Textarea
                    value={draft}
                    rows={3}
                    autoFocus
                    onChange={(event) => setDraft(event.target.value)}
                  />
                  <div className="flex justify-end gap-2 text-xs">
                    <button
                      type="button"
                      className="text-ink-muted hover:text-ink"
                      onClick={() => {
                        setDraft(message.content ?? "");
                        setEditing(false);
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="font-medium text-primary hover:text-primary-600"
                      onClick={() => void saveEdit()}
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {message.content && (
                    <div
                      className="msg-body"
                      dangerouslySetInnerHTML={{
                        __html: renderMessageHtml(message.content),
                      }}
                    />
                  )}
                  {message.attachments.length > 0 && (
                    <div className={cn(message.content && "mt-2")}>
                      <Attachments
                        attachments={message.attachments}
                        outgoing={outgoing}
                      />
                    </div>
                  )}
                </>
              )}

              <div
                className={cn(
                  "mt-1 flex items-center gap-1 text-2xs text-ink-faint",
                  alignRight ? "justify-end" : "justify-start",
                )}
              >
                {message.edited_at && <span className="italic">edited</span>}
                <Tooltip label={fullTimestamp(message.created_at)}>
                  <time dateTime={message.created_at ?? undefined}>
                    {messageTimestamp(message.created_at)}
                  </time>
                </Tooltip>
                <DeliveryTicks message={message} />
              </div>
            </div>
          )}

          {/* hover actions */}
          <div className="flex shrink-0 items-center gap-0.5 self-center">
            <AddReactionButton
              align={alignRight ? "right" : "left"}
              onSelect={(emoji) => onToggleReaction(message, emoji)}
            />
            <button
              type="button"
              aria-label="Reply"
              onClick={() => onReply(message)}
              className="rounded-full p-1 text-ink-faint opacity-0 transition group-hover/message:opacity-100 hover:bg-slate-100 hover:text-ink dark:hover:bg-slate-800"
            >
              <CornerUpLeft className="h-4 w-4" />
            </button>
            {canModerate && outgoing && (
              <Dropdown
                align={alignRight ? "right" : "left"}
                width="w-40"
                trigger={({ toggle }) => (
                  <button
                    type="button"
                    aria-label="Message actions"
                    onClick={toggle}
                    className="rounded-full p-1 text-ink-faint opacity-0 transition group-hover/message:opacity-100 hover:bg-slate-100 hover:text-ink dark:hover:bg-slate-800"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                )}
              >
                {({ close }) => (
                  <>
                    <DropdownItem
                      icon={<Pencil />}
                      onClick={() => {
                        setEditing(true);
                        close();
                      }}
                    >
                      Edit
                    </DropdownItem>
                    <DropdownItem
                      danger
                      icon={<Trash2 />}
                      onClick={() => {
                        onDelete(message);
                        close();
                      }}
                    >
                      Delete
                    </DropdownItem>
                  </>
                )}
              </Dropdown>
            )}
          </div>
        </div>

        <ReactionBar
          reactions={message.reactions}
          align={alignRight ? "right" : "left"}
          onToggle={(emoji) => onToggleReaction(message, emoji)}
        />

        {message.status === "failed" && (
          <div className="mt-1 flex items-center gap-2 text-2xs text-red-600">
            <AlertCircle className="h-3 w-3" />
            <span>{message.external_error || "Failed to send"}</span>
            <IconButton
              label="Retry sending"
              onClick={() => onRetry(message)}
              className="h-5 w-auto gap-1 px-1.5 text-red-600 hover:bg-red-50"
            >
              <RotateCw className="h-3 w-3" />
              <span className="text-2xs font-medium">Retry</span>
            </IconButton>
          </div>
        )}
      </div>
    </div>
  );
}

export default MessageBubble;
