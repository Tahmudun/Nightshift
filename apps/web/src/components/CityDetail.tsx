'use client';

/**
 * The selected role: what it is, what its position on this map does and does
 * not mean, and the two things you can do about it.
 *
 * This is the rest of `city.md` §4.8's sentence. Task 3 made the field
 * *findable* — legible, navigable, sortable — and §4.8 asks for three more
 * verbs: a role must be **inspected, saved and applied to**. Inspection is this
 * panel; saving and applying are `SaveJobButton`, which is the same control the
 * list uses and reaches the same append-only application record, because a
 * second way to save a job is a second place for the truth about it to live.
 *
 * **It also owns the URL, and it is the only thing that does.** §5.6 asks a
 * selection to be shareable and to preserve filters. Every other control here
 * — the beacons, the roster rows, escape, the close button — writes to the
 * scene store and nothing else; this component is the single seam between that
 * store and the address bar. The alternative, where each control builds its own
 * href, is how one of them ends up dropping the query it was supposed to keep.
 *
 * **It renders no map.** It reads the store the renderer reads and calls one
 * function on the camera (`focusColumn`). The reticle in the scene is drawn by
 * the custom layer subscribing to the same store, outside React — a selection
 * changing moves one mesh, it does not re-render anything holding a WebGL
 * context (`city.md` §5.5, `CLAUDE.md` §8).
 */

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useRef } from 'react';

import { SaveJobButton } from './SaveJobButton';
import { focusColumn } from '@/lib/city/focus';
import { useCityScene, visibleSignalsOf } from '@/lib/city/scene';
import type { SignalTreatment } from '@/lib/city/treatments';
import { selectionFromParams, selectionHref } from '@/lib/city/selection';
import { arrangeUnresolved } from '@/lib/city/unresolvedField';
import { EMPLOYMENT_LABELS, REMOTE_LABELS } from '@/lib/jobLabels';
import type { CitySignal, JobStatus } from '@/lib/schemas';

const PANEL = 'pointer-events-auto border border-signal-400/40 bg-ink-950/85 backdrop-blur-md';

const CHIP = 'inline-block border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em]';

/**
 * What each status means for a role you are looking at *right now*.
 *
 * Spelled out rather than shown as a bare enum because three of the four are
 * claims about our own knowledge rather than about the employer: I3 says a
 * source going quiet is not evidence a job closed, and `possibly_stale` is that
 * invariant surfacing in the interface. A person reading "possibly stale" with
 * no gloss will read it as "probably gone", which is the opposite of what it
 * records.
 */
const STATUS_NOTE: Record<JobStatus, { readonly label: string; readonly means: string }> = {
  open: { label: 'Open', means: 'Seen in the employer’s own board on the last poll.' },
  possibly_stale: {
    label: 'Possibly stale',
    means: 'Not seen recently. That is a gap in our observation, not a statement that it closed.',
  },
  unverified: {
    label: 'Unverified',
    means: 'We have not been able to re-check this listing against its source.',
  },
  closed: { label: 'Closed', means: 'Observed removed from the employer’s own board.' },
};

/** Whole days between an ISO timestamp and now, floored. */
export function daysSince(iso: string, now: number = Date.now()): number {
  return Math.max(0, Math.floor((now - Date.parse(iso)) / 86_400_000));
}

/**
 * Every §6 mark this role is carrying, in words.
 *
 * §5.6 requires a non-3D equivalent for everything the map says, and §12.4
 * requires that colour never carry a meaning alone. Both are satisfied by the
 * same paragraph: a person who cannot see the canvas — or who cannot tell gold
 * from cyan on it — reads the encoding here instead of inferring it.
 *
 * Order matters. The lifecycle mark comes first because it is the one about
 * *you*, then the reason the role is lit, then the pulse, which is the weakest
 * claim of the three.
 */
