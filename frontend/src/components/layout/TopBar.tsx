'use client';

import Link from 'next/link';
import { useThemeStore } from '@/stores/themeStore';
import { useAuthStore } from '@/stores/authStore';

export function TopBar() {
  const { mode, toggle } = useThemeStore();
  const { user } = useAuthStore();

  const initials =
    user?.display_name
      .split(' ')
      .map((n) => n[0])
      .filter(Boolean)
      .slice(0, 2)
      .join('') || '??';

  return (
    <header className="h-14 flex items-center gap-4 px-6 bg-[var(--surface)] border-b border-[var(--border)] sticky top-0 z-50">
      <Link href="/streamlits" className="flex items-center gap-2.5 font-extrabold text-sm tracking-wider">
        <svg width="22" height="22" viewBox="0 0 48 48" className="flex-none" aria-hidden="true">
          <g fill="#FFB635">
            <rect x="20" y="3" width="8" height="16" rx="3" transform="rotate(0 24 24)" />
            <rect x="20" y="3" width="8" height="16" rx="3" transform="rotate(72 24 24)" />
            <rect x="20" y="3" width="8" height="16" rx="3" transform="rotate(144 24 24)" />
            <rect x="20" y="3" width="8" height="16" rx="3" transform="rotate(216 24 24)" />
            <rect x="20" y="3" width="8" height="16" rx="3" transform="rotate(288 24 24)" />
          </g>
        </svg>
        STHub
      </Link>
      <div className="flex-1" />
      <button
        onClick={toggle}
        className="w-9 h-9 rounded-lg border border-[var(--border)] flex items-center justify-center text-[var(--text-2)]"
        title="Toggle theme"
      >
        {mode === 'dark' ? '☀' : '☾'}
      </button>
      {user && (
        <div className="flex items-center gap-3">
          <div className="text-right leading-tight">
            <div className="text-sm font-semibold">{user.display_name}</div>
            <div className="text-xs text-[var(--text-3)]">
              Group: {user.group}
              {user.is_admin && (
                <span className="ml-2 px-1.5 py-0.5 rounded bg-red-100 text-red-700 font-bold">
                  ADMIN
                </span>
              )}
            </div>
          </div>
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#FFD27A] to-[#FFB635] text-[var(--accent-ink)] flex items-center justify-center text-xs font-bold">
            {initials}
          </div>
        </div>
      )}
    </header>
  );
}
