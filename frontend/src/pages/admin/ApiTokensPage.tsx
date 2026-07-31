/**
 * `/admin/api-tokens` — personal access tokens for the REST API.
 *
 * The plaintext token exists only in the creation response, so it is shown once
 * in a copyable callout and never fetched again.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Trash2, TriangleAlert } from "lucide-react";
import { apiTokens as tokensApi } from "@/lib/api";
import { fullTimestamp, relativeTime } from "@/lib/format";
import type { ApiToken } from "@/lib/types";
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  Input,
  Modal,
  PageSpinner,
  useToast,
} from "@/components/ui";
import { Card } from "./components/Card";
import { CopyButton } from "./components/CopyButton";
import { PageHeader } from "./components/PageHeader";
import { TableMessage, TableWrap, Td, Th, Tr } from "./components/DataTable";

export function ApiTokensPage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [issued, setIssued] = useState<ApiToken | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ApiToken | null>(null);

  const listQuery = useQuery({ queryKey: ["api_tokens"], queryFn: tokensApi.list });

  const createMutation = useMutation({
    mutationFn: () =>
      tokensApi.create({
        name: name.trim(),
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      }),
    onSuccess: (token) => {
      setIssued(token);
      setOpen(false);
      setName("");
      setExpiresAt("");
      queryClient.invalidateQueries({ queryKey: ["api_tokens"] });
    },
    onError: (error: Error) => toast.error("Could not create the token", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => tokensApi.remove(id),
    onSuccess: () => {
      toast.success("Token revoked");
      setPendingDelete(null);
      queryClient.invalidateQueries({ queryKey: ["api_tokens"] });
    },
    onError: (error: Error) => toast.error("Could not revoke the token", error.message),
  });

  const list = listQuery.data ?? [];

  return (
    <>
      <PageHeader
        title="API tokens"
        description="Authenticate server-to-server calls with an Authorization: Bearer header."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            onClick={() => setOpen(true)}
          >
            New token
          </Button>
        }
      />

      {issued?.token && (
        <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/30">
          <p className="flex items-center gap-2 text-sm font-semibold text-amber-900 dark:text-amber-200">
            <TriangleAlert className="h-4 w-4" />
            Copy this token now — it will never be shown again.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-lg bg-white px-3 py-2 text-xs text-ink scroll-thin dark:bg-slate-900 dark:text-slate-100">
              {issued.token}
            </code>
            <CopyButton value={issued.token} label="Copy token" />
            <Button variant="ghost" size="sm" onClick={() => setIssued(null)}>
              Dismiss
            </Button>
          </div>
        </div>
      )}

      <Card flush>
        {listQuery.isLoading ? (
          <PageSpinner />
        ) : list.length === 0 ? (
          <div className="py-10">
            <EmptyState
              icon={<KeyRound />}
              title="No API tokens yet"
              description="Create one to drive ChattySup from your own scripts."
              action={
                <Button variant="primary" onClick={() => setOpen(true)}>
                  New token
                </Button>
              }
            />
          </div>
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Prefix</Th>
                <Th>Last used</Th>
                <Th>Expires</Th>
                <Th align="right" />
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <TableMessage colSpan={5}>No tokens.</TableMessage>
              ) : (
                list.map((token) => (
                  <Tr key={token.id}>
                    <Td>
                      <span className="font-medium text-ink dark:text-slate-100">
                        {token.name}
                      </span>
                      {!token.active && (
                        <Badge tone="warning" className="ml-2">
                          Revoked
                        </Badge>
                      )}
                    </Td>
                    <Td>
                      <code className="rounded bg-surface-muted px-1.5 py-0.5 text-xs dark:bg-slate-800">
                        {token.prefix}…
                      </code>
                    </Td>
                    <Td>
                      {token.last_used_at ? `${relativeTime(token.last_used_at)} ago` : "Never"}
                    </Td>
                    <Td title={fullTimestamp(token.expires_at)}>
                      {token.expires_at ? fullTimestamp(token.expires_at) : "Never"}
                    </Td>
                    <Td align="right">
                      <IconButton
                        label="Revoke token"
                        onClick={() => setPendingDelete(token)}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-red-500" />
                      </IconButton>
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
        title="New API token"
        description="The token inherits your own permissions."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={createMutation.isPending}
              disabled={!name.trim()}
              onClick={() => createMutation.mutate()}
            >
              Create token
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Name"
            value={name}
            placeholder="Zapier integration"
            onChange={(event) => setName(event.target.value)}
          />
          <Input
            label="Expires on"
            type="date"
            value={expiresAt}
            hint="Optional. Leave empty for a token that never expires."
            onChange={(event) => setExpiresAt(event.target.value)}
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Revoke ${pendingDelete?.name ?? "token"}?`}
        description="Any integration using it stops working immediately."
        confirmLabel="Revoke token"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default ApiTokensPage;
