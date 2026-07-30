'use client';

/**
 * The three modes from §2.2: Explore, Operate, Analyze.
 *
 * Not numbered. They are three views of the same data, chosen freely — not a
 * sequence — so numbering them would encode an order that does not exist.
 * Each carries a one-line description of its job instead, which is information
 * a new user actually needs.
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';

interface Mode {
  readonly href: string;
  readonly label: string;
  readonly purpose: string;
}

const MODES: readonly Mode[] = [
  { href: '/explore', label: 'Explore', purpose: 'Find roles' },
  { href: '/operate', label: 'Operate', purpose: 'Work the pipeline' },
  { href: '/analyze', label: 'Analyze', purpose: 'See the patterns' },
] as const;

export function ModeNav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Modes">
      <ul className="flex items-stretch">
        {MODES.map((mode) => {
          const active = pathname === mode.href || pathname.startsWith(`${mode.href}/`);
          return (
            <li key={mode.href}>
              <Link
                href={mode.href}
                aria-current={active ? 'page' : undefined}
                className={[
                  'group relative block px-4 py-2 transition-colors',
                  active ? 'text-paper' : 'text-paper-faint hover:text-paper-dim',
                ].join(' ')}
              >
                <span className="block text-[13px] font-medium tracking-tight">{mode.label}</span>
                <span className="block font-mono text-[9px] uppercase tracking-[0.14em] text-ink-500">
                  {mode.purpose}
                </span>
                {/* A hairline rule marks the active mode — a thin white
                 * highlight, per §4.2, not a filled tab. */}
                <span
                  aria-hidden="true"
                  className={[
                    'absolute inset-x-0 -bottom-px h-px transition-colors',
                    active ? 'bg-signal-400' : 'bg-transparent group-hover:bg-ink-600',
                  ].join(' ')}
                />
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
