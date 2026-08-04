interface Props {
  src: string;
  alt: string;
}

export function ImagePreview({ src, alt }: Props) {
  return (
    <div
      className="flex-1 flex flex-col items-center justify-center gap-3.5 p-6 min-h-0"
      style={{
        background:
          'repeating-conic-gradient(var(--surface-2) 0% 25%, var(--surface-3) 0% 50%) 0 / 22px 22px',
      }}
    >
      <img
        src={src}
        alt={alt}
        className="max-w-full max-h-full object-contain rounded-lg shadow-xl bg-[var(--surface)]"
      />
      <div className="inline-flex items-center gap-2 font-mono text-xs text-[var(--text-3)]">
        <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-[var(--surface-2)] font-sans font-bold">
          View only
        </span>
        {alt}
      </div>
    </div>
  );
}
