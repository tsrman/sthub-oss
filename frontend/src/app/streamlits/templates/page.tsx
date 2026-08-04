'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/Button';
import { useAuth } from '@/hooks/useAuth';
import { templates } from '@/lib/templates';
import * as api from '@/lib/api-methods';

export default function TemplatesPage() {
  useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  async function applyTemplate(tpl: (typeof templates)[0]) {
    setError(null);
    const slug = `${tpl.slug}-${Date.now()}`;
    try {
      const app = await api.createApp({ name: tpl.name, slug });
      await api.saveFile(app.id, 'app.py', { content: tpl.code, content_type: 'text/x-python' });
      await api.saveFile(app.id, 'requirements.txt', {
        content: tpl.requirements,
        content_type: 'text/plain',
      });
      router.push(`/streamlits/${app.id}/editor`);
    } catch (e) {
      setError(api.getApiErrorMessage(e));
    }
  }

  return (
    <AppLayout>
      <h1 className="text-2xl font-extrabold tracking-tight">Templates</h1>
      <p className="mt-1 text-sm text-[var(--text-3)]">
        Ready-made starting points — create an app in one click
      </p>
      {error && (
        <div className="mt-4 text-sm text-[var(--err-fg)] border border-[var(--err-fg)] rounded-lg px-4 py-3 bg-[var(--surface)]">
          {error}
        </div>
      )}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(310px,1fr))] gap-5 mt-5">
        {templates.map((tpl) => (
          <div
            key={tpl.id}
            data-testid="template-card"
            className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-5 flex flex-col shadow-sm"
          >
            <div className="flex items-center gap-3 mb-3">
              <div
                className="w-11 h-11 rounded-xl flex items-center justify-center text-xs font-bold font-mono"
                style={{ background: tpl.iconBg, color: tpl.iconColor }}
              >
                {tpl.badge}
              </div>
              <div className="font-bold text-[15px]">{tpl.name}</div>
            </div>
            <p className="text-xs text-[var(--text-3)] leading-relaxed flex-1">{tpl.desc}</p>
            <div className="flex flex-wrap gap-1.5 my-3">
              {tpl.tags.map((t) => (
                <span
                  key={t}
                  className="text-[11px] font-mono px-2 py-0.5 rounded bg-[var(--surface-2)] text-[var(--text-2)]"
                >
                  {t}
                </span>
              ))}
            </div>
            <Button variant="primary" onClick={() => applyTemplate(tpl)}>
              Use template
            </Button>
          </div>
        ))}
      </div>
    </AppLayout>
  );
}
