'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { initKeycloak, getToken } from '@/lib/auth';
import { setAuthToken } from '@/lib/api';
import * as api from '@/lib/api-methods';
import { useAuthStore } from '@/stores/authStore';

const SSO_TIMEOUT_MS = 2500;

export function useAuth(requireAuth = true) {
  const router = useRouter();
  const { user, isAuthenticated, error, setUser, setAuthenticated, setError } = useAuthStore();

  useEffect(() => {
    if (typeof window === 'undefined') return;
    Promise.race([
      initKeycloak({ onLoad: 'check-sso' }),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('sso timeout')), SSO_TIMEOUT_MS)
      ),
    ])
      .then(async (kc) => {
        if (!kc.authenticated) {
          if (requireAuth) router.push('/login');
          return;
        }
        const token = await getToken();
        setAuthToken(token);
        try {
          const me = await api.me();
          setUser(me);
          setAuthenticated(true);
          setError(null);
        } catch {
          // SSO is valid but the backend is unreachable. Keep the Keycloak
          // session and surface an error — bouncing to /login would just
          // loop back here through SSO.
          setError('The service is temporarily unavailable. Try reloading the page later.');
        }
      })
      .catch(() => {
        // Keycloak init itself failed (including the silent check-sso
        // timeout). Do NOT clear the stored instance — the init may still
        // complete in the background.
        if (requireAuth) router.push('/login');
      });
  }, [requireAuth, router, setUser, setAuthenticated, setError]);

  return { user, isAuthenticated, error };
}
