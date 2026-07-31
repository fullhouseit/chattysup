/**
 * Typed HTTP client for the ChattySup REST API (`/api/v1`).
 *
 * All calls send the session cookie (`credentials: "include"`) and, when a JWT
 * has been captured at login, an `Authorization: Bearer …` header as well — the
 * latter keeps the app working in setups where third-party cookies are blocked
 * and is what the WebSocket handshake reuses.
 *
 * Failures raise {@link ApiError} carrying the HTTP status and the server's
 * `detail` message. A `401` outside of the auth endpoints clears the stored
 * token and bounces the browser to `/login`.
 */
import type {
  AdminStats,
  ApiToken,
  AuthConfig,
  AuthResponse,
  Automation,
  AutomationCatalogue,
  CannedResponse,
  ChannelDescriptor,
  Contact,
  ContactNote,
  ContactPayload,
  Conversation,
  ConversationQuery,
  ConversationUpdatePayload,
  Dict,
  HealthResponse,
  Inbox,
  InboxPayload,
  Label,
  Message,
  Paginated,
  ProfileUpdatePayload,
  SendMessagePayload,
  SsoProvider,
  Team,
  User,
  UserPayload,
  Webhook,
} from "./types";

export const API_BASE = "/api/v1";
const TOKEN_KEY = "chattysup.token";

/* ------------------------------------------------------------------ token */

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode — the cookie still carries the session */
  }
}

/* ------------------------------------------------------------------ error */

/** An unsuccessful API response. */
export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }

  /** True when the failure is a validation problem the form should surface. */
  get isValidation(): boolean {
    return this.status === 422 || this.status === 400;
  }
}

function messageFrom(status: number, body: any): string {
  const detail = body?.detail ?? body?.message;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first?.msg) return `${(first.loc ?? []).slice(1).join(".")}: ${first.msg}`;
  }
  if (status === 401) return "Your session has expired. Please sign in again.";
  if (status === 403) return "You are not allowed to do that.";
  if (status === 404) return "Not found.";
  if (status >= 500) return "Something went wrong on the server.";
  return `Request failed (${status})`;
}

function handleUnauthorized(path: string): void {
  if (path.startsWith("/auth/login") || path.startsWith("/auth/register")) return;
  setToken(null);
  const here = window.location.pathname + window.location.search;
  if (!here.startsWith("/login")) {
    window.location.assign(`/login?next=${encodeURIComponent(here)}`);
  }
}

/* ------------------------------------------------------------------- core */

type Query = Record<string, string | number | boolean | null | undefined>;

/** Serialise a query object, dropping empty values. */
export function qs(params?: Query): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });
  } catch (cause) {
    throw new ApiError(0, "Network error — the server is unreachable.", cause);
  }

  if (response.status === 401) {
    handleUnauthorized(path);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let body: any = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, messageFrom(response.status, body), body);
  }
  return body as T;
}

function json<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const http = {
  get: <T>(path: string, params?: Query) => request<T>(`${path}${qs(params)}`),
  post: <T>(path: string, body?: unknown) => json<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown) => json<T>("PATCH", path, body),
  put: <T>(path: string, body?: unknown) => json<T>("PUT", path, body),
  delete: <T = void>(path: string) => json<T>("DELETE", path),
  /** Multipart helper — `FormData` must not carry an explicit Content-Type. */
  form: <T>(path: string, data: FormData, method = "POST") =>
    request<T>(path, { method, body: data }),
};

/* ------------------------------------------------------------------- auth */

export const auth = {
  config: () => http.get<AuthConfig>("/auth/config"),
  register: (payload: { name: string; email: string; password: string }) =>
    http.post<AuthResponse>("/auth/register", payload),
  login: (payload: { email: string; password: string }) =>
    http.post<AuthResponse>("/auth/login", payload),
  logout: () => http.post<{ status: string }>("/auth/logout"),
  me: () => http.get<User>("/auth/me"),
  updateMe: (payload: ProfileUpdatePayload) => http.patch<User>("/auth/me", payload),
  ssoLoginUrl: (slug: string) => `${API_BASE}/auth/sso/${encodeURIComponent(slug)}/login`,
};

/* ------------------------------------------------------------------ users */

export const users = {
  list: () => http.get<User[]>("/users"),
  create: (payload: UserPayload) => http.post<User>("/users", payload),
  get: (id: number) => http.get<User>(`/users/${id}`),
  update: (id: number, payload: UserPayload) => http.patch<User>(`/users/${id}`, payload),
  remove: (id: number) => http.delete(`/users/${id}`),
};

