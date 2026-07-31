/**
 * `/admin/sso` — OIDC / SAML identity providers.
 *
 * Enabled providers show up as buttons on the login screen and post back to
 * `/api/v1/auth/sso/{slug}/callback`, which is displayed here so it can be
 * pasted into the identity provider's console.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { API_BASE, sso as ssoApi } from "@/lib/api";
import { SECRET_MASK, type Dict, type SsoKind, type SsoProvider, type UserRole } from "@/lib/types";
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
  useToast,
} from "@/components/ui";
import { Card } from "./components/Card";
import { CopyButton } from "./components/CopyButton";
import { PageHeader } from "./components/PageHeader";
import { TableMessage, TableWrap, Td, Th, Tr } from "./components/DataTable";

interface SsoDraft {
  slug: string;
  name: string;
  kind: SsoKind;
  enabled: boolean;
  issuer: string;
  client_id: string;
  client_secret: string;
  scopes: string;
  jit_provisioning: boolean;
  default_role: UserRole;
}

const EMPTY: SsoDraft = {
  slug: "",
  name: "",
  kind: "oidc",
  enabled: false,
  issuer: "",
  client_id: "",
  client_secret: "",
  scopes: "openid email profile",
  jit_provisioning: true,
  default_role: "agent",
};

function draftFrom(provider: SsoProvider): SsoDraft {
  const config: Dict = provider.config ?? {};
  const scopes = config.scopes;
  return {
    slug: provider.slug,
    name: provider.name,
    kind: provider.kind,
    enabled: provider.enabled,
    issuer: config.issuer ?? "",
    client_id: config.client_id ?? "",
    client_secret: config.client_secret ?? "",
    scopes: Array.isArray(scopes) ? scopes.join(" ") : (scopes ?? "openid email profile"),
    jit_provisioning: config.jit_provisioning !== false,
    default_role: (config.default_role as UserRole) ?? "agent",
  };
}

/** Absolute callback URL an identity provider must redirect back to. */
function callbackUrl(slug: string): string {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  return `${origin}${API_BASE}/auth/sso/${slug || "{slug}"}/callback`;
}

