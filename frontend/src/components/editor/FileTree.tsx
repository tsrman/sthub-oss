'use client';

import { useState } from 'react';
import { StreamlitFileSummary } from '@/lib/types';

interface Props {
  files: StreamlitFileSummary[];
  active: string;
  onSelect: (path: string) => void;
  onUpload: () => void;
  onDelete: (path: string) => void;
  onDropFiles?: (files: FileList) => void;
  onCreateFile?: (path: string) => void;
  onRenameFile?: (oldPath: string, newPath: string) => void;
}

export function FileTree({
  files,
  active,
  onSelect,
  onUpload,
  onDelete,
  onDropFiles,
  onCreateFile,
  onRenameFile,
}: Props) {
  const [isOver, setIsOver] = useState(false);
  const canDrop = Boolean(onDropFiles);

  function handleDragOver(e: React.DragEvent) {
    if (!canDrop) return;
    e.preventDefault();
    if (e.dataTransfer.types.includes('Files')) {
      setIsOver(true);
    }
  }

  function handleDragLeave(e: React.DragEvent) {
    if (!canDrop) return;
    e.preventDefault();
    setIsOver(false);
  }

  function handleDrop(e: React.DragEvent) {
    if (!canDrop) return;
    e.preventDefault();
    setIsOver(false);
    onDropFiles!(e.dataTransfer.files);
  }

  function handleCreate() {
    if (!onCreateFile) return;
    const name = window.prompt('Name for the new file:', 'new_file.py');
    if (!name) return;
    const path = name.trim();
    if (!path) return;
    if (files.some((f) => f.path === path)) {
      window.alert(`File ${path} already exists.`);
      return;
    }
    onCreateFile(path);
  }

  function handleRename(oldPath: string) {
    if (!onRenameFile) return;
    const name = window.prompt('New name for the file:', oldPath);
    if (!name) return;
    const newPath = name.trim();
    if (!newPath || newPath === oldPath) return;
    if (files.some((f) => f.path === newPath)) {
      window.alert(`File ${newPath} already exists.`);
      return;
    }
    onRenameFile(oldPath, newPath);
  }

  const canModify = (path: string) => path !== 'app.py' && path !== 'requirements.txt';

  return (
    <div
      className={`w-52 flex-none border-r bg-[var(--surface-2)] flex flex-col ${
        isOver ? 'border-[var(--accent)] bg-[var(--accent-soft)]' : 'border-[var(--border)]'
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-[11px] uppercase tracking-wider text-[var(--muted)] font-bold">
          Project files
        </span>
        <div className="flex items-center gap-1">
          {onCreateFile && (
            <button
              onClick={handleCreate}
              className="w-6 h-6 rounded-md border border-[var(--border)] bg-[var(--surface)] text-[var(--text-2)] flex items-center justify-center"
              title="New file"
            >
              +
            </button>
          )}
          <button
            onClick={onUpload}
            className="w-6 h-6 rounded-md border border-[var(--border)] bg-[var(--surface)] text-[var(--text-2)] flex items-center justify-center"
            title="Upload files"
          >
            ↑
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto px-2 pb-2 flex flex-col gap-0.5">
        {files.map((file) => (
          <button
            key={file.path}
            onClick={() => onSelect(file.path)}
            className={`flex items-center gap-2 w-full text-left px-2 py-1.5 rounded-md font-mono text-xs group ${
              active === file.path
                ? 'bg-[var(--accent-soft)] text-[var(--text)] font-bold'
                : 'text-[var(--text-2)] hover:bg-[var(--surface-3)]'
            }`}
          >
            <span>{file.is_entrypoint ? '▶' : file.path.endsWith('.py') ? '›' : '•'}</span>
            <span className="truncate">{file.path}</span>
            {onRenameFile && canModify(file.path) && (
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  handleRename(file.path);
                }}
                className="ml-auto text-[var(--text-3)] opacity-0 group-hover:opacity-100"
                title="Rename"
              >
                ✎
              </span>
            )}
            {canModify(file.path) && (
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(file.path);
                }}
                className="text-[var(--err-fg)] opacity-0 group-hover:opacity-100"
              >
                ✕
              </span>
            )}
          </button>
        ))}
      </div>
      <button
        onClick={onUpload}
        className={`mx-2 mb-3 h-8 rounded-lg border border-dashed text-xs font-semibold flex items-center justify-center gap-1 ${
          isOver
            ? 'border-[var(--accent)] text-[var(--accent)]'
            : 'border-[var(--border)] text-[var(--text-2)]'
        }`}
      >
        {isOver ? '⬇ Drop files' : '↑ Upload files'}
      </button>
    </div>
  );
}
