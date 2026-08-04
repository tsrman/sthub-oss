'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import type { editor as monacoEditor } from 'monaco-editor';

import { AppLayout } from '@/components/layout/AppLayout';
import { Button } from '@/components/ui/Button';
import { FileTree } from '@/components/editor/FileTree';
import { MonacoEditor } from '@/components/editor/MonacoEditor';
import { ImagePreview } from '@/components/editor/ImagePreview';
import { ProblemsPanel } from '@/components/editor/ProblemsPanel';
import { AiAssistant } from '@/components/editor/AiAssistant';
import { StatusBadge } from '@/components/registry/StatusBadge';
import { useAuth } from '@/hooks/useAuth';
import { useStreamlitId } from '@/hooks/useStreamlitId';
import { getLanguageFromPath, isImageFile, isTextFile, isTextPath } from '@/lib/syntax';
import { bytesToBase64 } from '@/lib/base64';
import * as api from '@/lib/api-methods';
import { StreamlitFileSummary, LintError, StreamlitDetail } from '@/lib/types';

export default function EditorPage() {
  useAuth();
  const id = useStreamlitId();
  const inputRef = useRef<HTMLInputElement>(null);
  const editorRef = useRef<monacoEditor.IStandaloneCodeEditor | null>(null);

  const [app, setApp] = useState<StreamlitDetail | null>(null);
  const [files, setFiles] = useState<StreamlitFileSummary[]>([]);
  const [activePath, setActivePath] = useState<string>('');
  const [content, setContent] = useState<string>('');
  const [contentType, setContentType] = useState<string>('text/plain');
  const [problems, setProblems] = useState<LintError[]>([]);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function showError(e: unknown) {
    setError(api.getApiErrorMessage(e));
  }

  async function loadFiles() {
    const data = await api.listFiles(id);
    setFiles(data.items);
    return data.items;
  }

  async function openFile(path: string, items?: StreamlitFileSummary[]) {
    const list = items || files;
    const file = list.find((f) => f.path === path);
    if (!file) return;
    setActivePath(path);
    setContentType(file.content_type);
    try {
      if (isImageFile(file.content_type)) {
        const data = await api.getFile(id, path, { base64: true });
        setContent(data.content);
        return;
      }
      if (isTextFile(file.content_type)) {
        const data = await api.getFile(id, path);
        setContent(data.content);
        setDirty(false);
        return;
      }
      setContent('');
    } catch (e) {
      showError(e);
    }
  }

  async function load() {
    try {
      const [appData, filesData] = await Promise.all([api.getApp(id), api.listFiles(id)]);
      setApp(appData);
      setFiles(filesData.items);
      const first = filesData.items.find((f) => f.is_entrypoint) || filesData.items[0];
      if (first && !activePath) {
        await openFile(first.path, filesData.items);
      }
    } catch (e) {
      showError(e);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    api
      .aiStatus()
      .then((s) => setAiEnabled(s.enabled))
      .catch(() => setAiEnabled(false));
  }, []);

  async function handleSave() {
    if (!activePath || saving) return;
    setSaving(true);
    try {
      await api.saveFile(id, activePath, { content, content_type: contentType });
      setDirty(false);
      setError(null);
      await loadFiles();
      if (activePath.endsWith('.py')) {
        const res = await api.lintCode(id, content);
        setProblems(res.problems);
      } else {
        setProblems([]);
      }
    } catch (e) {
      // On an autosave failure the banner appears once (state is unchanged
      // while the message repeats) and `dirty` stays set so saving retries.
      showError(e);
    } finally {
      setSaving(false);
    }
  }

  // Autosave after the user pauses typing.
  useEffect(() => {
    if (!dirty || !activePath) return;
    const timer = setTimeout(() => {
      handleSave();
    }, 1500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, activePath, content, contentType]);

  // Ctrl/Cmd + S to save manually.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (dirty) handleSave();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, activePath, content, contentType, saving]);

  async function handleCheck() {
    if (!activePath.endsWith('.py')) return;
    try {
      const res = await api.lintCode(id, content);
      setProblems(res.problems);
    } catch (e) {
      showError(e);
    }
  }

  async function handleUpload(filesList: FileList | null) {
    if (!filesList) return;
    try {
      for (const file of Array.from(filesList)) {
        const buffer = await file.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        const isText = file.type.startsWith('text/') || isTextPath(file.name);
        if (isText) {
          const content = new TextDecoder('utf-8').decode(bytes);
          await api.saveFile(id, file.name, {
            content,
            content_type: file.type || 'text/plain',
          });
        } else {
          await api.saveFile(id, file.name, {
            content: bytesToBase64(bytes),
            content_type: file.type || 'application/octet-stream',
          });
        }
      }
      await loadFiles();
    } catch (e) {
      showError(e);
    }
  }

  async function handleDelete(path: string) {
    if (!confirm(`Delete ${path}?`)) return;
    try {
      await api.deleteFile(id, path);
      const items = await loadFiles();
      if (activePath === path) {
        const first = items.find((f) => f.is_entrypoint) || items[0];
        if (first) await openFile(first.path, items);
      }
    } catch (e) {
      showError(e);
    }
  }

  async function handleCreateFile(path: string) {
    try {
      await api.saveFile(id, path, { content: '', content_type: 'text/plain' });
      const items = await loadFiles();
      await openFile(path, items);
    } catch (e) {
      showError(e);
    }
  }

  async function handleRenameFile(oldPath: string, newPath: string) {
    try {
      const file = files.find((f) => f.path === oldPath);
      // Any non-text file must round-trip as base64, not just images.
      const needsBase64 = file ? !isTextFile(file.content_type) : false;
      const data = await api.getFile(id, oldPath, needsBase64 ? { base64: true } : undefined);
      await api.saveFile(id, newPath, { content: data.content, content_type: data.content_type });
      await api.deleteFile(id, oldPath);
      const items = await loadFiles();
      if (activePath === oldPath) {
        await openFile(newPath, items);
      }
    } catch (e) {
      showError(e);
    }
  }

  async function handleRun() {
    setActionLoading(true);
    try {
      await api.runApp(id);
      await load();
    } catch (e) {
      showError(e);
    } finally {
      setActionLoading(false);
    }
  }

  async function handleRestart() {
    setActionLoading(true);
    try {
      await api.restartApp(id);
      await load();
    } catch (e) {
      showError(e);
    } finally {
      setActionLoading(false);
    }
  }

  // Insert a snippet from the AI assistant at the current Monaco cursor.
  function insertAtCursor(code: string) {
    const ed = editorRef.current;
    if (!ed) return;
    const selection = ed.getSelection();
    if (!selection) return;
    ed.executeEdits('ai-assistant', [
      { range: selection, text: code, forceMoveMarkers: true },
    ]);
    ed.focus();
  }

  const language = getLanguageFromPath(activePath);
  const appUrl = app?.public_url || app?.url;

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  }

  function onDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
  }

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    await handleUpload(e.dataTransfer.files);
  }

  return (
    <div
      className="min-h-screen flex flex-col"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {isDragging && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="rounded-2xl border-2 border-dashed border-[var(--accent)] bg-[var(--surface)] px-10 py-8 text-center shadow-xl">
            <div className="text-4xl mb-3">⬇</div>
            <div className="text-lg font-bold">Drop files to upload</div>
          </div>
        </div>
      )}
      <header className="h-14 flex items-center gap-4 px-6 bg-[var(--surface)] border-b border-[var(--border)] sticky top-0 z-50">
        <Link href="/streamlits" className="text-sm text-[var(--text-2)] hover:text-[var(--text)]">
          ← Back
        </Link>
        <div className="w-px h-5 bg-[var(--border)]" />
        <Link href="/streamlits" className="font-extrabold text-sm tracking-wider">
          STHub
        </Link>
        <div className="w-px h-5 bg-[var(--border)]" />
        <span className="font-bold text-sm flex items-center gap-2">
          <span className="w-4 h-4 rounded bg-[var(--accent)] text-[var(--accent-ink)] flex items-center justify-center text-[10px]">
            S
          </span>
          {app?.name || 'Editor'}
        </span>
        {app && <StatusBadge status={app.status} />}
        {appUrl && (
          <a
            href={appUrl}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-mono text-[var(--text)] hover:underline truncate max-w-[240px]"
            title={appUrl}
          >
            ↗ {appUrl}
          </a>
        )}
        <div className="flex-1" />
        {app?.status === 'stopped' && (
          <Button
            variant="primary"
            onClick={handleRun}
            disabled={actionLoading}
            className="h-8 text-xs"
            data-testid="editor-run-button"
          >
            ▶ Start
          </Button>
        )}
        {(app?.status === 'running' || app?.status === 'error') && (
          <Button
            variant="primary"
            onClick={handleRestart}
            disabled={actionLoading}
            className="h-8 text-xs"
            data-testid="editor-restart-button"
          >
            ↻ Restart
          </Button>
        )}
        <Link href={`/streamlits/${id}/logs`}>
          <Button variant="secondary" className="h-8 text-xs">
            Logs
          </Button>
        </Link>
        <Button
          variant="secondary"
          onClick={handleCheck}
          className="h-8 text-xs"
          data-testid="check-button"
        >
          Check
        </Button>
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={saving || !dirty}
          className="h-8 text-xs"
          data-testid="save-button"
        >
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </header>
      {error && (
        <div
          data-testid="editor-error"
          className="mx-6 mt-3 flex items-center gap-3 text-sm text-[var(--err-fg)] border border-[var(--err-fg)] rounded-lg px-4 py-3 bg-[var(--surface)]"
        >
          <span className="flex-1">{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-[var(--text-3)] hover:text-[var(--text)]"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
      )}
      <div className="flex flex-1 min-h-0">
        <FileTree
          files={files}
          active={activePath}
          onSelect={(path) => openFile(path)}
          onUpload={() => inputRef.current?.click()}
          onDelete={handleDelete}
          onDropFiles={handleUpload}
          onCreateFile={handleCreateFile}
          onRenameFile={handleRenameFile}
        />
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => handleUpload(e.target.files)}
        />
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 min-h-0 bg-[var(--surface)]">
            {isImageFile(contentType) ? (
              <ImagePreview src={`data:${contentType};base64,${content}`} alt={activePath} />
            ) : isTextFile(contentType) ? (
              <MonacoEditor
                value={content}
                language={language}
                onMount={(ed) => {
                  editorRef.current = ed;
                }}
                onChange={(v) => {
                  setContent(v);
                  setDirty(true);
                }}
              />
            ) : (
              <div className="p-8 text-sm text-[var(--text-3)]">
                Preview of {activePath} is not available.
              </div>
            )}
          </div>
          <ProblemsPanel problems={problems} />
        </div>
      </div>
      {aiEnabled && !aiOpen && (
        <button
          onClick={() => setAiOpen(true)}
          className="fixed bottom-4 right-4 z-[90] flex h-12 items-center gap-2 rounded-full bg-[var(--accent)] px-5 text-sm font-bold text-[var(--accent-ink)] shadow-2xl hover:opacity-90"
          title="AI code assistant"
        >
          <span className="text-base">✦</span> Assistant
        </button>
      )}
      {aiEnabled && aiOpen && (
        <AiAssistant
          onClose={() => setAiOpen(false)}
          onInsertCode={isTextFile(contentType) ? insertAtCursor : undefined}
          getContext={() =>
            activePath
              ? {
                  path: activePath,
                  language: isTextFile(contentType) ? language : '',
                  content: isTextFile(contentType) ? content : '',
                }
              : null
          }
        />
      )}
    </div>
  );
}
