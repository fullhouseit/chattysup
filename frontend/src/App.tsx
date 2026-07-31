/** Provider stack: query client, theme, auth, workspace data, toasts, router. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { ApiError } from "@/lib/api";
import AppRoutes from "@/routes";
import { ToastProvider } from "@/components/ui";
import { AppDataProvider } from "@/store/app";
import { AuthProvider } from "@/store/auth";
import { ThemeProvider } from "@/store/theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 15_000,
      retry: (failureCount, error) => {
        // Never retry auth/permission failures — they will not fix themselves.
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false;
        }
        return failureCount < 2;
      },
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <BrowserRouter>
            <AuthProvider>
              <AppDataProvider>
                <AppRoutes />
              </AppDataProvider>
            </AuthProvider>
          </BrowserRouter>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
