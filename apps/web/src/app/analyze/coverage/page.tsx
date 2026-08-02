'use client';

import { useQuery } from '@tanstack/react-query';

import { fetchCoverage } from '@/lib/api';
import type { BlindSpot } from '@/lib/schemas';

/**
 * Coverage — and the reason this page exists, which is the second section.
 *
 * The M1 acceptance criterion is not that this page reports coverage. It is
 * that it **names what is not covered**. So "What is not covered" is a sibling
 * of "What is covered", not a footnote: it is not collapsible, not behind a
 * tab, and not below a fold the first section can push it past.
 *
 * There is deliberately no percentage anywhere on this page. Nobody knows how
 * many tech roles open in New York, so a figure like "we cover 73%" would be
 * arithmetic on a denominator that does not exist. The page reports what it
 * counted and admits what it could not.
 */
export default function CoveragePage() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['coverage'],
    queryFn: fetchCoverage,
  });

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">Coverage</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          Which employers this system can see at all — and, below, the ones it cannot. No
          percentage is reported anywhere on this page: nobody knows how many tech roles open in
          New York, so there is no denominator to divide by, and a coverage percentage would be a
          number this system invented.
        </p>
      </section>

      {isPending && <p className="text-[13px] text-paper-dim">Loading coverage…</p>}

      {isError && (
        <p className="border border-ink-700 bg-ink-900/40 p-5 text-[13px] text-paper-dim">
          Coverage is unavailable — the API could not be reached
          {error instanceof Error ? `: ${error.message}` : ''}. This is a reporting outage, not a
          finding: it says nothing about what is or is not covered.
        </p>
      )}

      {data && (
        <>
          <section
            aria-labelledby="covered-heading"
            className="border border-ink-700 bg-ink-900/40 p-5"
          >
            <h2
              id="covered-heading"
              className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint"
            >
              What is covered
            </h2>

            <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-4">
              <Stat label="Boards in registry" value={data.boards.total} />
              <Stat label="Actually polled" value={data.boards.pollable} />
              <Stat label="With an NYC office" value={data.boards.with_nyc_presence} />
              <Stat label="Discovered candidates" value={data.candidates_total} />
            </dl>

            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <Breakdown title="Boards by provider" counts={data.boards.by_ats} />
              <Breakdown title="Boards by status" counts={data.boards.by_status} />
            </div>

            <div className="mt-5">
              <Breakdown
                title="Candidates by verdict"
                counts={data.candidates}
                caption="A single pending number would hide that an unnamed board needs a human and an empty one does not."
              />
            </div>
          </section>

          <section
            aria-labelledby="not-covered-heading"
            className="border border-ink-600 bg-ink-900/60 p-5"
          >
            <h2
              id="not-covered-heading"
              className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint"
            >
              What is not covered
            </h2>
            <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
              Every row here is a real gap with a real reason. Where the size of a gap is genuinely
              unknowable it says <span className="text-paper">unknown</span> rather than zero —
              counting the New York employers on Workday would mean enumerating New York employers,
              which is the problem this system is trying to solve.
            </p>

            <ul className="mt-4 space-y-4">
              {data.blind_spots.map((spot) => (
                <BlindSpotRow key={spot.id} spot={spot} />
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-paper-faint">{label}</dt>
      <dd className="mt-0.5 font-mono text-[18px] text-paper">{value}</dd>
    </div>
  );
}

function Breakdown({
  title,
  counts,
  caption,
}: {
  title: string;
  counts: Record<string, number>;
  caption?: string;
}) {
  const entries = Object.entries(counts);
  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wide text-paper-faint">{title}</h3>
      {entries.length === 0 ? (
        <p className="mt-1 text-[13px] text-paper-dim">None.</p>
      ) : (
        <dl className="mt-1.5 space-y-1">
          {entries.map(([key, count]) => (
            <div key={key} className="flex justify-between gap-4 text-[13px]">
              <dt className="text-paper-dim">{key.replace(/_/g, ' ')}</dt>
              <dd className="font-mono text-paper">{count}</dd>
            </div>
          ))}
        </dl>
      )}
      {caption && <p className="mt-2 text-[12px] leading-relaxed text-paper-faint">{caption}</p>}
    </div>
  );
}

/**
 * `count === null` renders the word "unknown", never a zero and never a blank.
 * A blank cell reads as "no data yet"; a zero reads as "no gap here". Both are
 * claims this system has not earned.
 */
function BlindSpotRow({ spot }: { spot: BlindSpot }) {
  const unknown = spot.count === null;
  return (
    <li className="border-l-2 border-ink-600 pl-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          className={`font-mono text-[13px] ${unknown ? 'text-paper-faint' : 'text-paper'}`}
          title={unknown ? 'The size of this gap is genuinely unknown' : undefined}
        >
          {unknown ? 'unknown' : spot.count}
        </span>
        <h3 className="text-[14px] text-paper">{spot.title}</h3>
      </div>
      <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-paper-dim">
        {spot.explanation}
      </p>
    </li>
  );
}
