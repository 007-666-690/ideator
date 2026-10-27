import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import type { Me } from "./types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.me());
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 401) console.error(err);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = async (email: string, password: string) => setUser(await api.login(email, password));
  const register = async (name: string, email: string, password: string) => setUser(await api.register(name, email, password));
  const logout = async () => {
    await api.logout();
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, loading, login, register, logout, refresh }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fuera de AuthProvider");
  return ctx;
}
