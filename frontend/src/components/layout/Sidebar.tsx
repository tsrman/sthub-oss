'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const items = [
  { href: '/streamlits', label: 'My apps' },
  { href: '/streamlits/templates', label: 'Templates' },
  { href: '/streamlits/history', label: 'Deployment history' },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 flex-none bg-[var(--surface)] border-r border-[var(--border)] p-4 flex flex-col gap-1.5">
      {items.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-semibold ${
              active
                ? 'bg-[var(--accent-soft)] text-[var(--text)]'
                : 'text-[var(--text-2)] hover:bg-[var(--surface-2)]'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-sm ${active ? 'bg-[var(--text)]' : 'bg-[#c3c9d6]'}`}
            />
            {item.label}
          </Link>
        );
      })}
    </aside>
  );
}
