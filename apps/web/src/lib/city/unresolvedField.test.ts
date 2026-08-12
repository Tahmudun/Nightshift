import { describe, expect, it } from 'vitest';

import type { CitySignal } from '@/lib/schemas';

import {
  arrangeUnresolved,
  COMPANIES_PER_ROW,
  COMPANY_SPACING,
  FIELD_BASE_ALTITUDE,
  ROLE_SPACING,
} from './unresolvedField';

function signal(overrides: Partial<CitySignal> & Pick<CitySignal, 'job_id'>): CitySignal {
  return {
    title: 'Software Engineer',
    company_id: 'company-a',
    company_name: 'Alloy',
    employment_type: 'full_time',
    remote_policy: 'on_site',
    status: 'open',
    placement: {
      kind: 'unresolved',
      latitude: null,
      longitude: null,
      building_id: null,
      location_confidence: 'city_only',
      resolution_method: 'source_text_parse',
      stated: 'New York, NY',
      inherited: false,
      office_label: null,
      office_address: null,
    },
    ...overrides,
  } as CitySignal;
}

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

    expect(field.companies).toEqual(['Alloy', 'Ramp']);
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

    expect(field.companies).toEqual(['Acme', 'Acme']);
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
    expect(arrangeUnresolved([])).toEqual({ placements: [], companies: [] });
  });
});
