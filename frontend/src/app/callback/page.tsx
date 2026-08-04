'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { initKeycloak, getToken } from '@/lib/auth';
import { setAuthToken } from '@/lib/api';

export default function CallbackPage() {
  const router = useRouter();
  useEffect(() => {
    initKeycloak({}, true)
      .then(async (kc) => {
        if (!kc.authenticated) {
          router.push('/login');
          return;
        }
        const token = await getToken();
        setAuthToken(token);
        router.push('/streamlits');
      })
      .catch(() => {
        router.push('/login');
      });
  }, [router]);
  return <div className="p-8">Completing sign-in…</div>;
}
