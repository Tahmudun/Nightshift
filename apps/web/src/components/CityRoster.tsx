'use client';

/**
 * Who is hiring, in what order you asked for, and a way to reach every role.
 *
 * This is the half of `city.md` §4.8 that the beacons cannot be: *"a legible,
 * navigable, sortable field of signals"*. The plates in the scene say which
 * column is which; this says what the whole field contains, lets a person
 * choose how it is ordered, flies the camera to any column in it, and — since
 * Task 4 — opens any individual role.
 *
 * **It is also the field's non-3D equivalent, which §5.6 requires.** Every
 * employer on the map is a row here and every beacon is a row inside that,
 * reachable by tab and readable by a screen reader. Selecting a role from this
 * list and selecting the same role by clicking its beacon are the same action
 * on the same piece of state; there is no path through the canvas that does not
 * have one through here. A person who cannot use the canvas loses the view, not
 * the information.
 *
 * **It renders no map and holds no map state.** It reads the same store the
 * renderer reads and calls one method on the camera. Changing the sort writes
 * one value; the custom layer picks that up outside React and rebuilds its
 * instance buffer, so reordering thousands of beacons re-renders this list and
 * nothing else (§5.5, `CLAUDE.md` §8).
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { MAX_LABELS } from '@/lib/city/labelAtlas';
import { focusColumn } from '@/lib/city/focus';
import { useCityScene, visibleSignalsOf } from '@/lib/city/scene';
import type { SignalTreatment } from '@/lib/city/treatments';
import { arrangeUnresolved, FIELD_SORTS, type FieldSort } from '@/lib/city/unresolvedField';

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
 * The one word a row shows for whatever §6 has put on its beacon.
 *
 * At most one, and in this order: what you did about the role beats why it is
 * lit, which beats how new it is. A row 21rem wide cannot carry three labels,
 * and a person scanning a list wants the strongest fact — the detail panel
 * carries all of them in full when the role is selected.
 *
 * Deliberately not colour-coded to match the beacon. The row is 12px text and
 * `ink-450` — the archived shade — is a surface colour that fails contrast as
 * text; §12.4 is satisfied here by the *word*, which is the whole point of the
 * row existing.
 */
function rowMarkOf(treatment: SignalTreatment | undefined): ReactNode {
  if (treatment === undefined) return null;

  const label =
    treatment.track === 'offer'
      ? 'Offer'
      : treatment.track === 'in_process'
        ? 'Interview'
        : treatment.track === 'applied'
          ? 'Applied'
          : treatment.track === 'saved'
            ? 'Saved'
            : treatment.track === 'archived'
              ? 'Archived'
              : treatment.beam === 'deadline'
                ? 'Deadline'
                : treatment.beam === 'match'
                  ? 'Strong match'
                  : treatment.pulse !== 'none'
                    ? 'New'
                    : null;

  if (label === null) return null;
  return (
    <span className="shrink-0 font-mono text-[9px] tracking-[0.12em] text-paper-faint uppercase">
      {label}
    </span>
  );
}

