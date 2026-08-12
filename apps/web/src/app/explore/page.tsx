import Link from 'next/link';
import { Suspense } from 'react';

import { ConfidenceLegend } from '@/components/ConfidenceLadder';
import { CorpusReadout } from '@/components/CorpusReadout';
import { JobList } from '@/components/JobList';

/**
 * Explore, M0 form: the list view.
 *
 * §12.4 requires an alternative list view for every map result, and M4 builds
 * the map. Building the list first means the accessible path is the original
 * rather than a retrofit — the map becomes the enhancement, not the product.
 */
export default function ExplorePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Explore</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          Every role ingested from a first-party job board, with what we actually know about where
          it is. The 3D city arrives at milestone 4; this list is its permanent equivalent, not a
          placeholder.
        </p>
      </section>

      <CorpusReadout />

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          The city
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          New York, drawn offline from a tile archive on this machine. There are no roles on it yet
          — the map is a second view of this list and it arrives one layer at a time, starting with
          the ground.
        </p>
        <Link
          href="/explore/city"
          className="mt-3 inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
        >
          Open the city
        </Link>
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Ranked for you
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          The same roles, scored against your profile and grouped by whether each one is open to
          you. Every score decomposes into what it was made of, and every group says what it does
          not mean. The list below stays ordered by recency, which is a fact about the corpus rather
          than about you.
        </p>
        <Link
          href="/explore/matches"
          className="mt-3 inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
        >
          Open the ranked list
        </Link>
      </section>

      {/* JobList reads filter state from the URL via useSearchParams, which
          requires a Suspense boundary — without one, `next build` fails. */}
      <Suspense
        fallback={
          <p className="px-5 py-8 font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
            Loading filters…
          </p>
        }
      >
        <JobList />
      </Suspense>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Reading the confidence ladder
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          A job is only drawn at a position when the position is real. The ladder on every row shows
          how precisely we resolved that location — and refuses to imply more.
        </p>
        <div className="mt-4">
          <ConfidenceLegend />
        </div>
      </section>
    </div>
  );
}
