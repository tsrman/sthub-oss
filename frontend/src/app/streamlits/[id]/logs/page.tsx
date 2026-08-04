'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { useStreamlitId } from '@/hooks/useStreamlitId';
import { useSSELogs } from '@/hooks/useSSELogs';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/registry/StatusBadge';
import * as api from '@/lib/api-methods';
import { StreamlitDetail } from '@/lib/types';

const levels = ['debug', 'info', 'warning', 'error'];

function levelClass(level: string) {
  switch (level.toLowerCase()) {
    case 'error':
      return 'text-[var(--err-fg)]';
    case 'warning':
      return 'text-[var(--warn-fg)]';
    case 'info':
      return 'text-[var(--ok-fg)]';
    default:
      return 'text-[var(--logs-muted)]';
  }
}

export default function LogsPage() {
  useAuth();
  const id = useStreamlitId();
  const [enabled, setEnabled] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [search, setSearch] = useState('');
  const [activeLevels, setActiveLevels] = useState<Set<string>>(new Set(levels));
  const [app, setApp] = useState<StreamlitDetail | null>(null);
  const { lines, setLines, connected } = useSSELogs(id, enabled);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getApp(id).then(setApp).catch(() => setApp(null));
  }, [id]);

  const appUrl = app?.public_url || app?.url;

  useEffect(() => {
    if (enabled && autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, enabled, autoScroll]);

  function toggleLevel(level: string) {
    setActiveLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  }

  function clearLines() {
    setLines([]);
  }

  const filtered = lines.filter(
    (l) =>
      activeLevels.has(l.level.toLowerCase()) &&
      (!search || l.msg.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="min-h-screen flex flex-col bg-[var(--logs-bg)] text-[var(--logs-fg)]">
      <header className="h-14 flex items-center gap-4 px-6 border-b border-[var(--logs-border)] sticky top-0 z-50 bg-[var(--logs-header)]">
        <Link href="/streamlits" className="text-sm text-[var(--logs-muted)] hover:text-[var(--logs-fg)]">
          ← Registry
        </Link>
        <div className="w-px h-5 bg-[var(--logs-input-border)]" />
        <span className="font-bold text-sm text-[var(--logs-fg)]">{app?.name || 'App logs'}</span>
        {app && <StatusBadge status={app.status} />}
        {appUrl && (
          <span className="font-mono text-xs text-[var(--logs-muted)] truncate max-w-[280px]" title={appUrl}>
            {appUrl}
          </span>
        )}
        <div className="flex-1" />
        <Link href={`/streamlits/${id}/editor`}>
          <Button
            variant="secondary"
            className="h-8 text-xs bg-[var(--logs-surface)] border-[var(--logs-input-border)] text-[var(--logs-fg)]"
          >
            Editor
          </Button>
        </Link>
      </header>

      <div className="flex items-center gap-3 px-6 py-3 border-b border-[var(--logs-border)] bg-[var(--logs-toolbar)]">
        <div className="flex gap-1 bg-[var(--logs-chip-group)] p-1 rounded-lg">
          {levels.map((level) => (
            <button
              key={level}
              onClick={() => toggleLevel(level)}
              className={`text-xs px-2.5 py-1 rounded-md font-semibold ${
                activeLevels.has(level)
                  ? 'bg-[var(--logs-surface)] text-[var(--logs-fg)]'
                  : 'bg-transparent text-[var(--logs-muted)]'
              }`}
            >
              {level}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter lines…"
          className="h-8 px-3 rounded border border-[var(--logs-input-border)] bg-[var(--logs-surface)] text-sm outline-none w-60 text-[var(--logs-fg)] placeholder:text-[var(--logs-muted)]"
        />
        <div className="flex-1" />
        <Button
          variant="secondary"
          onClick={() => setAutoScroll((v) => !v)}
          data-testid="follow-toggle"
          className={`h-8 text-xs bg-[var(--logs-surface)] ${
            autoScroll
              ? 'border-[var(--accent)] text-[var(--accent)]'
              : 'border-[var(--logs-input-border)] text-[var(--logs-muted)]'
          }`}
        >
          ⤓ Follow
        </Button>
        <Button
          variant="secondary"
          onClick={() => setEnabled((v) => !v)}
          data-testid="pause-toggle"
          className="h-8 text-xs bg-[var(--logs-surface)] border-[var(--logs-input-border)] text-[var(--logs-fg)]"
        >
          {enabled ? '⏸ Pause' : '▶ Resume'}
        </Button>
        <Button
          variant="secondary"
          onClick={clearLines}
          data-testid="clear-logs-button"
          className="h-8 text-xs bg-[var(--logs-surface)] border-[var(--logs-input-border)] text-[var(--logs-fg)]"
        >
          Clear
        </Button>
        <div className={`text-xs ${connected ? 'text-[var(--ok-fg)]' : 'text-[var(--err-fg)]'}`}>
          {connected ? '● live' : '○ offline'}
        </div>
      </div>

      <div className="flex-1 overflow-auto font-mono text-xs p-4" data-testid="log-lines">
        {filtered.map((line, i) => (
          <div
            key={i}
            data-testid="log-line"
            className="flex gap-4 py-0.5 border-b border-[var(--logs-line)]"
          >
            <span className="w-28 flex-none text-[var(--logs-muted)]">{line.time}</span>
            <span className={`w-16 flex-none uppercase ${levelClass(line.level)}`}>{line.level}</span>
            <span className="w-24 flex-none text-[var(--logs-muted)]">{line.src}</span>
            <span className="whitespace-pre-wrap break-all">{line.msg}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
