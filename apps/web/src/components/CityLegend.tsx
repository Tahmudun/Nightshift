'use client';

/**
 * What the marks on the city mean — in the interface, not only in the docs.
 *
 * PRODUCT-SPEC §4.3's last line is a deliverable and `city.md` §6 repeats it:
 * "these meanings are documented **in the interface**, on a legend the user can
 * open, not only in this file". A visual language nobody can look up is
 * decoration, and worse, it is decoration a person will invent their own
 * meanings for.
 *
 * Three things make this more than a paint chart.
 *
 * **It counts.** Every row says how many roles carry it right now. A legend
 * that lists a gold beam on a city with no gold on it teaches a language nobody
 * will ever hear spoken, and a count of zero is the honest way to say so.
 *
 * **It lists the rows that are not drawn.** Two of §6's twelve cannot be drawn
 * on this corpus, and each says why in its own words. Hiding them would
 * document the renderer rather than the language, and would quietly shrink the
 * table every time something was deferred (I7).
 *
 * **It owns the archive toggle**, because that is where a person looks after
 * reading the row that says rejections are hidden.
 */

import { useMemo, useState } from 'react';

import { useCityScene } from '@/lib/city/scene';
import { useCityTreatments } from '@/lib/city/useTreatments';
import { archivedCount, TREATMENTS, type TreatmentRow } from '@/lib/city/treatments';
import type { CitySignal } from '@/lib/schemas';
import type { SignalTreatment } from '@/lib/city/treatments';

const PANEL = 'pointer-events-auto border border-ink-700/80 bg-ink-950/70 backdrop-blur-md';

/**
 * The Tailwind class for each swatch, written out rather than interpolated.
 *
 * `bg-${token}` does not survive Tailwind's build: the scanner reads source
 * text and cannot see a class that is assembled at runtime, so every swatch
 * would be transparent. A record is the version of this that ships.
 */
const SWATCH: Record<string, string> = {
  'signal-400': 'bg-signal-400',
  'gold-400': 'bg-gold-400',
  'verdant-400': 'bg-verdant-400',
  paper: 'bg-paper',
  'ink-450': 'bg-ink-450',
};

/**
 * How many roles on the city carry each row of §6, right now.
 *
 * Derived from the same treatment map the renderer reads, so the legend cannot
 * claim a count the city does not draw.
 */
export function countTreatments(
  signals: readonly CitySignal[],
  treatments: ReadonlyMap<string, SignalTreatment>,
): Record<string, number> {
  const counts: Record<string, number> = {};
  const bump = (id: string): void => {
    counts[id] = (counts[id] ?? 0) + 1;
  };

  for (const signal of signals) {
    const treatment = treatments.get(signal.job_id);
    if (treatment === undefined) continue;
    if (treatment.pulse === 'rapid') bump('new_internship');
    if (treatment.pulse === 'slow') bump('new_role');
    if (treatment.track === 'saved') bump('saved');
    if (treatment.track === 'applied') bump('applied');
    if (treatment.track === 'in_process') bump('in_process');
    if (treatment.track === 'offer') bump('offer');
    if (treatment.track === 'archived') bump('archived');
    if (treatment.beam !== 'none') bump('standout');
    if (treatment.dimmed) bump('stale');
    if (signal.placement.kind === 'unresolved') bump('unresolved');
    if (signal.placement.kind === 'area') bump('approximate');
  }
  return counts;
}

function Row({ row, count }: { readonly row: TreatmentRow; readonly count: number }) {
  const deferred = row.status.kind === 'deferred';
  return (
    <li className="flex gap-3 border-t border-ink-800/70 px-4 py-2.5 first:border-t-0">
      {/* The swatch is a block and never text: `ink-450` is a surface shade and
          would fail contrast as a label. The shape is spelled out beside it, so
          the row survives a reader who cannot tell cyan from gold (§12.4). */}
      <span
        aria-hidden="true"
        className={`mt-1 h-2.5 w-2.5 shrink-0 ${
          row.swatch === null ? 'border border-paper-faint' : (SWATCH[row.swatch] ?? 'bg-paper')
        } ${deferred ? 'opacity-30' : ''}`}
      />
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-2">
          <span className={`text-[12px] ${deferred ? 'text-paper-faint' : 'text-paper'}`}>
            {row.label}
          </span>
          <span className="font-mono text-[10px] tracking-[0.12em] text-paper-faint uppercase">
            {row.form}
          </span>
          {!deferred && (
            <span
              className={`ml-auto shrink-0 font-mono text-[11px] tabular-nums ${
                count > 0 ? 'text-signal-400' : 'text-paper-faint'
              }`}
            >
              {count.toLocaleString('en-US')}
            </span>
          )}
        </p>
        <p className="mt-0.5 text-[11px] leading-relaxed text-paper-dim">{row.means}</p>
        {row.status.kind === 'deferred' && (
          // Named as not-drawn, in the interface, with the reason. I7: a mock
          // presented as working functionality is the worst failure available,
          // and a legend is the easiest place in a product to commit it.
          <p className="mt-1 border-l-2 border-gold-400/50 pl-2 text-[11px] leading-relaxed text-gold-400">
            Not drawn on this city. {row.status.because}
          </p>
        )}
      </div>
    </li>
  );
}

export function CityLegend() {
  // The two fetches §6's lifecycle rows need. Here rather than in `CityRail`
  // because this is the panel that explains what they produce.
  useCityTreatments();

  const signals = useCityScene((state) => state.signals);
  const treatments = useCityScene((state) => state.treatments);
  const showArchived = useCityScene((state) => state.showArchived);
  const setShowArchived = useCityScene((state) => state.setShowArchived);
  const status = useCityScene((state) => state.status);

  const [open, setOpen] = useState(false);

  const counts = useMemo(() => countTreatments(signals, treatments), [signals, treatments]);
  const archived = useMemo(() => archivedCount(signals, treatments), [signals, treatments]);

  if (status.kind !== 'ready') return null;

  return (
    <section aria-labelledby="city-legend-heading" className={`shrink-0 ${PANEL}`}>
      {/* A disclosure rather than an always-open panel: the rail is already
          three panels tall on a laptop, and a legend is something a person
          reaches for rather than reads continuously. */}
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 p-4 text-left hover:bg-ink-800/40"
      >
        <h2
          id="city-legend-heading"
          className="font-mono text-[10px] tracking-[0.16em] text-paper-faint uppercase"
        >
          What the marks mean
        </h2>
        <span aria-hidden="true" className="ml-auto font-mono text-[10px] text-paper-faint">
          {open ? '−' : '+'}
        </span>
      </button>

      {open && (
        <>
          <ul>
            {TREATMENTS.map((row) => (
              <Row key={row.id} row={row} count={counts[row.id] ?? 0} />
            ))}
          </ul>

          <div className="border-t border-ink-700/80 p-4">
            <label className="flex cursor-pointer items-start gap-2 text-[12px] leading-relaxed text-paper-dim">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(event) => setShowArchived(event.target.checked)}
                className="mt-0.5 accent-signal-400"
              />
              <span>
                Show rejected and withdrawn roles
                <span className="text-paper-faint">
                  {' · '}
                  {archived.toLocaleString('en-US')} hidden
                </span>
              </span>
            </label>
          </div>
        </>
      )}
    </section>
  );
}
