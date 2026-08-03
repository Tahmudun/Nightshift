import Link from 'next/link';

import { BoardPollTable } from '@/components/BoardPollTable';
import { SourceHealthTable } from '@/components/SourceHealthTable';

/**
 * Operate: your pipeline first, then the state of the machinery behind it.
 *
 * Source health came first through M0 and M1 because tracking did not exist
 * yet. It does now (M2b), and §2.2 is clear that tracking is what Operate is
 * for — so the pipeline leads and ingestion health sits underneath it.
 */
export default function OperatePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Operate</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          The state of every job source. A source that failed is shown as failed — an error or a
          timeout never closes a listing, so an outage here means the roles you can see are simply
          older than they look. A board that answered and had nothing on it is a different fact
          entirely, and it does count against the roles it stopped listing.
        </p>
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Pipeline
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          Every role you have saved, and where it got to. Nothing moves on its own.
        </p>
        <Link
          href="/operate/pipeline"
          className="mt-3 inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
        >
          Open the pipeline
        </Link>
      </section>

      <SourceHealthTable />

      <BoardPollTable />

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Job table
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          Every canonical role, its closure state, and how many sources describe it — including the
          roles that have closed.
        </p>
        <Link
          href="/operate/jobs"
          className="mt-3 inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
        >
          Open the job table →
        </Link>
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Not built yet
        </h2>
        <ul className="mt-3 space-y-1.5 text-[13px] text-paper-dim">
          <li>Saving, applying, and stage tracking — milestone 2.</li>
          <li>The daily queue — milestone 2.</li>
          <li>Match scores and explanations — milestone 3.</li>
        </ul>
        <p className="mt-3 text-[12px] text-paper-faint">
          These are absent rather than stubbed. A control that looks real and does nothing is worse
          than no control.
        </p>
      </section>
    </div>
  );
}
