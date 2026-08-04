// Relative-time formatting for registry/history timestamps.
// Returns strings like "2 hours ago", "yesterday", "3 days ago".

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;

  const diffMs = Date.now() - then.getTime();
  const sec = Math.floor(diffMs / 1000);
  if (sec < 45) return 'just now';

  const min = Math.floor(sec / 60);
  if (min < 60) return relative.format(-min, 'minute');

  const hours = Math.floor(min / 60);
  if (hours < 24) return relative.format(-hours, 'hour');

  const days = Math.floor(hours / 24);
  if (days < 7) return relative.format(-days, 'day');

  const weeks = Math.floor(days / 7);
  if (weeks < 4) return relative.format(-weeks, 'week');

  return then.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
