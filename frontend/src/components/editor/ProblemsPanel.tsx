import { LintError } from '@/lib/types';

interface Props {
  problems: LintError[];
}

export function ProblemsPanel({ problems }: Props) {
  const errors = problems.filter((p) => p.severity === 'error');
  const warnings = problems.filter((p) => p.severity === 'warning');

  return (
    <div className="h-44 flex-none border-t border-[var(--border)] bg-[var(--surface)] flex flex-col">
      <div className="h-10 flex items-center gap-3 px-4 border-b border-[var(--border-soft)]">
        <span className="text-xs font-bold">Problems</span>
        {errors.length > 0 && <span className="text-xs text-[var(--err-fg)]">● {errors.length}</span>}
        {warnings.length > 0 && (
          <span className="text-xs text-[var(--warn-fg)]">● {warnings.length}</span>
        )}
        {problems.length === 0 && <span className="text-xs text-[var(--ok-fg)]">✓ Syntax is valid</span>}
      </div>
      <div className="flex-1 overflow-auto py-1">
        {problems.map((p, i) => (
          <div key={i} className="flex items-start gap-3 px-4 py-1.5 text-sm text-[var(--text-2)]">
            <span className={p.severity === 'error' ? 'text-[var(--err-fg)]' : 'text-[var(--warn-fg)]'}>
              {p.severity === 'error' ? '✕' : '⚠'}
            </span>
            <span className="flex-1">{p.message}</span>
            <span className="font-mono text-xs text-[var(--muted)]">line {p.line}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
