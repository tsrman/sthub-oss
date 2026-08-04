import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';

import { AiChatMessage } from './types';

const { getTokenMock, clearStoredKeycloakMock, setAuthTokenMock } = vi.hoisted(() => ({
  getTokenMock: vi.fn(),
  clearStoredKeycloakMock: vi.fn(),
  setAuthTokenMock: vi.fn(),
}));

vi.mock('./auth', () => ({
  getToken: getTokenMock,
  clearStoredKeycloak: clearStoredKeycloakMock,
}));
vi.mock('./api', () => ({ default: {}, setAuthToken: setAuthTokenMock }));

import { streamAiChat } from './ai';

function streamResponse(chunks: string[]) {
  const encoded = chunks.map((c) => new TextEncoder().encode(c));
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => {
        let i = 0;
        return {
          read: () =>
            i < encoded.length
              ? Promise.resolve({ done: false, value: encoded[i++] })
              : Promise.resolve({ done: true }),
        };
      },
    },
  };
}

function errorResponse(status: number, body: unknown) {
  return {
    ok: false,
    status,
    body: null,
    json: () => Promise.resolve(body),
  };
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

const messages: AiChatMessage[] = [{ role: 'user', content: 'hi' }];

describe('streamAiChat', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let onDelta: Mock<(text: string) => void>;
  let onDone: Mock<() => void>;
  let onError: Mock<(message: string) => void>;

  beforeEach(() => {
    getTokenMock.mockReset().mockResolvedValue('tok');
    clearStoredKeycloakMock.mockReset();
    setAuthTokenMock.mockReset();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    onDelta = vi.fn<(text: string) => void>();
    onDone = vi.fn<() => void>();
    onError = vi.fn<(message: string) => void>();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function start(controller = new AbortController()) {
    streamAiChat(messages, null, { onDelta, onDone, onError }, controller);
    return controller;
  }

  it('streams deltas and calls onDone exactly once on a done frame', async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        'data: {"type":"delta","text":"he"}\n\ndata: {"type":"delta","text":"llo"}\n\n',
        'data: {"type":"done"}\n\n',
      ])
    );
    start();
    await flush();

    expect(onDelta.mock.calls).toEqual([['he'], ['llo']]);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/ai/chat');
    expect(init.headers.Authorization).toBe('Bearer tok');
  });

  it('an error frame triggers only onError, never onDone', async () => {
    fetchMock.mockResolvedValue(streamResponse(['data: {"type":"error","message":"the model crashed"}\n\n']));
    start();
    await flush();

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith('the model crashed');
    expect(onDone).not.toHaveBeenCalled();
  });

  it('a stream ending without a done frame is reported as a broken connection', async () => {
    fetchMock.mockResolvedValue(streamResponse(['data: {"type":"delta","text":"x"}\n\n']));
    start();
    await flush();

    expect(onDone).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith('Connection to the assistant was interrupted');
  });

  it('surfaces the FastAPI detail string on HTTP errors', async () => {
    fetchMock.mockResolvedValue(errorResponse(422, { detail: 'too many messages' }));
    start();
    await flush();

    expect(onError).toHaveBeenCalledWith('too many messages');
    expect(onDone).not.toHaveBeenCalled();
  });

  it('surfaces detail.message when detail is an object', async () => {
    fetchMock.mockResolvedValue(errorResponse(429, { detail: { message: 'limit exceeded' } }));
    start();
    await flush();

    expect(onError).toHaveBeenCalledWith('limit exceeded');
  });

  it('falls back to a generic message on a non-JSON error body', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 502,
      body: null,
      json: () => Promise.reject(new Error('not json')),
    });
    start();
    await flush();

    expect(onError).toHaveBeenCalledWith('Could not reach the assistant');
  });

  it('on 401 clears the Keycloak instance like the axios interceptor', async () => {
    fetchMock.mockResolvedValue(errorResponse(401, { detail: 'unauthorized' }));
    start();
    await flush();

    expect(clearStoredKeycloakMock).toHaveBeenCalledTimes(1);
    expect(setAuthTokenMock).toHaveBeenCalledWith(null);
    expect(onError).toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('stays silent after the caller aborts', async () => {
    fetchMock.mockImplementation(
      (_url: string, init: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          init.signal.addEventListener('abort', () =>
            reject(new DOMException('The operation was aborted.', 'AbortError'))
          );
        })
    );
    const controller = start();
    controller.abort();
    await flush();

    expect(onDone).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });
});