/* ------------------------------------------------------------------ teams */

export const teams = {
  list: () => http.get<Team[]>("/teams"),
  create: (payload: { name: string; description?: string; allow_auto_assign?: boolean }) =>
    http.post<Team>("/teams", payload),
  update: (
    id: number,
    payload: { name?: string; description?: string; allow_auto_assign?: boolean },
  ) => http.patch<Team>(`/teams/${id}`, payload),
  remove: (id: number) => http.delete(`/teams/${id}`),
  setMembers: (id: number, userIds: number[]) =>
    http.put<Team>(`/teams/${id}/members`, { user_ids: userIds }),
};

/* --------------------------------------------------------------- channels */

export const channels = {
  list: () => http.get<ChannelDescriptor[]>("/channels"),
};

/* ---------------------------------------------------------------- inboxes */

export const inboxes = {
  list: () => http.get<Inbox[]>("/inboxes"),
  create: (payload: InboxPayload) => http.post<Inbox>("/inboxes", payload),
  get: (id: number) => http.get<Inbox>(`/inboxes/${id}`),
  update: (id: number, payload: InboxPayload) => http.patch<Inbox>(`/inboxes/${id}`, payload),
  remove: (id: number) => http.delete(`/inboxes/${id}`),
  test: (id: number) => http.post<Dict>(`/inboxes/${id}/test`),
  members: (id: number) => http.get<{ user_ids: number[] }>(`/inboxes/${id}/members`),
  setMembers: (id: number, userIds: number[]) =>
    http.put<{ user_ids: number[] }>(`/inboxes/${id}/members`, { user_ids: userIds }),
};

/* ----------------------------------------------------------- conversations */

export const conversations = {
  list: (query: ConversationQuery = {}) =>
    http.get<Paginated<Conversation>>("/conversations", query as Query),
  get: (id: number) => http.get<Conversation>(`/conversations/${id}`),
  update: (id: number, payload: ConversationUpdatePayload) =>
    http.patch<Conversation>(`/conversations/${id}`, payload),
  markRead: (id: number) => http.post<Conversation>(`/conversations/${id}/read`),
  typing: (id: number) => http.post<{ status: string }>(`/conversations/${id}/typing`),
  setLabels: (id: number, labels: string[]) =>
    http.put<Conversation>(`/conversations/${id}/labels`, { labels }),
  messages: (id: number, params: { before_id?: number; limit?: number } = {}) =>
    http.get<Message[]>(`/conversations/${id}/messages`, params as Query),
  participants: (id: number) => http.get<User[]>(`/conversations/${id}/participants`),
  addParticipant: (id: number, userId: number) =>
    http.post<User[]>(`/conversations/${id}/participants`, { user_id: userId }),
  removeParticipant: (id: number, userId: number) =>
    http.delete(`/conversations/${id}/participants/${userId}`),

  /** Post an agent reply / private note with optional uploads. */
  send: (id: number, payload: SendMessagePayload) => {
    const data = new FormData();
    if (payload.content) data.set("content", payload.content);
    data.set("private", String(Boolean(payload.private)));
    data.set("content_type", payload.content_type ?? "text");
    if (payload.is_voice) data.set("is_voice", "true");
    if (payload.reply_to_message_id) {
      data.set("reply_to_message_id", String(payload.reply_to_message_id));
    }
    for (const file of payload.files ?? []) data.append("files", file, file.name);
    return http.form<Message>(`/conversations/${id}/messages`, data);
  },
};

/* --------------------------------------------------------------- messages */

export const messages = {
  update: (id: number, content: string) => http.patch<Message>(`/messages/${id}`, { content }),
  remove: (id: number) => http.delete(`/messages/${id}`),
  react: (id: number, emoji: string) =>
    http.post<Message>(`/messages/${id}/reactions`, { emoji }),
  retry: (id: number) => http.post<Message>(`/messages/${id}/retry`),
};

/* ------------------------------------------------------------ attachments */

export const attachments = {
  /** Authenticated file URL; `variant=thumb` returns the preview rendition. */
  fileUrl: (id: number, variant?: "thumb") =>
    `${API_BASE}/attachments/${id}/file${variant ? `?variant=${variant}` : ""}`,
};

/* --------------------------------------------------------------- contacts */

