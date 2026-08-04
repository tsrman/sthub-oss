'use client';

import { useEffect } from 'react';
import { useThemeStore } from '@/stores/themeStore';

export function useTheme() {
  const store = useThemeStore();
  useEffect(() => {
    store.init();
  }, [store]);
  return store;
}
