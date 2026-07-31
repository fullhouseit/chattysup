/**
 * Account creation.
 *
 * Doubles as the installation bootstrap: when no user exists yet the form
 * explains that this first account becomes the super admin.
 */
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Lock, Mail, ShieldCheck, User as UserIcon } from "lucide-react";
import { useAuth } from "@/store/auth";
import { Button, Input, PageSpinner } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";

export function RegisterPage() {
  const { register, config, loading, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <PageSpinner />;
  if (isAuthenticated) return <Navigate to="/conversations" replace />;

  const firstUser = config ? !config.has_users : false;
  const closed = config ? !config.registration_enabled && !firstUser : false;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (password.length < 8) {
      setError("Use at least 8 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await register(name.trim(), email.trim(), password);
      navigate("/conversations", { replace: true });
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (closed) {
    return (
      <AuthLayout
        title="Registration is closed"
        subtitle="Ask an administrator to create your account."
      >
        <Link to="/login">
          <Button variant="primary" size="lg" block>
            Back to sign in
          </Button>
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title={firstUser ? "Set up ChattySup" : "Create your account"}
      subtitle={
        firstUser
          ? "One quick step and your helpdesk is ready."
          : "Join your team's shared inbox."
      }
    >
      {firstUser && (
        <div className="mb-4 flex items-start gap-2 rounded-lg bg-primary-50 p-3 text-xs text-primary-800 dark:bg-primary-900/30 dark:text-primary-200">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            This is the first account on this installation — it becomes the{" "}
            <strong>super admin</strong> with full access to settings, inboxes and
            agents.
          </p>
        </div>
      )}

      <form onSubmit={submit} className="space-y-3">
        <Input
          label="Full name"
          required
          autoComplete="name"
          icon={<UserIcon className="h-4 w-4" />}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Ada Lovelace"
        />
        <Input
          label="Email"
          type="email"
          required
          autoComplete="email"
          icon={<Mail className="h-4 w-4" />}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@company.com"
        />
        <Input
          label="Password"
          type="password"
          required
          autoComplete="new-password"
          icon={<Lock className="h-4 w-4" />}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="At least 8 characters"
          hint="At least 8 characters."
          error={error}
        />
        <Button type="submit" variant="primary" size="lg" block loading={busy}>
          {firstUser ? "Create admin account" : "Create account"}
        </Button>
      </form>

      {!firstUser && (
        <p className="mt-6 text-center text-xs text-ink-muted dark:text-slate-400">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </p>
      )}
    </AuthLayout>
  );
}

export default RegisterPage;