export const contacts = {
  list: (params: { q?: string; page?: number; per_page?: number; sort?: string } = {}) =>
    http.get<Paginated<Contact>>("/contacts", params as Query),
  create: (payload: ContactPayload) => http.post<Contact>("/contacts", payload),
  get: (id: number) => http.get<Contact>(`/contacts/${id}`),
  update: (id: number, payload: ContactPayload) =>
    http.patch<Contact>(`/contacts/${id}`, payload),
  remove: (id: number) => http.delete(`/contacts/${id}`),
  conversations: (id: number) => http.get<Conversation[]>(`/contacts/${id}/conversations`),
  notes: (id: number) => http.get<ContactNote[]>(`/contacts/${id}/notes`),
  addNote: (id: number, content: string) =>
    http.post<ContactNote>(`/contacts/${id}/notes`, { content }),
  removeNote: (id: number, noteId: number) => http.delete(`/contacts/${id}/notes/${noteId}`),
  block: (id: number, blocked: boolean) =>
    http.post<Contact>(`/contacts/${id}/block`, { blocked }),
};

/* ----------------------------------------------------------------- labels */

export const labels = {
  list: () => http.get<Label[]>("/labels"),
  create: (payload: {
    title: string;
    description?: string;
    color?: string;
    show_on_sidebar?: boolean;
  }) => http.post<Label>("/labels", payload),
  update: (
    id: number,
    payload: {
      title?: string;
      description?: string;
      color?: string;
      show_on_sidebar?: boolean;
    },
  ) => http.patch<Label>(`/labels/${id}`, payload),
  remove: (id: number) => http.delete(`/labels/${id}`),
};

/* -------------------------------------------------------- canned responses */

export const cannedResponses = {
  list: () => http.get<CannedResponse[]>("/canned_responses"),
  create: (payload: { short_code: string; content: string }) =>
    http.post<CannedResponse>("/canned_responses", payload),
  update: (id: number, payload: { short_code?: string; content?: string }) =>
    http.patch<CannedResponse>(`/canned_responses/${id}`, payload),
  remove: (id: number) => http.delete(`/canned_responses/${id}`),
};

/* ------------------------------------------------------------- automations */

export const automations = {
  catalogue: () => http.get<AutomationCatalogue>("/automations/catalogue"),
  list: () => http.get<Automation[]>("/automations"),
  create: (payload: Partial<Automation>) => http.post<Automation>("/automations", payload),
  update: (id: number, payload: Partial<Automation>) =>
    http.patch<Automation>(`/automations/${id}`, payload),
  remove: (id: number) => http.delete(`/automations/${id}`),
};

/* ---------------------------------------------------------------- webhooks */

export const webhooks = {
  list: () => http.get<Webhook[]>("/webhooks"),
  events: () => http.get<string[]>("/webhooks/events"),
  create: (payload: Partial<Webhook>) => http.post<Webhook>("/webhooks", payload),
  update: (id: number, payload: Partial<Webhook>) =>
    http.patch<Webhook>(`/webhooks/${id}`, payload),
  remove: (id: number) => http.delete(`/webhooks/${id}`),
};

/* -------------------------------------------------------------- api tokens */

export const apiTokens = {
  list: () => http.get<ApiToken[]>("/api_tokens"),
  /** The plaintext token is returned exactly once, on creation. */
  create: (payload: { name: string; scopes?: string[]; expires_at?: string | null }) =>
    http.post<ApiToken>("/api_tokens", payload),
  remove: (id: number) => http.delete(`/api_tokens/${id}`),
};

/* --------------------------------------------------------------------- sso */

export const sso = {
  list: () => http.get<SsoProvider[]>("/sso_providers"),
  create: (payload: Partial<SsoProvider>) => http.post<SsoProvider>("/sso_providers", payload),
  update: (id: number, payload: Partial<SsoProvider>) =>
    http.patch<SsoProvider>(`/sso_providers/${id}`, payload),
  remove: (id: number) => http.delete(`/sso_providers/${id}`),
};

/* ---------------------------------------------------------------- settings */

export const settings = {
  get: () => http.get<Dict>("/settings"),
  update: (payload: Dict) => http.patch<Dict>("/settings", payload),
};

/* ------------------------------------------------------------------- admin */

export const adminStats = {
  get: () => http.get<AdminStats>("/admin/stats"),
};

export const health = {
  get: () => http.get<HealthResponse>("/health"),
};

/** Namespaced access for callers that prefer a single import. */
export const api = {
  auth,
  users,
  teams,
  channels,
  inboxes,
  conversations,
  messages,
  attachments,
  contacts,
  labels,
  cannedResponses,
  automations,
  webhooks,
  apiTokens,
  sso,
  settings,
  adminStats,
  health,
};

export default api;
