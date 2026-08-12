/**
 * Where a role goes when nobody has said where it is.
 *
 * `city.md` §4.8 is the whole of this file, and its first sentence is the one
 * that matters: the unresolved layer is **the default view, not the fallback**.
 * §4.1 measured that no ATS posting in this corpus names a street, so every
 * role lands here on its own merits and leaves only by inheriting a confirmed
 * office. Today that means all of them. This field is not a placeholder someone
 * tolerates until the buildings arrive — it is the city.
 *
 * Two rules govern the arrangement and both are load-bearing for invariant I1:
 *
 * 1. **Nothing here is a spatial guess.** A position in this field encodes
 *    company and role family and *nothing else*. Two roles sitting near each
 *    other work at the same employer; they are not near each other in New York,
 *    and no viewer should be able to read the second from the first.
 * 2. **Nothing here touches the ground.** The signals float, with no building
 *    beneath them and no line drawn to one. The absence of a ground connection
 *    is the entire message, and it is the one piece of the visual language that
 *    an invariant depends on.
 *
 * The layout is therefore deliberately *legible as an index* rather than as a
 * map: columns of roles, one column per employer, in a grid above the skyline,
 * ordered by name. A viewer who reads it as geography has been misled, and a
 * viewer who reads it as a filing system has read it right.
 *
 * Pure, deterministic and unit-tested with no GPU: the same signals in produce
 * the same transforms out, in the same order, so the renderer's instance buffer
 * can be rebuilt without the field moving under the user.
 */

import type { CitySignal } from '@/lib/schemas';

/**
 * Metres above the anchor's ground plane where the field begins.
 *
 * One World Trade Center is 541 m. The field starts above everything the
 * skyline can put in front of it, because a signal that disappears behind a
 * tower reads as a signal that is *at* that tower — which is the exact false
 * reading rule 1 exists to prevent.
 */
export const FIELD_BASE_ALTITUDE = 700;

/** Vertical gap between two roles at the same employer, in metres. */
export const ROLE_SPACING = 45;

/** Horizontal gap between employers, in metres. */
export const COMPANY_SPACING = 620;

/**
 * How many employers before the field wraps to a second row.
 *
 * A single line of columns grows without bound and eventually leaves the
 * viewport at any pitch. A grid keeps the field's footprint square-ish as the
 * corpus grows, which is the shape that survives an arbitrary camera.
 */
export const COMPANIES_PER_ROW = 6;

/** One role's place in the field, in metres relative to the scene anchor. */
export interface FieldPlacement {
  readonly jobId: string;
  /** East of the anchor. */
  readonly x: number;
  /** North of the anchor. */
  readonly y: number;
  /** Above the anchor's ground plane. */
  readonly altitude: number;
}

export interface UnresolvedField {
  readonly placements: readonly FieldPlacement[];
  /** Employers in the order their columns are laid out. */
  readonly companies: readonly string[];
}

/**
 * Arrange every unresolved signal into the field.
 *
 * Signals that are *not* unresolved are ignored rather than filtered by the
 * caller: this function owns the rule that a placed role is not in this field,
 * and a caller that forgot to filter would otherwise draw a role twice — once
 * on its building and once floating above it, which reads as two openings.
 */
export function arrangeUnresolved(signals: readonly CitySignal[]): UnresolvedField {
  const unresolved = signals.filter((signal) => signal.placement.kind === 'unresolved');

  // Group by employer. `company_id` is the key and the name is only the sort,
  // because two employers can share a display name while normalization keeps
  // them apart — grouping on the name would merge them into one column and
  // claim they are one company.
  const groups = new Map<string, { name: string; roles: CitySignal[] }>();
  for (const signal of unresolved) {
    const existing = groups.get(signal.company_id);
    if (existing) existing.roles.push(signal);
    else groups.set(signal.company_id, { name: signal.company_name, roles: [signal] });
  }

  // Name, then id: the id breaks ties so two employers with the same display
  // name still get a stable order rather than one that depends on insertion.
  const ordered = [...groups.entries()].sort(
    ([idA, a], [idB, b]) => a.name.localeCompare(b.name) || idA.localeCompare(idB),
  );

  const placements: FieldPlacement[] = [];
  const companies: string[] = [];

  ordered.forEach(([, group], index) => {
    const column = index % COMPANIES_PER_ROW;
    const row = Math.floor(index / COMPANIES_PER_ROW);
    const rowWidth = Math.min(ordered.length - row * COMPANIES_PER_ROW, COMPANIES_PER_ROW);

    // Each row is centred on the anchor, so the field grows outward from the
    // middle of the view instead of off one edge of it.
    const x = (column - (rowWidth - 1) / 2) * COMPANY_SPACING;
    const y = -row * COMPANY_SPACING;

    companies.push(group.name);

    // Title, then job id. The sort is alphabetical rather than by date on
    // purpose: a stack that reorders when a poll runs is a stack a person
    // cannot learn the shape of.
    const roles = [...group.roles].sort(
      (a, b) => a.title.localeCompare(b.title) || a.job_id.localeCompare(b.job_id),
    );

    roles.forEach((signal, depth) => {
      placements.push({
        jobId: signal.job_id,
        x,
        y,
        altitude: FIELD_BASE_ALTITUDE + depth * ROLE_SPACING,
      });
    });
  });

  return { placements, companies };
}
