/**
 * Application routes.
 *
 * The contacts and admin screens live in sibling folders owned by another part
 * of the codebase; they are loaded lazily through {@link lazyPage}, which falls
 * back to a "Coming soon" placeholder if a module cannot be resolved so the app
 * always boots.
 */
import { Suspense, lazy, type ComponentType, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Hammer } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState, PageSpinner } from "@/components/ui";
import { useAuth } from "@/store/auth";
import ConversationsPage from "@/pages/Conversations";
import LoginPage from "@/pages/Login";
import NotFoundPage from "@/pages/NotFound";
import ProfilePage from "@/pages/Profile";
import RegisterPage from "@/pages/Register";

/* ------------------------------------------------------------ lazy loader */

function ComingSoon({ name }: { name: string }) {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <EmptyState
        icon={<Hammer />}
        title={`${name} is coming soon`}
        description="This screen has not been built yet."
      />
    </div>
  );
}

/** `React.lazy` that degrades to a placeholder instead of crashing the app. */
function lazyPage(loader: () => Promise<any>, name: string) {
  return lazy(async () => {
    try {
      const module = await loader();
      const component = (module?.default ?? module?.[name]) as ComponentType<any> | undefined;
      if (component) return { default: component };
    } catch {
      /* module missing — fall through to the placeholder */
    }
    return { default: () => <ComingSoon name={name} /> };
  });
}

/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-ignore -- provided by the contacts screens
const ContactsPage = lazyPage(() => import("./pages/contacts/ContactsPage"), "Contacts");
// @ts-ignore -- provided by the contacts screens
const ContactDetailPage = lazyPage(() => import("./pages/contacts/ContactDetailPage"), "Contact");
// @ts-ignore -- provided by the admin screens
const AdminLayout = lazyPage(() => import("./pages/admin/AdminLayout"), "Administration");
// @ts-ignore -- provided by the admin screens
const DashboardPage = lazyPage(() => import("./pages/admin/DashboardPage"), "Dashboard");
// @ts-ignore -- provided by the admin screens
const InboxesPage = lazyPage(() => import("./pages/admin/InboxesPage"), "Inboxes");
// @ts-ignore -- provided by the admin screens
const InboxNewPage = lazyPage(() => import("./pages/admin/InboxNewPage"), "New inbox");
// @ts-ignore -- provided by the admin screens
const InboxDetailPage = lazyPage(() => import("./pages/admin/InboxDetailPage"), "Inbox");
// @ts-ignore -- provided by the admin screens
const AgentsPage = lazyPage(() => import("./pages/admin/AgentsPage"), "Agents");
// @ts-ignore -- provided by the admin screens
const TeamsPage = lazyPage(() => import("./pages/admin/TeamsPage"), "Teams");
// @ts-ignore -- provided by the admin screens
const LabelsPage = lazyPage(() => import("./pages/admin/LabelsPage"), "Labels");
const CannedResponsesPage = lazyPage(
  // @ts-ignore -- provided by the admin screens
  () => import("./pages/admin/CannedResponsesPage"),
  "Canned responses",
);
// @ts-ignore -- provided by the admin screens
const AutomationsPage = lazyPage(() => import("./pages/admin/AutomationsPage"), "Automations");
// @ts-ignore -- provided by the admin screens
const WebhooksPage = lazyPage(() => import("./pages/admin/WebhooksPage"), "Webhooks");
// @ts-ignore -- provided by the admin screens
const ApiTokensPage = lazyPage(() => import("./pages/admin/ApiTokensPage"), "API tokens");
// @ts-ignore -- provided by the admin screens
const SsoPage = lazyPage(() => import("./pages/admin/SsoPage"), "Single sign-on");
// @ts-ignore -- provided by the admin screens
const SettingsPage = lazyPage(() => import("./pages/admin/SettingsPage"), "Settings");
/* eslint-enable @typescript-eslint/ban-ts-comment */

/* --------------------------------------------------------------- guards */

/** Redirects to `/login` when signed out, and to `/conversations` when the
 *  route requires an administrator. */
export function ProtectedRoute({
  children,
  adminOnly = false,
}: {
  children?: ReactNode;
  adminOnly?: boolean;
}) {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  const location = useLocation();

  if (loading) return <PageSpinner />;
  if (!isAuthenticated) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (adminOnly && !isAdmin) return <Navigate to="/conversations" replace />;
  return <>{children ?? <Outlet />}</>;
}

/** Wraps a routed screen in the app chrome and a suspense boundary. */
function Shell() {
  return (
    <AppShell>
      <Suspense fallback={<PageSpinner />}>
        <Outlet />
      </Suspense>
    </AppShell>
  );
}

/* --------------------------------------------------------------- routes */

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<Shell />}>
          <Route index element={<Navigate to="/conversations" replace />} />
          <Route path="/conversations" element={<ConversationsPage />} />
          <Route path="/conversations/:id" element={<ConversationsPage />} />

          <Route path="/contacts" element={<ContactsPage />} />
          <Route path="/contacts/:id" element={<ContactDetailPage />} />

          <Route path="/profile" element={<ProfilePage />} />

          <Route
            path="/admin"
            element={
              <ProtectedRoute adminOnly>
                <AdminLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="inboxes" element={<InboxesPage />} />
            <Route path="inboxes/new" element={<InboxNewPage />} />
            <Route path="inboxes/:id" element={<InboxDetailPage />} />
            <Route path="agents" element={<AgentsPage />} />
            <Route path="teams" element={<TeamsPage />} />
            <Route path="labels" element={<LabelsPage />} />
            <Route path="canned-responses" element={<CannedResponsesPage />} />
            <Route path="automations" element={<AutomationsPage />} />
            <Route path="webhooks" element={<WebhooksPage />} />
            <Route path="api-tokens" element={<ApiTokensPage />} />
            <Route path="sso" element={<SsoPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

export default AppRoutes;
