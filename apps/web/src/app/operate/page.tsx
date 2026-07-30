import { SourceHealthTable } from '@/components/SourceHealthTable';

/**
 * Operate, M0 form: source health.
 *
 * Application tracking is M2. What Operate can honestly show today is the state
 * of the ingestion pipeline, which §2.6 requires to be visible anyway. Shipping
 * the real thing that exists beats shipping a mock of the thing that does not.
 */
export default function OperatePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Operate</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          The state of every job source. A source that failed is shown as failed — an error or a
          timeout never closes a listing, so an outage here means the roles you can see are simply
          older than they look.
        </p>
      </section>

      <SourceHealthTable />

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
