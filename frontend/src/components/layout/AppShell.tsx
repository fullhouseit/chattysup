/**
 * Application chrome: the left rail plus the routed content area and the
 * "reconnecting" banner driven by the realtime connection state.
 */
import type { ReactNode } from "react";
import { WifiOff } from "lucide-react";
import { useAppData } from "@/store/app";
import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  const { connection } = useAppData();

  return (
    <div className="flex h-screen w-full overflow-hidden bg-surface-muted dark:bg-[#0F141A]">
      <Sidebar />
      <div className="relative flex min-w-0 flex-1 flex-col">
        {connection !== "open" && (
          <div className="flex items-center justify-center gap-2 bg-amber-100 px-3 py-1 text-2xs font-medium text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
            <WifiOff className="h-3 w-3" />
            {connection === "connecting"
              ? "Reconnecting to the live feed…"
              : "Live updates are offline — retrying…"}
          </div>
        )}
        <main className="flex min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}

export default AppShell;
