import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const { getTokenMock } = vi.hoisted(() => ({ getTokenMock: vi.fn() }));

vi.mock('@/lib/auth', () => ({ getToken: getTokenMock }));

import { useSSELogs } from './useSSELogs';

/** Minimal controllable stand-in for a ReadableStream body. */
class FakeStream {
  private chunks: string[] = [];
  private pending: (() => void) | null = null;
  private closed = false;
  private error: Error | null = null;

  getReader() {
    return {
      read: (): Promise<{ done: boolean; value?: Uint8Array }> => {
        const chunk = this.chunks.shift();
        if (chunk !== undefined) {
          return Promise.resolve({ done: false, value: new TextEncoder().encode(chunk) });
        }
        if (this.error) {
          const err = this.error;
          this.error = null;
          return Promise.reject(err);
        }
        if (this.closed) return Promise.resolve({ done: true });
        return new Promise((resolve) => {
          this.pending = () => resolve(this.getReader().read());
        });
      },
    };
  }

  push(text: string) {
    this.chunks.push(text);
    this.kick();
  }

  close() {
    this.closed = true;
    this.kick();
  }

  fail(err: Error) {
    this.error = err;
    this.kick();
  }

  private kick() {
    const pending = this.pending;
    this.pending = null;
    pending?.();
  }
}

function frame(obj: unknown) {
  return `data: ${JSON.stringify(obj)}\n\n`;
}

async function flush() {
  // Let the hook's promise chain (getToken → fetch → read loop) settle.
  await act(async () => {
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
}

describe('useSSELogs', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let streams: FakeStream[];

  beforeEach(() => {
    streams = [];
    getTokenMock.mockReset().mockResolvedValue('tok');
    fetchMock = vi.fn().mockImplementation(() => {
      const stream = new FakeStream();
      streams.push(stream);
      return Promise.resolve({ ok: true, status: 200, body: stream });
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('parses SSE frames into lines and ignores ping comments', async () => {
    const { result } = renderHook(() => useSSELogs('app1', true));
    await flush();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/streamlits/app1/logs');
    expect(url).not.toContain('token=');
    expect(init.headers.Authorization).toBe('Bearer tok');

    await act(async () => {
      streams[0].push(
        ':ping\n\n' +
          frame({ time: 't1', level: 'info', src: 'app', msg: 'one' }) +
          frame({ time: 't2', level: 'error', src: 'app', msg: 'two' })
      );
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });

    expect(result.current.connected).toBe(true);
    expect(result.current.lines).toEqual([
      { time: 't1', level: 'info', src: 'app', msg: 'one' },
      { time: 't2', level: 'error', src: 'app', msg: 'two' },
    ]);
  });

  it('reconnects with a fresh token after the stream breaks', async () => {
    vi.useFakeTimers();
    getTokenMock.mockResolvedValueOnce('tok1').mockResolvedValueOnce('tok2');

    const { result } = renderHook(() => useSSELogs('app1', true));
    await flush();
    expect(result.current.connected).toBe(true);

    await act(async () => {
      streams[0].fail(new Error('connection reset'));
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(result.current.connected).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Reconnect is scheduled with a delay, not immediately.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2999);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getTokenMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe('Bearer tok2');

    await act(async () => {
      streams[1].push(frame({ time: 't3', level: 'info', src: 'app', msg: 'after' }));
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });
    expect(result.current.connected).toBe(true);
    expect(result.current.lines.map((l) => l.msg)).toEqual(['after']);
  });

  it('keeps only the last 2000 lines', async () => {
    const { result } = renderHook(() => useSSELogs('app1', true));
    await flush();

    const bulk = Array.from({ length: 2005 }, (_, i) =>
      frame({ time: 't', level: 'info', src: 'app', msg: `m${i}` })
    ).join('');
    await act(async () => {
      streams[0].push(bulk);
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });

    expect(result.current.lines).toHaveLength(2000);
    expect(result.current.lines[0].msg).toBe('m5');
    expect(result.current.lines[1999].msg).toBe('m2004');
  });

  it('aborts and does not reconnect after unmount', async () => {
    vi.useFakeTimers();
    const { unmount } = renderHook(() => useSSELogs('app1', true));
    await flush();
    const signal = fetchMock.mock.calls[0][1].signal as AbortSignal;

    await act(async () => {
      streams[0].fail(new Error('connection reset'));
      for (let i = 0; i < 5; i++) await Promise.resolve();
    });

    unmount();
    expect(signal.aborted).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
