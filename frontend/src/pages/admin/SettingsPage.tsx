/**
 * `/admin/settings` — the installation-wide preferences stored in the
 * `settings` key/value table (`services/settings_service.py`).
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { settings as settingsApi } from "@/lib/api";
import type { Dict } from "@/lib/types";
import { useAuth } from "@/store/auth";
import { Avatar, Button, Input, PageSpinner, Select, Switch, useToast } from "@/components/ui";
import { Card, CardHeader } from "./components/Card";
import { PageHeader } from "./components/PageHeader";

interface SettingsForm {
  installation_name: string;
  logo_url: string;
  default_locale: string;
  enable_registration: boolean;
  auto_resolve_after_days: string;
}

const LOCALES = [
  { value: "en", label: "English" },
  { value: "de", label: "Deutsch" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "it", label: "Italiano" },
  { value: "nl", label: "Nederlands" },
  { value: "pt", label: "Português" },
  { value: "ru", label: "Русский" },
  { value: "uk", label: "Українська" },
];

function formFrom(values: Dict): SettingsForm {
  return {
    installation_name: values.installation_name ?? "ChattySup",
    logo_url: values.logo_url ?? "",
    default_locale: values.default_locale ?? "en",
    enable_registration: Boolean(values.enable_registration),
    auto_resolve_after_days:
      values.auto_resolve_after_days === null || values.auto_resolve_after_days === undefined
        ? "0"
        : String(values.auto_resolve_after_days),
  };
}

export function SettingsPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { refreshConfig } = useAuth();

  const [form, setForm] = useState<SettingsForm | null>(null);

  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: settingsApi.get });

  useEffect(() => {
    if (settingsQuery.data) setForm(formFrom(settingsQuery.data));
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      settingsApi.update({
        installation_name: form!.installation_name.trim(),
        logo_url: form!.logo_url.trim() || null,
        default_locale: form!.default_locale,
        enable_registration: form!.enable_registration,
        auto_resolve_after_days: Number(form!.auto_resolve_after_days || 0),
      }),
    onSuccess: async (next) => {
      toast.success("Settings saved");
      queryClient.setQueryData(["settings"], next);
      await refreshConfig();
    },
    onError: (error: Error) => toast.error("Could not save the settings", error.message),
  });

  if (settingsQuery.isLoading || !form) return <PageSpinner />;

  const patch = (next: Partial<SettingsForm>) =>
    setForm((state) => (state ? { ...state, ...next } : state));

  return (
    <>
      <PageHeader
        title="Settings"
        description="How this ChattySup installation presents itself."
        actions={
          <Button
            variant="primary"
            size="sm"
            loading={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            Save changes
          </Button>
        }
      />

      <div className="space-y-4">
        <Card flush>
          <CardHeader
            title="Branding"
            description="Shown on the login screen and in the workspace switcher."
          />
          <div className="max-w-xl space-y-4 p-5">
            <div className="flex items-center gap-3">
              <Avatar
                name={form.installation_name}
                src={form.logo_url || null}
                size="xl"
                square
              />
              <div className="min-w-0 flex-1">
                <Input
                  label="Logo URL"
                  value={form.logo_url}
                  placeholder="https://example.com/logo.png"
                  onChange={(event) => patch({ logo_url: event.target.value })}
                />
              </div>
            </div>
            <Input
              label="Installation name"
              value={form.installation_name}
              placeholder="ChattySup"
              onChange={(event) => patch({ installation_name: event.target.value })}
            />
            <Select
              label="Default language"
              value={form.default_locale}
              options={LOCALES}
              hint="Used for new agents until they pick their own."
              onChange={(event) => patch({ default_locale: event.target.value })}
            />
          </div>
        </Card>

        <Card flush>
          <CardHeader title="Access" description="Who is allowed to create an account." />
          <div className="max-w-xl space-y-4 p-5">
            <Switch
              checked={form.enable_registration}
              onChange={(enable_registration) => patch({ enable_registration })}
              label="Allow self-service registration"
              description="When off, only administrators can add agents. The very first account can always be created."
            />
          </div>
        </Card>

        <Card flush>
          <CardHeader
            title="Conversations"
            description="Housekeeping applied across every inbox."
          />
          <div className="max-w-xl space-y-4 p-5">
            <Input
              label="Auto-resolve after (days)"
              type="number"
              min={0}
              value={form.auto_resolve_after_days}
              hint="0 disables it. Inbox-level settings take precedence."
              onChange={(event) => patch({ auto_resolve_after_days: event.target.value })}
            />
          </div>
        </Card>
      </div>
    </>
  );
}

export default SettingsPage;
