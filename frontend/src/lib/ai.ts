import { clearStoredKeycloak, getToken } from './auth';
import { setAuthToken } from './api';
import { AiChatMessage, AiFileContext } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

export interface AiStreamHandlers {
  onDelta: (text: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

/** Extract a human-readable message from a FastAPI error response. */
async function readErrorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    const detail = data?.detail ?? data?.error?.message;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
      return detail.message;
    }
  } catch {
    // Not a JSON body — fall through to the generic message.
  }
  return 'Could not reach the assistant';
}

function handleUnauthorized() {
  // Same flow as the axios response interceptor: drop the stale Keycloak
  // instance and bounce to login, unless we are already there.
  clearStoredKeycloak();
  setAuthToken(null);
  if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
    window.location.href = '/login';
  }
}

/**
 * POST a chat request and stream the assistant reply over SSE.
 *
 * Uses `fetch` (not `EventSource`) because the request carries a body and the
 * JWT travels in the `Authorization` header. The caller owns the
 * `AbortController`, so it can cancel the request at any point — including
 * the token-refresh window before `fetch` starts.
 */
export function streamAiChat(
  messages: AiChatMessage[],
  context: AiFileContext | null,
  handlers: AiStreamHandlers,
  controller: AbortController
): void {
  (async () => {
    try {
      const token = await getToken();
      const res = await fetch(`${API_BASE}/ai/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ messages, context }),
        signal: controller.signal,
      });

      if (res.status === 401) {
        handleUnauthorized();
        handlers.onError('Your session has expired. Sign in again.');
        return;
      }
      if (!res.ok || !res.body) {
        handlers.onError(await readErrorMessage(res));
        return;
      }

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
          const line = frame.split('\n').find((l) => l.startsWith('data:'));
          if (!line) continue;
          try {
            const evt = JSON.parse(line.slice(5).trim());
            if (evt.type === 'delta') {
              handlers.onDelta(evt.text);
            } else if (evt.type === 'done') {
              handlers.onDone();
              return;
            } else if (evt.type === 'error') {
              handlers.onError(evt.message || 'Error');
              return;
            }
          } catch {
            // Ignore malformed frames.
          }
        }
      }
      // The stream ended without a terminal frame — the connection broke.
      handlers.onError('Connection to the assistant was interrupted');
    } catch (err) {
      if (controller.signal.aborted || (err as Error)?.name === 'AbortError') return;
      handlers.onError('Connection to the assistant was interrupted');
    }
  })();
}
