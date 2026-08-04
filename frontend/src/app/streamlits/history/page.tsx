'use client';

import { useEffect, useMemo, useState } from 'react';
import { AppLayout } from '@/components/layout/AppLayout';
import { useAuth } from '@/hooks/useAuth';
import { listDeployments } from '@/lib/api-methods';
import type { Deployment } from '@/lib/types';

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function eventLabel(kind: string): string {
  const labels: Record<string, string> = {
    run: 'Start',
    stop: 'Stop',
    restart: 'Restart',
    delete: 'Delete',
  };
  return labels[kind] ?? kind;
}

function eventBadge(kind: string): { bg: string; color: string; dot: string } {
  switch (kind) {
    case 'run':
    case 'restart':
      return { bg: 'var(--ok-bg)', color: 'var(--ok-fg)', dot: 'var(--ok-fg)' };
    case 'stop':
      return { bg: 'var(--surface-3)', color: 'var(--text-2)', dot: 'var(--muted)' };
    case 'delete':
      return { bg: 'var(--err-bg)', color: 'var(--err-fg)', dot: 'var(--err-fg)' };
    default:
      return { bg: 'var(--surface-3)', color: 'var(--text-2)', dot: 'var(--muted)' };
  }
}

function resultClass(result: string): string {
  if (result === 'started' || result === 'completed') {
    return 'text-emerald-600';
  }
  if (result === 'failed' || result === 'error') {
    return 'text-red-600';
  }
  return 'text-[var(--muted)]';
}

type FilterKind = 'all' | 'deploy' | 'stop' | 'error';

const filters: { key: FilterKind; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'deploy', label: 'Deployments' },
  { key: 'stop', label: 'Stops' },
  { key: 'error', label: 'Errors' },
];

export default function HistoryPage() {
  useAuth();
  const [events, setEvents] = useState<Deployment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKind>('all');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listDeployments()
      .then((resp) => {
        if (cancelled) return;
        setEvents(resp.items);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    switch (filter) {
      case 'deploy':
        return events.filter((ev) => ev.kind === 'run' || ev.kind === 'restart');
      case 'stop':
        return events.filter((ev) => ev.kind === 'stop');
      case 'error':
        return events.filter((ev) => ev.result === 'failed' || ev.result === 'error');
      default:
        return events;
    }
  }, [events, filter]);

  return (
    <AppLayout>
      <h1 className="text-2xl font-extrabold tracking-tight">Deployment history</h1>
      <p className="mt-1 text-sm text-[var(--text-3)]">{filtered.length} events</p>

      <div className="mt-4 flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition ${
              filter === f.key
                ? 'bg-[var(--accent)] text-[var(--accent-ink)] border-[var(--accent)]'
                : 'bg-[var(--surface)] text-[var(--text-2)] border-[var(--border)] hover:bg-[var(--surface-2)]'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      <div className="mt-5 bg-[var(--surface)] border border-[var(--border)] rounded-xl overflow-hidden">
        <div className="grid grid-cols-[160px_1fr_140px_80px_160px_100px] gap-2 min-w-[820px] px-5 py-3 border-b border-[var(--surface-3)] text-xs uppercase tracking-wider text-[var(--muted)] font-bold">
          <div>Time</div>
          <div>App</div>
          <div>Event</div>
          <div>Version</div>
          <div>Triggered by</div>
          <div>Result</div>
        </div>

        {loading ? (
          <div className="px-5 py-8 text-sm text-[var(--muted)]">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="px-5 py-8 text-sm text-[var(--muted)]">No history yet</div>
        ) : (
          filtered.map((ev) => (
            <div
              key={ev.id}
              className="grid grid-cols-[160px_1fr_140px_80px_160px_100px] gap-2 min-w-[820px] px-5 py-3 border-b border-[var(--surface-2)] items-center text-sm"
            >
              <div className="font-mono text-xs text-[var(--text-3)]">{formatTime(ev.ts)}</div>
              <div className="min-w-0 pr-3">
                <div className="font-semibold text-[var(--text)] truncate">{ev.streamlit_name}</div>
                {ev.streamlit_slug && (
                  <div className="font-mono text-[11px] text-[var(--muted)] truncate">
                    {ev.streamlit_slug}
                  </div>
                )}
              </div>
              <div>
                {(() => {
                  const b = eventBadge(ev.kind);
                  return (
                    <span
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold"
                      style={{ background: b.bg, color: b.color }}
                      data-testid="history-event"
                    >
                      <span
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ background: b.dot }}
                      />
                      {eventLabel(ev.kind)}
                    </span>
                  );
                })()}
              </div>
              <div className="font-mono text-xs text-[var(--text-2)]">{ev.version}</div>
              <div>{ev.actor.display_name || ev.actor.login}</div>
              <div className={resultClass(ev.result)}>{ev.result}</div>
            </div>
          ))
        )}
      </div>
    </AppLayout>
  );
}
