/**
 * `city.md` §6 — what the city encodes — as one table and one pure function.
 *
 * Every mark on a beacon means something about a role, and §6 is where those
 * meanings are decided. This file is where they are *written down once*: the
 * renderer reads it to choose a colour, the legend reads it to explain that
 * colour, and the detail panel reads it to say the same thing in a sentence. A
 * shader that decided its own encoding would be a second copy of this table,
 * free to disagree with the one the legend prints — and a legend that disagrees
 * with the city is worse than no legend, because it is believed.
 *
 * Three rules from §6 shape the shape of it.
 *
 * **Intensity tracks what you can act on, not what happened to you** (A7). A
 * deadline earns gold; a rejection earns dimming and then silence. This is why
 * `archived` suppresses the pulse and the beam rather than layering on top of
 * them, and why nothing in here gets brighter as a process goes badly.
 *
 * **Colour never carries a meaning alone** (§12.4). Every row with a swatch
 * also has a `form` — a shape or a motion — and `treatments.test.ts` asserts
 * that relationship rather than trusting it.
 *
 * **The table is the deliverable, not the subset that is live.** Four rows
 * cannot be drawn on this corpus, and each of them says why in `status`. A
 * legend listing only the drawable rows would document the renderer instead of
 * the language, and would quietly shrink every time something was deferred.
 */

import type { ApplicationStage, CitySignal, EligibilityState } from '@/lib/schemas';

/**
 * How recently a role must have arrived to still count as new, in days.
 *
 * A week, because that is roughly the cadence a person opens this tool at
 * during a search. A window of one day means the pulse is almost never on and
 * the treatment is decorative; a window of a month means it is always on and
 * the treatment says nothing.
 *
 * Measured against `first_seen_at`, which is *our* observation — a role that
 * has been open since spring but reached this database on Tuesday pulses,
 * because it is new to the person reading it, which is the only kind of new
 * this product can honestly claim (no ATS in the corpus publishes a reliable
 * posting date).
 */
export const NEW_WINDOW_DAYS = 7;

/** How close a deadline must be before it earns gold, in days. */
export const URGENT_DEADLINE_DAYS = 14;

/**
 * The fraction of the assessable that counts as exceptional.
 *
 * `fraction` is "of what could be assessed", not "of everything the posting
 * asks", so this is deliberately not a pass mark for the person — it is the
 * threshold at which the ranked list would have put the role near the top. The
 * beacon says "look at this one"; the panel and the job page carry the
 * decomposition, which is what I4 requires of any score that reaches a screen.
 */
export const EXCEPTIONAL_FRACTION = 0.75;

/** What is known about a role's score, as the ranked list reports it. */
export interface MatchStanding {
  /** Of what could be assessed. Null means nothing could be — never a zero. */
  readonly fraction: number | null;
  readonly eligibility: EligibilityState;
}

/**
 * Everything outside the signal itself that a treatment depends on.
 *
 * Passed in rather than fetched here: this module is pure, and the two queries
 * behind it (`/applications`, `/matches`) are already made by the page for
 * other reasons. `now` is a parameter for the same reason it is in
 * `daysSince` — a clock read inside a pure function makes its tests depend on
 * the day they run.
 */
export interface TreatmentContext {
  readonly stages: ReadonlyMap<string, ApplicationStage>;
  readonly matches: ReadonlyMap<string, MatchStanding>;
  readonly now: number;
}

/**
 * Where you and this role stand — the part of §6 that is about your own
 * history with a posting rather than about the posting.
 *
 * One value rather than a set of flags, because these states are genuinely
 * exclusive: an application is at exactly one stage. The beacon draws at most
 * one of these marks and the ordering below is the stage machine's own.
 */
export type TreatmentTrack = 'none' | 'saved' | 'applied' | 'in_process' | 'offer' | 'archived';

/** How fast the cyan pulses, or whether it does. */
export type TreatmentPulse = 'none' | 'slow' | 'rapid';

/** Why a role is lit gold, if it is. */
export type TreatmentBeam = 'none' | 'match' | 'deadline';

/** The marks one role carries. Independent axes, because the facts are. */
export interface SignalTreatment {
  readonly track: TreatmentTrack;
  readonly pulse: TreatmentPulse;
  readonly beam: TreatmentBeam;
  /**
   * Dimmed because *our* knowledge of the listing is old — never because the
   * role is a poor one. §6 is explicit that this is not a glitch: "a glitch
   * reads as a bug, gets reported as one, and then gets ignored", so the panel
   * carries the date beside the dimming.
   */
  readonly dimmed: boolean;
}

