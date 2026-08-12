'use client';

/**
 * Who is hiring, in what order you asked for, and a way to reach each of them.
 *
 * This is the half of `city.md` §4.8 that the beacons cannot be: *"a legible,
 * navigable, sortable field of signals"*. The plates in the scene say which
 * column is which; this says what the whole field contains, lets a person
 * choose how it is ordered, and flies the camera to any column in it.
 *
 * **It is also the field's non-3D equivalent, which §5.6 requires.** Every
 * employer on the map is a row here, reachable by tab and readable by a screen
 * reader, and the counts are text rather than a shape in a WebGL buffer. A
 * person who cannot use the canvas loses the view, not the information.
 *
 * **It renders no map and holds no map state.** It reads the same store the
 * renderer reads and calls one method on the camera. Changing the sort writes
 * one value; the custom layer picks that up outside React and rebuilds its
 * instance buffer, so reordering thousands of beacons re-renders this list and
 * nothing else (§5.5, `CLAUDE.md` §8).
 */

import { useMemo, useState } from 'react';

import { MAX_LABELS } from '@/lib/city/labelAtlas';
import { lngLatFromScene } from '@/lib/city/mercator';
import { useCityScene } from '@/lib/city/scene';
import { arrangeUnresolved, FIELD_SORTS, type FieldSort } from '@/lib/city/unresolvedField';
import { INITIAL_POSE } from '@/lib/map/camera';

const PANEL = 'pointer-events-auto border border-ink-700/80 bg-ink-950/70 backdrop-blur-md';

/**
 * What each ordering is called, and what it means.
 *
 * The description is not decoration: "newest" is ambiguous about *what* is
 * newest — the employer or the role — and a column ordered by its most recent
 * opening is a rule a person has to be told, not one they can infer from a
 * three-word label.
 */
const SORT_LABELS: Record<FieldSort, { readonly label: string; readonly means: string }> = {
  company: { label: 'Name', means: 'Employers A to Z.' },
  openings: { label: 'Openings', means: 'Most open roles first.' },
  newest: { label: 'Newest', means: 'The employer whose newest role we saw most recently, first.' },
};

/**
 * The zoom a column is read from.
 *
 * Lower than `focusOn`'s own default, which is set for a single building. A
 * column is 620 m from its neighbours and this field is kilometres wide, so
 * arriving at street zoom puts one stack of diamonds across the whole window
 * with nothing around it to say where you are.
 */
const COLUMN_ZOOM = 14;

/**
 * How much of each edge does not count as on screen.
 *
 * Wider than `focusOn`'s own default, and the reason is this panel. The rail
 * is 21rem, which is about a quarter of a laptop window, so a column drawn
 * behind it satisfies the default 18% margin while being completely invisible
 * — the camera then declines to move because the thing you asked for is
 * already "visible", and clicking a row appears to do nothing.
 */
const COLUMN_MARGIN = 0.3;

export function CityRoster() {
  const signals = useCityScene((state) => state.signals);
  const status = useCityScene((state) => state.status);
  const sort = useCityScene((state) => state.sort);
  const setSort = useCityScene((state) => state.setSort);
  const camera = useCityScene((state) => state.camera);

  /** Which column the camera was last sent to. Navigation, not selection. */
  const [visited, setVisited] = useState<string | null>(null);

  // The same pure function the renderer calls, with the same arguments, so the
  // list and the field cannot disagree about what is in the city or what order
  // it is in. Memoised because it runs over the whole corpus and this
  // component re-renders on every sort change.
  const { columns } = useMemo(() => arrangeUnresolved(signals, sort), [signals, sort]);

  const unlabelled = Math.max(0, columns.length - MAX_LABELS);

  if (status.kind !== 'ready' || columns.length === 0) return null;

  const roles = columns.reduce((sum, column) => sum + column.roles, 0);

  function focus(x: number, y: number, companyId: string): void {
    setVisited(companyId);
    // The anchor is the pose the scene is laid out around — the same one the
    // signal layer is constructed with. Reading it from anywhere else would be
    // a second definition of where the field is.
    camera?.focusOn(lngLatFromScene(INITIAL_POSE.center, x, y), {
      zoom: COLUMN_ZOOM,
      margin: COLUMN_MARGIN,
    });
  }

  return (
    <section aria-labelledby="city-roster-heading" className={`flex min-h-0 flex-col ${PANEL}`}>
      <div className="border-b border-ink-700/80 p-4 pb-3">
        <h2
          id="city-roster-heading"
          className="font-mono text-[10px] tracking-[0.16em] text-paper-faint uppercase"
        >
          Who is hiring
        </h2>
        <p className="mt-1 text-[13px] text-paper">
          {columns.length.toLocaleString('en-US')} {columns.length === 1 ? 'employer' : 'employers'}
          <span className="text-paper-dim">
            {' · '}
            {roles.toLocaleString('en-US')} {roles === 1 ? 'role' : 'roles'}
          </span>
        </p>

        <div role="radiogroup" aria-label="Order the field by" className="mt-3 flex gap-1">
          {FIELD_SORTS.map((option) => {
            const active = option === sort;
            return (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={active}
                title={SORT_LABELS[option].means}
                onClick={() => setSort(option)}
                className={`flex-1 border px-2 py-1.5 font-mono text-[10px] tracking-[0.12em] uppercase transition-colors ${
                  active
                    ? 'border-signal-400 text-signal-400'
                    : 'border-ink-700 text-paper-faint hover:border-ink-500 hover:text-paper-dim'
                }`}
              >
                {SORT_LABELS[option].label}
              </button>
            );
          })}
        </div>
        {/* The rule the chosen order follows, spelled out. A sort a person has
            to reverse-engineer from the result is a sort they cannot trust. */}
        <p className="mt-2 text-[11px] leading-relaxed text-paper-dim">{SORT_LABELS[sort].means}</p>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {columns.map((column, index) => (
          <li key={column.companyId}>
            <button
              type="button"
              onClick={() => focus(column.x, column.y, column.companyId)}
              aria-current={visited === column.companyId ? 'location' : undefined}
              disabled={camera === null}
              className={`flex w-full items-baseline gap-3 border-b border-ink-800/70 px-4 py-2 text-left transition-colors hover:bg-ink-800/50 disabled:cursor-not-allowed disabled:opacity-60 ${
                visited === column.companyId ? 'bg-ink-800/60' : ''
              }`}
            >
              {/* The row's rank under the chosen order — "the third-largest
                  employer", not "the third column from the left". The field is
                  in three dimensions and the camera turns, so left-to-right on
                  screen reverses with the bearing and no number could track
                  it. */}
              <span className="w-6 shrink-0 font-mono text-[10px] text-paper-faint tabular-nums">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1 truncate text-[13px] text-paper">{column.name}</span>
              <span className="shrink-0 font-mono text-[11px] text-signal-400 tabular-nums">
                {column.roles}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {unlabelled > 0 && (
        // Said out loud rather than left to look like a rendering fault. The
        // atlas holds a fixed number of name plates; past it a column is still
        // drawn and still listed here, it just has no name floating over it.
        <p className="border-t border-ink-700/80 px-4 py-2 font-mono text-[10px] leading-relaxed tracking-[0.12em] text-gold-400 uppercase">
          {unlabelled.toLocaleString('en-US')} of these have no name plate on the map — the list
          above is the only place they are named
        </p>
      )}
    </section>
  );
}
