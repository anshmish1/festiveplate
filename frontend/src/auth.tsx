import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "./api";
import type { Me, User } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  acceptToken: (token: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    tokenStore.clear();
    setMe(null);
  }, []);

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) {
      setMe(null);
      return;
    }
    try {
      setMe(await api.get<Me>("/api/me"));
    } catch {
      logout();
    }
  }, [logout]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    refresh().finally(() => setLoading(false));
  }, [refresh, logout]);

  const acceptToken = useCallback(async (token: string) => {
    tokenStore.set(token);
    const m = await api.get<Me>("/api/me");
    setMe(m);
    return m.user;
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const r = await api.post<{ access_token: string }>("/api/auth/login", { email, password });
      return acceptToken(r.access_token);
    },
    [acceptToken],
  );

  return <Ctx.Provider value={{ me, loading, login, acceptToken, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}

export function homeFor(role: string | undefined): string {
  switch (role) {
    case "DONOR": return "/donor";
    case "NGO": return "/ngo";
    case "VOLUNTEER": return "/volunteer";
    case "ADMIN": return "/admin";
    default: return "/";
  }
}
