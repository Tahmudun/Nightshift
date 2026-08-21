import { describe, expect, it } from 'vitest';

import { lngLatFromScene } from './mercator';
import { signalFixture, UNRESOLVED_PLACEMENT } from './signal.fixture';
import {
  arrangeOnBuildings,
  DEFAULT_ROOF_METRES,
  ROOF_CLEARANCE,
  ROOF_ROLE_SPACING,
} from './buildingField';

import type { CitySignal } from '@/lib/schemas';

/** Times Square-ish: the anchor the city opens on. */
const ANCHOR = [-73.9857, 40.7484] as const;

/** 620 8th Avenue — Datadog's floor of the New York Times Building. */
const NYT = { lat: 40.755913, lng: -73.989658, bin: '1087186' };
/** 28 West 23rd Street — Ramp, in the Flatiron. */
const HOME_DEPOT = { lat: 40.741817, lng: -73.990988, bin: '1080672' };

function onBuilding(
  jobId: string,
  at: { lat: number; lng: number; bin: string },
  overrides: Partial<CitySignal> = {},
): CitySignal {
  return signalFixture({
    job_id: jobId,
    ...overrides,
    placement: {
      kind: 'building',
      latitude: at.lat,
      longitude: at.lng,
      building_id: at.bin,
      location_confidence: 'verified',
      resolution_method: 'nyc_geosearch',
      stated: 'New York, NY',
      inherited: true,
      office_label: 'New York HQ',
      office_address: '620 8th Avenue, New York, NY',
    },
  });
}

describe('where a placed role stands', () => {
  it('stands over the coordinate its office was geocoded to, not over the anchor', () => {
    const field = arrangeOnBuildings([onBuilding('job-1', NYT)], ANCHOR);

    // The whole point of a `building` placement, and the assertion is written
    // as a round trip rather than against two literal metre offsets: the scene
    // position must convert *back* to the coordinate the geocoder returned. A
    // layout that drifted by a hundred metres would still look like a building
    // in Midtown, and no eye would catch it.
    const [lng, lat] = lngLatFromScene(ANCHOR, field.placements[0]!.x, field.placements[0]!.y);
    expect(lng).toBeCloseTo(NYT.lng, 9);
    expect(lat).toBeCloseTo(NYT.lat, 9);
  });

  it('ignores a role nobody has placed', () => {
    const signals = [
      onBuilding('placed', NYT),
      signalFixture({ job_id: 'floating', placement: UNRESOLVED_PLACEMENT }),
    ];

    const field = arrangeOnBuildings(signals, ANCHOR);

    // The mirror of `arrangeUnresolved`'s own filter. Each field owns the rule
    // about what belongs in it, so a caller that forgot to split the corpus
    // draws every role exactly once rather than twice — and a role drawn twice
    // reads as two openings.
    expect(field.placements.map((p) => p.jobId)).toEqual(['placed']);
  });

  it('ignores an approximate placement, which is an area and not a roof', () => {
    const area = signalFixture({
      job_id: 'approximate',
      placement: {
        kind: 'area',
        latitude: 40.7484,
        longitude: -73.9857,
        building_id: null,
        location_confidence: 'approximate',
        resolution_method: 'nominatim',
        stated: 'Manhattan, NY',
        inherited: false,
        office_label: null,
        office_address: null,
      },
    });

    // §6 draws an approximate location as a translucent radius, never a point,
    // and standing one on a roof would be the exact fabrication I1 forbids —
    // the placement says "somewhere in this neighbourhood" and the roof would
    // say "this building".
    expect(arrangeOnBuildings([area], ANCHOR).placements).toEqual([]);
  });

  it('refuses an area even when one arrives carrying a building id', () => {
    // This payload cannot come from the API: `placementSchema` rejects it with
    // "a BIN is not a promotion (I1)". It is constructed here anyway, because
    // the test above passes with the `kind` check deleted — the area it uses
    // has a null `building_id` and the *other* guard catches it. A test that
    // survives the removal of the line it exists to protect is documentation,
    // not a test.
    //
    // What this pins is what happens the day the schema is loosened by somebody
    // who has not read this file: the field still refuses, rather than lighting
    // a specific roof on the strength of a neighbourhood.
    const promoted = signalFixture({
      job_id: 'promoted',
      placement: {
        kind: 'area',
        latitude: NYT.lat,
        longitude: NYT.lng,
        building_id: NYT.bin,
        location_confidence: 'approximate',
        resolution_method: 'nominatim',
        stated: 'Midtown, NY',
        inherited: false,
        office_label: null,
        office_address: null,
      },
    });

    expect(arrangeOnBuildings([promoted], ANCHOR).placements).toEqual([]);
  });
});

