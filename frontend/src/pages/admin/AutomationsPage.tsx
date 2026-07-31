/**
 * `/admin/automations` — the rule engine's user interface.
 *
 * Nothing here is hard-coded: the events, condition attributes, operators and
 * actions all come from `GET /automations/catalogue`, and each input adapts to
 * the attribute or parameter type the backend declares.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Pencil, Plus, Trash2, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { automations as automationsApi } from "@/lib/api";
import { humanize, relativeTime } from "@/lib/format";
import type {
  Automation,
  AutomationAction,
  AutomationCondition,
  Dict,
  Json,
} from "@/lib/types";
import { queryKeys, useAppData } from "@/store/app";
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  Input,
  Modal,
  PageSpinner,
  Select,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import { Card } from "./components/Card";
import { PageHeader } from "./components/PageHeader";
import { TableMessage, TableWrap, Td, Th, Tr } from "./components/DataTable";

/* --------------------------------------------------------- catalogue types */

interface AttributeSpec {
  key: string;
  label: string;
  type: string;
  options?: string[];
}

interface OperatorSpec {
  key: string;
  label: string;
}

interface ActionSpec {
  key: string;
  label: string;
  params: string[];
}

/** Operators that compare against nothing, so the value input is hidden. */
const UNARY_OPERATORS = new Set(["is_present", "is_not_present"]);

/* ------------------------------------------------------------------ draft */

interface AutomationDraft {
  name: string;
  description: string;
  event_name: string;
  condition_logic: "and" | "or";
  conditions: AutomationCondition[];
  actions: AutomationAction[];
  inbox_id: number | null;
  run_once_per_conversation: boolean;
  active: boolean;
}

function emptyDraft(event: string): AutomationDraft {
  return {
    name: "",
    description: "",
    event_name: event,
    condition_logic: "and",
    conditions: [],
    actions: [],
    inbox_id: null,
    run_once_per_conversation: false,
    active: true,
  };
}

function draftFrom(rule: Automation): AutomationDraft {
  return {
    name: rule.name,
    description: rule.description ?? "",
    event_name: rule.event_name,
    condition_logic: rule.condition_logic ?? "and",
    conditions: (rule.conditions ?? []).map((condition) => ({ ...condition })),
    actions: (rule.actions ?? []).map((action) => ({ ...action, params: { ...action.params } })),
    inbox_id: rule.inbox_id,
    run_once_per_conversation: rule.run_once_per_conversation,
    active: rule.active,
  };
}

