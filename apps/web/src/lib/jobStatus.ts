/**
 * The closure states, and what each one is allowed to mean.
 *
 * The same job this module does for status that `confidence.ts` does for
 * location precision: one place that owns the label, the plain-language
 * explanation, and the visual tone, so no component invents its own wording.
 *
 * The distinction that matters most is between `possibly_stale` and
 * `unverified`, and it is the reason this file exists rather than a map of
 * strings to colours. They look alike — both mean "we are not sure this job is
 * still open" — but they are different claims:
 *
 *   possibly_stale  the board answered, and this job was not in the answer.
 *                   That is evidence about the job.
 *   unverified      the board did not answer at all. That is evidence about
 *                   the source, and none whatever about the job.
 *
 * Invariant I3 is that difference. Only `possibly_stale` can ever lead to
 * `closed`; no amount of time in `unverified` does. If those two ever read the
 * same way on screen, the invariant is true in the database and false to the
 * person looking at it — which is the failure the whole design exists to
 * prevent.
 */

import type { JobStatus } from './schemas';

export interface JobStatusMeta {
  readonly value: JobStatus;
  readonly label: string;
  /** Written for the user, not for the developer. */
  readonly meaning: string;
  /** Whether this job should still be treated as worth applying to. */
  readonly stillWorthApplying: boolean;
  /** Tailwind text colour token. Never the only carrier of the meaning (§12.4). */
  readonly tone: string;
}

export const JOB_STATUS_SCALE: readonly JobStatusMeta[] = [
  {
    value: 'open',
    label: 'Open',
    meaning: 'Listed on the company’s board at the most recent check.',
    stillWorthApplying: true,
    tone: 'text-signal-400',
  },
  {
    value: 'possibly_stale',
    label: 'Possibly stale',
    meaning:
      'The board answered and this job was not in it, three checks running. It may have been filled, or briefly unpublished. Still shown, because it is not gone long enough to be sure.',
    stillWorthApplying: true,
    tone: 'text-gold-400',
  },
  {
    value: 'unverified',
    label: 'Unverified',
    meaning:
      'We have not been able to check this board recently, so we know nothing new about this job either way. Nothing here has been closed — an outage is not evidence.',
    stillWorthApplying: true,
    tone: 'text-paper-dim',
  },
  {
    value: 'closed',
    label: 'Closed',
    meaning:
      'Absent from three checks in a row spread over at least seven days. Kept on the record rather than deleted, so its history stays readable.',
    stillWorthApplying: false,
    tone: 'text-alert-400',
  },
] as const;

const BY_VALUE = new Map(JOB_STATUS_SCALE.map((meta) => [meta.value, meta]));

export function jobStatusMeta(value: JobStatus): JobStatusMeta {
  const meta = BY_VALUE.get(value);
  if (meta === undefined) {
    // Unreachable through the Zod schema. A thrown error beats a silent
    // fallback that would render an unrecognised status as though it were fine.
    throw new Error(`unrecognised job status: ${String(value)}`);
  }
  return meta;
}

/** The order the states are presented in — a life cycle, not an alphabet. */
export const JOB_STATUS_ORDER: readonly JobStatus[] = JOB_STATUS_SCALE.map((meta) => meta.value);
