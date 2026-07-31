/**
 * Shared workspace data + the realtime bus.
 *
 * Everything the whole UI needs regardless of the current route — inboxes,
 * labels, agents, teams, canned responses — is fetched once here through React
 * Query and kept warm. The provider also owns the single WebSocket connection
 * and re-exports a `useRealtime` hook so any component can subscribe to server
 * events without opening its own socket.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cannedResponses as cannedApi,
  inboxes as inboxesApi,
  labels as labelsApi,
  teams as teamsApi,
  users as usersApi,
} from "@/lib/api";
import { realtime, type ConnectionState } from "@/lib/ws";
import type { CannedResponse, Inbox, Label, Team, User } from "@/lib/types";
import { useAuth } from "./auth";

export const queryKeys = {
  inboxes: ["inboxes"] as const,
  labels: ["labels"] as const,
  agents: ["users"] as const,
  teams: ["teams"] as const,
  canned: ["canned_responses"] as const,
  conversations: (query: unknown) => ["conversations", query] as const,
  conversation: (id: number) => ["conversation", id] as const,
  messages: (id: number) => ["messages", id] as const,
  participants: (id: number) => ["participants", id] as const,
  contact: (id: number) => ["contact", id] as const,
};

interface AppContextValue {
  inboxes: Inbox[];
  labels: Label[];
  agents: User[];
  teams: Team[];
  canned: CannedResponse[];
  loading: boolean;
  connection: ConnectionState;
  inboxById: (id: number | null | undefined) => Inbox | undefined;
  agentById: (id: number | null | undefined) => User | undefined;
  labelByTitle: (title: string) => Label | undefined;
  refreshAll: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppDataProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const [connection, setConnection] = useState<ConnectionState>(realtime.state);

  const enabled = isAuthenticated;
  const common = { enabled, staleTime: 60_000 };

  const inboxesQuery = useQuery({
    queryKey: queryKeys.inboxes,
    queryFn: inboxesApi.list,
    ...common,
  });
  const labelsQuery = useQuery({
    queryKey: queryKeys.labels,
    queryFn: labelsApi.list,
    ...common,
  });
  const agentsQuery = useQuery({
    queryKey: queryKeys.agents,
    queryFn: usersApi.list,
    ...common,
    // /users is admin-only; agents fall back to an empty roster.
    retry: false,
  });
  const teamsQuery = useQuery({
    queryKey: queryKeys.teams,
    queryFn: teamsApi.list,
    ...common,
    retry: false,
  });
  const cannedQuery = useQuery({
    queryKey: queryKeys.canned,
    queryFn: cannedApi.list,
    ...common,
  });

  /* ------------------------------------------------------------- realtime */

  useEffect(() => {
    if (!isAuthenticated) {
      realtime.stop();
      setConnection("closed");
      return;
    }
    const off = realtime.on("status", (state: ConnectionState) => setConnection(state));
    realtime.start();
    return () => {
      off();
      realtime.stop();
    };
  }, [isAuthenticated]);

  // Keep the shared collections fresh when the server says they changed.
  useEffect(() => {
    if (!isAuthenticated) return;
    const offInbox = realtime.on("inbox.updated", () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inboxes });
    });
    const offPresence = realtime.on("presence.updated", () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents });
    });
    return () => {
      offInbox();
      offPresence();
    };
  }, [isAuthenticated, queryClient]);

  const inboxes = inboxesQuery.data ?? [];
  const labels = labelsQuery.data ?? [];
  const agents = agentsQuery.data ?? [];
  const teams = teamsQuery.data ?? [];
  const canned = cannedQuery.data ?? [];

  const refreshAll = useCallback(() => {
    for (const key of [
      queryKeys.inboxes,
      queryKeys.labels,
      queryKeys.agents,
      queryKeys.teams,
      queryKeys.canned,
    ]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  }, [queryClient]);

  const value = useMemo<AppContextValue>(
    () => ({
      inboxes,
      labels,
      agents,
      teams,
      canned,
      loading:
        enabled &&
        (inboxesQuery.isLoading || labelsQuery.isLoading || cannedQuery.isLoading),
      connection,
      inboxById: (id) => inboxes.find((inbox) => inbox.id === id),
      agentById: (id) => agents.find((agent) => agent.id === id),
      labelByTitle: (title) =>
        labels.find((label) => label.title.toLowerCase() === title.toLowerCase()),
      refreshAll,
    }),
    [
      inboxes,
      labels,
      agents,
      teams,
      canned,
      enabled,
      connection,
      inboxesQuery.isLoading,
      labelsQuery.isLoading,
      cannedQuery.isLoading,
      refreshAll,
    ],
  );

  // `isAdmin` is unused today but keeps the dependency explicit for future
  // admin-only prefetching.
  void isAdmin;

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

/** Access the shared workspace data. */
export function useAppData(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error("useAppData must be used inside <AppDataProvider>");
  return context;
}

/**
 * Subscribe to a realtime event for the lifetime of the component.
 *
 * ```tsx
 * useRealtime("message.created", (message) => append(message));
 * ```
 */
export function useRealtime<T = any>(
  event: string,
  handler: (data: T, event: string) => void,
): void {
  useEffect(() => realtime.on(event, handler as (data: any, event: string) => void), [
    event,
    handler,
  ]);
}

export { realtime };
export default AppDataProvider;