/** The mark an application stage earns, or none. */
const TRACK_BY_STAGE: Record<ApplicationStage, TreatmentTrack> = {
  // The three stages before anything has been sent. All of them mean the same
  // thing to a person looking at a skyline: I put this one aside.
  discovered: 'saved',
  saved: 'saved',
  preparing: 'saved',
  applied: 'applied',
  assessment: 'in_process',
  interview: 'in_process',
  offer: 'offer',
  // The archived three. §6 gives rejection a "dim neutral archived state" and
  // is explicit about why it is not a red fracture: this tool is opened daily
  // during a search, and accumulating red across the skyline makes it worse to
  // use over exactly the period it is needed most.
  rejected: 'archived',
  withdrawn: 'archived',
  closed: 'archived',
};

/** Days between two instants, floored, and never negative. */
function daysBetween(from: number, to: number): number {
  return Math.floor((to - from) / 86_400_000);
}

/**
 * Resolve every mark one role carries.
 *
 * Deterministic and total: the same signal and context produce the same
 * treatment, and every role gets one — an untouched, old, unscored posting
 * resolves to a plain beacon rather than to `null`, so no caller has to invent
 * a default.
 */
export function treatmentFor(signal: CitySignal, context: TreatmentContext): SignalTreatment {
  const stage = context.stages.get(signal.job_id);
  const track = stage === undefined ? 'none' : TRACK_BY_STAGE[stage];
  const archived = track === 'archived';

  const dimmed = signal.status === 'possibly_stale' || signal.status === 'unverified';

  return {
    track,
    pulse: archived ? 'none' : pulseFor(signal, context.now, track),
    beam: archived ? 'none' : beamFor(signal, context),
    dimmed,
  };
}

function pulseFor(signal: CitySignal, now: number, track: TreatmentTrack): TreatmentPulse {
  // A role you have acted on is not an invitation to look — A7 again. It keeps
  // the pulse for `saved`, which is a bookmark rather than an action.
  if (track === 'applied' || track === 'in_process' || track === 'offer') return 'none';

  const age = daysBetween(Date.parse(signal.first_seen_at), now);
  if (age >= NEW_WINDOW_DAYS) return 'none';

  // §6 gives the faster pulse to internships, and the reason is seasonal: an
  // internship posting is open for weeks rather than months and the person this
  // product is for is a student. The urgency is real, so it is drawn.
  return signal.employment_type === 'internship' ? 'rapid' : 'slow';
}

function beamFor(signal: CitySignal, context: TreatmentContext): TreatmentBeam {
  if (signal.application_deadline !== null) {
    const remaining = daysBetween(context.now, Date.parse(signal.application_deadline));
    // A window that has closed is not urgent, it is over. Lighting it gold
    // sends a person to a form that will not take them.
    if (remaining >= 0 && remaining < URGENT_DEADLINE_DAYS) return 'deadline';
  }

  const match = context.matches.get(signal.job_id);
  if (match === undefined) return 'none';
  // Two refusals, and both are invariants rather than taste. `fraction: null`
  // means nothing could be assessed, and reading it as a score would be a
  // qualification claimed from no evidence (I2). And a verdict that is not
  // `eligible` never becomes points: `matching.md` §5.2 keeps the state beside
  // the number, so a 99 that is `uncertain` gets no gold from this function.
  if (match.fraction === null || match.eligibility !== 'eligible') return 'none';
  return match.fraction >= EXCEPTIONAL_FRACTION ? 'match' : 'none';
}

/**
 * The corpus with the archived roles taken out, unless they were asked for.
 *
 * §6 puts rejection "behind a toggle that is off by default", and this is that
 * toggle — one function, called wherever the field is built, so the map, the
 * roster and the detail panel cannot disagree about what is on the city. §5.6
 * makes that agreement an acceptance criterion rather than a nicety.
 *
 * A role with no treatment yet is *never* hidden. The applications fetch lands
 * after the corpus does, and a filter that read "no treatment" as "archived"
 * would blank the city for a frame on every load.
 */
export function visibleSignals(
  signals: readonly CitySignal[],
  treatments: ReadonlyMap<string, SignalTreatment>,
  showArchived: boolean,
): readonly CitySignal[] {
  if (showArchived) return signals;
  return signals.filter((signal) => treatments.get(signal.job_id)?.track !== 'archived');
}

/**
 * How many roles the toggle is currently hiding.
 *
 * Exposed because a field that silently shrinks is a field nobody can trust:
 * the roster's count and the city's count both come from `visibleSignals`, so
 * the number missing between them has to be sayable somewhere on screen.
 */
export function archivedCount(
  signals: readonly CitySignal[],
  treatments: ReadonlyMap<string, SignalTreatment>,
): number {
  return signals.filter((signal) => treatments.get(signal.job_id)?.track === 'archived').length;
}