export function marksOf(signal: CitySignal, treatment: SignalTreatment | undefined): string[] {
  if (treatment === undefined) return [];
  const marks: string[] = [];

  if (treatment.track === 'saved') marks.push('Saved — a thin white outline on its beacon’s body.');
  if (treatment.track === 'applied') marks.push('Applied — the beacon is filled and fully lit.');
  if (treatment.track === 'in_process') {
    marks.push('Assessment or interview — a ring turns around it.');
  }
  if (treatment.track === 'offer') marks.push('An offer — a green core inside the beacon.');
  if (treatment.track === 'archived') {
    marks.push('Archived — drawn dim and neutral, and hidden unless you ask for it.');
  }

  if (treatment.beam === 'deadline') {
    marks.push('A gold beam: the deadline on this posting is close.');
  }
  if (treatment.beam === 'match') {
    marks.push(
      'A gold beam: this scored near the top of what could be assessed, and cleared the ' +
        'eligibility gate. The breakdown is on the role’s own page — the beam is a pointer, ' +
        'not the evidence.',
    );
  }

  if (treatment.pulse === 'rapid') marks.push('New internship — its beacon pulses quickly.');
  if (treatment.pulse === 'slow') marks.push('New role — its beacon pulses slowly.');

  if (treatment.dimmed) marks.push(`Drawn faint: ${freshnessPhrase(signal)}`);

  return marks;
}

/**
 * What "we have not re-checked this" actually amounts to, for this role.
 *
 * Two observations, kept apart, because ADR 0007's phase-2 polling never
 * refetches an unchanged posting: `last_seen_at` is "the board listed it" and
 * `last_verified_at` is "we read its text". A panel that printed one under the
 * other's name would be inventing an observation, which is I3's failure mode
 * with a date on it.
 */
function freshnessPhrase(signal: CitySignal): string {
  const listed = `listed on its board ${phraseFor(daysSince(signal.last_seen_at))}`;
  if (signal.last_verified_at === null) {
    return `${listed}, and its text has never been re-read.`;
  }
  return `${listed}, and its text last read ${phraseFor(daysSince(signal.last_verified_at))}.`;
}

function phraseFor(days: number): string {
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  return `${days.toLocaleString('en-US')} days ago`;
}

function firstSeenPhrase(iso: string): string {
  return phraseFor(daysSince(iso));
}

/**
 * What this role's position on the map is permitted to mean.
 *
 * The unresolved sentence is the one that matters and it is the reason this
 * panel exists in the shape it does: the beacon *is* somewhere, on a screen,
 * above New York, and a person will read a position as a location unless they
 * are told otherwise in the place they are looking. I1 is not satisfied by a
 * comment in the source.
 */
function placementAccount(signal: CitySignal): {
  readonly heading: string;
  readonly body: string;
} {
  const { placement } = signal;
  if (placement.kind === 'unresolved') {
    return {
      heading: 'Floating — no confirmed address',
      body:
        'This role is drawn above the city, connected to nothing. Its position encodes its ' +
        'employer and its place in the stack, and nothing whatsoever about where in New York ' +
        'the work happens.',
    };
  }
  if (placement.kind === 'area') {
    return {
      heading: 'An area, not a point',
      body:
        'This role is drawn over a region rather than a structure. The coordinate is ' +
        'approximate and no building is being claimed.',
    };
  }
  return {
    heading: placement.inherited ? 'On its employer’s confirmed office' : 'On a confirmed address',
    body: placement.inherited
      ? `The posting itself named no street. It is drawn at ${
          placement.office_label ?? 'an office'
        } — an address a person confirmed — which is a fact about the employer, not about this ` +
        'listing.'
      : 'This posting named an address that resolved to a specific structure.',
  };
}

