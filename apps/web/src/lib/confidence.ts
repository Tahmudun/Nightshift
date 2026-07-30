/**
 * The location-confidence scale, and what each value is allowed to mean.
 *
 * §4.3 requires that the interface document its own visual language, and
 * invariant I1 requires that a coordinate never appear without its precision
 * claim. This module is the single source for both: the ordering, the labels,
 * and the plain-language explanation the UI shows the user.
 *
 * The ordering is a precision ranking, not an arbitrary list — the ladder
 * component renders it as a scale, so `verified` must be highest and `unknown`
 * lowest for that reading to be true.
 */

import type { LocationConfidence } from './schemas';

export interface ConfidenceMeta {
  readonly value: LocationConfidence;
  /** Position on the precision scale, 1 (lowest) to 5 (highest). */
  readonly rank: number;
  readonly label: string;
  /** Written for the user, not for the developer. */
  readonly meaning: string;
  /** Whether a job at this confidence can be drawn at a position on a map. */
  readonly mappable: boolean;
}

export const CONFIDENCE_SCALE: readonly ConfidenceMeta[] = [
  {
    value: 'unknown',
    rank: 1,
    label: 'Unknown',
    meaning: 'The posting names a place we could not resolve. It is not placed anywhere.',
    mappable: false,
  },
  {
    value: 'remote',
    rank: 2,
    label: 'Remote',
    meaning: 'The role is remote. There is no building to place it in.',
    mappable: false,
  },
  {
    value: 'city_only',
    rank: 3,
    label: 'City only',
    meaning: 'We know the city from the posting, but not an address. No point is shown.',
    mappable: false,
  },
  {
    value: 'approximate',
    rank: 4,
    label: 'Approximate',
    meaning: 'Resolved to a neighbourhood or a general area, shown as a radius, not a point.',
    mappable: true,
  },
  {
    value: 'verified',
    rank: 5,
    label: 'Verified',
    meaning: 'Resolved to a real address by an authoritative geocoder, placed on its building.',
    mappable: true,
  },
] as const;

const BY_VALUE = new Map(CONFIDENCE_SCALE.map((meta) => [meta.value, meta]));

export function confidenceMeta(value: LocationConfidence): ConfidenceMeta {
  const meta = BY_VALUE.get(value);
  if (meta === undefined) {
    // Unreachable through the Zod schema, but a thrown error beats a silent
    // fallback that would render an unrecognised confidence as if it were fine.
    throw new Error(`unrecognised location_confidence: ${String(value)}`);
  }
  return meta;
}

/** Highest confidence among a job's locations — what the row's ladder shows. */
export function bestConfidence(
  values: readonly LocationConfidence[],
): LocationConfidence | undefined {
  if (values.length === 0) return undefined;
  return values.reduce((best, current) =>
    confidenceMeta(current).rank > confidenceMeta(best).rank ? current : best,
  );
}
