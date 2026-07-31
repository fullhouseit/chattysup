/**
 * Chrome for every `/admin/*` screen.
 *
 * The app shell already supplies the workspace rail, so this layout only adds
 * the settings sub-navigation on the left and a scrolling content column that
 * the routed page fills with `<Outlet/>`.
 */
import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Bot,
  Gauge,
  Inbox as InboxIcon,
  KeyRound,
  MessageSquareQuote,
  Settings as SettingsIcon,
  ShieldCheck,
  Tag,
  Users,
  UsersRound,
  Webhook as WebhookIcon,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { PageSpinner } from "@/components/ui";

interface NavEntry {
  to: string;
  label: string;
  icon: LucideIcon;
  /** `index` routes need an exact match so they don't stay lit everywhere. */
  end?: boolean;
}

const GROUPS: { title: string; items: NavEntry[] }[] = [
  {
    title: "Workspace",
    items: [
      { to: "/admin", label: "Overview", icon: Gauge, end: true },
      { to: "/admin/inboxes", label: "Inboxes", icon: InboxIcon },
      { to: "/admin/agents", label: "Agents", icon: Users },
      { to: "/admin/teams", label: "Teams", icon: UsersRound },
    ],
  },
  {
    title: "Productivity",
    items: [
      { to: "/admin/labels", label: "Labels", icon: Tag },
      { to: "/admin/canned-responses", label: "Canned responses", icon: MessageSquareQuote },
      { to: "/admin/automations", label: "Automations", icon: Bot },
    ],
  },
  {
    title: "Developers",
    items: [
      { to: "/admin/webhooks", label: "Webhooks", icon: WebhookIcon },
      { to: "/admin/api-tokens", label: "API tokens", icon: KeyRound },
      { to: "/admin/sso", label: "Single sign-on", icon: ShieldCheck },
      { to: "/admin/settings", label: "Settings", icon: SettingsIcon },
    ],
  },
];

export function AdminLayout() {
  return (
    <div className="flex min-h-0 w-full flex-1">
      <nav className="w-56 shrink-0 overflow-y-auto border-r border-line bg-white px-2 py-4 scroll-thin dark:border-slate-800 dark:bg-slate-900">
        <p className="px-3 pb-3 text-sm font-semibold text-ink dark:text-slate-100">
          Settings
        </p>
        {GROUPS.map((group) => (
          <div key={group.title} className="mb-4">
            <p className="px-3 pb-1 text-2xs font-semibold uppercase tracking-wide text-ink-faint dark:text-slate-500">
              {group.title}
            </p>
            <ul className="space-y-0.5">
              {group.items.map(({ to, label, icon: Icon, end }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    end={end}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-sm transition-colors",
                        isActive
                          ? "bg-primary-50 font-medium text-primary dark:bg-primary-900/30 dark:text-primary-300"
                          : "text-ink-soft hover:bg-surface-muted dark:text-slate-300 dark:hover:bg-slate-800/70",
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="truncate">{label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="min-w-0 flex-1 overflow-y-auto bg-surface-muted p-6 scroll-thin dark:bg-[#0F141A]">
        <div className="mx-auto max-w-5xl">
          <Suspense fallback={<PageSpinner />}>
            <Outlet />
          </Suspense>
        </div>
      </div>
    </div>
  );
}

export default AdminLayout;
