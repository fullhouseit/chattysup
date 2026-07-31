/**
 * `/admin/canned-responses` — saved replies.
 *
 * Agents reach these from the composer by typing `/` followed by the short
 * code, so the code is what makes a response findable.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareQuote, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { cannedResponses as cannedApi } from "@/lib/api";
import { truncate } from "@/lib/format";
import type { CannedResponse } from "@/lib/types";
import { queryKeys } from "@/store/app";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  Input,
  Modal,
  PageSpinner,
  Textarea,
  useToast,
} from "@/components/ui";
import { Card } from "./components/Card";
import { PageHeader } from "./components/PageHeader";
import { TableMessage, TableWrap, Td, Th, Tr } from "./components/DataTable";

interface Draft {
  short_code: string;
  content: string;
}

const EMPTY: Draft = { short_code: "", content: "" };

export function CannedResponsesPage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<CannedResponse | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [pendingDelete, setPendingDelete] = useState<CannedResponse | null>(null);

  const listQuery = useQuery({ queryKey: queryKeys.canned, queryFn: cannedApi.list });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: queryKeys.canned });
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = {
        short_code: draft.short_code.trim(),
        content: draft.content,
      };
      return editing ? cannedApi.update(editing.id, payload) : cannedApi.create(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Response updated" : "Response created");
      setOpen(false);
      setEditing(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not save the response", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => cannedApi.remove(id),
    onSuccess: () => {
      toast.success("Response deleted");
      setPendingDelete(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not delete the response", error.message),
  });

  function startCreate() {
    setEditing(null);
    setDraft(EMPTY);
    setOpen(true);
  }

  function startEdit(response: CannedResponse) {
    setEditing(response);
    setDraft({ short_code: response.short_code, content: response.content });
    setOpen(true);
  }

  const list = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const all = listQuery.data ?? [];
    if (!needle) return all;
    return all.filter(
      (item) =>
        item.short_code.toLowerCase().includes(needle) ||
        item.content.toLowerCase().includes(needle),
    );
  }, [listQuery.data, query]);

  return (
    <>
      <PageHeader
        title="Canned responses"
        description="Type “/” in the composer to insert one of these."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            onClick={startCreate}
          >
            New response
          </Button>
        }
      />

      <div className="mb-3 max-w-sm">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search responses…"
          icon={<Search className="h-3.5 w-3.5" />}
        />
      </div>

      <Card flush>
        {listQuery.isLoading ? (
          <PageSpinner />
        ) : (listQuery.data ?? []).length === 0 ? (
          <div className="py-10">
            <EmptyState
              icon={<MessageSquareQuote />}
              title="No canned responses yet"
              description="Save the answers your team writes over and over."
              action={
                <Button variant="primary" onClick={startCreate}>
                  New response
                </Button>
              }
            />
          </div>
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <Th className="w-40">Short code</Th>
                <Th>Content</Th>
                <Th align="right" />
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <TableMessage colSpan={3}>Nothing matches “{query}”.</TableMessage>
              ) : (
                list.map((response) => (
                  <Tr key={response.id} onClick={() => startEdit(response)}>
                    <Td>
                      <code className="rounded bg-surface-muted px-1.5 py-0.5 text-xs text-primary dark:bg-slate-800">
                        /{response.short_code}
                      </code>
                    </Td>
                    <Td className="max-w-xl">
                      <span className="block truncate">{truncate(response.content, 140)}</span>
                    </Td>
                    <Td align="right">
                      <span
                        className="inline-flex gap-1"
                        onClick={(event) => event.stopPropagation()}
                      >
                        <IconButton label="Edit response" onClick={() => startEdit(response)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </IconButton>
                        <IconButton
                          label="Delete response"
                          onClick={() => setPendingDelete(response)}
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
        title={editing ? `Edit /${editing.short_code}` : "New canned response"}
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={saveMutation.isPending}
              disabled={!draft.short_code.trim() || !draft.content.trim()}
              onClick={() => saveMutation.mutate()}
            >
              {editing ? "Save response" : "Create response"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Short code"
            value={draft.short_code}
            placeholder="thanks"
            hint="Agents type “/thanks” to insert it."
            onChange={(event) => setDraft({ ...draft, short_code: event.target.value })}
          />
          <Textarea
            label="Content"
            rows={6}
            value={draft.content}
            placeholder="Thank you for reaching out! Is there anything else I can help with?"
            onChange={(event) => setDraft({ ...draft, content: event.target.value })}
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Delete /${pendingDelete?.short_code ?? ""}?`}
        description="Agents will no longer be able to insert this reply."
        confirmLabel="Delete response"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default CannedResponsesPage;
