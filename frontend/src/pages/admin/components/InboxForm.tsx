/**
 * The inbox form, shared by the creation wizard and the inbox detail screen.
 *
 * Nothing about a channel is hard-coded: the connection form is generated from
 * the `config_fields` the backend advertises in `GET /channels`, and the common
 * options (mode, proxy, greeting, business hours…) are only offered when the
 * channel declares support for them.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/cn";
import { SECRET_MASK } from "@/lib/types";
import type {
  ChannelDescriptor,
  ChannelFieldSpec,
  Dict,
  Inbox,
  InboxMode,
  InboxPayload,
} from "@/lib/types";
import { Input, Select, Switch, Textarea } from "@/components/ui";
import { WorkingHoursEditor } from "./WorkingHoursEditor";

/* --------------------------------------------------------------- state */

export interface InboxFormState {
  name: string;
  mode: InboxMode;
  proxy_url: string;
  config: Dict;
  greeting_enabled: boolean;
  greeting_message: string;
  out_of_office_message: string;
  csat_enabled: boolean;
  auto_assignment_enabled: boolean;
  auto_resolve_after_minutes: string;
  working_hours: Dict;
}

/** The default value the descriptor declares for a config field. */
function defaultFor(field: ChannelFieldSpec): unknown {
  if (field.default !== null && field.default !== undefined) return field.default;
  return field.kind === "boolean" ? false : "";
}

/** A blank form pre-filled from a channel descriptor's defaults. */
export function emptyInboxForm(channel: ChannelDescriptor | null): InboxFormState {
  const config: Dict = {};
  for (const field of channel?.config_fields ?? []) {
    config[field.key] = defaultFor(field);
  }
  return {
    name: "",
    mode: channel?.supports_webhook && !channel?.supports_polling ? "webhook" : "polling",
    proxy_url: "",
    config,
    greeting_enabled: false,
    greeting_message: "",
    out_of_office_message: "",
    csat_enabled: false,
    auto_assignment_enabled: true,
    auto_resolve_after_minutes: "",
    working_hours: {},
  };
}

/** Hydrate the form from a saved inbox (secrets arrive pre-masked). */
export function inboxFormFromInbox(inbox: Inbox): InboxFormState {
  return {
    name: inbox.name,
    mode: inbox.mode,
    proxy_url: inbox.proxy_url ?? "",
    config: { ...(inbox.config ?? {}) },
    greeting_enabled: inbox.greeting_enabled,
    greeting_message: inbox.greeting_message ?? "",
    out_of_office_message: inbox.out_of_office_message ?? "",
    csat_enabled: inbox.csat_enabled,
    auto_assignment_enabled: inbox.auto_assignment_enabled,
    auto_resolve_after_minutes:
      inbox.auto_resolve_after_minutes === null ? "" : String(inbox.auto_resolve_after_minutes),
    working_hours: { ...(inbox.working_hours ?? {}) },
  };
}

/**
 * Convert the form to an API payload.
 *
 * Untouched secrets are sent back as {@link SECRET_MASK}, which the API reads
 * as "keep the stored value".
 */
export function toInboxPayload(state: InboxFormState, channelType?: string): InboxPayload {
  const minutes = state.auto_resolve_after_minutes.trim();
  return {
    ...(channelType ? { channel_type: channelType } : {}),
    name: state.name.trim(),
    mode: state.mode,
    proxy_url: state.proxy_url.trim() || null,
    config: state.config,
    greeting_enabled: state.greeting_enabled,
    greeting_message: state.greeting_message.trim() || null,
    out_of_office_message: state.out_of_office_message.trim() || null,
    csat_enabled: state.csat_enabled,
    auto_assignment_enabled: state.auto_assignment_enabled,
    auto_resolve_after_minutes: minutes === "" ? null : Number(minutes),
    working_hours: state.working_hours,
  };
}

/** Names of required config fields that are still blank. */
export function missingRequired(
  channel: ChannelDescriptor | null,
  state: InboxFormState,
): string[] {
  const missing: string[] = [];
  for (const field of channel?.config_fields ?? []) {
    if (!field.required) continue;
    const value = state.config[field.key];
    if (value === undefined || value === null || value === "") missing.push(field.label);
  }
  return missing;
}

/* ---------------------------------------------------------------- fields */

