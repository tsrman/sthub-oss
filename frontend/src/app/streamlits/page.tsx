'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { AppLayout } from '@/components/layout/AppLayout';
import { AppCard } from '@/components/registry/AppCard';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useAuthStore } from '@/stores/authStore';
import * as api from '@/lib/api-methods';
import { StreamlitApp } from '@/lib/types';

const chips = [
  { key: 'all', label: 'All' },
  { key: 'running', label: 'Running' },
  { key: 'stopped', label: 'Stopped' },
  { key: 'building', label: 'Building' },
  { key: 'error', label: 'Errors' },
];

export default function RegistryPage() {
  useAuth();
  const currentUser = useAuthStore((state) => state.user);
  const isAdmin = currentUser?.is_admin ?? false;
  const [apps, setApps] = useState<StreamlitApp[]>([]);
  const [total, setTotal] = useState(0);
  const [running, setRunning] = useState(0);
  const [filter, setFilter] = useState('all');
  const [q, setQ] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<StreamlitApp | null>(null);
  const router = useRouter();

  async function load() {
    try {
      const params: { status?: string; q?: string; owner?: string } = {};
      if (filter !== 'all') params.status = filter;
      if (q) params.q = q;
      if (isAdmin && ownerFilter) params.owner = ownerFilter;
      const data = await api.listApps(params);
      setApps(data.items);
      setTotal(data.total);
      setRunning(data.running);
      setError(null);
    } catch (e) {
      setError(api.getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // Auto-refresh while an app may be building/running so the UI keeps up
    // with worker state without manual reload.
    const interval = setInterval(() => {
      load();
    }, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, q, ownerFilter]);

  async function confirmDelete() {
    if (!pendingDelete) return;
    const { id } = pendingDelete;
    setPendingDelete(null);
    try {
      await api.deleteApp(id);
      load();
    } catch (e) {
      setError(api.getApiErrorMessage(e));
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="p-8">Loading…</div>
      </AppLayout>
    );
  }

  const owners = isAdmin
    ? Array.from(new Map(apps.map((a) => [a.owner.login, a.owner])).values()).sort((a, b) =>
        a.login.localeCompare(b.login)
      )
    : [];

  return (
    <AppLayout>
      <div className="flex items-end justify-between mb-5">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">
            {isAdmin ? 'All apps' : 'My apps'}
          </h1>
          <div className="mt-1 text-sm text-[var(--text-3)]">
            {total} shown · {running} running
          </div>
        </div>
        <Link href="/streamlits/new">
          <Button variant="primary">+ Create app</Button>
        </Link>
      </div>

      {error && (
        <div className="mb-5 text-sm text-[var(--err-fg)] border border-[var(--err-fg)] rounded-lg px-4 py-3 bg-[var(--surface)]">
          {error}
        </div>
      )}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <div className="relative flex-1 min-w-[220px] max-w-[340px]">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]">⌕</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name or URL…"
            className="w-full h-9 pl-9 pr-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm outline-none"
          />
        </div>
        {isAdmin && (
          <select
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value)}
            className="h-9 px-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm outline-none"
          >
            <option value="">All owners</option>
            {owners.map((owner) => (
              <option key={owner.login} value={owner.login}>
                {owner.display_name || owner.login}
              </option>
            ))}
          </select>
        )}
        <div className="flex gap-1 bg-[var(--surface-3)] p-1 rounded-lg">
          {chips.map((chip) => (
            <button
              key={chip.key}
              onClick={() => setFilter(chip.key)}
              className={`h-7 px-3 rounded-md text-xs font-semibold ${
                filter === chip.key
                  ? 'bg-[var(--chip-on)] text-[var(--text)]'
                  : 'text-[var(--text-3)]'
              }`}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(330px,1fr))] gap-5">
        {apps.map((app) => (
          <AppCard
            key={app.id}
            app={app}
            onRun={() => api.runApp(app.id).then(load)}
            onStop={() => api.stopApp(app.id).then(load)}
            onRestart={() => api.restartApp(app.id).then(load)}
            onDuplicate={() => api.duplicateApp(app.id).then(() => router.refresh())}
            onDelete={() => setPendingDelete(app)}
          />
        ))}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete app?"
        message={`“${pendingDelete?.name ?? ''}” will be stopped and removed from the registry along with its code. This cannot be undone.`}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </AppLayout>
  );
}
