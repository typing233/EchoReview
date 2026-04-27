import { create } from "zustand";

export interface User {
  id: number;
  username: string;
  email?: string;
  display_name?: string;
  avatar_url?: string;
  created_at: string;
  platforms: string[];
}

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  setAuth: (user: User, token: string) => void;
  clearAuth: () => void;
  initFromStorage: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isLoading: true,
  setAuth: (user, token) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("access_token", token);
      localStorage.setItem("user", JSON.stringify(user));
    }
    set({ user, token, isLoading: false });
  },
  clearAuth: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
    }
    set({ user: null, token: null, isLoading: false });
  },
  initFromStorage: () => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("access_token");
      const userStr = localStorage.getItem("user");
      if (token && userStr) {
        try {
          const user = JSON.parse(userStr);
          set({ user, token, isLoading: false });
          return;
        } catch {}
      }
    }
    set({ isLoading: false });
  },
}));
