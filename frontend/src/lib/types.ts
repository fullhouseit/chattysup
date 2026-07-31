/**
 * TypeScript mirrors of `backend/app/serializers.py` and the REST contract.
 *
 * Every interface here matches, key for key, the plain dicts the API returns.
 * Nothing in the app should invent a different shape for a server object.
 */

/* ------------------------------------------------------------------ enums */

export type UserRole = "admin" | "agent";
export type Availability = "online" | "busy" | "offline";
export type ConversationStatus = "open" | "pending" | "snoozed" | "resolved";
export type ConversationPriority = "none" | "low" | "medium" | "high" | "urgent";
export type MessageType = "incoming" | "outgoing" | "activity" | "template";
export type MessageStatus = "pending" | "sent" | "delivered" | "read" | "failed";
export type SenderType = "contact" | "user" | "system" | "bot";
export type ContentType =
  | "text"
  | "sticker"
  | "location"
  | "contact_card"
  | "poll"
  | "story"
  | "system";
export type AttachmentType =
  | "image"
  | "audio"
  | "voice"
  | "video"
  | "video_note"
  | "file"
  | "sticker"
  | "animation"
  | "location"
  | "contact_card";
export type InboxMode = "polling" | "webhook";
export type SsoKind = "oidc" | "saml";
export type ConnectionStatus = string;

/** The mask the API substitutes for stored secrets. */
export const SECRET_MASK = "••••••••";

/* ------------------------------------------------------------- primitives */

export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
export type Dict<T = any> = Record<string, T>;

export interface Paginated<T> {
  data: T[];
  meta: PageMeta;
}

export interface PageMeta {
  total: number;
  page: number;
  per_page: number;
  counts?: ConversationCounts;
}

export interface ConversationCounts {
  mine: number;
  unassigned: number;
  all: number;
}

/* ------------------------------------------------------------------ users */

/** `serialize_user` */
export interface User {
  id: number;
  name: string;
  display_name: string;
  email: string;
  role: UserRole;
  avatar_url: string | null;
  availability: Availability;
  signature: string | null;
  is_active: boolean;
  provider: string | null;
  created_at: string | null;
}

/** `serialize_team` */
export interface Team {
  id: number;
  name: string;
  description: string | null;
  allow_auto_assign: boolean;
  member_ids: number[];
}

/** `serialize_label` */
export interface Label {
  id: number;
  title: string;
  description: string | null;
  color: string;
  show_on_sidebar: boolean;
}

/* --------------------------------------------------------------- channels */

export interface ChannelFieldSpec {
  key: string;
  label: string;
  kind: "text" | "password" | "textarea" | "number" | "boolean" | "select" | "url";
  required: boolean;
  placeholder: string;
  help_text: string;
  default: Json;
  secret: boolean;
  options: { value: string; label: string }[];
}

/** `BaseChannel.describe()` */
export interface ChannelDescriptor {
  key: string;
  display_name: string;
  description: string;
  icon: string;
  color: string;
  supports_polling: boolean;
  supports_webhook: boolean;
  supports_proxy: boolean;
  capabilities: string[];
  config_fields: ChannelFieldSpec[];
}

/* ---------------------------------------------------------------- inboxes */

/** `serialize_inbox` */
export interface Inbox {
  id: number;
  name: string;
  channel_type: string;
  avatar_url: string | null;
  is_active: boolean;
  mode: InboxMode;
  proxy_url: string | null;
  config: Dict;
  capabilities: string[];
  greeting_enabled: boolean;
  greeting_message: string | null;
  csat_enabled: boolean;
  auto_assignment_enabled: boolean;
  auto_resolve_after_minutes: number | null;
  working_hours: Dict;
  out_of_office_message: string | null;
  connection_status: ConnectionStatus;
  connection_error: string | null;
  last_polled_at: string | null;
  webhook_url: string | null;
  created_at: string | null;
}

/** The trimmed inbox embedded in `serialize_conversation`. */
export interface InboxRef {
  id: number;
  name: string;
  channel_type: string;
  avatar_url: string | null;
}

/* --------------------------------------------------------------- contacts */

/** `serialize_contact` */
export interface Contact {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  avatar_url: string | null;
  identifier: string | null;
  company: string | null;
  title: string | null;
  location: string | null;
  country_code: string | null;
  timezone: string | null;
  blocked: boolean;
  custom_attributes: Dict;
  social_profiles: Dict<string>;
  last_activity_at: string | null;
  created_at: string | null;
}

/** `serialize_contact_note` */
export interface ContactNote {
  id: number;
  contact_id: number;
  user_id: number | null;
  content: string;
  created_at: string | null;
}

/* ------------------------------------------------------------- attachments */

/** `serialize_attachment` */
export interface Attachment {
  id: number;
  file_type: AttachmentType;
  file_name: string | null;
  file_size: number | null;
  mime_type: string | null;
  url: string | null;
  thumb_url: string | null;
  meta: Dict;
}

/* ---------------------------------------------------------------- messages */

export interface Reaction {
  emoji: string;
  count: number;
  by_me: boolean;
  user_ids: number[];
}

/** `serialize_message` */
export interface Message {
  id: number;
  conversation_id: number;
  inbox_id: number;
  content: string | null;
  message_type: MessageType;
  content_type: ContentType;
  private: boolean;
  status: MessageStatus;
  sender_type: SenderType | null;
  sender_id: number | null;
  source_id: string | null;
  content_attributes: Dict;
  attachments: Attachment[];
  reactions: Reaction[];
  edited_at: string | null;
  deleted_at: string | null;
  external_error: string | null;
  created_at: string | null;
}

