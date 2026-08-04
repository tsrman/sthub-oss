'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { StreamlitApp } from '@/lib/types';
import { useAuthStore } from '@/stores/authStore';
import { formatRelativeTime } from '@/lib/time';
import { StatusBadge } from './StatusBadge';
import { Button } from '@/components/ui/Button';

interface Props {
  app: StreamlitApp;
  onRun: () => void;
  onStop: () => void;
  onRestart: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
}

export function AppCard({ app, onRun, onStop, onRestart, onDelete, onDuplicate }: Props) {
  const currentUser = useAuthStore((state) => state.user);
  const showOwner = currentUser?.is_admin && app.owner.login !== currentUser.login;
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onClick(e: MouseEvent) {
      if (!menuRef.current?.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [menuOpen]);

  return (
    <div
      data-testid="app-card"
      className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-4 flex flex-col shadow-sm"
    >
      <StatusBadge status={app.status} />
      <div className="mt-3 font-bold text-[15px] leading-tight">{app.name}</div>
      <a
        href={app.public_url || app.url}
        target="_blank"
        rel="noreferrer"
        className="mt-1.5 text-xs font-mono text-[var(--text)] hover:underline truncate flex items-center gap-1"
      >
        ↗ {app.public_url || app.url}
      </a>
      {app.description && (
        <p className="mt-2 text-xs text-[var(--text-3)] leading-relaxed line-clamp-2">
          {app.description}
        </p>
      )}
      <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--muted)] flex-wrap">
        {showOwner && (
          <>
            <span>{app.owner.display_name || app.owner.login}</span>
            <span className="text-[var(--border)]">·</span>
          </>
        )}
        <span>{formatRelativeTime(app.updated_at)}</span>
      </div>
      <div className="mt-auto pt-3 flex items-center gap-2 border-t border-[var(--border-soft)]">
        {app.status === 'stopped' && (
          <Button variant="primary" onClick={onRun} className="h-8 text-xs" data-testid="run-button">
            ▶ Start
          </Button>
        )}
        {app.status === 'running' && (
          <>
            <Button
              variant="secondary"
              onClick={onStop}
              className="h-8 text-xs"
              data-testid="stop-button"
            >
              ⏹ Stop
            </Button>
            <Button
              variant="secondary"
              onClick={onRestart}
              className="h-8 w-8 p-0"
              title="Restart"
              data-testid="restart-button"
            >
              ↻
            </Button>
          </>
        )}
        {app.status === 'error' && (
          <Button
            variant="primary"
            onClick={onRestart}
            className="h-8 text-xs"
            data-testid="restart-button"
          >
            ↻ Restart
          </Button>
        )}
        {app.status === 'building' && (
          <div className="h-8 px-3 rounded-lg bg-[var(--warn-bg)] text-[var(--warn-fg)] text-xs font-bold flex items-center">
            ⟳ Building…
          </div>
        )}
        <div className="flex-1" />
        <Link href={`/streamlits/${app.id}/editor`}>
          <Button variant="secondary" className="h-8 text-xs">
            Editor
          </Button>
        </Link>
        <div className="relative" ref={menuRef}>
          <Button
            variant="secondary"
            onClick={() => setMenuOpen((v) => !v)}
            className="h-8 w-8 p-0"
            title="More"
            data-testid="card-menu-button"
          >
            …
          </Button>
          {menuOpen && (
            <div className="absolute right-0 bottom-full mb-1 w-44 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-lg py-1 z-10">
              <Link
                href={`/streamlits/${app.id}/logs`}
                className="block px-4 py-2 text-sm text-[var(--text-2)] hover:bg-[var(--surface-2)]"
                onClick={() => setMenuOpen(false)}
                data-testid="menu-logs"
              >
                Logs
              </Link>
              <Link
                href={`/streamlits/${app.id}/settings`}
                className="block px-4 py-2 text-sm text-[var(--text-2)] hover:bg-[var(--surface-2)]"
                onClick={() => setMenuOpen(false)}
                data-testid="menu-settings"
              >
                Settings and URL
              </Link>
              <button
                onClick={() => {
                  setMenuOpen(false);
                  onDuplicate();
                }}
                className="block w-full text-left px-4 py-2 text-sm text-[var(--text-2)] hover:bg-[var(--surface-2)]"
                data-testid="menu-duplicate"
              >
                Duplicate
              </button>
              <div className="h-px bg-[var(--border-soft)] my-1 mx-1.5" />
              <button
                onClick={() => {
                  setMenuOpen(false);
                  onDelete();
                }}
                className="block w-full text-left px-4 py-2 text-sm text-[var(--err-fg)] hover:bg-[var(--surface-2)]"
                data-testid="menu-delete"
              >
                Delete
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
