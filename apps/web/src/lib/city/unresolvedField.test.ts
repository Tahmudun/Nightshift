import { describe, expect, it } from 'vitest';

import type { CitySignal } from '@/lib/schemas';

import { signalFixture } from './signal.fixture';
import {
  arrangeUnresolved,
  COMPANIES_PER_ROW,
  COMPANY_SPACING,
  FIELD_BASE_ALTITUDE,
  FIELD_SORTS,
  LABEL_GAP,
  ROLE_SPACING,
} from './unresolvedField';

const signal = signalFixture;

describe('arrangeUnresolved', () => {
  it('places every unresolved role and nothing else', () => {
    const placed = signal({
      job_id: 'placed',
      placement: {
        kind: 'building',
        latitude: 40.75,
        longitude: -73.99,
        building_id: '1087186',
        location_confidence: 'verified',
        resolution_method: 'company_office',
        stated: 'New York, NY',
        inherited: true,
        office_label: 'New York HQ',
        office_address: '620 Eighth Avenue, New York, NY',
      },
    });

    const field = arrangeUnresolved([signal({ job_id: 'floating' }), placed]);

    // A role drawn both on its building and floating above it reads as two
    // openings, so this filter is the module's rule rather than the caller's.
    expect(field.placements.map((p) => p.jobId)).toEqual(['floating']);
  });

  it('never touches the ground', () => {
    const field = arrangeUnresolved([signal({ job_id: 'a' }), signal({ job_id: 'b' })]);

    // §4.8: the absence of a ground connection is the whole message. The base
    // clears One World Trade at 541m, so no signal can hide behind a tower and
    // read as being *at* it.
    for (const placement of field.placements) {
      expect(placement.altitude).toBeGreaterThanOrEqual(FIELD_BASE_ALTITUDE);
      expect(placement.altitude).toBeGreaterThan(541);
    }
  });

  it('stacks one employer’s roles in a single column', () => {
    const field = arrangeUnresolved([
      signal({ job_id: 'a', title: 'Backend Engineer' }),
      signal({ job_id: 'b', title: 'Frontend Engineer' }),
      signal({ job_id: 'c', title: 'Data Engineer' }),
    ]);

    const xs = new Set(field.placements.map((p) => p.x));
    const ys = new Set(field.placements.map((p) => p.y));
    expect(xs.size).toBe(1);
    expect(ys.size).toBe(1);
    expect(field.placements.map((p) => p.altitude)).toEqual([
      FIELD_BASE_ALTITUDE,
      FIELD_BASE_ALTITUDE + ROLE_SPACING,
      FIELD_BASE_ALTITUDE + 2 * ROLE_SPACING,
    ]);
  });

  it('orders a column by title so a poll cannot reshuffle it', () => {
    const field = arrangeUnresolved([
      signal({ job_id: 'z', title: 'Zookeeper' }),
      signal({ job_id: 'a', title: 'Analyst' }),
    ]);

    expect(field.placements.map((p) => p.jobId)).toEqual(['a', 'z']);
  });

  it('gives each employer its own column, ordered by name', () => {
    const field = arrangeUnresolved([
      signal({ job_id: '1', company_id: 'c2', company_name: 'Ramp' }),
      signal({ job_id: '2', company_id: 'c1', company_name: 'Alloy' }),
    ]);

    expect(field.columns.map((c) => c.name)).toEqual(['Alloy', 'Ramp']);
    const [alloy, ramp] = field.placements;
    expect(alloy?.jobId).toBe('2');
    expect(ramp?.jobId).toBe('1');
    expect(Math.abs(ramp!.x - alloy!.x)).toBe(COMPANY_SPACING);
  });

  it('keeps two employers sharing a display name apart', () => {
    // Normalization can hold two companies apart under one display name, and
    // grouping on the name would merge their columns into a claim that they
    // are one employer.
    const field = arrangeUnresolved([
      signal({ job_id: '1', company_id: 'first', company_name: 'Acme' }),
      signal({ job_id: '2', company_id: 'second', company_name: 'Acme' }),
    ]);

    expect(field.columns.map((c) => c.name)).toEqual(['Acme', 'Acme']);
    expect(field.columns.map((c) => c.companyId)).toEqual(['first', 'second']);
    expect(field.placements[0]?.x).not.toBe(field.placements[1]?.x);
  });

  it('wraps to a second row rather than growing without bound', () => {
    const signals = Array.from({ length: COMPANIES_PER_ROW + 1 }, (_, i) =>
      signal({ job_id: `job-${i}`, company_id: `c-${i}`, company_name: `Company ${i}` }),
    );

    const field = arrangeUnresolved(signals);

    const rows = new Set(field.placements.map((p) => p.y));
    expect(rows.size).toBe(2);
  });

  it('centres each row on the anchor', () => {
    const signals = Array.from({ length: 3 }, (_, i) =>
      signal({ job_id: `job-${i}`, company_id: `c-${i}`, company_name: `Company ${i}` }),
    );

    const field = arrangeUnresolved(signals);
    const xs = field.placements.map((p) => p.x);

    expect(xs).toEqual([-COMPANY_SPACING, 0, COMPANY_SPACING]);
  });

  it('is deterministic — the same input twice gives the same field', () => {
    const signals = [
      signal({ job_id: 'b', company_id: 'c2', company_name: 'Ramp' }),
      signal({ job_id: 'a', company_id: 'c1', company_name: 'Alloy' }),
    ];

    // The renderer rebuilds its instance buffer from this. If the order moved
    // between two loads of the same corpus, the field would reshuffle under a
    // user who had changed nothing.
    expect(arrangeUnresolved(signals)).toEqual(arrangeUnresolved(signals));
  });

  it('arranges nothing into nothing', () => {
    expect(arrangeUnresolved([])).toEqual({ placements: [], columns: [] });
  });
});

