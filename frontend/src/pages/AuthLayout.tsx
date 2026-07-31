/** Shared centred card used by the login and register screens. */
import type { ReactNode } from "react";

export interface AuthLayoutProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4 py-10 dark:bg-[#0F141A]">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-lg font-bold text-white shadow-card">
            C
          </span>
          <h1 className="text-lg font-semibold text-ink dark:text-slate-100">{title}</h1>
          {subtitle && (
            <p className="text-sm text-ink-muted dark:text-slate-400">{subtitle}</p>
          )}
        </div>
        <div className="rounded-xl border border-line bg-white p-6 shadow-card dark:border-slate-800 dark:bg-slate-900">
          {children}
        </div>
        {footer}
      </div>
    </div>
  );
}

export default AuthLayout;
