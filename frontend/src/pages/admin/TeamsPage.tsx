/**
 * `/admin/teams` — groups used for routing and shared ownership.
 *
 * Creating or editing a team also saves its roster, which the API exposes as a
 * separate `PUT /teams/{id}/members` call.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2, UsersRound } from "lucide-react";
import { teams as teamsApi, users as usersApi } from "@/lib/api";
import type { Team } from "@/lib/types";
import { queryKeys } from "@/store/app";
import {
  Avatar,
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  Input,
  Modal,
  PageSpinner,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import { Card } from "./components/Card";
import { MultiSelect } from "./components/MultiSelect";
import { PageHeader } from "./components/PageHeader";

interface TeamDraft {
  name: string;
  description: string;
  allow_auto_assign: boolean;
  member_ids: number[];
}

const EMPTY: TeamDraft = { name: "", description: "", allow_auto_assign: true, member_ids: [] };

export function TeamsPage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [editing, setEditing] = useState<Team | null>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<TeamDraft>(EMPTY);
  const [pendingDelete, setPendingDelete] = useState<Team | null>(null);

  const teamsQuery = useQuery({ queryKey: queryKeys.teams, queryFn: teamsApi.list });
  const agentsQuery = useQuery({ queryKey: queryKeys.agents, queryFn: usersApi.list });
  const agents = agentsQuery.data ?? [];

  function refresh() {
    queryClient.invalidateQueries({ queryKey: queryKeys.teams });
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: draft.name.trim(),
        description: draft.description.trim(),
        allow_auto_assign: draft.allow_auto_assign,
      };
      const team = editing
        ? await teamsApi.update(editing.id, payload)
        : await teamsApi.create(payload);
      await teamsApi.setMembers(team.id, draft.member_ids);
      return team;
    },
    onSuccess: () => {
      toast.success(editing ? "Team updated" : "Team created");
      setOpen(false);
      setEditing(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not save the team", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => teamsApi.remove(id),
    onSuccess: () => {
      toast.success("Team deleted");
      setPendingDelete(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not delete the team", error.message),
  });

  function startCreate() {
    setEditing(null);
    setDraft(EMPTY);
    setOpen(true);
  }

  function startEdit(team: Team) {
    setEditing(team);
    setDraft({
      name: team.name,
      description: team.description ?? "",
      allow_auto_assign: team.allow_auto_assign,
      member_ids: [...(team.member_ids ?? [])],
    });
    setOpen(true);
  }

  const list = teamsQuery.data ?? [];

  return (
    <>
      <PageHeader
        title="Teams"
        description="Route conversations to a group instead of one person."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            onClick={startCreate}
          >
            New team
          </Button>
        }
      />

      {teamsQuery.isLoading ? (
        <PageSpinner />
      ) : list.length === 0 ? (
        <Card className="py-10">
          <EmptyState
            icon={<UsersRound />}
            title="No teams yet"
            description="Create one to group agents by product, language or shift."
            action={
              <Button variant="primary" onClick={startCreate}>
                New team
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {list.map((team) => {
            const members = agents.filter((agent) => team.member_ids?.includes(agent.id));
            return (
              <Card key={team.id} className="flex flex-col gap-3">
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-ink dark:text-slate-100">
                      {team.name}
                    </p>
                    <p className="mt-0.5 text-xs text-ink-muted dark:text-slate-400">
                      {team.description || "No description"}
                    </p>
                  </div>
                  <IconButton label="Edit team" onClick={() => startEdit(team)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </IconButton>
                  <IconButton label="Delete team" onClick={() => setPendingDelete(team)}>
                    <Trash2 className="h-3.5 w-3.5 text-red-500" />
                  </IconButton>
                </div>

                <div className="flex items-center gap-2">
                  {members.length === 0 ? (
                    <span className="text-xs text-ink-muted dark:text-slate-400">
                      No members yet
                    </span>
                  ) : (
                    <>
                      <div className="flex -space-x-1.5">
                        {members.slice(0, 6).map((member) => (
                          <Avatar
                            key={member.id}
                            name={member.display_name || member.name}
                            src={member.avatar_url}
                            seed={member.id}
                            size="sm"
                            className="ring-2 ring-white dark:ring-slate-900"
                          />
                        ))}
                      </div>
                      <span className="text-xs text-ink-muted dark:text-slate-400">
                        {members.length} member{members.length === 1 ? "" : "s"}
                      </span>
                    </>
                  )}
                  {team.allow_auto_assign && (
                    <Badge tone="neutral" className="ml-auto">
                      Auto-assign
                    </Badge>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? `Edit ${editing.name}` : "New team"}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={saveMutation.isPending}
              disabled={!draft.name.trim()}
              onClick={() => saveMutation.mutate()}
            >
              {editing ? "Save team" : "Create team"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Team name"
            value={draft.name}
            placeholder="Billing"
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
          <Textarea
            label="Description"
            rows={2}
            value={draft.description}
            placeholder="Handles invoices, refunds and subscription questions."
            onChange={(event) => setDraft({ ...draft, description: event.target.value })}
          />
          <MultiSelect
            label="Members"
            options={agents.map((agent) => ({
              value: agent.id,
              label: agent.display_name || agent.name,
              description: agent.email,
            }))}
            value={draft.member_ids}
            onChange={(member_ids) => setDraft({ ...draft, member_ids })}
          />
          <Switch
            checked={draft.allow_auto_assign}
            onChange={(allow_auto_assign) => setDraft({ ...draft, allow_auto_assign })}
            label="Allow automatic assignment"
            description="New conversations routed here are handed to an available member."
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Delete ${pendingDelete?.name ?? "team"}?`}
        description="Conversations assigned to it become unassigned."
        confirmLabel="Delete team"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default TeamsPage;
