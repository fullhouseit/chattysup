/**
 * `/contacts/:id` — one person's profile.
 *
 * Three columns of information: the editable identity card, the notes timeline
 * and the list of conversations this contact has had, each linking back into
 * the inbox.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Ban,
  Building2,
  CircleCheck,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  Trash2,
} from "lucide-react";
import { contacts as contactsApi } from "@/lib/api";
import { fullTimestamp, messagePreview, relativeTime } from "@/lib/format";
import type { Contact, ContactPayload, Dict } from "@/lib/types";
import { queryKeys, useRealtime } from "@/store/app";
import { useAuth } from "@/store/auth";
import {
  Avatar,
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  Input,
  PageSpinner,
  Textarea,
  useToast,
} from "@/components/ui";
import { ChannelIcon } from "@/components/conversations/ChannelIcon";
import { Card, CardHeader } from "../admin/components/Card";
import { CopyButton } from "../admin/components/CopyButton";
import { KeyValueEditor } from "../admin/components/KeyValueEditor";
import { PageHeader } from "../admin/components/PageHeader";

interface ProfileForm {
  name: string;
  email: string;
  phone: string;
  company: string;
  title: string;
  location: string;
  identifier: string;
  timezone: string;
  avatar_url: string;
}

function formFrom(contact: Contact): ProfileForm {
  return {
    name: contact.name ?? "",
    email: contact.email ?? "",
    phone: contact.phone ?? "",
    company: contact.company ?? "",
    title: contact.title ?? "",
    location: contact.location ?? "",
    identifier: contact.identifier ?? "",
    timezone: contact.timezone ?? "",
    avatar_url: contact.avatar_url ?? "",
  };
}

function toPayload(form: ProfileForm, custom: Dict): ContactPayload {
  const clean = (value: string) => value.trim() || null;
  return {
    name: form.name.trim(),
    email: clean(form.email),
    phone: clean(form.phone),
    company: clean(form.company),
    title: clean(form.title),
    location: clean(form.location),
    identifier: clean(form.identifier),
    timezone: clean(form.timezone),
    avatar_url: clean(form.avatar_url),
    custom_attributes: custom,
  };
}

/** One read-only detail row with an icon and a copy button. */
function DetailRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
}) {
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <span className="text-ink-faint">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-2xs uppercase tracking-wide text-ink-faint">{label}</span>
        <span className="block truncate text-sm text-ink dark:text-slate-200">
          {value || "—"}
        </span>
      </span>
      {value && <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />}
    </div>
  );
}

