import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { formatRelativeTime } from './time';

const NOW = new Date('2026-06-28T12:00:00Z').getTime();

function ago(ms: number): string {
  return new Date(NOW - ms).toISOString();
}

const SEC = 1000;
const MIN = 60 * SEC;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

describe('formatRelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns "just now" for very recent times', () => {
    expect(formatRelativeTime(ago(5 * SEC))).toBe('just now');
  });

  it('formats minutes', () => {
    expect(formatRelativeTime(ago(1 * MIN))).toBe('1 minute ago');
    expect(formatRelativeTime(ago(3 * MIN))).toBe('3 minutes ago');
    expect(formatRelativeTime(ago(11 * MIN))).toBe('11 minutes ago');
  });

  it('formats hours', () => {
    expect(formatRelativeTime(ago(1 * HOUR))).toBe('1 hour ago');
    expect(formatRelativeTime(ago(2 * HOUR))).toBe('2 hours ago');
    expect(formatRelativeTime(ago(5 * HOUR))).toBe('5 hours ago');
  });

  it('formats days, using the idiomatic form for one day', () => {
    expect(formatRelativeTime(ago(1 * DAY))).toBe('yesterday');
    expect(formatRelativeTime(ago(3 * DAY))).toBe('3 days ago');
  });

  it('formats weeks, using the idiomatic form for one week', () => {
    expect(formatRelativeTime(ago(7 * DAY))).toBe('last week');
    expect(formatRelativeTime(ago(21 * DAY))).toBe('3 weeks ago');
  });

  it('falls back to an absolute date past a month', () => {
    const out = formatRelativeTime(ago(60 * DAY));
    expect(out).toMatch(/\d{2}\/\d{2}\/\d{4}/);
  });

  it('returns the input verbatim for invalid dates', () => {
    expect(formatRelativeTime('not-a-date')).toBe('not-a-date');
  });
});
