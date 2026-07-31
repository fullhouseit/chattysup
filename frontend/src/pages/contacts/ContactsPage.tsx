/**
 * `/contacts` — the address book.
 *
 * A searchable, sortable and paginated table backed by `GET /contacts`, with a
 * "New contact" modal and the per-row block / delete actions.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban,
  CircleCheck,
  MoreVertical,
  Plus,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { contacts as contactsApi } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { Contact, ContactPayload } from "@/lib/types";
import {
  Avatar,
  Badge,
  Button,
  ConfirmDialog,
  Dropdown,
  DropdownItem,
  DropdownSeparator,
  EmptyState,
  IconButton,
  Input,
  Modal,
  Select,
  Spinner,
  useToast,
} from "@/components/ui";
import { Card } from "../admin/components/Card";
import { PageHeader } from "../admin/components/PageHeader";
import { TableMessage, TableWrap, Td, Th, Tr } from "../admin/components/DataTable";

const PER_PAGE = 25;

const SORTS = [
  { value: "recent", label: "Last activity" },
  { value: "name", label: "Name (A–Z)" },
  { value: "oldest", label: "Oldest first" },
];

const EMPTY_DRAFT: ContactPayload = {
  name: "",
  email: "",
  phone: "",
  company: "",
  title: "",
  location: "",
};

export function ContactsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();

  const query = params.get("q") ?? "";
  const sort = params.get("sort") ?? "recent";
  const page = Math.max(1, Number(params.get("page") ?? 1));

  const [search, setSearch] = useState(query);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ContactPayload>(EMPTY_DRAFT);
  const [pendingDelete, setPendingDelete] = useState<Contact | null>(null);

  // Debounce typing into the URL so the query is shareable but not chatty.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (search === query) return;
      const next = new URLSearchParams(params);
      if (search) next.set("q", search);
      else next.delete("q");
      next.delete("page");
      setParams(next, { replace: true });
    }, 300);
    return () => window.clearTimeout(timer);
    // `params` is intentionally read fresh inside the timer only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  }

  const listQuery = useQuery({
    queryKey: ["contacts", { q: query, sort, page }],
    queryFn: () => contactsApi.list({ q: query, sort, page, per_page: PER_PAGE }),
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["contacts"] });
  }

  const createMutation = useMutation({
    mutationFn: () =>
      contactsApi.create({
        name: (draft.name ?? "").trim(),
        email: (draft.email ?? "").trim() || null,
        phone: (draft.phone ?? "").trim() || null,
        company: (draft.company ?? "").trim() || null,
        title: (draft.title ?? "").trim() || null,
        location: (draft.location ?? "").trim() || null,
      }),
    onSuccess: (contact) => {
      toast.success("Contact created");
      setCreating(false);
      setDraft(EMPTY_DRAFT);
      refresh();
      navigate(`/contacts/${contact.id}`);
    },
    onError: (error: Error) => toast.error("Could not create the contact", error.message),
  });

  const blockMutation = useMutation({
    mutationFn: ({ id, blocked }: { id: number; blocked: boolean }) =>
      contactsApi.block(id, blocked),
    onSuccess: (contact) => {
      toast.success(contact.blocked ? "Contact blocked" : "Contact unblocked");
      refresh();
    },
    onError: (error: Error) => toast.error("Could not update the contact", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => contactsApi.remove(id),
    onSuccess: () => {
      toast.success("Contact deleted");
      setPendingDelete(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not delete the contact", error.message),
  });

  const rows = listQuery.data?.data ?? [];
  const meta = listQuery.data?.meta;
  const totalPages = useMemo(
    () => (meta ? Math.max(1, Math.ceil(meta.total / (meta.per_page || PER_PAGE))) : 1),
    [meta],
  );

  return (
    <div className="h-full w-full overflow-y-auto bg-surface-muted p-6 scroll-thin dark:bg-[#0F141A]">
      <div className="mx-auto max-w-6xl">
        <PageHeader
          title="Contacts"
          description={
            meta ? `${meta.total} ${meta.total === 1 ? "person" : "people"}` : "Your address book."
          }
          actions={
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Plus className="h-3.5 w-3.5" />}
              onClick={() => {
                setDraft(EMPTY_DRAFT);
                setCreating(true);
              }}
            >
              New contact
            </Button>
          }
        />

        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by name, email, phone or company…"
            icon={<Search className="h-3.5 w-3.5" />}
            wrapperClassName="w-full max-w-sm"
          />
          <Select
            value={sort}
            options={SORTS}
            wrapperClassName="w-48"
            onChange={(event) => setParam("sort", event.target.value)}
          />
          {listQuery.isFetching && <Spinner size="sm" />}
        </div>

        <Card flush>
          <TableWrap>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Email</Th>
                <Th>Phone</Th>
                <Th>Company</Th>
                <Th>Profiles</Th>
                <Th>Last activity</Th>
                <Th align="right" />
              </tr>
            </thead>
            <tbody>
              {listQuery.isLoading ? (
                <TableMessage colSpan={7}>
                  <Spinner />
                </TableMessage>
              ) : rows.length === 0 ? (
                <TableMessage colSpan={7}>
                  {query ? (
                    `Nothing matches “${query}”.`
                  ) : (
                    <EmptyState
                      compact
                      icon={<Users />}
                      title="No contacts yet"
                      description="They appear here as soon as someone writes in."
                    />
                  )}
                </TableMessage>
              ) : (
                rows.map((contact) => (
                  <Tr key={contact.id} onClick={() => navigate(`/contacts/${contact.id}`)}>
                    <Td>
                      <span className="flex items-center gap-2.5">
                        <Avatar
                          name={contact.name}
                          src={contact.avatar_url}
                          seed={contact.id}
                          size="sm"
                        />
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-ink dark:text-slate-100">
                            {contact.name || "Unnamed contact"}
                          </span>
                          {contact.title && (
                            <span className="block truncate text-2xs text-ink-muted">
                              {contact.title}
                            </span>
                          )}
                        </span>
                        {contact.blocked && <Badge tone="danger">Blocked</Badge>}
                      </span>
                    </Td>
                    <Td className="max-w-[200px] truncate">{contact.email || "—"}</Td>
                    <Td className="whitespace-nowrap">{contact.phone || "—"}</Td>
                    <Td className="max-w-[160px] truncate">{contact.company || "—"}</Td>
                    <Td>
                      {Object.keys(contact.social_profiles ?? {}).length === 0 ? (
                        <span className="text-ink-faint">—</span>
                      ) : (
                        <span className="flex flex-wrap gap-1">
                          {Object.keys(contact.social_profiles).map((network) => (
                            <Badge key={network} tone="neutral">
                              {network}
                            </Badge>
                          ))}
                        </span>
                      )}
                    </Td>
                    <Td className="whitespace-nowrap">
                      {contact.last_activity_at
                        ? `${relativeTime(contact.last_activity_at)} ago`
                        : "—"}
                    </Td>
                    <Td align="right">
                      <span onClick={(event) => event.stopPropagation()}>
                        <Dropdown
                          align="right"
                          trigger={({ toggle }) => (
                            <IconButton label="Contact actions" onClick={toggle}>
                              <MoreVertical className="h-4 w-4" />
                            </IconButton>
                          )}
                        >
                          {({ close }) => (
                            <>
                              <DropdownItem
                                onClick={() => {
                                  close();
                                  navigate(`/contacts/${contact.id}`);
                                }}
                              >
                                Open profile
                              </DropdownItem>
                              <DropdownItem
                                icon={
                                  contact.blocked ? (
                                    <CircleCheck className="h-3.5 w-3.5" />
                                  ) : (
                                    <Ban className="h-3.5 w-3.5" />
                                  )
                                }
                                onClick={() => {
                                  close();
                                  blockMutation.mutate({
                                    id: contact.id,
                                    blocked: !contact.blocked,
                                  });
                                }}
                              >
                                {contact.blocked ? "Unblock" : "Block"}
                              </DropdownItem>
                              <DropdownSeparator />
                              <DropdownItem
                                danger
                                icon={<Trash2 className="h-3.5 w-3.5" />}
                                onClick={() => {
                                  close();
                                  setPendingDelete(contact);
                                }}
                              >
                                Delete
                              </DropdownItem>
                            </>
                          )}
                        </Dropdown>
                      </span>
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </TableWrap>

          {meta && meta.total > meta.per_page && (
            <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-xs text-ink-muted dark:border-slate-800">
              <span>
                Page {page} of {totalPages} · {meta.total} contacts
              </span>
              <span className="flex gap-1.5">
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={page <= 1}
                  onClick={() => setParam("page", String(page - 1))}
                >
                  Previous
                </Button>
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={page >= totalPages}
                  onClick={() => setParam("page", String(page + 1))}
                >
                  Next
                </Button>
              </span>
            </div>
          )}
        </Card>
      </div>

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="New contact"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={createMutation.isPending}
              disabled={!(draft.name ?? "").trim()}
              onClick={() => createMutation.mutate()}
            >
              Create contact
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={draft.name ?? ""}
            placeholder="Jane Cooper"
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              label="Email"
              type="email"
              value={draft.email ?? ""}
              onChange={(event) => setDraft({ ...draft, email: event.target.value })}
            />
            <Input
              label="Phone"
              value={draft.phone ?? ""}
              placeholder="+1 555 010 0000"
              onChange={(event) => setDraft({ ...draft, phone: event.target.value })}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              label="Company"
              value={draft.company ?? ""}
              onChange={(event) => setDraft({ ...draft, company: event.target.value })}
            />
            <Input
              label="Job title"
              value={draft.title ?? ""}
              onChange={(event) => setDraft({ ...draft, title: event.target.value })}
            />
          </div>
          <Input
            label="Location"
            value={draft.location ?? ""}
            placeholder="Berlin, Germany"
            onChange={(event) => setDraft({ ...draft, location: event.target.value })}
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Delete ${pendingDelete?.name ?? "contact"}?`}
        description="Their conversations and messages are deleted with them."
        confirmLabel="Delete contact"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </div>
  );
}

export default ContactsPage;
