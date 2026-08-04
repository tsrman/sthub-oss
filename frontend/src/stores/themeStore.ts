import { create } from 'zustand';

type ThemeMode = 'light' | 'dark';

interface ThemeState {
  mode: ThemeMode;
  toggle: () => void;
  init: () => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: 'light',
  toggle: () =>
    set((state) => {
      const next = state.mode === 'light' ? 'dark' : 'light';
      if (typeof window !== 'undefined') {
        localStorage.setItem('st-theme', next);
        document.documentElement.classList.toggle('dark', next === 'dark');
      }
      return { mode: next };
    }),
  init: () => {
    if (typeof window === 'undefined') return;
    const saved = localStorage.getItem('st-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const mode: ThemeMode = saved === 'dark' || (!saved && prefersDark) ? 'dark' : 'light';
    document.documentElement.classList.toggle('dark', mode === 'dark');
    set({ mode });
  },
}));
