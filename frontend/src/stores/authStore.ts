import { create } from 'zustand';
import { User } from '@/lib/types';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  /** Set when SSO succeeded but the backend is unreachable. */
  error: string | null;
  setUser: (user: User | null) => void;
  setAuthenticated: (value: boolean) => void;
  setError: (value: string | null) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  error: null,
  setUser: (user) => set({ user }),
  setAuthenticated: (isAuthenticated) => set({ isAuthenticated }),
  setError: (error) => set({ error }),
}));
