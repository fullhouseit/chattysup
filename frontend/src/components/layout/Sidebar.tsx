/**
 * PANE 1 — the fixed left rail.
 *
 * Workspace header, global search + compose, then the navigation groups
 * (Conversations / Folders / Teams / Channels / Labels) and the account menu.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  AtSign,
  BookMarked,
  ChevronDown,
  ChevronRight,
  Contact as ContactIcon,
  Inbox as InboxIcon,
  LogOut,
  MessageSquare,
  Moon,
  PencilLine,
  Search,
  Settings,
  Sun,
  Trash2,
  UserCircle2,
  Users,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { useFolders } from "@/lib/folders";
import { useAppData } from "@/store/app";
import { useAuth } from "@/store/auth";
import type { Availability } from "@/lib/types";
import {
  Avatar,
  Dropdown,
  DropdownItem,
  DropdownLabel,
  DropdownSeparator,
  IconButton,
  Tooltip,
} from "@/components/ui";
import { ChannelIcon } from "@/components/conversations/ChannelIcon";
import { useTheme } from "@/store/theme";

/* --------------------------------------------------------------- helpers */

interface NavItemProps {
  to: string;
  icon?: ReactNode;
  label: string;
  active: boolean;
  trailing?: ReactNode;
  onContextAction?: ReactNode;
}