describe('how a stack sits on its roof', () => {
  it('starts clear of the roof when the roof height is known', () => {
    const heights = new Map([[NYT.bin, 318]]);

    const field = arrangeOnBuildings([onBuilding('job-1', NYT)], ANCHOR, heights);

    expect(field.placements[0]!.altitude).toBe(318 + ROOF_CLEARANCE);
  });

  it('falls back to a stated default when no tile has reported the roof', () => {
    // The archive is loaded per tile, so a building outside the viewport has no
    // measured height yet. A default is honest — it is a drawing decision about
    // how high to hang a marker — in a way that inventing a *position* never
    // would be.
    const field = arrangeOnBuildings([onBuilding('job-1', NYT)], ANCHOR);

    expect(field.placements[0]!.altitude).toBe(DEFAULT_ROOF_METRES + ROOF_CLEARANCE);
  });

  it('stacks two roles at one employer without either hiding the other', () => {
    const field = arrangeOnBuildings(
      [onBuilding('job-b', NYT, { title: 'B' }), onBuilding('job-a', NYT, { title: 'A' })],
      ANCHOR,
      new Map([[NYT.bin, 100]]),
    );

    expect(field.placements).toEqual([
      {
        jobId: 'job-a',
        x: expect.any(Number),
        y: expect.any(Number),
        altitude: 100 + ROOF_CLEARANCE,
      },
      {
        jobId: 'job-b',
        x: expect.any(Number),
        y: expect.any(Number),
        altitude: 100 + ROOF_CLEARANCE + ROOF_ROLE_SPACING,
      },
    ]);
  });

  it('keeps every role in a stack over the same point on the ground', () => {
    const field = arrangeOnBuildings([onBuilding('job-a', NYT), onBuilding('job-b', NYT)], ANCHOR);

    // A stack that fanned out horizontally would be claiming several addresses
    // for one office. Only the altitude may differ.
    expect(field.placements[0]!.x).toBe(field.placements[1]!.x);
    expect(field.placements[0]!.y).toBe(field.placements[1]!.y);
  });
});

describe('the buildings themselves', () => {
  it('reports one building per BIN, however many roles stand on it', () => {
    const field = arrangeOnBuildings(
      [
        onBuilding('job-a', NYT, { company_name: 'Alloy' }),
        onBuilding('job-b', NYT, { company_name: 'Alloy' }),
        onBuilding('job-c', HOME_DEPOT, { company_id: 'c2', company_name: 'Zebra' }),
      ],
      ANCHOR,
    );

    expect(field.buildings.map((b) => b.buildingId)).toEqual([NYT.bin, HOME_DEPOT.bin]);
    expect(field.buildings[0]!.jobIds).toEqual(['job-a', 'job-b']);
  });

  it('names a building after its employer when only one is hiring there', () => {
    const field = arrangeOnBuildings(
      [onBuilding('job-a', NYT, { company_name: 'Datadog' })],
      ANCHOR,
    );

    expect(field.buildings[0]!.name).toBe('Datadog');
  });

  it('counts the employers rather than picking one when a tower has several', () => {
    // 620 8th Avenue is the New York Times Building and Datadog has part of it.
    // A plate reading "Datadog" over a tower where two employers are hiring is
    // a claim about the other one's address that nobody made.
    const field = arrangeOnBuildings(
      [
        onBuilding('job-a', NYT, { company_id: 'c1', company_name: 'Datadog' }),
        onBuilding('job-b', NYT, { company_id: 'c2', company_name: 'The Times' }),
      ],
      ANCHOR,
    );

    expect(field.buildings).toHaveLength(1);
    expect(field.buildings[0]!.name).toBe('2 employers');
  });

  it('puts the plate above the top role rather than on it', () => {
    const heights = new Map([[NYT.bin, 100]]);

    const field = arrangeOnBuildings(
      [onBuilding('job-a', NYT), onBuilding('job-b', NYT)],
      ANCHOR,
      heights,
    );

    const top = field.placements[1]!.altitude;
    expect(field.buildings[0]!.labelAltitude).toBeGreaterThan(top);
  });

  it('gives the beam enough height to pass every role standing on it', () => {
    const field = arrangeOnBuildings(
      [onBuilding('job-a', NYT), onBuilding('job-b', NYT), onBuilding('job-c', NYT)],
      ANCHOR,
      new Map([[NYT.bin, 100]]),
    );

    // ADR 0023's beam is "a narrow column of light leaving the roof and
    // dissipating into the sky". A beam that stopped below the top of its own
    // stack would leave the highest roles hanging above the light they are
    // supposed to be standing in — which is precisely how the untethered field
    // reads, and the two must not be able to look the same.
    const topRole = field.placements[2]!.altitude;
    const building = field.buildings[0]!;

    expect(building.roofAltitude + building.beamHeight).toBeGreaterThan(topRole);
  });

  it('starts the beam at the roof, which is where the light leaves the building', () => {
    const field = arrangeOnBuildings([onBuilding('job-a', NYT)], ANCHOR, new Map([[NYT.bin, 318]]));

    // ADR 0023: a hiring building is a beam leaving the roof. Starting it at
    // the ground would draw a column of light through the tower it is meant to
    // be coming out of.
    expect(field.buildings[0]!.roofAltitude).toBe(318);
  });
});

describe('what must not move under the viewer', () => {
  it('produces byte-identical output for the same corpus twice', () => {
    const signals = [
      onBuilding('job-c', HOME_DEPOT, { title: 'C' }),
      onBuilding('job-a', NYT, { title: 'A' }),
      onBuilding('job-b', NYT, { title: 'B' }),
    ];

    // The instance buffer is rebuilt on every treatment change and every poll.
    // A layout that depended on insertion order would reshuffle the city under
    // a viewer who did nothing.
    expect(arrangeOnBuildings(signals, ANCHOR)).toEqual(
      arrangeOnBuildings([...signals].reverse(), ANCHOR),
    );
  });

  it('orders buildings by employer name so the field does not depend on the fetch', () => {
    const field = arrangeOnBuildings(
      [
        onBuilding('job-z', HOME_DEPOT, { company_id: 'c2', company_name: 'Zebra' }),
        onBuilding('job-a', NYT, { company_id: 'c1', company_name: 'Alloy' }),
      ],
      ANCHOR,
    );

    expect(field.buildings.map((b) => b.name)).toEqual(['Alloy', 'Zebra']);
  });
});
