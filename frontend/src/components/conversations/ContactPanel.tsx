/**
 * PANE 4 — the right-hand contact sidebar.
 *
 * Identity block, quick actions and the collapsible sections: conversation
 * actions, participants, macros, contact attributes, conversation information
 * and the contact's previous conversations.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AtSign,
  Ban,
  Building2,
  Check,
  Copy,
  Globe,
  Link2,
  Mail,
  MapPin,
  MessageSquare,
  Merge,
  Phone,
  Plus,
  Trash2,
  Pencil,
  X,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/cn";
import {
  contacts as contactsApi,
  conversations as conversationsApi,
} from "@/lib/api";
import { fullTimestamp, humanize, relativeTime } from "@/lib/format";
import type {
  Conversation,
  ConversationPriority,
  ConversationStatus,
} from "@/lib/types";
import { queryKeys, useAppData } from "@/store/app";
import {
  Accordion,
  Avatar,
  Badge,
  Button,
  ConfirmDialog,
  Dropdown,
  DropdownItem,
  IconButton,
  Input,
  Modal,
  Select,
  Spinner,
  Tabs,
  Tooltip,
  useToast,
} from "@/components/ui";
import { ChannelIcon } from "./ChannelIcon";

export interface ContactPanelProps {
  conversation: Conversation;
  onUpdateConversation: (patch: Record<string, unknown>) => void;
  onInsertCanned: (content: string) => void;
  onSelectConversation: (id: number) => void;
  onClose: () => void;
}

/* ------------------------------------------------------------- fragments */

function CopyRow({
  icon,
  value,
  href,
  placeholder,
}: {
  icon: React.ReactNode;
  value: string | null | undefined;
  href?: string;
  placeholder: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="group flex items-center gap-2 py-1">
      <span className="shrink-0 text-ink-faint [&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
      {value ? (
        href ? (
          <a
            href={href}
            className="min-w-0 flex-1 truncate text-xs text-ink-soft hover:text-primary dark:text-slate-300"
          >
            {value}
          </a>
        ) : (
          <span className="min-w-0 flex-1 truncate text-xs text-ink-soft dark:text-slate-300">
            {value}
          </span>
        )
      ) : (
        <span className="min-w-0 flex-1 truncate text-xs italic text-ink-faint">
          {placeholder}
        </span>
      )}
      {value && (
        <button
          type="button"
          onClick={() => void copy()}
          aria-label="Copy"
          className="shrink-0 text-ink-faint opacity-0 transition group-hover:opacity-100 hover:text-primary"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      )}
    </div>
  );
}

function RoundAction({
  icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <Tooltip label={label}>
      <button
        type="button"
        aria-label={label}
        onClick={onClick}
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-full border border-line bg-white text-ink-muted transition hover:border-primary-200 hover:bg-primary-50 hover:text-primary",
          "dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700",
          danger && "hover:border-red-200 hover:bg-red-50 hover:text-red-600",
          "[&>svg]:h-4 [&>svg]:w-4",
        )}
      >
        {icon}
      </button>
    </Tooltip>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1 text-xs">
      <span className="shrink-0 text-ink-faint">{label}</span>
      <span className="min-w-0 truncate text-right text-ink-soft dark:text-slate-300">
        {value ?? "—"}
      </span>
    </div>
  );
}

/* ----------------------------------------------------------------- panel */

