'use client';

import { TopBar } from './TopBar';
import { Sidebar } from './Sidebar';
import { useAuthStore } from '@/stores/authStore';

export function AppLayout({ children }: { children: React.ReactNode }) {
  const authError = useAuthStore((state) => state.error);

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <main className="flex-1 p-7 overflow-auto">
          {authError && (
            <div className="mb-5 text-sm text-[var(--err-fg)] border border-[var(--err-fg)] rounded-lg px-4 py-3 bg-[var(--surface)]">
              {authError}
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