export function CityDetail() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const signals = useCityScene((state) => state.signals);
  const sort = useCityScene((state) => state.sort);
  const selected = useCityScene((state) => state.selected);
  const treatments = useCityScene((state) => state.treatments);
  const showArchived = useCityScene((state) => state.showArchived);
  const select = useCityScene((state) => state.select);
  const camera = useCityScene((state) => state.camera);

  const urlSelection = selectionFromParams(searchParams);

  /**
   * The last value the URL and the store were known to agree on.
   *
   * One ref, one effect, and the direction of the sync decided by *which side
   * changed* — which is the only version of this that converges. Two effects,
   * one each way, ping-pong: the store-to-URL effect closes over the selection
   * from the render before the URL-to-store effect adopted a deep link, so
   * landing on `?job=…` immediately rewrites the URL to remove it.
   */
  const agreed = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    const first = agreed.current === undefined;

    if (first && urlSelection === null) {
      // Arrived with nothing shared. There is no selection to adopt, so the
      // city's own is the truth — start from it rather than from null, which
      // would delete a selection made before this panel mounted.
      agreed.current = null;
    } else if (first || urlSelection !== agreed.current) {
      // The URL is the truth: a deep link on the way in, or the back button.
      agreed.current = urlSelection;
      // Read the live value rather than the render's. On the first pass this
      // effect runs before React has re-rendered with anything it just set,
      // and comparing against a stale `selected` is how an adopted deep link
      // gets written straight back out as a removal.
      if (useCityScene.getState().selected !== urlSelection) select(urlSelection);
      return;
    }

    if (selected !== agreed.current) {
      // The city moved: a beacon, a roster row, escape. Write it down.
      agreed.current = selected;
      // `replace`, not `push`: clicking through a field of beacons must not
      // fill the back stack with one entry per role, the same rule the filters
      // in `/explore` follow. `scroll: false` because this page does not
      // scroll and a scroll reset would fight the map.
      router.replace(selectionHref(pathname, searchParams, selected), { scroll: false });
    }
  }, [urlSelection, selected, select, router, pathname, searchParams]);

  // The same pure function the renderer and the roster call, with the same
  // arguments — so the panel cannot describe a role in a position the field
  // does not put it in.
  // The same filtered list the renderer and the roster use — the panel places
  // the camera from these coordinates, so a field it disagreed with would fly
  // to the wrong column.
  const visible = useMemo(
    () => visibleSignalsOf({ signals, treatments, showArchived }),
    [signals, treatments, showArchived],
  );

  const { placements } = useMemo(() => arrangeUnresolved(visible, sort), [visible, sort]);

  const signal = useMemo(
    () => (selected === null ? null : (signals.find((s) => s.job_id === selected) ?? null)),
    [signals, selected],
  );

  /**
   * Escape clears the selection, from anywhere on the page.
   *
   * On `document` rather than on the map, because focus is as likely to be in
   * this panel or in the roster as on the canvas. The camera's own container
   * listener runs first when focus *is* on the canvas — it bubbles from deeper
   * — so the camera stops before the selection goes, which is the order
   * `camera.ts` wrote down when it left this half for M4c: a person should be
   * looking at a still frame by the time anything else happens.
   */
  useEffect(() => {
    if (selected === null) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') select(null);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [selected, select]);

  /**
   * Bring the selected role on screen — **only if it is not already**.
   *
   * §5.6. `focusOn` answers that question itself and returns false when it
   * declines, so a click on a beacon the person is already looking at costs no
   * camera movement at all, and a deep link into a role across the city flies.
   */
  const placement = placements.find((p) => p.jobId === selected);
  const focusX = placement?.x;
  const focusY = placement?.y;
  useEffect(() => {
    if (focusX === undefined || focusY === undefined) return;
    focusColumn(camera, focusX, focusY);
  }, [camera, focusX, focusY]);

  /**
   * Bring the panel itself on screen.
   *
   * The rail is one scroll container (see `CityRail`), so on a short window a
   * person who has scrolled down the roster and then clicks a beacon gets a
   * panel that opens *above* their scroll position — the map appears to have
   * swallowed the click. `block: 'nearest'` scrolls the minimum needed and
   * does nothing at all when the panel is already visible.
   */
  const panel = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (selected !== null) panel.current?.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  if (selected === null) return null;

  // A selection that names no role in the corpus. Reachable two honest ways: a
  // shared link to a role that has since closed, and a poll that removed one
  // while the panel was open. Saying nothing would leave a reticle-less city
  // with an inexplicable `?job=` in the URL.
  if (signal === null) {
    return (
      <section
        ref={panel}
        aria-labelledby="city-detail-heading"
        data-testid="city-detail"
        className={`shrink-0 p-4 ${PANEL}`}
      >
        <h2
          id="city-detail-heading"
          className="font-mono text-[10px] tracking-[0.16em] text-gold-400 uppercase"
        >
          That role is not on this city
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-paper-dim">
          The link names a role that is not in the corpus this map is showing. It may have closed,
          or it may never have been here.
        </p>
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => select(null)}
            className={`${CHIP} border-ink-700 text-paper-dim hover:border-signal-400 hover:text-signal-400`}
          >
            Clear
          </button>
          <Link
            href={`/explore/jobs/${selected}`}
            className={`${CHIP} border-ink-700 text-paper-dim hover:border-signal-400 hover:text-signal-400`}
          >
            Look it up in the list
          </Link>
        </div>
      </section>
    );
  }

  const account = placementAccount(signal);
  const status = STATUS_NOTE[signal.status];
  const marks = marksOf(signal, treatments.get(signal.job_id));

  return (
    <section
      ref={panel}
      aria-labelledby="city-detail-heading"
      data-testid="city-detail"
      className={`shrink-0 ${PANEL}`}
    >
      <div className="flex items-start gap-3 border-b border-ink-700/80 p-4 pb-3">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[10px] tracking-[0.16em] text-signal-400 uppercase">
            Selected role
          </p>
          <h2 id="city-detail-heading" className="mt-1 text-[15px] leading-snug text-paper">
            {signal.title}
          </h2>
          <Link
            href={`/explore/companies/${signal.company_id}`}
            className="mt-0.5 inline-block text-[13px] text-paper-dim hover:text-signal-400"
          >
            {signal.company_name}
          </Link>
        </div>
        {/* Not an icon. The one thing a person needs to be able to find without
            learning the interface is the way out of it. */}
        <button
          type="button"
          onClick={() => select(null)}
          className="shrink-0 border border-ink-700 px-2 py-1 font-mono text-[10px] tracking-[0.14em] text-paper-faint uppercase hover:border-signal-400 hover:text-signal-400"
        >
          Close
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-ink-700/80 p-4 py-3">
        <span className={`${CHIP} border-ink-600 text-paper-dim`}>
          {EMPLOYMENT_LABELS[signal.employment_type]}
        </span>
        <span className={`${CHIP} border-ink-600 text-paper-dim`}>
          {REMOTE_LABELS[signal.remote_policy]}
        </span>
        <SaveJobButton jobId={signal.job_id} />
      </div>

      <div className="space-y-3 p-4">
        {/* The position, explained where the position is being looked at. */}
        <div>
          <h3 className="font-mono text-[10px] tracking-[0.14em] text-paper-faint uppercase">
            {account.heading}
          </h3>
          <p className="mt-1 text-[12px] leading-relaxed text-paper-dim">{account.body}</p>
          {signal.placement.stated !== null && (
            // The source's own words, quoted and attributed. §4.1 measured that
            // this is almost always "New York, NY" — showing it is what makes
            // the floating beacon legible rather than mysterious.
            <p className="mt-1.5 text-[12px] leading-relaxed text-paper-dim">
              The posting says:{' '}
              <span className="font-mono text-[11px] text-paper">“{signal.placement.stated}”</span>
            </p>
          )}
        </div>

        <div>
          <h3 className="font-mono text-[10px] tracking-[0.14em] text-paper-faint uppercase">
            {status.label}
          </h3>
          <p className="mt-1 text-[12px] leading-relaxed text-paper-dim">{status.means}</p>
        </div>

        {marks.length > 0 && (
          // §5.6's non-3D equivalent for the one thing the canvas says that no
          // other panel does: what this particular beacon looks like, and why.
          <div>
            <h3 className="font-mono text-[10px] tracking-[0.14em] text-paper-faint uppercase">
              How this role is drawn
            </h3>
            <ul className="mt-1 space-y-1">
              {marks.map((mark) => (
                <li key={mark} className="text-[12px] leading-relaxed text-paper-dim">
                  {mark}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Labelled for what it is. "First seen" is our observation; no ATS in
            this corpus reports a publication date we would trust, so this is
            never rendered as "Posted". */}
        <p className="text-[12px] leading-relaxed text-paper-dim">
          First seen by ingestion{' '}
          <span className="text-paper">{firstSeenPhrase(signal.first_seen_at)}</span>.
        </p>

        <Link
          href={`/explore/jobs/${signal.job_id}`}
          className="inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] tracking-[0.14em] text-signal-400 uppercase hover:border-signal-400"
        >
          Open the full role
        </Link>
      </div>
    </section>
  );
}
