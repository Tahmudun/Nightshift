import type { Metadata } from 'next';

import './globals.css';

import { HealthTelemetry } from '@/components/HealthTelemetry';
import { ModeNav } from '@/components/ModeNav';
import { Providers } from '@/components/Providers';
import { SessionGate } from '@/components/SessionGate';
import { SessionIdentity } from '@/components/SessionIdentity';

/*
 * §4.1: keep the product name isolated so it can be changed later, and do not
 * hardcode branding across dozens of files. It is defined once, here.
 */
const PRODUCT_NAME = 'Nightshift';
const PRODUCT_TAGLINE = 'Live career intelligence for New York tech';

export const metadata: Metadata = {
  title: `${PRODUCT_NAME} — ${PRODUCT_TAGLINE}`,
  description: PRODUCT_TAGLINE,
};

export default function RootLayout({ children }: { readonly children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Providers>
          {/* Skip link: the non-3D interface must be keyboard-navigable (§12.4). */}
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:border focus:border-signal-500 focus:bg-ink-900 focus:px-3 focus:py-2 focus:text-[13px] focus:text-paper"
          >
            Skip to content
          </a>

          <header className="sticky top-0 z-40 border-b border-ink-700 bg-ink-950/85 backdrop-blur-sm">
            <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-3 px-5 py-3">
              <div className="flex items-baseline gap-2.5">
                {/* The wordmark: a cyan signal glyph against a blackened mass.
                 * Set in mono with wide tracking — the type treatment is the
                 * identity, not a logo file. */}
                <span aria-hidden="true" className="text-signal-400">
                  ▮
                </span>
                <span className="font-mono text-[13px] font-semibold uppercase tracking-[0.28em] text-paper">
                  {PRODUCT_NAME}
                </span>
              </div>

              <div className="order-3 w-full sm:order-none sm:w-auto">
                <ModeNav />
              </div>

              <div className="ms-auto flex items-center gap-4">
                <SessionIdentity />
                <HealthTelemetry />
              </div>
            </div>
          </header>

          {/* Every page is behind the gate, including ones that do not exist
           * yet — the same argument `main.py` makes for putting the session
           * dependency on the router rather than on each handler. */}
          <main id="main" className="mx-auto max-w-6xl px-5 py-8">
            <SessionGate>{children}</SessionGate>
          </main>

          <footer className="mx-auto max-w-6xl border-t border-ink-800 px-5 py-6">
            {/* Says where the product actually is. It read "milestone 0 ·
             * ingestion spine · no map yet" until M4b put a map on the screen,
             * which is the seventh time in this project a description has
             * outlived the thing it described. */}
            <p className="font-mono text-[10px] tracking-[0.14em] text-paper-faint uppercase">
              Milestone 5 · the open hand · accounts, and postings you hand it yourself
            </p>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
