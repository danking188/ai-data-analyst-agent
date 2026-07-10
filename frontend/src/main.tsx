import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AppErrorBoundary } from "./components/ui/AppErrorBoundary";
import { ToastProvider } from "./components/ui/ToastProvider";
import { AppProvider } from "./context/AppContext";
import { AuthProvider } from "./context/AuthContext";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <AppErrorBoundary>
            <AuthProvider>
              <AppProvider>
                <App />
              </AppProvider>
            </AuthProvider>
          </AppErrorBoundary>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