export function ContactPanel({
  conversation,
  onUpdateConversation,
  onInsertCanned,
  onSelectConversation,
  onClose,
}: ContactPanelProps) {
  const { agents, teams, canned } = useAppData();
  const queryClient = useQueryClient();
  const toast = useToast();
  const contact = conversation.contact;

  const [tab, setTab] = useState<"contact" | "copilot">("contact");
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [attributeDraft, setAttributeDraft] = useState({ key: "", value: "" });

  const participantsQuery = useQuery({
    queryKey: queryKeys.participants(conversation.id),
    queryFn: () => conversationsApi.participants(conversation.id),
  });

  const previousQuery = useQuery({
    queryKey: ["contact-conversations", contact?.id],
    queryFn: () => contactsApi.conversations(contact!.id),
    enabled: Boolean(contact?.id),
  });

  const socials = useMemo(
    () => Object.entries(contact?.social_profiles ?? {}).filter(([, value]) => value),
    [contact],
  );

  async function patchContact(payload: Record<string, unknown>) {
    if (!contact) return;
    try {
      await contactsApi.update(contact.id, payload);
      queryClient.invalidateQueries({ queryKey: queryKeys.conversation(conversation.id) });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      toast.success("Contact updated");
    } catch (error) {
      toast.error("Could not update the contact", (error as Error).message);
    }
  }

  async function addParticipant(userId: number) {
    try {
      await conversationsApi.addParticipant(conversation.id, userId);
      queryClient.invalidateQueries({
        queryKey: queryKeys.participants(conversation.id),
      });
    } catch (error) {
      toast.error("Could not add the participant", (error as Error).message);
    }
  }

  async function removeParticipant(userId: number) {
    try {
      await conversationsApi.removeParticipant(conversation.id, userId);
      queryClient.invalidateQueries({
        queryKey: queryKeys.participants(conversation.id),
      });
    } catch (error) {
      toast.error("Could not remove the participant", (error as Error).message);
    }
  }

  async function deleteContact() {
    if (!contact) return;
    try {
      await contactsApi.remove(contact.id);
      toast.success("Contact deleted");
      setConfirmDelete(false);
      onClose();
    } catch (error) {
      toast.error("Could not delete the contact", (error as Error).message);
    }
  }

  const participants = participantsQuery.data ?? [];
  const availableAgents = agents.filter(
    (agent) => !participants.some((person) => person.id === agent.id),
  );
  const previous = (previousQuery.data ?? []).filter(
    (item) => item.id !== conversation.id,
  );

  return (
    <aside className="flex h-full w-[330px] shrink-0 flex-col border-l border-line bg-white dark:border-slate-800 dark:bg-slate-900">
      <Tabs
        value={tab}
        onChange={(value) => setTab(value as "contact" | "copilot")}
        items={[
          { key: "contact", label: "Contact" },
          { key: "copilot", label: "Copilot", disabled: true },
        ]}
        size="sm"
        className="px-2"
      />

      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin">
        {/* Identity */}
        <div className="flex flex-col items-center gap-2 px-4 pb-4 pt-5 text-center">
          <Avatar
            name={contact?.name}
            src={contact?.avatar_url}
            seed={contact?.id}
            size="2xl"
          />
          <div>
            <h3 className="text-md font-semibold text-ink dark:text-slate-100">
              {contact?.name || "Unknown contact"}
            </h3>
            {(contact?.title || contact?.company) && (
              <p className="text-xs text-ink-muted dark:text-slate-400">
                {[contact?.title, contact?.company].filter(Boolean).join(" @ ")}
              </p>
            )}
            {contact?.blocked && (
              <Badge tone="danger" size="xs" className="mt-1">
                Blocked
              </Badge>
            )}
          </div>

          <div className="mt-1 flex items-center gap-2">
            <RoundAction
              icon={<MessageSquare />}
              label="Go to conversation"
              onClick={() => onSelectConversation(conversation.id)}
            />
            <RoundAction icon={<Pencil />} label="Edit contact" onClick={() => setEditing(true)} />
            <RoundAction
              icon={<Merge />}
              label="Merge contact"
              onClick={() =>
                toast.toast({
                  title: "Merge contacts",
                  description: "Pick the target contact from the Contacts screen.",
                  tone: "info",
                })
              }
            />
            <RoundAction
              icon={<Ban />}
              label={contact?.blocked ? "Unblock" : "Block"}
              onClick={() =>
                contact &&
                void contactsApi
                  .block(contact.id, !contact.blocked)
                  .then(() => {
                    queryClient.invalidateQueries({
                      queryKey: queryKeys.conversation(conversation.id),
                    });
                  })
                  .catch((error: Error) => toast.error("Failed", error.message))
              }
            />
            <RoundAction
              danger
              icon={<Trash2 />}
              label="Delete contact"
              onClick={() => setConfirmDelete(true)}
            />
          </div>
        </div>

        {/* Contact details */}
        <div className="border-b border-line px-4 pb-3 dark:border-slate-800">
          <CopyRow
            icon={<Mail />}
            value={contact?.email}
            href={contact?.email ? `mailto:${contact.email}` : undefined}
            placeholder="No email address"
          />
          <CopyRow
            icon={<Phone />}
            value={contact?.phone}
            href={contact?.phone ? `tel:${contact.phone}` : undefined}
            placeholder="No phone number"
          />
          <CopyRow icon={<Building2 />} value={contact?.company} placeholder="No company" />
          <CopyRow icon={<MapPin />} value={contact?.location} placeholder="No location" />
          <CopyRow icon={<AtSign />} value={contact?.identifier} placeholder="No identifier" />

          {socials.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {socials.map(([network, handle]) => (
                <a
                  key={network}
                  href={String(handle).startsWith("http") ? String(handle) : undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-2xs text-ink-soft transition hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
                >
                  <Link2 className="h-3 w-3" />
                  {humanize(network)}
                </a>
              ))}
            </div>
          )}
        </div>

        {/* Conversation actions */}
        <Accordion title="Conversation Actions">
          <div className="space-y-2.5">
            <Select
              label="Assignee"
              value={conversation.assignee_id ?? ""}
              onChange={(event) =>
                onUpdateConversation({
                  assignee_id: event.target.value ? Number(event.target.value) : null,
                })
              }
              placeholder="Unassigned"
              options={agents.map((agent) => ({
                value: agent.id,
                label: agent.display_name || agent.name,
              }))}
            />
            <Select
              label="Team"
              value={conversation.team_id ?? ""}
              onChange={(event) =>
                onUpdateConversation({
                  team_id: event.target.value ? Number(event.target.value) : null,
                })
              }
              placeholder="No team"
              options={teams.map((team) => ({ value: team.id, label: team.name }))}
            />
            <Select
              label="Priority"
              value={conversation.priority}
              onChange={(event) =>
                onUpdateConversation({
                  priority: event.target.value as ConversationPriority,
                })
              }
              options={["none", "low", "medium", "high", "urgent"].map((value) => ({
                value,
                label: value[0]!.toUpperCase() + value.slice(1),
              }))}
            />
            <Select
              label="Status"
              value={conversation.status}
              onChange={(event) =>
                onUpdateConversation({ status: event.target.value as ConversationStatus })
              }
              options={["open", "pending", "snoozed", "resolved"].map((value) => ({
                value,
                label: value[0]!.toUpperCase() + value.slice(1),
              }))}
            />
          </div>
        </Accordion>

        {/* Participants */}
        <Accordion
          title="Conversation participants"
          action={
            <Dropdown
              align="right"
              width="w-52"
              trigger={({ toggle }) => (
                <IconButton label="Add participant" onClick={toggle} className="h-6 w-6">
                  <Plus className="h-3.5 w-3.5" />
                </IconButton>
              )}
            >
              {({ close }) =>
                availableAgents.length ? (
                  <>
                    {availableAgents.map((agent) => (
                      <DropdownItem
                        key={agent.id}
                        onClick={() => {
                          void addParticipant(agent.id);
                          close();
                        }}
                      >
                        {agent.display_name || agent.name}
                      </DropdownItem>
                    ))}
                  </>
                ) : (
                  <p className="px-2.5 py-2 text-xs text-ink-faint">Everyone is added</p>
                )
              }
            </Dropdown>
          }
        >
          {participantsQuery.isLoading ? (
            <Spinner size="sm" />
          ) : participants.length === 0 ? (
            <p className="text-xs text-ink-faint">No extra participants.</p>
          ) : (
            <ul className="space-y-1.5">
              {participants.map((person) => (
                <li key={person.id} className="group flex items-center gap-2">
                  <Avatar
                    name={person.display_name || person.name}
                    src={person.avatar_url}
                    seed={person.id}
                    size="sm"
                    status={person.availability}
                  />
                  <span className="min-w-0 flex-1 truncate text-xs text-ink-soft dark:text-slate-300">
                    {person.display_name || person.name}
                  </span>
                  <button
                    type="button"
                    aria-label={`Remove ${person.name}`}
                    onClick={() => void removeParticipant(person.id)}
                    className="text-ink-faint opacity-0 transition group-hover:opacity-100 hover:text-red-500"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Accordion>

        {/* Macros */}
        <Accordion title="Macros" defaultOpen={false}>
          {canned.length === 0 ? (
            <p className="text-xs text-ink-faint">No canned responses yet.</p>
          ) : (
            <ul className="space-y-1">
              {canned.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onInsertCanned(item.content)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-surface-muted dark:hover:bg-slate-800"
                  >
                    <Zap className="h-3.5 w-3.5 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1 truncate text-xs text-ink-soft dark:text-slate-300">
                      /{item.short_code}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Accordion>

        {/* Custom attributes */}
        <Accordion title="Contact Attributes" defaultOpen={false}>
          <div className="space-y-1.5">
            {Object.entries(contact?.custom_attributes ?? {}).map(([key, value]) => (
              <div key={key} className="group flex items-center gap-2">
                <span className="w-1/3 shrink-0 truncate text-2xs text-ink-faint">
                  {humanize(key)}
                </span>
                <input
                  defaultValue={String(value ?? "")}
                  onBlur={(event) => {
                    if (event.target.value === String(value ?? "")) return;
                    void patchContact({
                      custom_attributes: {
                        ...(contact?.custom_attributes ?? {}),
                        [key]: event.target.value,
                      },
                    });
                  }}
                  className="min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1.5 py-1 text-xs text-ink-soft hover:border-line focus:border-primary-300 focus:bg-white focus:outline-none dark:text-slate-300 dark:focus:bg-slate-800"
                />
                <button
                  type="button"
                  aria-label={`Remove ${key}`}
                  onClick={() => {
                    const next = { ...(contact?.custom_attributes ?? {}) };
                    delete next[key];
                    void patchContact({ custom_attributes: next });
                  }}
                  className="text-ink-faint opacity-0 transition group-hover:opacity-100 hover:text-red-500"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}

            <div className="flex items-center gap-1.5 pt-1">
              <Input
                placeholder="Key"
                value={attributeDraft.key}
                onChange={(event) =>
                  setAttributeDraft((draft) => ({ ...draft, key: event.target.value }))
                }
                className="h-7 text-xs"
                wrapperClassName="flex-1"
              />
              <Input
                placeholder="Value"
                value={attributeDraft.value}
                onChange={(event) =>
                  setAttributeDraft((draft) => ({ ...draft, value: event.target.value }))
                }
                className="h-7 text-xs"
                wrapperClassName="flex-1"
              />
              <IconButton
                label="Add attribute"
                className="h-7 w-7"
                onClick={() => {
                  if (!attributeDraft.key.trim()) return;
                  void patchContact({
                    custom_attributes: {
                      ...(contact?.custom_attributes ?? {}),
                      [attributeDraft.key.trim()]: attributeDraft.value,
                    },
                  });
                  setAttributeDraft({ key: "", value: "" });
                }}
              >
                <Plus className="h-3.5 w-3.5" />
              </IconButton>
            </div>
          </div>
        </Accordion>

        {/* Conversation information */}
        <Accordion title="Conversation Information" defaultOpen={false}>
          <InfoRow label="Conversation" value={`#${conversation.id}`} />
          <InfoRow
            label="Inbox"
            value={
              <span className="inline-flex items-center gap-1">
                <ChannelIcon channelType={conversation.inbox?.channel_type} />
                {conversation.inbox?.name}
              </span>
            }
          />
          <InfoRow label="Source" value={humanize(conversation.inbox?.channel_type ?? "—")} />
          <InfoRow label="Created" value={fullTimestamp(conversation.created_at)} />
          <InfoRow
            label="Last activity"
            value={relativeTime(conversation.last_activity_at) || "—"}
          />
          <InfoRow
            label="Browser"
            value={
              (conversation.custom_attributes?.browser as string) ??
              (conversation.custom_attributes?.user_agent as string) ??
              "—"
            }
          />
          <InfoRow label="Contact since" value={fullTimestamp(contact?.created_at)} />
          <InfoRow label="Timezone" value={contact?.timezone ?? "—"} />
        </Accordion>

        {/* Previous conversations */}
        <Accordion title="Previous Conversations" defaultOpen={false}>
          {previousQuery.isLoading ? (
            <Spinner size="sm" />
          ) : previous.length === 0 ? (
            <p className="text-xs text-ink-faint">No other conversations.</p>
          ) : (
            <ul className="space-y-1">
              {previous.slice(0, 8).map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onSelectConversation(item.id)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-surface-muted dark:hover:bg-slate-800"
                  >
                    <ChannelIcon channelType={item.inbox?.channel_type} />
                    <span className="min-w-0 flex-1 truncate text-xs text-ink-soft dark:text-slate-300">
                      #{item.id} · {item.inbox?.name}
                    </span>
                    <span className="shrink-0 text-2xs text-ink-faint">
                      {relativeTime(item.last_activity_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Accordion>
      </div>

      {contact && (
        <EditContactModal
          open={editing}
          contact={contact}
          onClose={() => setEditing(false)}
          onSave={async (payload) => {
            await patchContact(payload);
            setEditing(false);
          }}
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this contact?"
        description="All of their conversations and messages will be removed. This cannot be undone."
        confirmLabel="Delete contact"
        onConfirm={deleteContact}
        onCancel={() => setConfirmDelete(false)}
      />
    </aside>
  );
}

/* ----------------------------------------------------------- edit modal */

function EditContactModal({
  open,
  contact,
  onClose,
  onSave,
}: {
  open: boolean;
  contact: NonNullable<Conversation["contact"]>;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [form, setForm] = useState({
    name: contact.name ?? "",
    email: contact.email ?? "",
    phone: contact.phone ?? "",
    company: contact.company ?? "",
    title: contact.title ?? "",
    location: contact.location ?? "",
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({
      name: contact.name ?? "",
      email: contact.email ?? "",
      phone: contact.phone ?? "",
      company: contact.company ?? "",
      title: contact.title ?? "",
      location: contact.location ?? "",
    });
  }, [open, contact]);

  async function submit() {
    setSaving(true);
    try {
      await onSave({
        name: form.name,
        email: form.email || null,
        phone: form.phone || null,
        company: form.company || null,
        title: form.title || null,
        location: form.location || null,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Edit contact"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={saving} onClick={() => void submit()}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <Input
          label="Name"
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
          wrapperClassName="col-span-2"
        />
        <Input
          label="Email"
          type="email"
          icon={<Mail className="h-3.5 w-3.5" />}
          value={form.email}
          onChange={(event) => setForm({ ...form, email: event.target.value })}
        />
        <Input
          label="Phone"
          icon={<Phone className="h-3.5 w-3.5" />}
          value={form.phone}
          onChange={(event) => setForm({ ...form, phone: event.target.value })}
        />
        <Input
          label="Company"
          icon={<Building2 className="h-3.5 w-3.5" />}
          value={form.company}
          onChange={(event) => setForm({ ...form, company: event.target.value })}
        />
        <Input
          label="Job title"
          value={form.title}
          onChange={(event) => setForm({ ...form, title: event.target.value })}
        />
        <Input
          label="Location"
          icon={<Globe className="h-3.5 w-3.5" />}
          value={form.location}
          onChange={(event) => setForm({ ...form, location: event.target.value })}
          wrapperClassName="col-span-2"
        />
      </div>
    </Modal>
  );
}

export default ContactPanel;
