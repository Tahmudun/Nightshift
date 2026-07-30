import type { Metadata } from 'next';

import './globals.css';

import { HealthTelemetry } from '@/components/HealthTelemetry';
import { ModeNav } from '@/components/ModeNav';
import { Providers } from '@/components/Providers';

/*
 * §4.1: keep the product name isolated so it can be changed later, and do not
 * hardcode branding across dozens of files. It is defined once, here.
 */
const PRODUCT_NAME = 'CitySignal';
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

              <div className="ms-auto">
                <HealthTelemetry />
              </div>
            </div>
          </header>

          <main id="main" className="mx-auto max-w-6xl px-5 py-8">
            {children}
          </main>

          <footer className="mx-auto max-w-6xl border-t border-ink-800 px-5 py-6">
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
              Milestone 0 · ingestion spine · no map yet
            </p>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