/** Whether a row of §6 is drawn today, and if not, why not. */
export type TreatmentStatus =
  { readonly kind: 'drawn' } | { readonly kind: 'deferred'; readonly because: string };

/**
 * One row of §6's table, in the form the legend renders.
 *
 * `form` is the half of the row that survives without colour (§12.4), and
 * `means` is what the row claims about a role — deliberately separate, because
 * "a thin white outline" and "you put this one aside" are different sentences
 * and a legend that only gave the first would be a paint chart.
 */
export interface TreatmentRow {
  readonly id: string;
  readonly label: string;
  /** The palette token, or null for rows drawn with no colour of their own. */
  readonly swatch: string | null;
  /** The shape or motion. Never empty when there is a swatch. */
  readonly form: string;
  /** What it says about the role. */
  readonly means: string;
  readonly status: TreatmentStatus;
}

const drawn: TreatmentStatus = { kind: 'drawn' };

/**
 * §6's table, in the order a person meets it: what is new, what you did about
 * it, what happened next, and what the position itself means.
 */
export const TREATMENTS: readonly TreatmentRow[] = [
  {
    id: 'new_internship',
    label: 'New internship',
    swatch: 'signal-400',
    form: 'Rapid pulse',
    means: `An internship first seen in the last ${NEW_WINDOW_DAYS} days.`,
    status: drawn,
  },
  {
    id: 'new_role',
    label: 'New role',
    swatch: 'signal-400',
    form: 'Slow pulse',
    means: `Any other role first seen in the last ${NEW_WINDOW_DAYS} days. "First seen" is when ingestion found it, not when the employer posted it.`,
    status: drawn,
  },
  {
    id: 'saved',
    label: 'Saved',
    swatch: 'paper',
    form: 'Thin outline',
    means: 'You put this one aside. Nothing has been sent.',
    status: drawn,
  },
  {
    id: 'applied',
    label: 'Applied',
    swatch: 'signal-400',
    form: 'Solid, fully lit',
    means:
      'You have applied. §6 asks for a solid illuminated building; the beacon itself fills instead, so the mark reads the same whether or not the employer has published an address.',
    status: drawn,
  },
  {
    id: 'in_process',
    label: 'Assessment or interview',
    swatch: 'signal-400',
    form: 'Rotating ring',
    means: 'Something is scheduled or outstanding between you and this employer.',
    status: drawn,
  },
  {
    id: 'offer',
    label: 'Offer',
    swatch: 'verdant-400',
    form: 'Soft core',
    means: 'An offer is on the table.',
    status: drawn,
  },
  {
    id: 'standout',
    label: 'Exceptional match or urgent deadline',
    swatch: 'gold-400',
    form: 'Vertical beam',
    means: `Either the role scores at least ${Math.round(EXCEPTIONAL_FRACTION * 100)}% of what could be assessed *and* clears the eligibility gate, or its deadline is inside ${URGENT_DEADLINE_DAYS} days. The score's breakdown is on the role's own page — the beam is a pointer, never the evidence.`,
    status: drawn,
  },
  {
    id: 'archived',
    label: 'Rejected or withdrawn',
    swatch: 'ink-450',
    form: 'Dim, neutral, hidden by default',
    means:
      'Off the skyline unless you ask for it. Accumulating rejections across the city makes this tool worse to open over exactly the weeks it is needed most.',
    status: drawn,
  },
  {
    id: 'stale',
    label: 'Stale or unverified',
    swatch: null,
    form: 'Reduced opacity',
    means:
      'A statement about our own knowledge, not about the employer: the listing has not been re-checked recently. The panel gives the date. A source going quiet never closes a listing (I3).',
    status: drawn,
  },
  {
    id: 'unresolved',
    label: 'No confirmed address',
    swatch: 'signal-400',
    form: 'Floating, connected to nothing',
    means:
      'The position encodes the employer and nothing about New York. On this corpus that is every role — no ATS posting names a street.',
    status: drawn,
  },
  {
    id: 'approximate',
    label: 'Approximate location',
    swatch: 'signal-400',
    form: 'Translucent area, never a point',
    means: 'A role known to a neighbourhood rather than to a door would be drawn over a region.',
    status: {
      kind: 'deferred',
      because:
        'No role in this corpus resolves to an area: it takes a confirmed office at approximate confidence, and there are none. The renderer would have nothing to draw and no test could see it on screen.',
    },
  },
  {
    id: 'closed',
    label: 'Closed',
    swatch: null,
    form: 'Fading afterimage',
    means: 'A listing observed removed from its employer’s own board.',
    status: {
      kind: 'deferred',
      because:
        'An afterimage belongs to the session that watched the role close. Closed listings are absent from a cold load by design, so there is nothing on screen to fade — it arrives with live polling.',
    },
  },
];