export function ContactDetailPage() {
  const { id } = useParams();
  const contactId = Number(id);
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user: me } = useAuth();

  const [form, setForm] = useState<ProfileForm | null>(null);
  const [custom, setCustom] = useState<Dict>({});
  const [note, setNote] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const contactQuery = useQuery({
    queryKey: queryKeys.contact(contactId),
    queryFn: () => contactsApi.get(contactId),
    enabled: Number.isFinite(contactId),
  });
  const notesQuery = useQuery({
    queryKey: ["contact", contactId, "notes"],
    queryFn: () => contactsApi.notes(contactId),
    enabled: Number.isFinite(contactId),
  });
  const conversationsQuery = useQuery({
    queryKey: ["contact", contactId, "conversations"],
    queryFn: () => contactsApi.conversations(contactId),
    enabled: Number.isFinite(contactId),
  });

  const contact = contactQuery.data;

  useEffect(() => {
    if (contact) {
      setForm(formFrom(contact));
      setCustom({ ...(contact.custom_attributes ?? {}) });
    }
  }, [contact]);

  // Keep the profile in sync when an agent edits it from the chat sidebar.
  const onContactUpdated = useCallback(
    (payload: { contact?: Contact }) => {
      if (payload?.contact?.id === contactId) {
        queryClient.setQueryData(queryKeys.contact(contactId), payload.contact);
      }
    },
    [contactId, queryClient],
  );
  useRealtime<{ contact?: Contact }>("contact.updated", onContactUpdated);

  const saveMutation = useMutation({
    mutationFn: () => contactsApi.update(contactId, toPayload(form!, custom)),
    onSuccess: (next) => {
      toast.success("Contact saved");
      queryClient.setQueryData(queryKeys.contact(contactId), next);
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (error: Error) => toast.error("Could not save the contact", error.message),
  });

  const blockMutation = useMutation({
    mutationFn: (blocked: boolean) => contactsApi.block(contactId, blocked),
    onSuccess: (next) => {
      toast.success(next.blocked ? "Contact blocked" : "Contact unblocked");
      queryClient.setQueryData(queryKeys.contact(contactId), next);
    },
    onError: (error: Error) => toast.error("Could not update the contact", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => contactsApi.remove(contactId),
    onSuccess: () => {
      toast.success("Contact deleted");
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
      navigate("/contacts");
    },
    onError: (error: Error) => toast.error("Could not delete the contact", error.message),
  });

  const addNoteMutation = useMutation({
    mutationFn: () => contactsApi.addNote(contactId, note.trim()),
    onSuccess: () => {
      setNote("");
      queryClient.invalidateQueries({ queryKey: ["contact", contactId, "notes"] });
    },
    onError: (error: Error) => toast.error("Could not add the note", error.message),
  });

  const removeNoteMutation = useMutation({
    mutationFn: (noteId: number) => contactsApi.removeNote(contactId, noteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["contact", contactId, "notes"] });
    },
    onError: (error: Error) => toast.error("Could not delete the note", error.message),
  });

  if (contactQuery.isLoading || !form) return <PageSpinner />;

  if (contactQuery.isError || !contact) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <EmptyState
          title="Contact not found"
          description="It may have been deleted."
          action={
            <Link to="/contacts">
              <Button variant="secondary">Back to contacts</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const patch = (next: Partial<ProfileForm>) =>
    setForm((state) => (state ? { ...state, ...next } : state));
  const conversations = conversationsQuery.data ?? [];
  const notes = notesQuery.data ?? [];
  const socials = Object.entries(contact.social_profiles ?? {});

  return (
    <div className="h-full w-full overflow-y-auto bg-surface-muted p-6 scroll-thin dark:bg-[#0F141A]">
      <div className="mx-auto max-w-6xl">
        <PageHeader
          above={
            <Link
              to="/contacts"
              className="inline-flex items-center gap-1.5 text-sm text-ink-muted transition hover:text-ink dark:text-slate-400"
            >
              <ArrowLeft className="h-4 w-4" /> Back to contacts
            </Link>
          }
          title={
            <span className="flex items-center gap-3">
              <Avatar
                name={contact.name}
                src={contact.avatar_url}
                seed={contact.id}
                size="lg"
              />
              <span className="min-w-0">
                <span className="block truncate">{contact.name || "Unnamed contact"}</span>
                <span className="block text-sm font-normal text-ink-muted dark:text-slate-400">
                  {[contact.title, contact.company].filter(Boolean).join(" @ ") ||
                    "No company on file"}
                </span>
              </span>
              {contact.blocked && <Badge tone="danger">Blocked</Badge>}
            </span>
          }
          actions={
            <>
              <Button
                variant="secondary"
                size="sm"
                leftIcon={
                  contact.blocked ? (
                    <CircleCheck className="h-3.5 w-3.5" />
                  ) : (
                    <Ban className="h-3.5 w-3.5" />
                  )
                }
                loading={blockMutation.isPending}
                onClick={() => blockMutation.mutate(!contact.blocked)}
              >
                {contact.blocked ? "Unblock" : "Block"}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<Trash2 className="h-3.5 w-3.5" />}
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </Button>
              <Button
                variant="primary"
                size="sm"
                loading={saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                Save changes
              </Button>
            </>
          }
        />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* ------------------------------------------------ profile */}
          <div className="space-y-4 lg:col-span-2">
            <Card flush>
              <CardHeader title="Profile" description="Edit any field and save." />
              <div className="grid grid-cols-1 gap-3 p-5 sm:grid-cols-2">
                <Input
                  label="Name"
                  value={form.name}
                  onChange={(event) => patch({ name: event.target.value })}
                />
                <Input
                  label="Email"
                  type="email"
                  value={form.email}
                  onChange={(event) => patch({ email: event.target.value })}
                />
                <Input
                  label="Phone"
                  value={form.phone}
                  onChange={(event) => patch({ phone: event.target.value })}
                />
                <Input
                  label="Company"
                  value={form.company}
                  onChange={(event) => patch({ company: event.target.value })}
                />
                <Input
                  label="Job title"
                  value={form.title}
                  onChange={(event) => patch({ title: event.target.value })}
                />
                <Input
                  label="Location"
                  value={form.location}
                  onChange={(event) => patch({ location: event.target.value })}
                />
                <Input
                  label="Timezone"
                  value={form.timezone}
                  placeholder="Europe/Berlin"
                  onChange={(event) => patch({ timezone: event.target.value })}
                />
                <Input
                  label="External identifier"
                  value={form.identifier}
                  hint="The id this person has on the source channel."
                  onChange={(event) => patch({ identifier: event.target.value })}
                />
                <Input
                  label="Avatar URL"
                  value={form.avatar_url}
                  wrapperClassName="sm:col-span-2"
                  onChange={(event) => patch({ avatar_url: event.target.value })}
                />
              </div>
            </Card>

            <Card flush>
              <CardHeader
                title="Custom attributes"
                description="Anything else you want to remember about this person."
              />
              <div className="p-5">
                <KeyValueEditor value={custom} onChange={setCustom} />
              </div>
            </Card>

            <Card flush>
              <CardHeader
                title="Conversations"
                description={`${conversations.length} in total`}
              />
              {conversationsQuery.isLoading ? (
                <p className="px-5 py-6 text-center text-sm text-ink-muted">Loading…</p>
              ) : conversations.length === 0 ? (
                <p className="px-5 py-6 text-center text-sm text-ink-muted dark:text-slate-400">
                  This contact has not written in yet.
                </p>
              ) : (
                <ul className="divide-y divide-line dark:divide-slate-800">
                  {conversations.map((conversation) => (
                    <li key={conversation.id}>
                      <Link
                        to={`/conversations/${conversation.id}`}
                        className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-muted dark:hover:bg-slate-800/50"
                      >
                        <ChannelIcon channelType={conversation.inbox?.channel_type} />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-2">
                            <span className="truncate text-sm font-medium text-ink dark:text-slate-100">
                              #{conversation.id} · {conversation.inbox?.name ?? "Inbox"}
                            </span>
                            <Badge
                              tone={
                                conversation.status === "open"
                                  ? "success"
                                  : conversation.status === "resolved"
                                    ? "neutral"
                                    : "warning"
                              }
                            >
                              {conversation.status}
                            </Badge>
                          </span>
                          <span className="block truncate text-xs text-ink-muted dark:text-slate-400">
                            {messagePreview(
                              conversation.last_message?.content,
                              conversation.last_message?.attachments?.[0]?.file_type,
                            )}
                          </span>
                        </span>
                        <span className="shrink-0 text-2xs text-ink-faint">
                          {relativeTime(conversation.last_activity_at)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {/* -------------------------------------------------- aside */}
          <div className="space-y-4">
            <Card>
              <h2 className="mb-2 text-sm font-semibold text-ink dark:text-slate-100">
                At a glance
              </h2>
              <DetailRow
                icon={<Mail className="h-3.5 w-3.5" />}
                label="Email"
                value={contact.email}
              />
              <DetailRow
                icon={<Phone className="h-3.5 w-3.5" />}
                label="Phone"
                value={contact.phone}
              />
              <DetailRow
                icon={<Building2 className="h-3.5 w-3.5" />}
                label="Company"
                value={contact.company}
              />
              <DetailRow
                icon={<MapPin className="h-3.5 w-3.5" />}
                label="Location"
                value={contact.location}
              />
              {socials.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3 dark:border-slate-800">
                  {socials.map(([network, handle]) => (
                    <a
                      key={network}
                      href={
                        String(handle).startsWith("http")
                          ? String(handle)
                          : `https://${network}.com/${handle}`
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded-full bg-surface-muted px-2 py-0.5 text-2xs text-ink-soft transition hover:text-primary dark:bg-slate-800 dark:text-slate-300"
                    >
                      {network}
                    </a>
                  ))}
                </div>
              )}
              <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3 text-2xs dark:border-slate-800">
                <div>
                  <dt className="text-ink-faint">Created</dt>
                  <dd className="text-ink-soft dark:text-slate-300">
                    {fullTimestamp(contact.created_at) || "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-ink-faint">Last activity</dt>
                  <dd className="text-ink-soft dark:text-slate-300">
                    {fullTimestamp(contact.last_activity_at) || "—"}
                  </dd>
                </div>
              </dl>
              {conversations[0] && (
                <Link to={`/conversations/${conversations[0].id}`}>
                  <Button
                    className="mt-3"
                    variant="secondary"
                    size="sm"
                    block
                    leftIcon={<MessageSquare className="h-3.5 w-3.5" />}
                  >
                    Open latest conversation
                  </Button>
                </Link>
              )}
            </Card>

            <Card flush>
              <CardHeader title="Notes" description="Private to your team." />
              <div className="space-y-2 p-4">
                <Textarea
                  rows={3}
                  value={note}
                  placeholder="Add a note…"
                  onChange={(event) => setNote(event.target.value)}
                />
                <Button
                  variant="primary"
                  size="sm"
                  disabled={!note.trim()}
                  loading={addNoteMutation.isPending}
                  onClick={() => addNoteMutation.mutate()}
                >
                  Add note
                </Button>
              </div>
              {notes.length > 0 && (
                <ul className="divide-y divide-line border-t border-line dark:divide-slate-800 dark:border-slate-800">
                  {notes.map((entry) => (
                    <li key={entry.id} className="group px-4 py-3">
                      <p className="whitespace-pre-wrap text-sm text-ink dark:text-slate-200">
                        {entry.content}
                      </p>
                      <div className="mt-1 flex items-center gap-2 text-2xs text-ink-faint">
                        <span>{fullTimestamp(entry.created_at)}</span>
                        {entry.user_id === me?.id && <span>· you</span>}
                        <IconButton
                          label="Delete note"
                          className="ml-auto opacity-0 transition group-hover:opacity-100"
                          onClick={() => removeNoteMutation.mutate(entry.id)}
                        >
                          <Trash2 className="h-3 w-3 text-red-500" />
                        </IconButton>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${contact.name || "this contact"}?`}
        description="Their conversations and messages are deleted with them."
        confirmLabel="Delete contact"
        tone="danger"
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => deleteMutation.mutate()}
      />
    </div>
  );
}

export default ContactDetailPage;