export function CityRoster() {
  const signals = useCityScene((state) => state.signals);
  const status = useCityScene((state) => state.status);
  const sort = useCityScene((state) => state.sort);
  const setSort = useCityScene((state) => state.setSort);
  const camera = useCityScene((state) => state.camera);
  const selected = useCityScene((state) => state.selected);
  const select = useCityScene((state) => state.select);
  const treatments = useCityScene((state) => state.treatments);
  const showArchived = useCityScene((state) => state.showArchived);

  /** Which column the camera was last sent to. Navigation, not selection. */
  const [visited, setVisited] = useState<string | null>(null);
  /** Which employer's roles are showing. One at a time; the rail is 21rem wide. */
  const [opened, setOpened] = useState<string | null>(null);

  // The same pure function the renderer calls, with the same arguments, so the
  // list and the field cannot disagree about what is in the city, what order it
  // is in, or which beacon a row belongs to. Memoised because it runs over the
  // whole corpus and this component re-renders on every sort change.
  // `visibleSignalsOf`, not `signals`: §6 keeps rejections off the city by
  // default, and a list that still showed them would let a person click a row
  // for a beacon that is not there. One filter, shared with the renderer.
  const visible = useMemo(
    () => visibleSignalsOf({ signals, treatments, showArchived }),
    [signals, treatments, showArchived],
  );

  const { columns } = useMemo(() => arrangeUnresolved(visible, sort), [visible, sort]);

  /** Titles for the ids the field hands back. The field owns order, not text. */
  const titles = useMemo(
    () => new Map(visible.map((signal) => [signal.job_id, signal.title])),
    [visible],
  );

  const employerOf = useMemo(
    () => new Map(visible.map((signal) => [signal.job_id, signal.company_id])),
    [visible],
  );
  const selectedEmployer = selected === null ? null : (employerOf.get(selected) ?? null);

  /**
   * A selection made anywhere opens the employer it belongs to.
   *
   * This is the list half of list↔map sync, and it is the half that is easy to
   * skip: without it, clicking a beacon highlights a row that is inside a
   * collapsed group, so the list silently disagrees with the map about what is
   * being shown. The person can still collapse it afterwards — this fires on a
   * *change* of employer, not on every render.
   */
  useEffect(() => {
    if (selectedEmployer !== null) setOpened(selectedEmployer);
  }, [selectedEmployer]);

  /**
   * And scroll it into view, because opening a group off-screen is not showing
   * it. `block: 'nearest'` moves the minimum and does nothing when the row is
   * already visible, so a selection made *in* this list does not jump.
   */
  const selectedRow = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (selected !== null) selectedRow.current?.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  if (status.kind !== 'ready' || columns.length === 0) return null;

  const unlabelled = Math.max(0, columns.length - MAX_LABELS);
  const roles = columns.reduce((sum, column) => sum + column.jobIds.length, 0);

  function open(companyId: string, x: number, y: number): void {
    setVisited(companyId);
    setOpened((current) => (current === companyId ? null : companyId));
    focusColumn(camera, x, y);
  }

  return (
    // Natural height, and `shrink-0` like every other panel in the rail: the
    // rail is the scroll container now, so nothing here competes for a fixed
    // budget. See `CityRail` for why that turned out to matter at three rows.
    <section aria-labelledby="city-roster-heading" className={`flex shrink-0 flex-col ${PANEL}`}>
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

      <ul>
        {columns.map((column, index) => {
          const isOpen = opened === column.companyId;
          return (
            <li key={column.companyId}>
              <button
                type="button"
                onClick={() => open(column.companyId, column.x, column.y)}
                aria-expanded={isOpen}
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
                <span className="min-w-0 flex-1 truncate text-[13px] text-paper">
                  {column.name}
                </span>
                <span className="shrink-0 font-mono text-[11px] text-signal-400 tabular-nums">
                  {column.jobIds.length}
                </span>
              </button>

              {isOpen && (
                // Top of the list is the top of the stack in the scene, so the
                // reading order matches what a person is looking at rather than
                // the buffer's own bottom-up order.
                <ul className="border-b border-ink-800/70 bg-ink-900/40">
                  {[...column.jobIds].reverse().map((jobId) => {
                    const isSelected = jobId === selected;
                    return (
                      <li key={jobId}>
                        <button
                          type="button"
                          ref={isSelected ? selectedRow : undefined}
                          onClick={() => select(isSelected ? null : jobId)}
                          aria-current={isSelected ? 'true' : undefined}
                          className={`flex w-full items-baseline gap-2 py-1.5 pr-4 pl-10 text-left text-[12px] transition-colors hover:bg-ink-800/60 ${
                            isSelected
                              ? 'bg-signal-900/60 text-signal-400'
                              : 'text-paper-dim hover:text-paper'
                          }`}
                        >
                          <span
                            aria-hidden="true"
                            className={`shrink-0 font-mono text-[10px] ${
                              isSelected ? 'text-signal-400' : 'text-paper-faint'
                            }`}
                          >
                            {isSelected ? '◆' : '◇'}
                          </span>
                          <span className="min-w-0 flex-1">{titles.get(jobId) ?? jobId}</span>
                          {/* The §6 marks, in a word, on the row that stands
                              for the beacon carrying them. §5.6 asks the list
                              to be an equal view rather than a poorer one, and
                              a row that says only the title is poorer by
                              exactly the encoding. The full sentence is in the
                              detail panel; this is the glance. */}
                          {rowMarkOf(treatments.get(jobId))}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
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
