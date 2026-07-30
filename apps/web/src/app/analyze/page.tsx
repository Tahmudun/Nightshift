import { CorpusReadout } from '@/components/CorpusReadout';

/**
 * Analyze, M0 form: the one honest analysis available.
 *
 * Historical intelligence is M6 and needs snapshots that do not exist yet.
 * What M0 can measure truthfully is the shape of its own knowledge — how much
 * of the corpus is located, and how precisely.
 */
export default function AnalyzePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Analyze</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          Trends over time need history, and history starts accumulating at milestone 6. What can be
          measured today is how much this system honestly knows.
        </p>
      </section>

      <CorpusReadout />

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Why every location is unresolved
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          Milestone 0 parses the location text a job board publishes and stores one row per place
          named — but it does not geocode. No coordinate has been looked up, so no role can be drawn
          at a position. Geocoding against NYC GeoSearch arrives at milestone 1, and only the
          addresses it resolves will be marked verified.
        </p>
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Not built yet
        </h2>
        <ul className="mt-3 space-y-1.5 text-[13px] text-paper-dim">
          <li>Hiring velocity and posting trends — milestone 6.</li>
          <li>Skill demand over time — milestone 6.</li>
          <li>Funnel and outcome analysis — milestone 6.</li>
        </ul>
      </section>
    </div>
  );
}
