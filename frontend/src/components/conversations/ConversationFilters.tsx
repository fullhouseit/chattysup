/**
 * PANE 2 header — title, status chip and the filter / sort / collapse controls.
 */
import { ArrowDownWideNarrow, ChevronDown, PanelLeftClose, SlidersHorizontal, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { useAppData } from "@/store/app";
import type { ConversationPriority, ConversationStatus } from "@/lib/types";
import {
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  IconButton,
  Tooltip,
} from "@/components/ui";

export type StatusFilter = ConversationStatus | "all";
export type SortOrder = "latest" | "oldest" | "priority";

export interface ConversationFilterState {
  status: StatusFilter;
  assignee: "me" | "unassigned" | "all";
  inboxId: number | null;
  labels: string[];
  priority: ConversationPriority | "all";
  sort: SortOrder;
  q: string;
}

export const DEFAULT_FILTERS: ConversationFilterState = {
  status: "open",
  assignee: "all",
  inboxId: null,
  labels: [],
  priority: "all",
  sort: "latest",
  q: "",
};

const STATUS_LABELS: Record<StatusFilter, string> = {
  open: "Open",
  pending: "Pending",
  snoozed: "Snoozed",
  resolved: "Resolved",
  all: "All",
};

const SORT_LABELS: Record<SortOrder, string> = {
  latest: "Latest activity",
  oldest: "Oldest activity",
  priority: "Priority first",
};

const PRIORITIES: (ConversationPriority | "all")[] = [
  "all",
  "urgent",
  "high",
  "medium",
  "low",
  "none",
];

export interface ConversationFiltersProps {
  filters: ConversationFilterState;
  onChange: (patch: Partial<ConversationFilterState>) => void;
  onCollapse?: () => void;
  total?: number;
}

export function ConversationFilters({
  filters,
  onChange,
  onCollapse,
  total,
}: ConversationFiltersProps) {
  const { inboxes, labels } = useAppData();
  const activeCount =
    (filters.inboxId ? 1 : 0) +
    filters.labels.length +
    (filters.priority !== "all" ? 1 : 0) +
    (filters.q ? 1 : 0);

  function toggleLabel(title: string) {
    const next = filters.labels.includes(title)
      ? filters.labels.filter((item) => item !== title)
      : [...filters.labels, title];
    onChange({ labels: next });
  }

  return (
    <div className="border-b border-line px-3 py-2.5 dark:border-slate-800">
      <div className="flex items-center gap-2">
        <h1 className="text-md font-semibold text-ink dark:text-slate-100">
          Conversations
        </h1>

        {/* Status chip */}
        <Dropdown
          width="w-44"
          trigger={({ toggle }) => (
            <button
              type="button"
              onClick={toggle}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-ink-soft transition-colors hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {STATUS_LABELS[filters.status]}
              {total !== undefined && (
                <span className="tabular-nums text-ink-faint">{total}</span>
              )}
              <ChevronDown className="h-3 w-3" />
            </button>
          )}
        >
          {({ close }) => (
            <>
              <DropdownLabel>Status</DropdownLabel>
              {(Object.keys(STATUS_LABELS) as StatusFilter[]).map((status) => (
                <DropdownItem
                  key={status}
                  active={filters.status === status}
                  onClick={() => {
                    onChange({ status });
                    close();
                  }}
                >
                  {STATUS_LABELS[status]}
                </DropdownItem>
              ))}
            </>
          )}
        </Dropdown>

        <div className="ml-auto flex items-center gap-0.5">
          {/* Filters */}
          <Dropdown
            align="right"
            width="w-64"
            trigger={({ toggle }) => (
              <Tooltip label="Filter">
                <IconButton label="Filter" onClick={toggle} className="relative">
                  <SlidersHorizontal className="h-4 w-4" />
                  {activeCount > 0 && (
                    <span className="absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full bg-primary" />
                  )}
                </IconButton>
              </Tooltip>
            )}
          >
            <div className="max-h-[60vh] overflow-y-auto scroll-thin">
              <DropdownLabel>Inbox</DropdownLabel>
              <DropdownItem
                active={filters.inboxId === null}
                onClick={() => onChange({ inboxId: null })}
              >
                All inboxes
              </DropdownItem>
              {inboxes.map((inbox) => (
                <DropdownItem
                  key={inbox.id}
                  active={filters.inboxId === inbox.id}
                  onClick={() => onChange({ inboxId: inbox.id })}
                >
                  {inbox.name}
                </DropdownItem>
              ))}

              <DropdownSeparator />
              <DropdownLabel>Priority</DropdownLabel>
              {PRIORITIES.map((priority) => (
                <DropdownItem
                  key={priority}
                  active={filters.priority === priority}
                  onClick={() => onChange({ priority })}
                >
                  {priority === "all"
                    ? "Any priority"
                    : priority[0]!.toUpperCase() + priority.slice(1)}
                </DropdownItem>
              ))}

              {labels.length > 0 && (
                <>
                  <DropdownSeparator />
                  <DropdownLabel>Labels</DropdownLabel>
                  {labels.map((label) => (
                    <DropdownItem
                      key={label.id}
                      active={filters.labels.includes(label.title)}
                      icon={
                        <span
                          className="block h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: label.color }}
                        />
                      }
                      onClick={() => toggleLabel(label.title)}
                    >
                      {label.title}
                    </DropdownItem>
                  ))}
                </>
              )}

              {activeCount > 0 && (
                <>
                  <DropdownSeparator />
                  <DropdownItem
                    danger
                    icon={<X />}
                    onClick={() =>
                      onChange({ inboxId: null, labels: [], priority: "all", q: "" })
                    }
                  >
                    Clear filters
                  </DropdownItem>
                </>
              )}
            </div>
          </Dropdown>

          {/* Sort */}
          <Dropdown
            align="right"
            width="w-48"
            trigger={({ toggle }) => (
              <Tooltip label="Sort">
                <IconButton label="Sort" onClick={toggle}>
                  <ArrowDownWideNarrow className="h-4 w-4" />
                </IconButton>
              </Tooltip>
            )}
          >
            {({ close }) => (
              <>
                <DropdownLabel>Sort by</DropdownLabel>
                {(Object.keys(SORT_LABELS) as SortOrder[]).map((sort) => (
                  <DropdownItem
                    key={sort}
                    active={filters.sort === sort}
                    onClick={() => {
                      onChange({ sort });
                      close();
                    }}
                  >
                    {SORT_LABELS[sort]}
                  </DropdownItem>
                ))}
              </>
            )}
          </Dropdown>

          {onCollapse && (
            <Tooltip label="Collapse list">
              <IconButton label="Collapse list" onClick={onCollapse}>
                <PanelLeftClose className="h-4 w-4" />
              </IconButton>
            </Tooltip>
          )}
        </div>
      </div>

      {/* Active chips */}
      {(filters.q || filters.labels.length > 0 || filters.inboxId) && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {filters.q && (
            <FilterChip label={`“${filters.q}”`} onClear={() => onChange({ q: "" })} />
          )}
          {filters.inboxId && (
            <FilterChip
              label={
                inboxes.find((inbox) => inbox.id === filters.inboxId)?.name ?? "Inbox"
              }
              onClear={() => onChange({ inboxId: null })}
            />
          )}
          {filters.labels.map((title) => (
            <FilterChip key={title} label={title} onClear={() => toggleLabel(title)} />
          ))}
        </div>
      )}
    </div>
  );
}

function FilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-[160px] items-center gap-1 rounded-full bg-primary-50 px-2 py-0.5 text-2xs font-medium text-primary-700",
        "dark:bg-primary-900/30 dark:text-primary-200",
      )}
    >
      <span className="truncate">{label}</span>
      <button type="button" onClick={onClear} aria-label={`Remove ${label}`}>
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

export default ConversationFilters;
