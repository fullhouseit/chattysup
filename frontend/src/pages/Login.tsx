/**
 * Sign-in screen.
 *
 * When the installation has no users yet the register form is shown instead —
 * the first account becomes the super admin.
 */
import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { KeyRound, Lock, Mail } from "lucide-react";
import { auth as authApi } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { Button, Input, PageSpinner } from "@/components/ui";
import { AuthLayout } from "./AuthLayout";
import RegisterPage from "./Register";

export function LoginPage() {
  const { login, config, loading, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/conversations";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <PageSpinner />;
  if (isAuthenticated) return <Navigate to={next} replace />;

  // Fresh installation: go straight to the bootstrap registration form.
  if (config && !config.has_users) return <RegisterPage />;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(next, { replace: true });
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title={`Sign in to ${config?.installation_name ?? "ChattySup"}`}
      subtitle="Your conversations are waiting."
    >
      <form onSubmit={submit} className="space-y-3">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          required
          icon={<Mail className="h-4 w-4" />}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@company.com"
        />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          icon={<Lock className="h-4 w-4" />}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="••••••••"
          error={error}
        />
        <Button type="submit" variant="primary" size="lg" block loading={busy}>
          Sign in
        </Button>
      </form>

      {config && config.sso_providers.length > 0 && (
        <>
          <div className="my-5 flex items-center gap-3">
            <span className="h-px flex-1 bg-line dark:bg-slate-700" />
            <span className="text-2xs uppercase tracking-wide text-ink-faint">or</span>
            <span className="h-px flex-1 bg-line dark:bg-slate-700" />
          </div>
          <div className="space-y-2">
            {config.sso_providers.map((provider) => (
              <a
                key={provider.slug}
                href={authApi.ssoLoginUrl(provider.slug)}
                className="flex h-11 w-full items-center justify-center gap-2 rounded-lg border border-line bg-white text-sm font-medium text-ink-soft transition hover:bg-surface-muted dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
              >
                <KeyRound className="h-4 w-4" />
                Continue with {provider.name}
              </a>
            ))}
          </div>
        </>
      )}

      {config?.registration_enabled && (
        <p className="mt-6 text-center text-xs text-ink-muted dark:text-slate-400">
          Don&apos;t have an account?{" "}
          <Link to="/register" className="font-medium text-primary hover:underline">
            Create one
          </Link>
        </p>
      )}
    </AuthLayout>
  );
}

export default LoginPage;
