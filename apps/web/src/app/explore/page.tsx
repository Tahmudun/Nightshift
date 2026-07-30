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

      <section className="border border-ink-700 bg-ink-900/40">
        <JobList />
      </section>

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
