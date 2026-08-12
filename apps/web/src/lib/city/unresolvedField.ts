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

/**
 * Metres between the top role in a column and its name plate.
 *
 * A label sitting on the topmost beacon reads as a caption for *that role*
 * rather than for the stack. The gap is what makes it a column heading.
 */
export const LABEL_GAP = 95;

/**
 * The orderings the field offers, and the whole of §4.8's "sortable".
 *
 * Three rather than one because the field is the default view of this product
 * (§4.8) and a default view with a single fixed order is a list nobody can
 * interrogate. Each answers a different question a person actually arrives
 * with: *who is hiring* (`company`), *who is hiring most* (`openings`), and
 * *what is new since I last looked* (`newest`).
 */
export const FIELD_SORTS = ['company', 'openings', 'newest'] as const;
export type FieldSort = (typeof FIELD_SORTS)[number];

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

/**
 * One employer's column: who it is, how tall it is, and where it stands.
 *
 * It carries geometry because two things outside this file need to point *at*
 * a column rather than at a role — the name plates in the scene, and the
 * roster panel's fly-to. Recomputing the column's position in either of them
 * would be a second implementation of this layout, free to disagree with it.
 */
export interface FieldColumn {
  readonly companyId: string;
  readonly name: string;
  /** How many unresolved roles are stacked here. */
  readonly roles: number;
  /** East of the anchor. */
  readonly x: number;
  /** North of the anchor. */
  readonly y: number;
  /** Where this column's name plate goes: clear of the topmost beacon. */
  readonly labelAltitude: number;
}

export interface UnresolvedField {
  readonly placements: readonly FieldPlacement[];
  /** Employers in the order their columns are laid out, left to right. */
  readonly columns: readonly FieldColumn[];
}

/** One employer mid-grouping: the id it is keyed by, and what landed under it. */
type GroupEntry = readonly [string, { readonly name: string; readonly roles: CitySignal[] }];

/** Milliseconds since the epoch, from the ISO string Zod already validated. */
function seenAt(signal: CitySignal): number {
  return Date.parse(signal.first_seen_at);
}

/** The most recent `first_seen_at` in a column, which is the column's own age. */
function newestIn(roles: readonly CitySignal[]): number {
  return roles.reduce((newest, role) => Math.max(newest, seenAt(role)), Number.NEGATIVE_INFINITY);
}

/**
 * Arrange every unresolved signal into the field.
 *
 * Signals that are *not* unresolved are ignored rather than filtered by the
 * caller: this function owns the rule that a placed role is not in this field,
 * and a caller that forgot to filter would otherwise draw a role twice — once
 * on its building and once floating above it, which reads as two openings.
 *
 * `sort` reorders **columns**, and only `newest` also reorders the roles
 * inside one. That asymmetry is deliberate and it is a reversal of this
 * module's original rule, so it is worth the sentence: a stack that reshuffles
 * when a poll runs is a stack a person cannot learn the shape of, which is why
 * the default stays alphabetical. But a person who has *asked* for recency has
 * asked for exactly that reshuffle, and refusing it would be the module
 * deciding it knows better.
 */
export function arrangeUnresolved(
  signals: readonly CitySignal[],
  sort: FieldSort = 'company',
): UnresolvedField {
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

  // Name, then id, as the base ordering. The id breaks ties so two employers
  // with the same display name still get a stable order rather than one that
  // depends on insertion, and every other sort falls back to this pair — so no
  // ordering below can ever be ambiguous, however many employers tie on it.
  const byName = ([idA, a]: GroupEntry, [idB, b]: GroupEntry): number =>
    a.name.localeCompare(b.name) || idA.localeCompare(idB);

  const comparators: Record<FieldSort, (a: GroupEntry, b: GroupEntry) => number> = {
    company: byName,
    // Tallest column first. Ties fall back to the name, so the field does not
    // reshuffle among equal-height columns between two loads.
    openings: (a, b) => b[1].roles.length - a[1].roles.length || byName(a, b),
    // A column is as new as its newest role. Sorting a column by its oldest or
    // its average would bury an employer who posted this morning behind one
    // who has been open since spring.
    newest: (a, b) => newestIn(b[1].roles) - newestIn(a[1].roles) || byName(a, b),
  };

  const ordered = [...groups.entries()].sort(comparators[sort]);

  const placements: FieldPlacement[] = [];
  const columns: FieldColumn[] = [];

  ordered.forEach(([companyId, group], index) => {
    const column = index % COMPANIES_PER_ROW;
    const row = Math.floor(index / COMPANIES_PER_ROW);
    const rowWidth = Math.min(ordered.length - row * COMPANIES_PER_ROW, COMPANIES_PER_ROW);

    // Each row is centred on the anchor, so the field grows outward from the
    // middle of the view instead of off one edge of it.
    const x = (column - (rowWidth - 1) / 2) * COMPANY_SPACING;
    // `|| 0` normalises negative zero, which `-row * spacing` produces for the
    // first row. It renders identically and compares equal under `===`, so it
    // survives every obvious check and then fails an `Object.is` deep-equal in
    // a caller's test with a diff reading `0` versus `-0`.
    const y = -row * COMPANY_SPACING || 0;

    // Title, then job id — see the note on `sort` above for why recency is the
    // one ordering allowed to move a role within its own column.
    const roles = [...group.roles].sort((a, b) =>
      sort === 'newest'
        ? seenAt(b) - seenAt(a) || a.job_id.localeCompare(b.job_id)
        : a.title.localeCompare(b.title) || a.job_id.localeCompare(b.job_id),
    );

    columns.push({
      companyId,
      name: group.name,
      roles: roles.length,
      x,
      y,
      labelAltitude: FIELD_BASE_ALTITUDE + (roles.length - 1) * ROLE_SPACING + LABEL_GAP,
    });

    roles.forEach((signal, depth) => {
      placements.push({
        jobId: signal.job_id,
        x,
        y,
        altitude: FIELD_BASE_ALTITUDE + depth * ROLE_SPACING,
      });
    });
  });

  return { placements, columns };
}