export function SsoPage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<SsoProvider | null>(null);
  const [draft, setDraft] = useState<SsoDraft>(EMPTY);
  const [pendingDelete, setPendingDelete] = useState<SsoProvider | null>(null);

  const listQuery = useQuery({ queryKey: ["sso_providers"], queryFn: ssoApi.list });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["sso_providers"] });
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      const config: Dict = {
        issuer: draft.issuer.trim(),
        client_id: draft.client_id.trim(),
        scopes: draft.scopes.split(/[\s,]+/).filter(Boolean),
        jit_provisioning: draft.jit_provisioning,
        default_role: draft.default_role,
      };
      // Send the mask back untouched so the stored secret survives.
      config.client_secret = draft.client_secret;
      const payload: Partial<SsoProvider> = {
        slug: draft.slug.trim(),
        name: draft.name.trim(),
        kind: draft.kind,
        enabled: draft.enabled,
        config,
      };
      return editing ? ssoApi.update(editing.id, payload) : ssoApi.create(payload);
    },
    onSuccess: () => {
      toast.success(editing ? "Provider updated" : "Provider created");
      setOpen(false);
      setEditing(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not save the provider", error.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => ssoApi.remove(id),
    onSuccess: () => {
      toast.success("Provider deleted");
      setPendingDelete(null);
      refresh();
    },
    onError: (error: Error) => toast.error("Could not delete the provider", error.message),
  });

  function startCreate() {
    setEditing(null);
    setDraft(EMPTY);
    setOpen(true);
  }

  function startEdit(provider: SsoProvider) {
    setEditing(provider);
    setDraft(draftFrom(provider));
    setOpen(true);
  }

  const list = listQuery.data ?? [];

  return (
    <>
      <PageHeader
        title="Single sign-on"
        description="Enabled providers appear as sign-in buttons on the login screen."
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            onClick={startCreate}
          >
            New provider
          </Button>
        }
      />

      <Card flush>
        {listQuery.isLoading ? (
          <PageSpinner />
        ) : list.length === 0 ? (
          <div className="py-10">
            <EmptyState
              icon={<ShieldCheck />}
              title="No identity providers yet"
              description="Connect Google Workspace, Okta, Keycloak or any OIDC issuer."
              action={
                <Button variant="primary" onClick={startCreate}>
                  New provider
                </Button>
              }
            />
          </div>
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <Th>Provider</Th>
                <Th>Kind</Th>
                <Th>Issuer</Th>
                <Th>Status</Th>
                <Th align="right" />
              </tr>
            </thead>
            <tbody>
              {list.length === 0 ? (
                <TableMessage colSpan={5}>No providers.</TableMessage>
              ) : (
                list.map((provider) => (
                  <Tr key={provider.id}>
                    <Td>
                      <span className="font-medium text-ink dark:text-slate-100">
                        {provider.name}
                      </span>
                      <span className="block text-2xs text-ink-muted">/{provider.slug}</span>
                    </Td>
                    <Td className="uppercase">{provider.kind}</Td>
                    <Td className="max-w-xs truncate">
                      {(provider.config?.issuer as string) || "—"}
                    </Td>
                    <Td>
                      {provider.enabled ? (
                        <Badge tone="success">Enabled</Badge>
                      ) : (
                        <Badge tone="neutral">Disabled</Badge>
                      )}
                    </Td>
                    <Td align="right">
                      <span className="inline-flex gap-1">
                        <IconButton label="Edit provider" onClick={() => startEdit(provider)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </IconButton>
                        <IconButton
                          label="Delete provider"
                          onClick={() => setPendingDelete(provider)}
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
        size="lg"
        title={editing ? `Edit ${editing.name}` : "New identity provider"}
        description="Once enabled, this provider is offered as a button on the login screen."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={saveMutation.isPending}
              disabled={!draft.slug.trim() || !draft.name.trim()}
              onClick={() => saveMutation.mutate()}
            >
              {editing ? "Save provider" : "Create provider"}
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              label="Display name"
              value={draft.name}
              placeholder="Google Workspace"
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
            />
            <Input
              label="Slug"
              value={draft.slug}
              placeholder="google"
              hint="Used in the login and callback URLs."
              onChange={(event) =>
                setDraft({
                  ...draft,
                  slug: event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""),
                })
              }
            />
          </div>

          <div className="rounded-lg bg-surface-muted p-3 dark:bg-slate-800/60">
            <p className="text-xs font-medium text-ink-soft dark:text-slate-300">
              Redirect / callback URL
            </p>
            <div className="mt-1.5 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded bg-white px-2 py-1 text-xs dark:bg-slate-900">
                {callbackUrl(draft.slug)}
              </code>
              <CopyButton value={callbackUrl(draft.slug)} label="Copy callback URL" />
            </div>
          </div>

          <Select
            label="Protocol"
            value={draft.kind}
            options={[
              { value: "oidc", label: "OpenID Connect" },
              { value: "saml", label: "SAML 2.0" },
            ]}
            onChange={(event) => setDraft({ ...draft, kind: event.target.value as SsoKind })}
          />
          <Input
            label="Issuer URL"
            type="url"
            value={draft.issuer}
            placeholder="https://accounts.google.com"
            hint="The discovery document is read from {issuer}/.well-known/openid-configuration."
            onChange={(event) => setDraft({ ...draft, issuer: event.target.value })}
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input
              label="Client ID"
              value={draft.client_id}
              onChange={(event) => setDraft({ ...draft, client_id: event.target.value })}
            />
            <Input
              label="Client secret"
              type="password"
              value={draft.client_secret}
              hint={
                draft.client_secret === SECRET_MASK
                  ? "Stored securely. Type to replace it."
                  : undefined
              }
              onFocus={() => {
                if (draft.client_secret === SECRET_MASK) {
                  setDraft({ ...draft, client_secret: "" });
                }
              }}
              onChange={(event) => setDraft({ ...draft, client_secret: event.target.value })}
            />
          </div>
          <Input
            label="Scopes"
            value={draft.scopes}
            placeholder="openid email profile"
            hint="Space separated."
            onChange={(event) => setDraft({ ...draft, scopes: event.target.value })}
          />
          <Select
            label="Default role for new users"
            value={draft.default_role}
            options={[
              { value: "agent", label: "Agent" },
              { value: "admin", label: "Administrator" },
            ]}
            onChange={(event) =>
              setDraft({ ...draft, default_role: event.target.value as UserRole })
            }
          />
          <Switch
            checked={draft.jit_provisioning}
            onChange={(jit_provisioning) => setDraft({ ...draft, jit_provisioning })}
            label="Just-in-time provisioning"
            description="Create an account automatically the first time someone signs in."
          />
          <Switch
            checked={draft.enabled}
            onChange={(enabled) => setDraft({ ...draft, enabled })}
            label="Show on the login screen"
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={`Delete ${pendingDelete?.name ?? "provider"}?`}
        description="Users who sign in through it will lose access."
        confirmLabel="Delete provider"
        tone="danger"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
        }}
      />
    </>
  );
}

export default SsoPage;
