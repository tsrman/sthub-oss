'use client';

import { useEffect } from 'react';
import Editor, { loader, useMonaco } from '@monaco-editor/react';
import type * as monaco from 'monaco-editor';

import { useThemeStore } from '@/stores/themeStore';

loader.config({ paths: { vs: '/monaco-editor/min/vs' } });

interface Props {
  value: string;
  language: string;
  onChange: (value: string) => void;
  onMount?: (editor: monaco.editor.IStandaloneCodeEditor) => void;
}

// Monaco's token-theme color registry only accepts 6-digit (#RRGGBB) hex.
// Production CSS minification collapses e.g. #ffffff → #fff, which Monaco then
// rejects ("Illegal value for token color"), so normalise every colour here.
// 4- and 8-digit hex values are accepted with the alpha channel dropped.
export function normalizeHex(value: string, fallback: string): string {
  const v = value.trim();
  const short = /^#([0-9a-fA-F]{3,4})$/.exec(v);
  if (short) {
    const [r, g, b] = short[1];
    return `#${r}${r}${g}${g}${b}${b}`;
  }
  const long = /^#([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?$/.exec(v);
  if (long) return `#${long[1]}`;
  return fallback;
}

function getCssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return normalizeHex(value, fallback);
}

function defineSthubTheme(monacoInstance: typeof monaco, mode: 'light' | 'dark') {
  const isDark = mode === 'dark';
  const themeName = isDark ? 'sthub-dark' : 'sthub-light';

  const bg = getCssVar('--surface', isDark ? '#1f2220' : '#ffffff');
  const fg = getCssVar('--code-fg', isDark ? '#e6e8e4' : '#2b303b');
  const lineHighlight = getCssVar('--surface-2', isDark ? '#191b19' : '#fafbfc');
  const selection = getCssVar('--accent-soft', isDark ? '#3a3320' : '#fff3dc');
  const border = getCssVar('--border', isDark ? '#363a37' : '#e6e8ef');
  const muted = getCssVar('--muted', isDark ? '#7c827d' : '#9aa3b2');
  const accent = getCssVar('--accent', '#ffb635');
  const ok = getCssVar('--ok-fg', isDark ? '#3fc9a6' : '#00735e');
  const err = getCssVar('--err-fg', isDark ? '#f07a98' : '#9c1a3e');
  const warn = getCssVar('--warn-fg', isDark ? '#ff9d4d' : '#b34c00');

  monacoInstance.editor.defineTheme(themeName, {
    base: isDark ? 'vs-dark' : 'vs',
    inherit: true,
    rules: [
      { token: 'comment', foreground: muted.replace('#', ''), fontStyle: 'italic' },
      { token: 'keyword', foreground: accent.replace('#', '') },
      { token: 'identifier', foreground: fg.replace('#', '') },
      { token: 'string', foreground: ok.replace('#', '') },
      { token: 'number', foreground: warn.replace('#', '') },
      { token: 'tag', foreground: accent.replace('#', '') },
      { token: 'attribute.name', foreground: fg.replace('#', '') },
      { token: 'attribute.value', foreground: ok.replace('#', '') },
      { token: 'error', foreground: err.replace('#', '') },
    ],
    colors: {
      'editor.background': bg,
      'editor.foreground': fg,
      'editorLineNumber.foreground': muted,
      'editorLineNumber.activeForeground': fg,
      'editor.lineHighlightBackground': lineHighlight,
      'editor.selectionBackground': selection,
      'editor.inactiveSelectionBackground': selection,
      'editor.border': border,
      'editorGutter.background': lineHighlight,
    },
  });

  monacoInstance.editor.setTheme(themeName);
}

export function MonacoEditor({ value, language, onChange, onMount }: Props) {
  const mode = useThemeStore((state) => state.mode);
  const monaco = useMonaco();

  useEffect(() => {
    if (!monaco) return;
    defineSthubTheme(monaco, mode);
  }, [monaco, mode]);

  return (
    <Editor
      height="100%"
      language={language}
      value={value}
      onChange={(v) => onChange(v || '')}
      onMount={(editor) => onMount?.(editor)}
      theme={mode === 'dark' ? 'sthub-dark' : 'sthub-light'}
      options={{
        minimap: { enabled: false },
        fontSize: 13,
        lineNumbers: 'on',
        automaticLayout: true,
        scrollBeyondLastLine: false,
      }}
    />
  );
}
