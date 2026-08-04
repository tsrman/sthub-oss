import { AppStatus } from '@/lib/types';

const meta: Record<
  AppStatus,
  { label: string; bg: string; color: string; dot: string; anim?: string }
> = {
  running: {
    label: 'Running',
    bg: 'bg-[var(--ok-bg)]',
    color: 'text-[var(--ok-fg)]',
    dot: 'var(--status-running-dot)',
  },
  stopped: {
    label: 'Stopped',
    bg: 'bg-[var(--surface-3)]',
    color: 'text-[var(--text-2)]',
    dot: 'var(--status-stopped-dot)',
  },
  building: {
    label: 'Building',
    bg: 'bg-[var(--warn-bg)]',
    color: 'text-[var(--warn-fg)]',
    dot: 'var(--status-building-dot)',
    anim: 'animate-pulse',
  },
  error: {
    label: 'Error',
    bg: 'bg-[var(--err-bg)]',
    color: 'text-[var(--err-fg)]',
    dot: 'var(--status-error-dot)',
    anim: 'animate-pulse',
  },
};

export function StatusBadge({ status }: { status: AppStatus }) {
  const m = meta[status];
  return (
    <span
      data-testid="status-badge"
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-bold ${m.bg} ${m.color}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${m.anim || ''}`}
        style={{ background: m.dot }}
      />
      {m.label}
    </span>
  );
}
