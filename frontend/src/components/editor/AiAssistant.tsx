'use client';

import { useEffect, useRef, useState } from 'react';

import { streamAiChat } from '@/lib/ai';
import { AiChatMessage, AiFileContext } from '@/lib/types';

// The server caps history at 40 messages — send only a sliding window.
const MAX_HISTORY_MESSAGES = 30;

interface Props {
  /** Returns the file currently open in the editor, for context. */
  getContext: () => AiFileContext | null;
  /** Insert a snippet into the editor at the cursor; omit to hide the button. */
  onInsertCode?: (code: string) => void;
  onClose: () => void;
}

/** A fenced code block with copy / insert-into-editor actions. */
function CodeBlock({
  code,
  onInsert,
}: {
  code: string;
  onInsert?: (code: string) => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable (e.g. insecure context) — ignore.
    }
  }

  return (
    <div className="my-2 overflow-hidden rounded-md border border-[var(--border)] bg-[var(--surface-2)]">
      <div className="flex items-center justify-end gap-1 border-b border-[var(--border)] px-2 py-1">
        <button
          onClick={copy}
          className="rounded px-2 py-0.5 text-[11px] font-semibold text-[var(--text-3)] hover:text-[var(--text)]"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
        {onInsert && (
          <button
            onClick={() => onInsert(code)}
            className="rounded px-2 py-0.5 text-[11px] font-semibold text-[var(--accent)] hover:opacity-80"
          >
            Insert into editor
          </button>
        )}
      </div>
      <pre className="overflow-x-auto p-2 text-xs font-mono">{code}</pre>
    </div>
  );
}

/** Renders assistant text with lightweight ```fenced``` code-block styling. */
export function MessageBody({
  text,
  onInsertCode,
}: {
  text: string;
  onInsertCode?: (code: string) => void;
}) {
  const parts = text.split('```');
  return (
    <div className="text-sm leading-relaxed whitespace-pre-wrap break-words">
      {parts.map((part, i) => {
        // Odd parts are code blocks — but only when a closing fence exists.
        // While the block is still streaming (last part, no closing fence),
        // show raw text without actions so an unfinished snippet can't be
        // copied/inserted by mistake.
        const isCompleteBlock = i % 2 === 1 && i < parts.length - 1;
        if (isCompleteBlock) {
          return (
            <CodeBlock
              key={i}
              code={part.replace(/^[a-z0-9]*\n/i, '')}
              onInsert={onInsertCode}
            />
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </div>
  );
}

export function AiAssistant({ getContext, onInsertCode, onClose }: Props) {
  const [messages, setMessages] = useState<AiChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, streaming]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  function send() {
    const text = input.trim();
    if (!text || streaming) return;
    setError('');
    const history: AiChatMessage[] = [...messages, { role: 'user', content: text }];
    // Append an empty assistant turn we stream into.
    setMessages([...history, { role: 'assistant', content: '' }]);
    setInput('');
    setStreaming(true);

    // Create the controller synchronously so stop() cancels the request even
    // while the token is still being refreshed inside streamAiChat.
    const controller = new AbortController();
    abortRef.current = controller;
    streamAiChat(history.slice(-MAX_HISTORY_MESSAGES), getContext(), {
      onDelta: (chunk) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === 'assistant') {
            next[next.length - 1] = { ...last, content: last.content + chunk };
          }
          return next;
        });
      },
      onDone: () => {
        setStreaming(false);
        abortRef.current = null;
      },
      onError: (message) => {
        setError(message);
        setStreaming(false);
        abortRef.current = null;
        // Drop the empty assistant placeholder if nothing streamed.
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'assistant' && last.content === '') return prev.slice(0, -1);
          return prev;
        });
      },
    }, controller);
  }

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-[90] flex h-[560px] max-h-[80vh] w-[400px] max-w-[calc(100vw-2rem)] flex-col rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl">
      <header className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--accent)] text-[var(--accent-ink)] text-xs font-bold">
          AI
        </span>
        <span className="text-sm font-bold">Code assistant</span>
        <div className="flex-1" />
        {messages.length > 0 && (
          <button
            onClick={() => setMessages([])}
            className="text-xs text-[var(--text-3)] hover:text-[var(--text)]"
          >
            Clear
          </button>
        )}
        <button
          onClick={onClose}
          className="text-[var(--text-3)] hover:text-[var(--text)]"
          aria-label="Close"
        >
          ✕
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <div className="mt-8 text-center text-sm text-[var(--text-3)]">
            Ask about the code in the open file, request an example, or get help with an error.
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            data-testid={m.role === 'user' ? 'ai-message-user' : 'ai-message-assistant'}
            className={
              m.role === 'user'
                ? 'ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-[var(--accent-soft)] px-3 py-2 text-sm whitespace-pre-wrap break-words'
                : 'mr-auto max-w-[92%] rounded-2xl rounded-bl-sm bg-[var(--surface-2)] px-3 py-2'
            }
          >
            {m.role === 'assistant' ? (
              m.content ? (
                <MessageBody text={m.content} onInsertCode={onInsertCode} />
              ) : (
                <span className="text-sm text-[var(--text-3)]">…</span>
              )
            ) : (
              m.content
            )}
          </div>
        ))}
      </div>

      {error && (
        <div className="border-t border-[var(--border)] px-4 py-2 text-xs text-[var(--err-fg)]">
          {error}
        </div>
      )}

      <div className="border-t border-[var(--border)] p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
            placeholder="Type a message…"
            className="flex-1 resize-none rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          />
          {streaming ? (
            <button
              onClick={stop}
              className="h-9 rounded-lg border border-[var(--border)] px-3 text-sm font-semibold text-[var(--text-2)]"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={send}
              disabled={!input.trim()}
              aria-label="Send"
              className="h-9 rounded-lg bg-[var(--accent)] px-3 text-sm font-bold text-[var(--accent-ink)] disabled:opacity-50"
            >
              ↑
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
