'use client';

import { useEffect } from 'react';
import { doLogin } from '@/lib/auth';

export default function LoginPage() {
  useEffect(() => {
    doLogin();
  }, []);
  return <div className="p-8">Redirecting to sign-in…</div>;
}
