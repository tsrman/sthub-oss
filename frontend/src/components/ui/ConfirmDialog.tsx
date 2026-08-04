'use client';

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Delete',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-[rgba(20,26,44,0.45)]"
      onClick={onCancel}
    >
      <div
        className="w-[380px] rounded-2xl bg-[var(--surface)] p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-[17px] font-extrabold mb-2">{title}</div>
        <div className="text-sm text-[var(--text-3)] leading-relaxed mb-6">{message}</div>
        <div className="flex justify-end gap-2.5">
          <button
            onClick={onCancel}
            className="h-10 px-4 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-[var(--text-2)] text-sm font-semibold"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className="h-10 px-[18px] rounded-lg bg-[#d64545] text-white text-sm font-bold"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
