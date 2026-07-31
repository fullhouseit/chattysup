/**
 * `/admin/agents` — the people who can sign in.
 *
 * Administrators create accounts with an initial password, change roles,
 * deactivate an account without losing its history, or delete it outright.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreVertical, Plus, ShieldCheck, Trash2, UserMinus, UserPlus } from "lucide-react";
import { users as usersApi } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { User, UserPayload, UserRole } from "@/lib/types";
import { useAuth } from "@/store/auth";
import { queryKeys } from "@/store/app";
import {
  Avatar,
  Badge,
  Button,
  ConfirmDialog,
  Dropdown,
  DropdownItem,
  DropdownSeparator,
  IconButton,
  Input,
  Modal,
  PageSpinner,
  Select,
  useToast,
} from "@/components/ui";
import { Card } from "./components/Card";
import { PageHeader } from "./components/PageHeader";
import { SortableTh, TableMessage, TableWrap, Td, Th, Tr } from "./components/DataTable";

interface AgentDraft {
  name: string;
  email: string;
  password: string;
  role: UserRole;
}

const EMPTY_DRAFT: AgentDraft = { name: "", email: "", password: "", role: "agent" };

export function AgentsPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user: me } = useAuth();

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<AgentDraft>(EMPTY_DRAFT);
  const [editing, setEditing] = useState<User | null>(null);
  const [editDraft, setEditDraft] = useState<UserPayload>({});
  const [pendingDelete, setPendingDelete] = useState<User | null>(null);
  const [sort, setSort] = useState<{ key: string; direction: "asc" | "desc" }>({
    key: "name",
    direction: "asc",
  });

  const agentsQuery = useQuery({ queryKey: queryKeys.agents, queryFn: usersApi.list });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: queryKeys.agents });
  }

  const createMutation = useMutation({
    mutationFn: () =>
      usersApi.create({
        name: draft.name.trim(),
        email: draft.email.trim(),
        password: draft.password,
        role: draft.role,
      }),
    onSuccess: () => {
      toast.success("Agent created", `${draft.name} can sign in now.`);
      setCreating(false);
      setDraft(EMPTY_DRAFT);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not create the agent", error.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: UserPayload }) =>
      usersApi.update(id, payload),
    onSuccess: () => {
      toast.success("Agent updated");
      setEditing(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not update the agent", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => usersApi.remove(id),
    onSuccess: () => {
      toast.success("Agent deleted");
      setPendingDelete(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not delete the agent", error.message),
  });

  function onSort(key: string) {
    setSort((state) =>
      state.key === key
        ? { key, direction: state.direction === "asc" ? "desc" : "asc" }
        : { key, direction: "asc" },
    );
  }

  const agents = [...(agentsQuery.data ?? [])].sort((a, b) => {
    const factor = sort.direction === "asc" ? 1 : -1;
    switch (sort.key) {
      case "email":
        return a.email.localeCompare(b.email) * factor;
      case "role":
        return a.role.localeCompare(b.role) * factor;
      case "created_at":
        return ((a.created_at ?? "") < (b.created_at ?? "") ? -1 : 1) * factor;
      default:
        return (a.display_name || a.name).localeCompare(b.display_name || b.name) * factor;
    }
  });

  function openEditor(agent: User) {
    setEditing(agent);
    setEditDraft({
      name: agent.name,
      display_name: agent.display_name,
      role: agent.role,
      is_active: agent.is_active,
    });
  }

  return (
    <>
      <PageHeader
        title="Agents"
        description="Everyone with access to this workspace."
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
            New agent
          </Button>
        }
      />

      <Card flush>
        {agentsQuery.isLoading ? (
          <PageSpinner />
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <SortableTh sortKey="name" active={sort.key} direction={sort.direction} onSort={onSort}>
                  Name
                </SortableTh>
                <SortableTh sortKey="email" active={sort.key} direction={sort.direction} onSort={onSort}>
                  Email
                </SortableTh>
                <SortableTh sortKey="role" active={sort.key} direction={sort.direction} onSort={onSort}>
                  Role
                </SortableTh>
                <Th>Availability</Th>
                <SortableTh
                  sortKey="created_at"
                  active={sort.key}
                  direction={sort.direction}
                  onSort={onSort}
                >
                  Joined
                </SortableTh>
                <Th align="right" />
              </tr>
            </thead>
            <tbody>
              {agents.length === 0 ? (
                <TableMessage colSpan={6}>No agents yet.</TableMessage>
              ) : (
                agents.map((agent) => (
                  <Tr key={agent.id}>
                    <Td>
                      <span className="flex items-center gap-2.5">
                        <Avatar
                          name={agent.display_name || agent.name}
                          src={agent.avatar_url}
                          seed={agent.id}
                          size="sm"
                          status={agent.availability}
                        />
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-ink dark:text-slate-100">
                            {agent.display_name || agent.name}
                            {agent.id === me?.id && (
                              <span className="ml-1.5 text-2xs text-ink-faint">(you)</span>
                            )}
                          </span>
                          {!agent.is_active && <Badge tone="warning">Deactivated</Badge>}
                        </span>
                      </span>
                    </Td>
                    <Td className="truncate">{agent.email}</Td>
                    <Td>
                      {agent.role === "admin" ? (
                        <Badge tone="primary">Administrator</Badge>
                      ) : (
                        <Badge tone="neutral">Agent</Badge>
                      )}
                    </Td>
                    <Td className="capitalize">{agent.availability}</Td>
                    <Td>{agent.created_at ? `${relativeTime(agent.created_at)} ago` : "—"}</Td>
                    <Td align="right">
                      <Dropdown
                        align="right"
                        trigger={({ toggle }) => (
                          <IconButton label="Agent actions" onClick={toggle}>
                            <MoreVertical className="h-4 w-4" />
                          </IconButton>
                        )}
                      >
                        {({ close }) => (
                          <>
                            <DropdownItem
                              icon={<ShieldCheck className="h-3.5 w-3.5" />}
                              onClick={() => {
                                close();
                                openEditor(agent);
                              }}
                            >
                              Edit agent
                            </DropdownItem>
                            <DropdownItem
                              icon={
                                agent.is_active ? (
                                  <UserMinus className="h-3.5 w-3.5" />
                                ) : (
                                  <UserPlus className="h-3.5 w-3.5" />
                                )
                              }
                              disabled={agent.id === me?.id}
                              onClick={() => {
                                close();
                                updateMutation.mutate({
                                  id: agent.id,
                                  payload: { is_active: !agent.is_active },
                                });
                              }}
                            >
                              {agent.is_active ? "Deactivate" : "Reactivate"}
                            </DropdownItem>
                            <DropdownSeparator />
                            <DropdownItem
                              danger
                              disabled={agent.id === me?.id}
                              icon={<Trash2 className="h-3.5 w-3.5" />}
                              onClick={() => {
                                close();
                                setPendingDelete(agent);
                              }}
                            >
                              Delete
                            </DropdownItem>
                          </>
                        )}
                      </Dropdown>
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </TableWrap>
        )}
      </Card>

      {/* ------------------------------------------------------- create */}
      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="New agent"
        description="They can change the password from their profile after signing in."
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={createMutation.isPending}
              disabled={!draft.name.trim() || !draft.email.trim() || draft.password.length < 8}
              onClick={() => createMutation.mutate()}
            >
              Create agent
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Full name"
            value={draft.name}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            placeholder="Ada Lovelace"
          />
          <Input
            label="Email"
            type="email"
            value={draft.email}
            onChange={(event) => setDraft({ ...draft, email: event.target.value })}
            placeholder="ada@example.com"
          />
          <Input
            label="Temporary password"
            type="password"
            value={draft.password}
            hint="At least 8 characters."
            onChange={(event) => setDraft({ ...draft, password: event.target.value })}
          />
          <Select
            label="Role"
            value={draft.role}
            options={[
              { value: "agent", label: "Agent — answers conversations" },
              { value: "admin", label: "Administrator — full access" },
            ]}
            onChange={(event) => setDraft({ ...draft, role: event.target.value as UserRole })}
          />
        </div>
      </Modal>

      {/* --------------------------------------------------------- edit */}
      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={`Edit ${editing?.name ?? "agent"}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={updateMutation.isPending}
              onClick={() => {
                if (!editing) return;
                const payload = { ...editDraft };
                // An empty field means "keep the current password".
                if (!payload.password) delete payload.password;
                updateMutation.mutate({ id: editing.id, payload });
              }}
            >
              Save
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Full name"
            value={editDraft.name ?? ""}
            onChange={(event) => setEditDraft({ ...editDraft, name: event.target.value })}
          />
          <Input
            label="Display name"
            value={editDraft.display_name ?? ""}
            hint="Shown to contacts instead of the full name."
            onChange={(event) =>
              setEditDraft({ ...editDraft, display_name: event.target.value })
            }
          />
          <Select
            label="Role"
            value={editDraft.role ?? "agent"}
            disabled={editing?.id === me?.id}
            hint={
              editing?.id === me?.id ? "You cannot change your own role." : undefined
            }
            options={[
              { value: "agent", label: "Agent" },
              { value: "admin", label: "Administrator" },
            ]}
            onChange={(event) =>
              setEditDraft({ ...editDraft, role: event.target.value as UserRole })
            }
          />
          <Input
            label="New password"
            type="password"
            value={editDraft.password ?? ""}
            hint="Leave empty to keep the current password."
            onChange={(event) => setEditDraft({ ...editDraft, password: event.target.value })}
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Delete ${pendingDelete?.name ?? "agent"}?`}
        description="Their conversations stay, but they lose access immediately."
        confirmLabel="Delete agent"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default AgentsPage;
