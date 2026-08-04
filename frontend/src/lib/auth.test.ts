import { describe, it, expect, vi, beforeEach } from 'vitest';

// Shared init spy across all mocked Keycloak instances.
// vi.hoisted so the mocks exist when the hoisted vi.mock factory runs.
const { initMock, KeycloakMock } = vi.hoisted(() => {
  const initMock = vi.fn().mockResolvedValue(undefined);
  const KeycloakMock = vi.fn(function KeycloakMock() {
    return {
      init: initMock,
      authenticated: false,
      token: 'tok',
      updateToken: vi.fn().mockResolvedValue(true),
    };
  });
  return { initMock, KeycloakMock };
});

vi.mock('keycloak-js', () => ({ default: KeycloakMock }));
vi.mock('./config', () => ({
  fetchPublicConfig: vi
    .fn()
    .mockResolvedValue({ keycloak: { url: 'u', realm: 'r', client: 'c' } }),
}));

import { initKeycloak, clearStoredKeycloak } from './auth';

describe('initKeycloak (init-once regression guard)', () => {
  beforeEach(() => {
    clearStoredKeycloak();
    initMock.mockClear();
    KeycloakMock.mockClear();
  });

  it('initialises exactly once across repeated sequential calls', async () => {
    await initKeycloak({ onLoad: 'check-sso' });
    await initKeycloak({ onLoad: 'check-sso' });
    await initKeycloak();

    // Regression: previously an unauthenticated stored instance was re-init()ed,
    // which keycloak-js rejects with "can only be initialized once".
    expect(KeycloakMock).toHaveBeenCalledTimes(1);
    expect(initMock).toHaveBeenCalledTimes(1);
  });

  it('forces a fresh instance when force=true (doLogin path)', async () => {
    await initKeycloak({ onLoad: 'check-sso' });
    await initKeycloak({}, true);

    expect(KeycloakMock).toHaveBeenCalledTimes(2);
    expect(initMock).toHaveBeenCalledTimes(2);
  });
});
