/**
 * `/admin/labels` — the tag vocabulary used across conversations.
 *
 * Colours come from a fixed swatch palette with a free-form hex fallback so the
 * sidebar dots stay legible in both themes.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Tag, Trash2 } from "lucide-react";
import { cn } from "@/lib/cn";
import { labels as labelsApi } from "@/lib/api";
import type { Label } from "@/lib/types";
import { queryKeys } from "@/store/app";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  Input,
  Modal,
  PageSpinner,
  Switch,
  useToast,
} from "@/components/ui";
import { Card } from "./components/Card";
import { PageHeader } from "./components/PageHeader";
import { TableMessage, TableWrap, Td, Th, Tr } from "./components/DataTable";

const SWATCHES = [
  "#1F93FF",
  "#27AE60",
  "#F2994A",
  "#B02525",
  "#9B51E0",
  "#0F766E",
  "#BE185D",
  "#4338CA",
  "#6B7280",
];

interface LabelDraft {
  title: string;
  description: string;
  color: string;
  show_on_sidebar: boolean;
}

const EMPTY: LabelDraft = {
  title: "",
  description: "",
  color: SWATCHES[0]!,
  show_on_sidebar: true,
};

export function LabelsPage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Label | null>(null);
  const [draft, setDraft] = useState<LabelDraft>(EMPTY);
  const [pendingDelete, setPendingDelete] = useState<Label | null>(null);

  const labelsQuery = useQuery({ queryKey: queryKeys.labels, queryFn: labelsApi.list });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: queryKeys.labels });
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = {
        title: draft.title.trim(),
        description: draft.description.trim(),
        color: draft.color,
        show_on_sidebar: draft.show_on_sidebar,
      };
      return editing ? labelsApi.update(editing.id, payload) : labelsApi.create(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Label updated" : "Label created");
      setOpen(false);
      setEditing(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not save the label", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => labelsApi.remove(id),
    onSuccess: () => {
      toast.success("Label deleted");
      setPendingDelete(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not delete the label", error.message),
  });

  function startCreate() {
    setEditing(null);
    setDraft(EMPTY);
    setOpen(true);
  }

  function startEdit(label: Label) {
    setEditing(label);
    setDraft({
      title: label.title,
      description: label.description ?? "",
      color: label.color || SWATCHES[0]!,
      show_on_sidebar: label.show_on_sidebar,
    });
    setOpen(true);
  }

  const list = labelsQuery.data ?? [];

  return (
    <>
      <PageHeader
        title="Labels"
        description="Categorise conversations so filters and automations can find them."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            onClick={startCreate}
          >
            New label
          </Button>
        }
      />

      <Card flush>
        {labelsQuery.isLoading ? (
          <PageSpinner />
        ) : list.length === 0 ? (
          <div className="py-10">
            <EmptyState
              icon={<Tag />}
              title="No labels yet"
              description="Labels appear in the sidebar and on every conversation row."
              action={
                <Button variant="primary" onClick={startCreate}>
                  New label
                </Button>
              }
            />
          </div>
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <Th>Label</Th>
                <Th>Description</Th>
                <Th>Sidebar</Th>
                <Th align="right" />
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <TableMessage colSpan={4}>No labels.</TableMessage>
              ) : (
                list.map((label) => (
                  <Tr key={label.id}>
                    <Td>
                      <span className="flex items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ backgroundColor: label.color }}
                        />
                        <span className="font-medium text-ink dark:text-slate-100">
                          {label.title}
                        </span>
                      </span>
                    </Td>
                    <Td className="max-w-md truncate">{label.description || "—"}</Td>
                    <Td>{label.show_on_sidebar ? "Shown" : "Hidden"}</Td>
                    <Td align="right">
                      <span className="inline-flex gap-1">
                        <IconButton label="Edit label" onClick={() => startEdit(label)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </IconButton>
                        <IconButton
                          label="Delete label"
                          onClick={() => setPendingDelete(label)}
                        >
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

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? `Edit ${editing.title}` : "New label"}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={saveMutation.isPending}
              disabled={!draft.title.trim()}
              onClick={() => saveMutation.mutate()}
            >
              {editing ? "Save label" : "Create label"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Title"
            value={draft.title}
            placeholder="billing"
            hint="Lowercase, no spaces — it is used as the filter value."
            onChange={(event) => setDraft({ ...draft, title: event.target.value })}
          />
          <Input
            label="Description"
            value={draft.description}
            placeholder="Invoices and refunds"
            onChange={(event) => setDraft({ ...draft, description: event.target.value })}
          />
          <div className="space-y-1.5">
            <span className="block text-xs font-medium text-ink-soft dark:text-slate-300">
              Colour
            </span>
            <div className="flex flex-wrap items-center gap-2">
              {SWATCHES.map((swatch) => (
                <button
                  key={swatch}
                  type="button"
                  aria-label={`Use ${swatch}`}
                  onClick={() => setDraft({ ...draft, color: swatch })}
                  className={cn(
                    "h-7 w-7 rounded-full border-2 transition",
                    draft.color.toLowerCase() === swatch.toLowerCase()
                      ? "border-ink dark:border-white"
                      : "border-transparent",
                  )}
                  style={{ backgroundColor: swatch }}
                />
              ))}
              <input
                type="color"
                value={draft.color}
                onChange={(event) => setDraft({ ...draft, color: event.target.value })}
                className="h-7 w-9 cursor-pointer rounded border border-line bg-transparent dark:border-slate-700"
                aria-label="Custom colour"
              />
              <Input
                value={draft.color}
                wrapperClassName="w-28"
                onChange={(event) => setDraft({ ...draft, color: event.target.value })}
                aria-label="Colour hex"
              />
            </div>
          </div>
          <Switch
            checked={draft.show_on_sidebar}
            onChange={(show_on_sidebar) => setDraft({ ...draft, show_on_sidebar })}
            label="Show in the sidebar"
            description="Pin this label under Labels in the left rail."
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Delete ${pendingDelete?.title ?? "label"}?`}
        description="It is removed from every conversation that carries it."
        confirmLabel="Delete label"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default LabelsPage;
