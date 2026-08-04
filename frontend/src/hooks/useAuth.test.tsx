import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const { pushMock, initKeycloakMock, getTokenMock, clearStoredKeycloakMock, meMock } = vi.hoisted(
  () => ({
    pushMock: vi.fn(),
    initKeycloakMock: vi.fn(),
    getTokenMock: vi.fn(),
    clearStoredKeycloakMock: vi.fn(),
    meMock: vi.fn(),
  })
);

vi.mock('next/navigation', () => {
  // A stable router instance — next/navigation's useRouter is referentially
  // stable in production, and useAuth depends on that in its effect deps.
  const router = { push: pushMock };
  return { useRouter: () => router };
});
vi.mock('@/lib/auth', () => ({
  initKeycloak: initKeycloakMock,
  getToken: getTokenMock,
  clearStoredKeycloak: clearStoredKeycloakMock,
}));
vi.mock('@/lib/api', () => ({ default: {}, setAuthToken: vi.fn() }));
vi.mock('@/lib/api-methods', () => ({ me: meMock }));

import { useAuth } from './useAuth';
import { useAuthStore } from '@/stores/authStore';

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: null, isAuthenticated: false, error: null });
    getTokenMock.mockResolvedValue('tok');
  });

  it('redirects to /login when SSO reports an anonymous session', async () => {
    initKeycloakMock.mockResolvedValue({ authenticated: false });
    renderHook(() => useAuth());

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'));
    expect(clearStoredKeycloakMock).not.toHaveBeenCalled();
  });

  it('stores the user on the happy path', async () => {
    initKeycloakMock.mockResolvedValue({ authenticated: true });
    meMock.mockResolvedValue({ login: 'testuser' });
    renderHook(() => useAuth());

    await waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(true));
    expect(pushMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().user?.login).toBe('testuser');
    expect(useAuthStore.getState().error).toBeNull();
  });

  it('does NOT redirect or clear Keycloak when the backend is down', async () => {
    initKeycloakMock.mockResolvedValue({ authenticated: true });
    meMock.mockRejectedValue(new Error('Network Error'));
    renderHook(() => useAuth());

    // Regression: this used to clear the session and bounce to /login,
    // which looped straight back through SSO.
    await waitFor(() => expect(useAuthStore.getState().error).toBeTruthy());
    expect(pushMock).not.toHaveBeenCalled();
    expect(clearStoredKeycloakMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('does NOT clear the stored Keycloak instance on a silent-sso failure', async () => {
    initKeycloakMock.mockRejectedValue(new Error('sso timeout'));
    renderHook(() => useAuth());

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'));
    expect(clearStoredKeycloakMock).not.toHaveBeenCalled();
  });
});