function SecretInput({
  field,
  value,
  onChange,
}: {
  field: ChannelFieldSpec;
  value: string;
  onChange: (next: string) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const masked = value === SECRET_MASK;
  return (
    <Input
      label={field.label}
      type={revealed && !masked ? "text" : "password"}
      value={value}
      required={field.required}
      placeholder={field.placeholder || undefined}
      hint={
        masked
          ? "Stored securely. Type a new value to replace it."
          : field.help_text || undefined
      }
      onChange={(event) => onChange(event.target.value)}
      onFocus={() => {
        if (masked) onChange("");
      }}
      trailing={
        <button
          type="button"
          onClick={() => setRevealed((state) => !state)}
          className="pointer-events-auto text-ink-faint transition hover:text-ink-muted"
          aria-label={revealed ? "Hide value" : "Reveal value"}
        >
          {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
        </button>
      }
    />
  );
}

/** Render one `config_fields` entry according to its declared `kind`. */
export function ChannelField({
  field,
  value,
  onChange,
}: {
  field: ChannelFieldSpec;
  value: unknown;
  onChange: (next: unknown) => void;
}) {
  const text = value === null || value === undefined ? "" : String(value);

  switch (field.kind) {
    case "boolean":
      return (
        <Switch
          checked={Boolean(value)}
          onChange={onChange}
          label={field.label}
          description={field.help_text || undefined}
        />
      );
    case "textarea":
      return (
        <Textarea
          label={field.label}
          value={text}
          rows={4}
          required={field.required}
          placeholder={field.placeholder || undefined}
          hint={field.help_text || undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      );
    case "number":
      return (
        <Input
          label={field.label}
          type="number"
          value={text}
          required={field.required}
          placeholder={field.placeholder || undefined}
          hint={field.help_text || undefined}
          onChange={(event) =>
            onChange(event.target.value === "" ? "" : Number(event.target.value))
          }
        />
      );
    case "select":
      return (
        <Select
          label={field.label}
          value={text}
          required={field.required}
          hint={field.help_text || undefined}
          placeholder={field.placeholder || "Choose…"}
          options={field.options.map((option) => ({
            value: option.value,
            label: option.label,
          }))}
          onChange={(event) => onChange(event.target.value)}
        />
      );
    case "password":
      return <SecretInput field={field} value={text} onChange={onChange} />;
    case "url":
      return (
        <Input
          label={field.label}
          type="url"
          value={text}
          required={field.required}
          placeholder={field.placeholder || "https://…"}
          hint={field.help_text || undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      );
    case "text":
    default:
      return (
        <Input
          label={field.label}
          value={text}
          required={field.required}
          placeholder={field.placeholder || undefined}
          hint={field.help_text || undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      );
  }
}

/* ------------------------------------------------------------- sections */

export interface InboxSectionProps {
  channel?: ChannelDescriptor | null;
  state: InboxFormState;
  onChange: (patch: Partial<InboxFormState>) => void;
  className?: string;
  /** Extra content rendered under the connection fields (e.g. the webhook URL). */
  footer?: ReactNode;
}

/** Inbox name, the channel's own credentials, delivery mode and proxy. */
export function ConfigurationFields({
  channel,
  state,
  onChange,
  className,
  footer,
}: InboxSectionProps) {
  const modes = useMemo(() => {
    const options: { value: InboxMode; label: string }[] = [];
    if (channel?.supports_polling !== false) {
      options.push({ value: "polling", label: "Polling — the server fetches updates" });
    }
    if (channel?.supports_webhook) {
      options.push({ value: "webhook", label: "Webhook — the provider pushes to us" });
    }
    return options;
  }, [channel]);

  function setConfig(key: string, next: unknown) {
    onChange({ config: { ...state.config, [key]: next } });
  }

  return (
    <div className={cn("space-y-4", className)}>
      <Input
        label="Inbox name"
        value={state.name}
        required
        placeholder="Support — Telegram"
        hint="Shown in the sidebar and on every conversation from this channel."
        onChange={(event) => onChange({ name: event.target.value })}
      />

      {(channel?.config_fields ?? []).map((field) => (
        <ChannelField
          key={field.key}
          field={field}
          value={state.config[field.key]}
          onChange={(next) => setConfig(field.key, next)}
        />
      ))}

      {modes.length > 1 && (
        <Select
          label="Delivery mode"
          value={state.mode}
          options={modes}
          hint="Webhook is instant but needs a publicly reachable base URL."
          onChange={(event) => onChange({ mode: event.target.value as InboxMode })}
        />
      )}

      {channel?.supports_proxy && (
        <Input
          label="Proxy URL"
          value={state.proxy_url}
          placeholder="http://user:pass@host:3128"
          hint="Optional. Routes this inbox's outbound calls through an HTTP proxy."
          onChange={(event) => onChange({ proxy_url: event.target.value })}
        />
      )}

      {footer}
    </div>
  );
}

/** Greetings, business hours, assignment and auto-resolve. */
export function BehaviourFields({ state, onChange, className }: InboxSectionProps) {
  return (
    <div className={cn("space-y-5", className)}>
      <div className="space-y-3">
        <Switch
          checked={state.greeting_enabled}
          onChange={(next) => onChange({ greeting_enabled: next })}
          label="Send a greeting"
          description="Replies automatically the first time a contact writes in."
        />
        {state.greeting_enabled && (
          <Textarea
            label="Greeting message"
            rows={3}
            value={state.greeting_message}
            placeholder="Hi 👋 thanks for reaching out — an agent will be with you shortly."
            onChange={(event) => onChange({ greeting_message: event.target.value })}
          />
        )}
      </div>

      <Textarea
        label="Out-of-office message"
        rows={3}
        value={state.out_of_office_message}
        placeholder="We're away right now and will reply during business hours."
        hint="Sent when a message arrives outside the business hours below."
        onChange={(event) => onChange({ out_of_office_message: event.target.value })}
      />

      <WorkingHoursEditor
        value={state.working_hours}
        onChange={(next) => onChange({ working_hours: next })}
      />

      <Switch
        checked={state.auto_assignment_enabled}
        onChange={(next) => onChange({ auto_assignment_enabled: next })}
        label="Automatic assignment"
        description="Spread new conversations across the inbox's online collaborators."
      />

      <Switch
        checked={state.csat_enabled}
        onChange={(next) => onChange({ csat_enabled: next })}
        label="Ask for a satisfaction rating"
        description="Requests a CSAT score once a conversation is resolved."
      />

      <Input
        label="Auto-resolve after (minutes)"
        type="number"
        min={0}
        value={state.auto_resolve_after_minutes}
        placeholder="Leave empty to never auto-resolve"
        hint="Idle conversations in this inbox are resolved once this much time passes."
        onChange={(event) => onChange({ auto_resolve_after_minutes: event.target.value })}
      />
    </div>
  );
}
