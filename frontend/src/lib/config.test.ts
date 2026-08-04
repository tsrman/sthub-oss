import { describe, it, expect, vi, afterEach } from 'vitest';

async function loadModule() {
  // Module-level cache — re-import fresh for every test.
  vi.resetModules();
  return await import('./config');
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchPublicConfig', () => {
  it('retries after a failed fetch instead of caching the rejected promise', async () => {
    const payload = { keycloak: { url: 'u', realm: 'r', client: 'c' } };
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    vi.stubGlobal('fetch', fetchMock);

    const { fetchPublicConfig } = await loadModule();

    await expect(fetchPublicConfig()).rejects.toThrow('network down');
    await expect(fetchPublicConfig()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('serves subsequent calls from cache after a success', async () => {
    const payload = { keycloak: { url: 'u', realm: 'r', client: 'c' } };
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: () => Promise.resolve(payload) });
    vi.stubGlobal('fetch', fetchMock);

    const { fetchPublicConfig } = await loadModule();

    await expect(fetchPublicConfig()).resolves.toEqual(payload);
    await expect(fetchPublicConfig()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
