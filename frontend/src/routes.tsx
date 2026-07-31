/**
 * Application routes.
 *
 * The contacts and admin screens are code-split: they are only fetched when an
 * agent actually navigates to them, which keeps the conversation bundle small.
 */
import { Suspense, lazy, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { PageSpinner } from "@/components/ui";
import { useAuth } from "@/store/auth";
import ConversationsPage from "@/pages/Conversations";
import LoginPage from "@/pages/Login";
import NotFoundPage from "@/pages/NotFound";
import ProfilePage from "@/pages/Profile";
import RegisterPage from "@/pages/Register";

/* ---------------------------------------------------- code-split screens */

const ContactsPage = lazy(() => import("./pages/contacts/ContactsPage"));
const ContactDetailPage = lazy(() => import("./pages/contacts/ContactDetailPage"));
const AdminLayout = lazy(() => import("./pages/admin/AdminLayout"));
const DashboardPage = lazy(() => import("./pages/admin/DashboardPage"));
const InboxesPage = lazy(() => import("./pages/admin/InboxesPage"));
const InboxNewPage = lazy(() => import("./pages/admin/InboxNewPage"));
const InboxDetailPage = lazy(() => import("./pages/admin/InboxDetailPage"));
const AgentsPage = lazy(() => import("./pages/admin/AgentsPage"));
const TeamsPage = lazy(() => import("./pages/admin/TeamsPage"));
const LabelsPage = lazy(() => import("./pages/admin/LabelsPage"));
const CannedResponsesPage = lazy(() => import("./pages/admin/CannedResponsesPage"));
const AutomationsPage = lazy(() => import("./pages/admin/AutomationsPage"));
const WebhooksPage = lazy(() => import("./pages/admin/WebhooksPage"));
const ApiTokensPage = lazy(() => import("./pages/admin/ApiTokensPage"));
const SsoPage = lazy(() => import("./pages/admin/SsoPage"));
const SettingsPage = lazy(() => import("./pages/admin/SettingsPage"));

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