/* ----------------------------------------------------------- conversations */

/** `serialize_conversation` */
export interface Conversation {
  id: number;
  inbox_id: number;
  inbox: InboxRef | null;
  contact: Contact | null;
  assignee: User | null;
  assignee_id: number | null;
  team_id: number | null;
  status: ConversationStatus;
  priority: ConversationPriority;
  unread_count: number;
  muted: boolean;
  labels: Label[];
  custom_attributes: Dict;
  last_activity_at: string | null;
  waiting_since: string | null;
  snoozed_until: string | null;
  resolved_at: string | null;
  created_at: string | null;
  last_message: Message | null;
  sender: User | null;
}

/* ------------------------------------------------------------------- misc */

export interface CannedResponse {
  id: number;
  short_code: string;
  content: string;
}

export interface AutomationCondition {
  attribute: string;
  operator: string;
  values: Json[];
}

export interface AutomationAction {
  action: string;
  params?: Dict;
}

export interface Automation {
  id: number;
  name: string;
  description: string | null;
  event_name: string;
  conditions: AutomationCondition[];
  condition_logic: "and" | "or";
  actions: AutomationAction[];
  active: boolean;
  inbox_id: number | null;
  run_once_per_conversation: boolean;
  execution_count: number;
  last_executed_at: string | null;
  created_at: string | null;
}

export interface AutomationCatalogue {
  events: string[];
  attributes: Dict<any>;
  operators: Dict<any>;
  actions: Dict<any> | any[];
}

export interface Webhook {
  id: number;
  url: string;
  name: string | null;
  subscriptions: string[];
  secret: string | null;
  active: boolean;
  inbox_id: number | null;
  last_status: number | null;
  last_error: string | null;
  last_delivered_at: string | null;
  created_at?: string | null;
}

export interface ApiToken {
  id: number;
  name: string;
  prefix: string;
  user_id: number;
  scopes: string[];
  active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string | null;
  /** Only present in the POST /api_tokens response. */
  token?: string;
}

export interface SsoProvider {
  id: number;
  slug: string;
  name: string;
  kind: SsoKind;
  enabled: boolean;
  config: Dict;
}

export interface SsoProviderRef {
  slug: string;
  name: string;
  kind: SsoKind;
}

export interface AuthConfig {
  installation_name: string;
  registration_enabled: boolean;
  has_users: boolean;
  sso_providers: SsoProviderRef[];
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface HealthResponse {
  status: string;
  version: string;
  channels: string[];
}

export interface AdminStatsInbox {
  id: number;
  name: string;
  channel_type: string;
  connection_status: string;
  open_conversations: number;
}

export interface AdminStats {
  conversations: {
    open: number;
    pending: number;
    resolved: number;
    snoozed: number;
    total: number;
  };
  messages_today: number;
  contacts: number;
  agents: number;
  agents_online: number;
  inboxes: AdminStatsInbox[];
  recent_activity: Dict[];
}

/* ------------------------------------------------------------- realtime */

export type RealtimeEvent =
  | "conversation.created"
  | "conversation.updated"
  | "conversation.typing"
  | "message.created"
  | "message.updated"
  | "message.deleted"
  | "contact.updated"
  | "inbox.updated"
  | "presence.updated";

export interface RealtimeEnvelope<T = any> {
  event: RealtimeEvent | string;
  data: T;
}

/* --------------------------------------------------------- request bodies */

export interface ConversationQuery {
  status?: ConversationStatus | "all";
  inbox_id?: number;
  assignee?: "me" | "unassigned" | "all" | string;
  labels?: string;
  priority?: ConversationPriority | "all";
  q?: string;
  sort?: "latest" | "oldest" | "priority";
  page?: number;
  per_page?: number;
}

export interface ConversationUpdatePayload {
  status?: ConversationStatus;
  priority?: ConversationPriority;
  assignee_id?: number | null;
  team_id?: number | null;
  muted?: boolean;
  snoozed_until?: string | null;
  custom_attributes?: Dict;
}

export interface SendMessagePayload {
  content?: string;
  private?: boolean;
  reply_to_message_id?: number | null;
  content_type?: ContentType;
  is_voice?: boolean;
  files?: File[];
}

export interface ProfileUpdatePayload {
  name?: string;
  display_name?: string;
  avatar_url?: string | null;
  signature?: string | null;
  availability?: Availability;
  password?: string;
  current_password?: string;
}

export interface InboxPayload {
  name?: string;
  channel_type?: string;
  mode?: InboxMode;
  proxy_url?: string | null;
  config?: Dict;
  greeting_enabled?: boolean;
  greeting_message?: string | null;
  csat_enabled?: boolean;
  auto_assignment_enabled?: boolean;
  auto_resolve_after_minutes?: number | null;
  working_hours?: Dict;
  out_of_office_message?: string | null;
  is_active?: boolean;
  avatar_url?: string | null;
}

export interface UserPayload {
  name?: string;
  email?: string;
  password?: string;
  role?: UserRole;
  is_active?: boolean;
  availability?: Availability;
  display_name?: string;
  avatar_url?: string | null;
  signature?: string | null;
}

export interface ContactPayload {
  name?: string;
  email?: string | null;
  phone?: string | null;
  avatar_url?: string | null;
  identifier?: string | null;
  company?: string | null;
  title?: string | null;
  location?: string | null;
  country_code?: string | null;
  timezone?: string | null;
  custom_attributes?: Dict;
  social_profiles?: Dict<string>;
}
