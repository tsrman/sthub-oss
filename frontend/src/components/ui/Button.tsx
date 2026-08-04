import { ButtonHTMLAttributes } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
}

export function Button({ variant = 'secondary', className, ...props }: ButtonProps) {
  const variants = {
    primary: 'bg-[var(--accent)] text-[var(--accent-ink)] hover:opacity-90',
    secondary:
      'bg-[var(--surface)] border border-[var(--border)] text-[var(--text-2)] hover:bg-[var(--surface-2)]',
    danger: 'bg-[var(--err-bg)] text-[var(--err-fg)] hover:opacity-90',
    ghost: 'bg-transparent text-[var(--text-3)] hover:text-[var(--text)]',
  };
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-lg px-4 py-2 font-semibold text-sm transition',
        variants[variant],
        className
      )}
      {...props}
    />
  );
}