describe('the columns a roster can navigate by', () => {
  it('reports each column’s employer, roles and position', () => {
    const field = arrangeUnresolved([
      signal({ job_id: 'a1', company_id: 'alloy', company_name: 'Alloy' }),
      signal({ job_id: 'a2', company_id: 'alloy', company_name: 'Alloy', title: 'Analyst' }),
      signal({ job_id: 'r1', company_id: 'ramp', company_name: 'Ramp' }),
    ]);

    expect(field.columns).toEqual([
      {
        companyId: 'alloy',
        name: 'Alloy',
        // Bottom to top, in the buffer's own order: 'Analyst' sorts before
        // 'Software Engineer'. The roster lists these by name, so the ids and
        // their order are the contract, not the count.
        jobIds: ['a2', 'a1'],
        x: -COMPANY_SPACING / 2,
        y: 0,
        labelAltitude: FIELD_BASE_ALTITUDE + ROLE_SPACING + LABEL_GAP,
      },
      {
        companyId: 'ramp',
        name: 'Ramp',
        jobIds: ['r1'],
        x: COMPANY_SPACING / 2,
        y: 0,
        labelAltitude: FIELD_BASE_ALTITUDE + LABEL_GAP,
      },
    ]);
  });

  it('puts every name plate clear of the beacon below it', () => {
    // A label resting on the topmost beacon captions that one role rather than
    // the stack, which is the difference between a heading and a tooltip.
    const field = arrangeUnresolved(
      Array.from({ length: 5 }, (_, i) => signal({ job_id: `j${i}`, title: `Role ${i}` })),
    );

    const top = Math.max(...field.placements.map((p) => p.altitude));
    expect(field.columns[0]?.labelAltitude).toBe(top + LABEL_GAP);
    expect(field.columns[0]?.labelAltitude).toBeGreaterThan(top);
  });

  it('sits every column exactly over its own roles', () => {
    // The roster flies the camera to `column.x/y`. If a column's coordinates
    // and its roles' coordinates could disagree, that flight would land on
    // empty sky next to the stack it named.
    const field = arrangeUnresolved(
      Array.from({ length: COMPANIES_PER_ROW + 2 }, (_, i) =>
        signal({ job_id: `j${i}`, company_id: `c${i}`, company_name: `Company ${i}` }),
      ),
    );

    for (const column of field.columns) {
      const own = field.placements.filter((p) => p.x === column.x && p.y === column.y);
      expect(own).toHaveLength(column.jobIds.length);
    }
  });
});

