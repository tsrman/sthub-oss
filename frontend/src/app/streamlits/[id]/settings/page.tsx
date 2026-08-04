'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/Button';
import { useAuth } from '@/hooks/useAuth';
import { useStreamlitId } from '@/hooks/useStreamlitId';
import { useAuthStore } from '@/stores/authStore';
import * as api from '@/lib/api-methods';

function normalizeSlug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '');
}

export default function SettingsPage() {
  useAuth();
  const router = useRouter();
  const { user } = useAuthStore();
  const id = useStreamlitId();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [slug, setSlug] = useState('');
  const [slugStatus, setSlugStatus] = useState<'free' | 'taken' | 'idle'>('idle');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getApp(id).then((app) => {
      setName(app.name);
      setDescription(app.description || '');
      setSlug(app.slug);
      setLoading(false);
    });
  }, [id]);

  async function checkSlug(value: string) {
    const s = normalizeSlug(value);
    setSlug(s);
    if (!s) {
      setSlugStatus('idle');
      return;
    }
    try {
      const res = await api.checkSlug(s, id);
      setSlugStatus(res.available ? 'free' : 'taken');
    } catch {
      setSlugStatus('idle');
    }
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (slugStatus === 'taken') return;
    setSubmitting(true);
    setError(null);
    try {
      await api.updateApp(id, { name, slug, description });
      router.push('/streamlits');
    } catch (e) {
      setError(api.getApiErrorMessage(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="p-8">Loading…</div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="max-w-3xl mx-auto">
        <button
          onClick={() => router.push('/streamlits')}
          className="text-sm text-[var(--text-3)] mb-4"
        >
          ← To registry
        </button>
        <h1 className="text-2xl font-extrabold tracking-tight">App settings</h1>
        {error && (
          <div
            data-testid="settings-error"
            className="mt-5 text-sm text-[var(--err-fg)] border border-[var(--err-fg)] rounded-lg px-4 py-3 bg-[var(--surface)]"
          >
            {error}
          </div>
        )}
        <form onSubmit={onSubmit} className="flex flex-col gap-5 mt-6">
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="text-xs font-bold uppercase tracking-wider text-[var(--muted)] mb-3">
              General
            </div>
            <label className="block text-xs font-semibold text-[var(--text-2)] mb-1.5">
              Name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              data-testid="settings-name-input"
              className="w-full h-10 px-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm outline-none mb-4"
            />
            <label className="block text-xs font-semibold text-[var(--text-2)] mb-1.5">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full h-16 px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm outline-none resize-y"
            />
          </div>
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5">
            <div className="text-xs font-bold uppercase tracking-wider text-[var(--muted)] mb-3">
              Route
            </div>
            <div className="flex border border-[var(--border)] rounded-lg overflow-hidden font-mono text-sm">
              <span className="flex items-center px-3 bg-[var(--surface-2)] text-[var(--muted)] border-r border-[var(--border)]">
                /st/{user?.login || 'me'}/
              </span>
              <input
                value={slug}
                onChange={(e) => checkSlug(e.target.value)}
                placeholder="my-app"
                required
                className="flex-1 h-10 px-3 outline-none bg-[var(--surface)] text-[var(--text)]"
              />
            </div>
            <div
              className={`mt-2 text-xs ${
                slugStatus === 'taken'
                  ? 'text-[var(--err-fg)]'
                  : slugStatus === 'free'
                  ? 'text-[var(--ok-fg)]'
                  : 'text-[var(--muted)]'
              }`}
            >
              {slugStatus === 'taken'
                ? '✕ Address taken'
                : slugStatus === 'free'
                ? '✓ Address available'
                : 'The address is checked as you type'}
            </div>
          </div>
          <div className="flex justify-end gap-3">
            <Button type="button" variant="secondary" onClick={() => router.push('/streamlits')}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              Save
            </Button>
          </div>
        </form>
      </div>
    </AppLayout>
  );
}