function NavItem({ to, icon, label, active, trailing, onContextAction }: NavItemProps) {
  return (
    <div className="group/nav relative">
      <Link
        to={to}
        className={cn(
          "flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors",
          active
            ? "bg-primary-50 font-medium text-primary dark:bg-primary-900/30 dark:text-primary-200"
            : "text-ink-soft hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
        )}
      >
        {icon && (
          <span className="shrink-0 [&>svg]:h-4 [&>svg]:w-4 [&>svg]:stroke-[1.75]">
            {icon}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {trailing}
      </Link>
      {onContextAction && (
        <span className="absolute right-1 top-1/2 hidden -translate-y-1/2 group-hover/nav:block">
          {onContextAction}
        </span>
      )}
    </div>
  );
}

function NavGroup({
  title,
  icon,
  children,
  collapsible = true,
  action,
  defaultOpen = true,
}: {
  title: string;
  icon?: ReactNode;
  children: ReactNode;
  collapsible?: boolean;
  action?: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="px-2 pb-1 pt-3">
      <div className="flex items-center gap-1 pl-2 pr-1">
        <button
          type="button"
          onClick={() => collapsible && setOpen((value) => !value)}
          className="flex min-w-0 flex-1 items-center gap-1 py-1 text-left text-2xs font-semibold uppercase tracking-wide text-ink-faint transition-colors hover:text-ink-muted"
        >
          {collapsible &&
            (open ? (
              <ChevronDown className="h-3 w-3 shrink-0" />
            ) : (
              <ChevronRight className="h-3 w-3 shrink-0" />
            ))}
          {icon}
          <span className="truncate">{title}</span>
        </button>
        {action}
      </div>
      {open && <div className="mt-0.5 space-y-0.5">{children}</div>}
    </div>
  );
}

/* --------------------------------------------------------------- sidebar */

export function Sidebar() {
  const { user, config, logout, updateProfile } = useAuth();
  const { inboxes, labels, teams } = useAppData();
  const { folders, add: addFolder, remove: removeFolder } = useFolders();
  const { theme, toggle: toggleTheme } = useTheme();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  const onConversations = location.pathname.startsWith("/conversations");
  const currentQuery = params.toString();

  const active = useMemo(
    () => ({
      all:
        onConversations &&
        !params.get("view") &&
        !params.get("inbox_id") &&
        !params.get("labels") &&
        !params.get("team_id") &&
        (params.get("assignee") ?? "all") === "all",
      mentions: onConversations && params.get("view") === "mentions",
      unattended: onConversations && params.get("view") === "unattended",
      inbox: (id: number) => onConversations && params.get("inbox_id") === String(id),
      label: (title: string) => onConversations && params.get("labels") === title,
      team: (id: number) => onConversations && params.get("team_id") === String(id),
      folder: (query: string) => onConversations && currentQuery === query,
    }),
    [onConversations, params, currentQuery],
  );

  function submitSearch(event: React.FormEvent) {
    event.preventDefault();
    const term = search.trim();
    navigate(term ? `/conversations?q=${encodeURIComponent(term)}` : "/conversations");
  }

  function saveCurrentAsFolder() {
    const name = window.prompt("Name this folder", "My filter");
    if (name?.trim()) addFolder(name.trim(), currentQuery);
  }

  async function setAvailability(availability: Availability) {
    await updateProfile({ availability });
  }

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r border-line bg-white dark:border-slate-800 dark:bg-slate-900">
      {/* Workspace header */}
      <Dropdown
        width="w-52"
        className="px-2 pt-2"
        trigger={({ toggle, open }) => (
          <button
            type="button"
            onClick={toggle}
            className={cn(
              "flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-slate-100 dark:hover:bg-slate-800",
              open && "bg-slate-100 dark:bg-slate-800",
            )}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-white">
              C
            </span>
            <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink dark:text-slate-100">
              {config?.installation_name || "ChattySup"}
            </span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
          </button>
        )}
      >
        {({ close }) => (
          <>
            <DropdownItem
              icon={<ContactIcon />}
              onClick={() => {
                close();
                navigate("/contacts");
              }}
            >
              Contacts
            </DropdownItem>
            <DropdownItem
              icon={<Zap />}
              onClick={() => {
                close();
                navigate("/admin");
              }}
            >
              Administration
            </DropdownItem>
            <DropdownSeparator />
            <DropdownItem
              icon={theme === "dark" ? <Sun /> : <Moon />}
              onClick={() => {
                close();
                toggleTheme();
              }}
            >
              {theme === "dark" ? "Light theme" : "Dark theme"}
            </DropdownItem>
          </>
        )}
      </Dropdown>

      {/* Search + compose */}
      <form onSubmit={submitSearch} className="flex items-center gap-1 px-2 py-2">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search"
            aria-label="Search conversations"
            className="h-8 w-full rounded-lg border border-line bg-surface-muted pl-8 pr-2 text-sm text-ink placeholder:text-ink-faint focus:border-primary-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-primary-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:bg-slate-900"
          />
        </div>
        <Tooltip label="New conversation">
          <IconButton
            label="New conversation"
            onClick={() => navigate("/contacts")}
            className="h-8 w-8"
          >
            <PencilLine className="h-4 w-4" />
          </IconButton>
        </Tooltip>
      </form>

      {/* Navigation */}
      <nav className="min-h-0 flex-1 overflow-y-auto pb-3 scroll-thin">
        <NavGroup title="Conversations" collapsible>
          <NavItem
            to="/conversations"
            icon={<MessageSquare />}
            label="All Conversations"
            active={active.all}
          />
          <NavItem
            to="/conversations?view=mentions"
            icon={<AtSign />}
            label="Mentions"
            active={active.mentions}
          />
          <NavItem
            to="/conversations?view=unattended"
            icon={<InboxIcon />}
            label="Unattended"
            active={active.unattended}
          />
        </NavGroup>

        <NavGroup
          title="Folders"
          action={
            onConversations ? (
              <Tooltip label="Save current filter">
                <IconButton
                  label="Save current filter"
                  onClick={saveCurrentAsFolder}
                  className="h-5 w-5"
                >
                  <BookMarked className="h-3 w-3" />
                </IconButton>
              </Tooltip>
            ) : undefined
          }
        >
          {folders.length === 0 ? (
            <p className="px-2 py-1 text-xs text-ink-faint">No saved filters yet</p>
          ) : (
            folders.map((folder) => (
              <NavItem
                key={folder.id}
                to={`/conversations?${folder.query}`}
                icon={<BookMarked />}
                label={folder.name}
                active={active.folder(folder.query)}
                onContextAction={
                  <IconButton
                    label={`Delete ${folder.name}`}
                    onClick={() => removeFolder(folder.id)}
                    className="h-5 w-5 bg-white/80 dark:bg-slate-900/80"
                  >
                    <Trash2 className="h-3 w-3" />
                  </IconButton>
                }
              />
            ))
          )}
        </NavGroup>

        {teams.length > 0 && (
          <NavGroup title="Teams">
            {teams.map((team) => (
              <NavItem
                key={team.id}
                to={`/conversations?team_id=${team.id}`}
                icon={<Users />}
                label={team.name}
                active={active.team(team.id)}
              />
            ))}
          </NavGroup>
        )}

        <NavGroup title="Channels">
          {inboxes.length === 0 ? (
            <Link
              to="/admin/inboxes/new"
              className="block rounded-lg px-2 py-1.5 text-xs text-primary hover:bg-primary-50 dark:hover:bg-primary-900/30"
            >
              + Connect a channel
            </Link>
          ) : (
            inboxes.map((inbox) => (
              <NavItem
                key={inbox.id}
                to={`/conversations?inbox_id=${inbox.id}`}
                icon={<ChannelIcon channelType={inbox.channel_type} />}
                label={inbox.name}
                active={active.inbox(inbox.id)}
                trailing={
                  inbox.connection_status && inbox.connection_status !== "connected" ? (
                    <Tooltip label={inbox.connection_status}>
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                    </Tooltip>
                  ) : undefined
                }
              />
            ))
          )}
        </NavGroup>

        {labels.length > 0 && (
          <NavGroup title="Labels">
            {labels
              .filter((label) => label.show_on_sidebar)
              .map((label) => (
                <NavItem
                  key={label.id}
                  to={`/conversations?labels=${encodeURIComponent(label.title)}`}
                  icon={
                    <span
                      className="block h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: label.color }}
                    />
                  }
                  label={label.title}
                  active={active.label(label.title)}
                />
              ))}
          </NavGroup>
        )}
      </nav>

      {/* Account */}
      <div className="border-t border-line p-2 dark:border-slate-800">
        <Dropdown
          above
          width="w-52"
          trigger={({ toggle, open }) => (
            <button
              type="button"
              onClick={toggle}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-slate-100 dark:hover:bg-slate-800",
                open && "bg-slate-100 dark:bg-slate-800",
              )}
            >
              <Avatar
                name={user?.display_name ?? user?.name}
                src={user?.avatar_url}
                seed={user?.id}
                size="md"
                status={user?.availability ?? "offline"}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink dark:text-slate-100">
                  {user?.display_name ?? user?.name}
                </span>
                <span className="block truncate text-2xs text-ink-muted dark:text-slate-400">
                  {user?.email}
                </span>
              </span>
            </button>
          )}
        >
          {({ close }) => (
            <>
              <DropdownItem
                icon={<UserCircle2 />}
                onClick={() => {
                  close();
                  navigate("/profile");
                }}
              >
                Profile settings
              </DropdownItem>
              <DropdownSeparator />
              <DropdownLabel>Availability</DropdownLabel>
              {(["online", "busy", "offline"] as Availability[]).map((option) => (
                <DropdownItem
                  key={option}
                  active={user?.availability === option}
                  icon={
                    <span
                      className={cn(
                        "block h-2 w-2 rounded-full",
                        option === "online" && "bg-emerald-500",
                        option === "busy" && "bg-amber-500",
                        option === "offline" && "bg-slate-400",
                      )}
                    />
                  }
                  onClick={() => {
                    close();
                    void setAvailability(option);
                  }}
                >
                  {option[0]!.toUpperCase() + option.slice(1)}
                </DropdownItem>
              ))}
              <DropdownSeparator />
              <DropdownItem
                icon={<Settings />}
                onClick={() => {
                  close();
                  navigate("/admin");
                }}
              >
                Settings
              </DropdownItem>
              <DropdownItem
                danger
                icon={<LogOut />}
                onClick={() => {
                  close();
                  void logout().then(() => navigate("/login"));
                }}
              >
                Log out
              </DropdownItem>
            </>
          )}
        </Dropdown>
      </div>
    </aside>
  );
}

export default Sidebar;