export function AutomationsPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { inboxes, agents, teams, labels } = useAppData();

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Automation | null>(null);
  const [draft, setDraft] = useState<AutomationDraft>(() => emptyDraft(""));
  const [pendingDelete, setPendingDelete] = useState<Automation | null>(null);

  const catalogueQuery = useQuery({
    queryKey: ["automations", "catalogue"],
    queryFn: automationsApi.catalogue,
    staleTime: Infinity,
  });
  const listQuery = useQuery({ queryKey: ["automations"], queryFn: automationsApi.list });

  const events = (catalogueQuery.data?.events ?? []) as string[];
  const attributes = (catalogueQuery.data?.attributes ?? []) as unknown as AttributeSpec[];
  const operators = (catalogueQuery.data?.operators ?? []) as unknown as OperatorSpec[];
  const actionSpecs = (catalogueQuery.data?.actions ?? []) as unknown as ActionSpec[];

  const attributeByKey = useMemo(
    () => new Map(attributes.map((item) => [item.key, item])),
    [attributes],
  );
  const actionByKey = useMemo(
    () => new Map(actionSpecs.map((item) => [item.key, item])),
    [actionSpecs],
  );

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["automations"] });
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload: Partial<Automation> = {
        name: draft.name.trim(),
        description: draft.description.trim() || null,
        event_name: draft.event_name,
        condition_logic: draft.condition_logic,
        conditions: draft.conditions,
        actions: draft.actions,
        inbox_id: draft.inbox_id,
        run_once_per_conversation: draft.run_once_per_conversation,
        active: draft.active,
      };
      return editing ? automationsApi.update(editing.id, payload) : automationsApi.create(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Rule updated" : "Rule created");
      setOpen(false);
      setEditing(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not save the rule", error.message),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      automationsApi.update(id, { active }),
    onSuccess: () => refresh(),
    onError: (error: Error) => toast.error("Could not update the rule", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => automationsApi.remove(id),
    onSuccess: () => {
      toast.success("Rule deleted");
      setPendingDelete(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not delete the rule", error.message),
  });

  function startCreate() {
    setEditing(null);
    setDraft(emptyDraft(events[0] ?? "message_created"));
    setOpen(true);
  }

  function startEdit(rule: Automation) {
    setEditing(rule);
    setDraft(draftFrom(rule));
    setOpen(true);
  }

  /* ------------------------------------------------------ condition rows */

  function addCondition() {
    const first = attributes[0];
    setDraft((state) => ({
      ...state,
      conditions: [
        ...state.conditions,
        { attribute: first?.key ?? "", operator: operators[0]?.key ?? "equal_to", values: [""] },
      ],
    }));
  }

  function patchCondition(index: number, patch: Partial<AutomationCondition>) {
    setDraft((state) => ({
      ...state,
      conditions: state.conditions.map((condition, position) =>
        position === index ? { ...condition, ...patch } : condition,
      ),
    }));
  }

  function removeCondition(index: number) {
    setDraft((state) => ({
      ...state,
      conditions: state.conditions.filter((_, position) => position !== index),
    }));
  }

  /* --------------------------------------------------------- action rows */

  function addAction() {
    const first = actionSpecs[0];
    setDraft((state) => ({
      ...state,
      actions: [...state.actions, { action: first?.key ?? "", params: {} }],
    }));
  }

  function patchAction(index: number, patch: Partial<AutomationAction>) {
    setDraft((state) => ({
      ...state,
      actions: state.actions.map((action, position) =>
        position === index ? { ...action, ...patch } : action,
      ),
    }));
  }

  function patchActionParam(index: number, key: string, value: Json) {
    setDraft((state) => ({
      ...state,
      actions: state.actions.map((action, position) =>
        position === index
          ? { ...action, params: { ...(action.params ?? {}), [key]: value } }
          : action,
      ),
    }));
  }

  function removeAction(index: number) {
    setDraft((state) => ({
      ...state,
      actions: state.actions.filter((_, position) => position !== index),
    }));
  }

  /* ------------------------------------------------------- value inputs */

  /**
   * The right editor for a condition's value, chosen by the attribute type.
   *
   * This is a plain render function rather than a component so React keeps the
   * same input instance across keystrokes instead of remounting it.
   */
  function renderConditionValue(condition: AutomationCondition, index: number) {
    if (UNARY_OPERATORS.has(condition.operator)) {
      return (
        <span className="flex h-9 items-center text-xs text-ink-muted dark:text-slate-400">
          no value needed
        </span>
      );
    }

    const spec = attributeByKey.get(condition.attribute);
    const raw = condition.values?.[0];
    const text = raw === null || raw === undefined ? "" : String(raw);
    const set = (value: Json) => patchCondition(index, { values: [value] });

    switch (spec?.type) {
      case "boolean":
        return (
          <Select
            value={text || "true"}
            options={[
              { value: "true", label: "Yes" },
              { value: "false", label: "No" },
            ]}
            onChange={(event) => set(event.target.value === "true")}
          />
        );
      case "inbox":
        return (
          <Select
            value={text}
            placeholder="Choose an inbox"
            options={inboxes.map((inbox) => ({ value: inbox.id, label: inbox.name }))}
            onChange={(event) => set(Number(event.target.value))}
          />
        );
      case "agent":
        return (
          <Select
            value={text}
            placeholder="Choose an agent"
            options={agents.map((agent) => ({
              value: agent.id,
              label: agent.display_name || agent.name,
            }))}
            onChange={(event) => set(Number(event.target.value))}
          />
        );
      case "team":
        return (
          <Select
            value={text}
            placeholder="Choose a team"
            options={teams.map((team) => ({ value: team.id, label: team.name }))}
            onChange={(event) => set(Number(event.target.value))}
          />
        );
      case "label":
        return (
          <Select
            value={text}
            placeholder="Choose a label"
            options={labels.map((label) => ({ value: label.title, label: label.title }))}
            onChange={(event) => set(event.target.value)}
          />
        );
      case "select":
        return (
          <Select
            value={text}
            placeholder="Choose a value"
            options={(spec.options ?? []).map((option) => ({
              value: option,
              label: humanize(option),
            }))}
            onChange={(event) => set(event.target.value)}
          />
        );
      default:
        return (
          <Input
            value={text}
            placeholder="Value"
            onChange={(event) => set(event.target.value)}
          />
        );
    }
  }

  /** The right editor for one action parameter, chosen by its name. */
  function renderActionParam(index: number, action: AutomationAction, param: string) {
    const params: Dict = action.params ?? {};
    const raw = params[param];
    const text = raw === null || raw === undefined ? "" : String(raw);
    const set = (value: Json) => patchActionParam(index, param, value);

    switch (param) {
      case "content":
        return (
          <Textarea
            label="Message"
            rows={3}
            value={text}
            placeholder="Thanks for writing in — we're on it!"
            onChange={(event) => set(event.target.value)}
          />
        );
      case "user_id":
        return (
          <Select
            label="Agent"
            value={text}
            placeholder="Choose an agent"
            options={agents.map((agent) => ({
              value: agent.id,
              label: agent.display_name || agent.name,
            }))}
            onChange={(event) => set(Number(event.target.value))}
          />
        );
      case "team_id":
        return (
          <Select
            label="Team"
            value={text}
            placeholder="Choose a team"
            options={teams.map((team) => ({ value: team.id, label: team.name }))}
            onChange={(event) => set(Number(event.target.value))}
          />
        );
      case "label":
        return (
          <Select
            label="Label"
            value={text}
            placeholder="Choose a label"
            options={labels.map((label) => ({ value: label.title, label: label.title }))}
            onChange={(event) => set(event.target.value)}
          />
        );
      case "priority":
        return (
          <Select
            label="Priority"
            value={text}
            placeholder="Choose a priority"
            options={["none", "low", "medium", "high", "urgent"].map((value) => ({
              value,
              label: humanize(value),
            }))}
            onChange={(event) => set(event.target.value)}
          />
        );
      case "status":
        return (
          <Select
            label="Status"
            value={text}
            placeholder="Choose a status"
            options={["open", "pending", "snoozed", "resolved"].map((value) => ({
              value,
              label: humanize(value),
            }))}
            onChange={(event) => set(event.target.value)}
          />
        );
      case "minutes":
        return (
          <Input
            label="Minutes"
            type="number"
            min={1}
            value={text}
            onChange={(event) => set(Number(event.target.value))}
          />
        );
      default:
        return (
          <Input
            label={humanize(param)}
            value={text}
            onChange={(event) => set(event.target.value)}
          />
        );
    }
  }

  const rules = listQuery.data ?? [];
  const canSave = draft.name.trim().length > 0 && draft.actions.length > 0;

  return (
    <>
      <PageHeader
        title="Automations"
        description="Run actions automatically when something happens in a conversation."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            disabled={catalogueQuery.isLoading}
            onClick={startCreate}
          >
            New rule
          </Button>
        }
      />

      <Card flush>
        {listQuery.isLoading ? (
          <PageSpinner />
        ) : rules.length === 0 ? (
          <div className="py-10">
            <EmptyState
              icon={<Bot />}
              title="No automations yet"
              description="Auto-assign, label or reply without lifting a finger."
              action={
                <Button variant="primary" onClick={startCreate}>
                  New rule
                </Button>
              }
            />
          </div>
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <Th>Rule</Th>
                <Th>When</Th>
                <Th>Actions</Th>
                <Th>Runs</Th>
                <Th align="right" />
              </tr>
            </thead>
            <tbody>
              {rules.length === 0 ? (
                <TableMessage colSpan={5}>No rules.</TableMessage>
              ) : (
                rules.map((rule) => (
                  <Tr key={rule.id}>
                    <Td>
                      <span className="flex items-center gap-2">
                        <span
                          className={cn(
                            "h-2 w-2 shrink-0 rounded-full",
                            rule.active ? "bg-emerald-500" : "bg-slate-300",
                          )}
                        />
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-ink dark:text-slate-100">
                            {rule.name}
                          </span>
                          {rule.description && (
                            <span className="block truncate text-2xs text-ink-muted">
                              {rule.description}
                            </span>
                          )}
                        </span>
                      </span>
                    </Td>
                    <Td>
                      <Badge tone="neutral">{humanize(rule.event_name)}</Badge>
                      {rule.conditions.length > 0 && (
                        <span className="ml-1.5 text-2xs text-ink-muted">
                          + {rule.conditions.length} condition
                          {rule.conditions.length === 1 ? "" : "s"}
                        </span>
                      )}
                    </Td>
                    <Td>
                      <span className="flex flex-wrap gap-1">
                        {rule.actions.map((action, index) => (
                          <Badge key={`${action.action}-${index}`} tone="primary">
                            {actionByKey.get(action.action)?.label ?? humanize(action.action)}
                          </Badge>
                        ))}
                      </span>
                    </Td>
                    <Td className="whitespace-nowrap tabular-nums">
                      {rule.execution_count}
                      {rule.last_executed_at && (
                        <span className="ml-1 text-2xs text-ink-faint">
                          ({relativeTime(rule.last_executed_at)} ago)
                        </span>
                      )}
                    </Td>
                    <Td align="right">
                      <span className="inline-flex items-center gap-1">
                        <Switch
                          size="sm"
                          checked={rule.active}
                          onChange={(active) => toggleMutation.mutate({ id: rule.id, active })}
                        />
                        <IconButton label="Edit rule" onClick={() => startEdit(rule)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </IconButton>
                        <IconButton label="Delete rule" onClick={() => setPendingDelete(rule)}>
                          <Trash2 className="h-3.5 w-3.5 text-red-500" />
                        </IconButton>
                      </span>
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </TableWrap>
        )}
      </Card>

      {/* ------------------------------------------------- rule builder */}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        size="xl"
        title={editing ? `Edit ${editing.name}` : "New automation"}
        description="Choose the trigger, narrow it down with conditions, then say what should happen."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={saveMutation.isPending}
              disabled={!canSave}
              onClick={() => saveMutation.mutate()}
            >
              {editing ? "Save rule" : "Create rule"}
            </Button>
          </>
        }
      >
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              label="Rule name"
              value={draft.name}
              placeholder="Assign billing questions to the Billing team"
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
            <Select
              label="Trigger event"
              value={draft.event_name}
              options={events.map((event) => ({ value: event, label: humanize(event) }))}
              onChange={(event) => setDraft({ ...draft, event_name: event.target.value })}
            />
          </div>

          <Input
            label="Description"
            value={draft.description}
            placeholder="Optional note for your team"
            onChange={(event) => setDraft({ ...draft, description: event.target.value })}
          />

          {/* conditions */}
          <section className="rounded-lg border border-line p-3 dark:border-slate-700">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                Conditions
              </h3>
              <div className="flex items-center gap-2">
                <div className="inline-flex overflow-hidden rounded-lg border border-line dark:border-slate-700">
                  {(["and", "or"] as const).map((logic) => (
                    <button
                      key={logic}
                      type="button"
                      onClick={() => setDraft({ ...draft, condition_logic: logic })}
                      className={cn(
                        "px-2.5 py-1 text-2xs font-semibold uppercase transition",
                        draft.condition_logic === logic
                          ? "bg-primary text-white"
                          : "text-ink-muted hover:bg-surface-muted dark:hover:bg-slate-800",
                      )}
                    >
                      {logic}
                    </button>
                  ))}
                </div>
                <Button
                  size="xs"
                  variant="secondary"
                  leftIcon={<Plus className="h-3 w-3" />}
                  onClick={addCondition}
                >
                  Add condition
                </Button>
              </div>
            </div>

            {draft.conditions.length === 0 ? (
              <p className="py-2 text-xs text-ink-muted dark:text-slate-400">
                No conditions — the rule runs on every {humanize(draft.event_name).toLowerCase()}{" "}
                event.
              </p>
            ) : (
              <div className="space-y-2">
                {draft.conditions.map((condition, index) => (
                  <div key={index} className="flex items-start gap-2">
                    <span className="w-10 shrink-0 pt-2 text-2xs font-semibold uppercase text-ink-faint">
                      {index === 0 ? "If" : draft.condition_logic}
                    </span>
                    <div className="w-1/3">
                      <Select
                        value={condition.attribute}
                        options={attributes.map((item) => ({
                          value: item.key,
                          label: item.label,
                        }))}
                        onChange={(event) =>
                          patchCondition(index, { attribute: event.target.value, values: [""] })
                        }
                      />
                    </div>
                    <div className="w-1/4">
                      <Select
                        value={condition.operator}
                        options={operators.map((item) => ({
                          value: item.key,
                          label: item.label,
                        }))}
                        onChange={(event) =>
                          patchCondition(index, { operator: event.target.value })
                        }
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      {renderConditionValue(condition, index)}
                    </div>
                    <IconButton label="Remove condition" onClick={() => removeCondition(index)}>
                      <X className="h-3.5 w-3.5" />
                    </IconButton>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* actions */}
          <section className="rounded-lg border border-line p-3 dark:border-slate-700">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                Actions
              </h3>
              <Button
                size="xs"
                variant="secondary"
                leftIcon={<Plus className="h-3 w-3" />}
                onClick={addAction}
              >
                Add action
              </Button>
            </div>

            {draft.actions.length === 0 ? (
              <p className="py-2 text-xs text-amber-700 dark:text-amber-300">
                Add at least one action.
              </p>
            ) : (
              <div className="space-y-3">
                {draft.actions.map((action, index) => {
                  const spec = actionByKey.get(action.action);
                  return (
                    <div
                      key={index}
                      className="rounded-lg bg-surface-muted p-3 dark:bg-slate-800/60"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-10 shrink-0 text-2xs font-semibold uppercase text-ink-faint">
                          Then
                        </span>
                        <div className="min-w-0 flex-1">
                          <Select
                            value={action.action}
                            options={actionSpecs.map((item) => ({
                              value: item.key,
                              label: item.label,
                            }))}
                            onChange={(event) =>
                              patchAction(index, { action: event.target.value, params: {} })
                            }
                          />
                        </div>
                        <IconButton label="Remove action" onClick={() => removeAction(index)}>
                          <X className="h-3.5 w-3.5" />
                        </IconButton>
                      </div>
                      {(spec?.params ?? []).length > 0 && (
                        <div className="mt-2 space-y-2 pl-12">
                          {(spec?.params ?? []).map((param) => (
                            <div key={param}>{renderActionParam(index, action, param)}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Select
              label="Limit to an inbox"
              value={draft.inbox_id === null ? "" : String(draft.inbox_id)}
              placeholder="All inboxes"
              options={inboxes.map((inbox) => ({ value: inbox.id, label: inbox.name }))}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  inbox_id: event.target.value === "" ? null : Number(event.target.value),
                })
              }
            />
            <div className="space-y-3 pt-1">
              <Switch
                checked={draft.run_once_per_conversation}
                onChange={(run_once_per_conversation) =>
                  setDraft({ ...draft, run_once_per_conversation })
                }
                label="Run once per conversation"
                description="Never fire twice for the same chat."
              />
              <Switch
                checked={draft.active}
                onChange={(active) => setDraft({ ...draft, active })}
                label="Rule is active"
              />
            </div>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Delete ${pendingDelete?.name ?? "rule"}?`}
        description="It stops running immediately."
        confirmLabel="Delete rule"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default AutomationsPage;
