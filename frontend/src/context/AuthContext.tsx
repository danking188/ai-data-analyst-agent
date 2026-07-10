import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useMemo, type ReactNode } from "react";
import { apiClient } from "../api/client";
import type { SessionInfo } from "../api/contracts";
import { LoginPage } from "../features/auth/LoginPage";
import { LoadingBlock } from "../components/ui/LoadingBlock";

interface AuthContextValue {
  session: SessionInfo;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const sessionKey = ["auth", "session"] as const;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const sessionQuery = useQuery({
    queryKey: sessionKey,
    queryFn: apiClient.getSession,
    retry: false,
  });
  const loginMutation = useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      apiClient.login(username, password),
    onSuccess: (session) => queryClient.setQueryData(sessionKey, session),
  });
  const logoutMutation = useMutation({
    mutationFn: apiClient.logout,
    onSuccess: () => queryClient.removeQueries({ queryKey: sessionKey }),
  });
  const value = useMemo(
    () => sessionQuery.data ? { session: sessionQuery.data, logout: logoutMutation.mutate } : null,
    [logoutMutation.mutate, sessionQuery.data],
  );

  if (sessionQuery.isLoading) return <div className="auth-loading"><LoadingBlock rows={5} /></div>;
  if (!value) {
    return (
      <LoginPage
        error={loginMutation.error}
        loading={loginMutation.isPending}
        onSubmit={(username, password) => loginMutation.mutate({ username, password })}
      />
    );
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
