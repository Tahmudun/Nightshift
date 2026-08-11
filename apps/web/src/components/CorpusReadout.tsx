'use client';

/**
 * The corpus readout: what is in the database, and how well it is located.
 *
 * The "mappable" figure is the important one and it is stated plainly rather
 * than buried. A dashboard that omitted that number until it looked good would
 * be the first step toward the fabrication invariant I1 exists to prevent.
 *
 * It reads zero, and the *reason* changed at M4a. Through M3 it was "nothing
 * has been geocoded", which was true — no geocoder existed. One exists now, and
 * the number is still zero for a better reason: M4a measured that no ATS
 * posting in the corpus names a street, so no posting can place itself. A job
 * reaches a building only by inheriting an office a human confirmed, and that
 * inheritance is a read-time join (city.md §4.4) rather than a row here.
 *
 * The note says so, because "nothing geocoded yet" would now describe a missing
 * feature instead of a property of the data — and the second is the honest and
 * more interesting statement.
 */

import { useQuery } from '@tanstack/react-query';

import { fetchStats } from '@/lib/api';
import { CONFIDENCE_SCALE } from '@/lib/confidence';

function Readout({
  label,
  value,
  note,
}: {
  readonly label: string;
  readonly value: string;
  readonly note?: string;
}) {
  return (
    <div className="border-l border-ink-700 px-4 py-1 first:border-l-0 first:pl-0">
      <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-paper-faint">{label}</p>
      <p className="mt-1 text-[20px] font-medium tracking-tight text-paper tnum">{value}</p>
      {note !== undefined ? (
        <p className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-paper-faint">
          {note}
        </p>
      ) : null}
    </div>
  );
}

export function CorpusReadout() {
  const { data, error } = useQuery({ queryKey: ['stats'], queryFn: fetchStats });

  if (error !== null || data === undefined) {
    return null;
  }

  const total = Object.values(data.location_confidence).reduce((sum, count) => sum + count, 0);

  return (
    <section aria-label="Corpus summary" className="space-y-4">
      <div className="flex flex-wrap gap-y-3">
        <Readout label="Roles" value={String(data.total_jobs)} note={`${data.open_jobs} open`} />
        <Readout label="Companies" value={String(data.total_companies)} />
        <Readout
          label="Raw source records"
          value={String(data.total_source_records)}
          note="provenance preserved"
        />
        <Readout
          label="Placeable on a map"
          value={String(data.mappable_locations)}
          note={
            data.mappable_locations === 0 ? 'no posting states a street' : 'verified or approximate'
          }
        />
      </div>

      {/* A single stacked bar of the confidence distribution. One bar, labelled
       * beneath — not four separate charts, and not a donut. */}
      {total > 0 ? (
        <div>
          <div className="flex h-1.5 w-full overflow-hidden border border-ink-700">
            {CONFIDENCE_SCALE.map((step) => {
              const count = data.location_confidence[step.value];
              if (count === 0) return null;
              return (
                <div
                  key={step.value}
                  style={{ width: `${(count / total) * 100}%` }}
                  className={
                    step.mappable
                      ? 'bg-signal-400'
                      : step.rank >= 3
                        ? 'bg-signal-600'
                        : 'bg-ink-600'
                  }
                  title={`${step.label}: ${count}`}
                />
              );
            })}
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
            {CONFIDENCE_SCALE.map((step) => (
              <li
                key={step.value}
                className="font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint tnum"
              >
                {step.label}{' '}
                <span className={data.location_confidence[step.value] > 0 ? 'text-paper-dim' : ''}>
                  {data.location_confidence[step.value]}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
