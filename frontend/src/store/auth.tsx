/**
 * Authentication context.
 *
 * Bootstraps `/auth/config` (installation name, whether registration is open,
 * SSO providers) and `/auth/me`, then exposes login / register / logout and a
 * profile updater. The JWT returned by the API is kept in `localStorage` so the
 * WebSocket handshake can reuse it; the httpOnly cookie remains the source of
 * truth for plain HTTP calls.
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
import { ApiError, auth as authApi, getToken, setToken } from "@/lib/api";
import type { AuthConfig, ProfileUpdatePayload, User } from "@/lib/types";

interface AuthContextValue {
  user: User | null;
  config: AuthConfig | null;
  /** True until the initial bootstrap round-trip settles. */
  loading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (name: string, email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<User | null>;
  refreshConfig: () => Promise<AuthConfig | null>;
  updateProfile: (payload: ProfileUpdatePayload) => Promise<User>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshConfig = useCallback(async () => {
    try {
      const next = await authApi.config();
      setConfig(next);
      return next;
    } catch {
      return null;
    }
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const next = await authApi.me();
      setUser(next);
      return next;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setUser(null);
        setToken(null);
      }
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const tasks: Promise<unknown>[] = [refreshConfig()];
      // Only probe /auth/me when a session is plausible; the cookie may exist
      // without a stored token, so try either way and swallow the 401.
      tasks.push(refreshUser());
      await Promise.all(tasks);
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshConfig, refreshUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await authApi.login({ email, password });
      setToken(result.token);
      setUser(result.user);
      await refreshConfig();
      return result.user;
    },
    [refreshConfig],
  );

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      const result = await authApi.register({ name, email, password });
      setToken(result.token);
      setUser(result.user);
      await refreshConfig();
      return result.user;
    },
    [refreshConfig],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* the local session is dropped regardless */
    }
    setToken(null);
    setUser(null);
  }, []);

  const updateProfile = useCallback(async (payload: ProfileUpdatePayload) => {
    const next = await authApi.updateMe(payload);
    setUser(next);
    return next;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      config,
      loading,
      isAuthenticated: Boolean(user),
      isAdmin: user?.role === "admin",
      login,
      register,
      logout,
      refreshUser,
      refreshConfig,
      updateProfile,
    }),
    [user, config, loading, login, register, logout, refreshUser, refreshConfig, updateProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Access the authentication context (throws outside the provider). */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

export { getToken };
export default AuthProvider;
