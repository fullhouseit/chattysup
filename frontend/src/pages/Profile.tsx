/** The signed-in agent's own profile: identity, signature and password. */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Moon, Sun } from "lucide-react";
import { useAuth } from "@/store/auth";
import { useTheme } from "@/store/theme";
import type { Availability } from "@/lib/types";
import {
  Avatar,
  Button,
  Input,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import { NotificationPreferences } from "@/components/NotificationPreferences";

export function ProfilePage() {
  const { user, updateProfile } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const toast = useToast();

  const [form, setForm] = useState({
    name: user?.name ?? "",
    display_name: user?.display_name ?? "",
    avatar_url: user?.avatar_url ?? "",
    signature: user?.signature ?? "",
    availability: (user?.availability ?? "online") as Availability,
  });
  const [passwords, setPasswords] = useState({ current_password: "", password: "" });
  const [saving, setSaving] = useState(false);

  async function saveProfile() {
    setSaving(true);
    try {
      await updateProfile({
        name: form.name,
        display_name: form.display_name,
        avatar_url: form.avatar_url || null,
        signature: form.signature || null,
        availability: form.availability,
      });
      toast.success("Profile saved");
    } catch (error) {
      toast.error("Could not save the profile", (error as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function savePassword() {
    if (!passwords.password) return;
    try {
      await updateProfile(passwords);
      setPasswords({ current_password: "", password: "" });
      toast.success("Password updated");
    } catch (error) {
      toast.error("Could not update the password", (error as Error).message);
    }
  }

  return (
    <div className="h-full w-full overflow-y-auto bg-surface-muted p-6 scroll-thin dark:bg-[#0F141A]">
      <div className="mx-auto max-w-2xl space-y-4">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-sm text-ink-muted transition hover:text-ink dark:text-slate-400"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        <section className="rounded-xl border border-line bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-4 flex items-center gap-3">
            <Avatar
              name={form.display_name || form.name}
              src={form.avatar_url || null}
              seed={user?.id}
              size="xl"
            />
            <div>
              <h2 className="text-md font-semibold text-ink dark:text-slate-100">
                {user?.display_name || user?.name}
              </h2>
              <p className="text-sm text-ink-muted dark:text-slate-400">{user?.email}</p>
            </div>
            <Button
              className="ml-auto"
              variant="secondary"
              size="sm"
              leftIcon={theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              onClick={toggle}
            >
              {theme === "dark" ? "Light theme" : "Dark theme"}
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Full name"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
            <Input
              label="Display name"
              value={form.display_name}
              onChange={(event) => setForm({ ...form, display_name: event.target.value })}
            />
            <Input
              label="Avatar URL"
              value={form.avatar_url}
              onChange={(event) => setForm({ ...form, avatar_url: event.target.value })}
              wrapperClassName="col-span-2"
            />
            <Select
              label="Availability"
              value={form.availability}
              onChange={(event) =>
                setForm({ ...form, availability: event.target.value as Availability })
              }
              options={[
                { value: "online", label: "Online" },
                { value: "busy", label: "Busy" },
                { value: "offline", label: "Offline" },
              ]}
            />
            <Textarea
              label="Signature"
              rows={3}
              value={form.signature}
              onChange={(event) => setForm({ ...form, signature: event.target.value })}
              hint="Appended when you use the signature button in the composer."
              wrapperClassName="col-span-2"
            />
          </div>

          <div className="mt-4 flex justify-end">
            <Button variant="primary" loading={saving} onClick={() => void saveProfile()}>
              Save changes
            </Button>
          </div>
        </section>

        <NotificationPreferences />

        <section className="rounded-xl border border-line bg-white p-5 shadow-card dark:border-slate-800 dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-ink dark:text-slate-100">
            Change password
          </h3>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Input
              label="Current password"
              type="password"
              autoComplete="current-password"
              value={passwords.current_password}
              onChange={(event) =>
                setPasswords({ ...passwords, current_password: event.target.value })
              }
            />
            <Input
              label="New password"
              type="password"
              autoComplete="new-password"
              value={passwords.password}
              onChange={(event) =>
                setPasswords({ ...passwords, password: event.target.value })
              }
            />
          </div>
          <div className="mt-4 flex justify-end">
            <Button
              variant="secondary"
              disabled={!passwords.password || !passwords.current_password}
              onClick={() => void savePassword()}
            >
              Update password
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}

export default ProfilePage;