describe('the field is sortable — §4.8', () => {
  const older = '2026-03-01T00:00:00Z';
  const newer = '2026-07-01T00:00:00Z';

  /** Two employers: one tall and old, one short and new. */
  function corpus(): CitySignal[] {
    return [
      signal({
        job_id: 'z1',
        company_id: 'zeta',
        company_name: 'Zeta',
        title: 'Analyst',
        first_seen_at: older,
      }),
      signal({
        job_id: 'z2',
        company_id: 'zeta',
        company_name: 'Zeta',
        title: 'Bookkeeper',
        first_seen_at: older,
      }),
      signal({
        job_id: 'a1',
        company_id: 'acme',
        company_name: 'Acme',
        title: 'Carpenter',
        first_seen_at: newer,
      }),
    ];
  }

  it('orders columns by employer name by default', () => {
    expect(arrangeUnresolved(corpus()).columns.map((c) => c.name)).toEqual(['Acme', 'Zeta']);
    // The default is the same object the explicit choice produces, so a caller
    // that omits the argument and one that passes 'company' cannot drift.
    expect(arrangeUnresolved(corpus())).toEqual(arrangeUnresolved(corpus(), 'company'));
  });

  it('orders columns by how many roles are open, tallest first', () => {
    const field = arrangeUnresolved(corpus(), 'openings');

    // Zeta has two and sorts before Acme despite losing on the alphabet.
    expect(field.columns.map((c) => c.name)).toEqual(['Zeta', 'Acme']);
    expect(field.columns.map((c) => c.jobIds.length)).toEqual([2, 1]);
  });

  it('orders columns by their newest role, not their oldest', () => {
    const field = arrangeUnresolved(corpus(), 'newest');

    expect(field.columns.map((c) => c.name)).toEqual(['Acme', 'Zeta']);
  });

  it('a single recent role carries its whole column forward', () => {
    // The rule that makes 'newest' mean anything: an employer who posted this
    // morning leads, even if everything else under them is months old.
    const signals = [
      ...corpus(),
      signal({
        job_id: 'z3',
        company_id: 'zeta',
        company_name: 'Zeta',
        title: 'Zookeeper',
        first_seen_at: '2026-08-01T00:00:00Z',
      }),
    ];

    expect(arrangeUnresolved(signals, 'newest').columns.map((c) => c.name)).toEqual([
      'Zeta',
      'Acme',
    ]);
  });

  it('reorders roles inside a column only when recency was asked for', () => {
    const signals = [
      signal({ job_id: 'old', title: 'Analyst', first_seen_at: older }),
      signal({ job_id: 'new', title: 'Zookeeper', first_seen_at: newer }),
    ];

    // Alphabetical by default: a poll must not reshuffle a stack.
    expect(arrangeUnresolved(signals, 'company').placements.map((p) => p.jobId)).toEqual([
      'old',
      'new',
    ]);
    expect(arrangeUnresolved(signals, 'openings').placements.map((p) => p.jobId)).toEqual([
      'old',
      'new',
    ]);
    // Recency was asked for, so the newest role heads the stack.
    expect(arrangeUnresolved(signals, 'newest').placements.map((p) => p.jobId)).toEqual([
      'new',
      'old',
    ]);
  });

  it('breaks every tie the same way, so no sort is ambiguous', () => {
    // Same height, same date, different names: each sort must still be total,
    // or the field reshuffles between two loads of an unchanged corpus.
    const signals = [
      signal({ job_id: 'b', company_id: 'cb', company_name: 'Beta' }),
      signal({ job_id: 'a', company_id: 'ca', company_name: 'Alpha' }),
    ];

    for (const sort of FIELD_SORTS) {
      expect(arrangeUnresolved(signals, sort).columns.map((c) => c.name)).toEqual([
        'Alpha',
        'Beta',
      ]);
      expect(arrangeUnresolved(signals, sort)).toEqual(arrangeUnresolved(signals, sort));
    }
  });

  it('keeps the same roles under every sort — an ordering is not a filter', () => {
    const ids = (sort: (typeof FIELD_SORTS)[number]) =>
      [...arrangeUnresolved(corpus(), sort).placements.map((p) => p.jobId)].sort();

    for (const sort of FIELD_SORTS) {
      expect(ids(sort)).toEqual(['a1', 'z1', 'z2']);
    }
  });
});
