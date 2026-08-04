import { useEffect, useState } from 'react';
import { getToken } from '@/lib/auth';

export interface LogLine {
  time: string;
  level: string;
  src: string;
  msg: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';
const MAX_LINES = 2000;
const RECONNECT_DELAY_MS = 3000;

/**
 * Stream app logs from the SSE endpoint.
 *
 * Uses `fetch` (not `EventSource`) so the JWT travels in the Authorization
 * header instead of the `?token=` query string, where it would end up in
 * access logs. Reconnects with a fresh token after errors while `enabled`.
 */
export function useSSELogs(appId: string, enabled: boolean) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let controller: AbortController | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    function appendLine(line: LogLine) {
      setLines((prev) =>
        prev.length >= MAX_LINES ? [...prev.slice(prev.length - MAX_LINES + 1), line] : [...prev, line]
      );
    }

    async function connect() {
      // Fresh token on every (re)connect — the previous one may have expired.
      let token = '';
      try {
        token = await getToken();
      } catch {
        // Token refresh failed — try the request anyway, the reconnect
        // loop below will keep retrying while the page is open.
      }
      if (cancelled) return;

      controller = new AbortController();
      try {
        const res = await fetch(`${API_BASE}/streamlits/${appId}/logs`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          throw new Error(`Log stream request failed: ${res.status}`);
        }
        setConnected(true);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by a blank line.
          let sep: number;
          while ((sep = buffer.indexOf('\n\n')) !== -1) {
            const frame = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            const dataLine = frame.split('\n').find((l) => l.startsWith('data:'));
            if (!dataLine) continue; // ':ping' keep-alives and other comments
            try {
              appendLine(JSON.parse(dataLine.slice(5).trim()));
            } catch {
              // Ignore malformed lines.
            }
          }
        }
      } catch (err) {
        if (cancelled || (err as Error)?.name === 'AbortError') return;
      }
      if (cancelled) return;

      // Stream ended or broke — reconnect after a delay.
      setConnected(false);
      reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
    }

    connect();

    return () => {
      cancelled = true;
      setConnected(false);
      controller?.abort();
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, [appId, enabled]);

  return { lines, setLines, connected };
}
