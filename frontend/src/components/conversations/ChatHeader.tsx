/**
 * PANE 3 header — contact identity, conversation actions and the split
 * Resolve button (Resolve / Snooze / Mark pending / Reopen).
 */
import { addDays, addHours, startOfTomorrow } from "date-fns";
import {
  Bell,
  BellOff,
  Check,
  ChevronDown,
  Clock,
  CornerUpLeft,
  PanelRightClose,
  PanelRightOpen,
  Share2,
  Sidebar as SidebarIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";
import type { Conversation, ConversationStatus } from "@/lib/types";
import {
  Avatar,
  Badge,
  Button,
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  IconButton,
  Tabs,
  Tooltip,
} from "@/components/ui";
import { ChannelIcon } from "./ChannelIcon";

export type ChatTab = "messages" | "dashboard";

export interface ChatHeaderProps {
  conversation: Conversation;
  detailsOpen: boolean;
  onToggleDetails: () => void;
  listCollapsed?: boolean;
  onExpandList?: () => void;
  tab: ChatTab;
  onTabChange: (tab: ChatTab) => void;
  onStatusChange: (status: ConversationStatus, snoozedUntil?: string | null) => void;
  onToggleMute: () => void;
  onCopyLink: () => void;
}

const STATUS_TONE = {
  open: "success",
  pending: "warning",
  snoozed: "purple",
  resolved: "neutral",
} as const;

export function ChatHeader({
  conversation,
  detailsOpen,
  onToggleDetails,
  listCollapsed,
  onExpandList,
  tab,
  onTabChange,
  onStatusChange,
  onToggleMute,
  onCopyLink,
}: ChatHeaderProps) {
  const contact = conversation.contact;
  const resolved = conversation.status === "resolved";

  function snooze(until: Date | null) {
    onStatusChange("snoozed", until ? until.toISOString() : null);
  }

  return (
    <header className="border-b border-line bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-3 px-4 py-2.5">
        {listCollapsed && onExpandList && (
          <Tooltip label="Show conversation list">
            <IconButton label="Show conversation list" onClick={onExpandList}>
              <SidebarIcon className="h-4 w-4" />
            </IconButton>
          </Tooltip>
        )}

        <Avatar
          name={contact?.name}
          src={contact?.avatar_url}
          seed={contact?.id ?? conversation.id}
          size="lg"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-md font-semibold text-ink dark:text-slate-100">
              {contact?.name || "Unknown contact"}
            </h2>
            <Badge tone={STATUS_TONE[conversation.status]} size="xs">
              {conversation.status}
            </Badge>
            {conversation.priority !== "none" && (
              <Badge
                size="xs"
                tone={
                  conversation.priority === "urgent" || conversation.priority === "high"
                    ? "danger"
                    : "neutral"
                }
              >
                {conversation.priority}
              </Badge>
            )}
          </div>
          <p className="flex items-center gap-1 text-2xs text-ink-muted dark:text-slate-400">
            <ChannelIcon channelType={conversation.inbox?.channel_type} className="h-3 w-3" />
            <span className="truncate">{conversation.inbox?.name ?? "Inbox"}</span>
            <span className="text-ink-faint">·</span>
            <span>#{conversation.id}</span>
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <Tooltip label={conversation.muted ? "Unmute" : "Mute notifications"}>
            <IconButton
              label={conversation.muted ? "Unmute" : "Mute"}
              onClick={onToggleMute}
              className={cn(conversation.muted && "text-amber-600")}
            >
              {conversation.muted ? (
                <BellOff className="h-4 w-4" />
              ) : (
                <Bell className="h-4 w-4" />
              )}
            </IconButton>
          </Tooltip>

          <Tooltip label="Copy conversation link">
            <IconButton label="Copy conversation link" onClick={onCopyLink}>
              <Share2 className="h-4 w-4" />
            </IconButton>
          </Tooltip>

          <Tooltip label={detailsOpen ? "Close details" : "Open details"}>
            <IconButton
              label={detailsOpen ? "Close details" : "Open details"}
              onClick={onToggleDetails}
            >
              {detailsOpen ? (
                <PanelRightClose className="h-4 w-4" />
              ) : (
                <PanelRightOpen className="h-4 w-4" />
              )}
            </IconButton>
          </Tooltip>

          {/* Split resolve button */}
          <div className="ml-1 flex items-stretch overflow-hidden rounded-lg shadow-card">
            <Button
              variant="primary"
              size="sm"
              className="rounded-none rounded-l-lg shadow-none"
              leftIcon={resolved ? <CornerUpLeft className="h-4 w-4" /> : <Check className="h-4 w-4" />}
              onClick={() => onStatusChange(resolved ? "open" : "resolved")}
            >
              {resolved ? "Reopen" : "Resolve"}
            </Button>
            <Dropdown
              align="right"
              width="w-52"
              trigger={({ toggle }) => (
                <button
                  type="button"
                  onClick={toggle}
                  aria-label="More status actions"
                  className="flex h-8 items-center border-l border-white/25 bg-primary px-1.5 text-white transition-colors hover:bg-primary-600"
                >
                  <ChevronDown className="h-4 w-4" />
                </button>
              )}
            >
              {({ close }) => (
                <>
                  <DropdownItem
                    icon={<Check />}
                    onClick={() => {
                      onStatusChange("resolved");
                      close();
                    }}
                  >
                    Resolve
                  </DropdownItem>
                  <DropdownItem
                    icon={<Clock />}
                    onClick={() => {
                      onStatusChange("pending");
                      close();
                    }}
                  >
                    Mark as pending
                  </DropdownItem>
                  <DropdownItem
                    icon={<CornerUpLeft />}
                    onClick={() => {
                      onStatusChange("open");
                      close();
                    }}
                  >
                    Reopen
                  </DropdownItem>
                  <DropdownSeparator />
                  <DropdownLabel>Snooze until</DropdownLabel>
                  <DropdownItem
                    onClick={() => {
                      snooze(addHours(new Date(), 1));
                      close();
                    }}
                  >
                    An hour from now
                  </DropdownItem>
                  <DropdownItem
                    onClick={() => {
                      snooze(startOfTomorrow());
                      close();
                    }}
                  >
                    Tomorrow morning
                  </DropdownItem>
                  <DropdownItem
                    onClick={() => {
                      snooze(addDays(new Date(), 7));
                      close();
                    }}
                  >
                    Next week
                  </DropdownItem>
                  <DropdownItem
                    onClick={() => {
                      snooze(null);
                      close();
                    }}
                  >
                    Until next reply
                  </DropdownItem>
                </>
              )}
            </Dropdown>
          </div>
        </div>
      </div>

      <Tabs
        value={tab}
        onChange={(value) => onTabChange(value as ChatTab)}
        items={[
          { key: "messages", label: "Messages" },
          { key: "dashboard", label: "Customer Dashboard" },
        ]}
        size="sm"
        className="px-3"
      />
    </header>
  );
}

export default ChatHeader;
