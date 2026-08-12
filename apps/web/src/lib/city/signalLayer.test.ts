import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import type { CitySignal } from '@/lib/schemas';

import { MAX_LABELS } from './labelAtlas';
import { createSignalLayer, MAX_BEACONS, SIGNAL_COLOR, SIGNAL_LAYER_ID } from './signalLayer';
import { COMPANIES_PER_ROW } from './unresolvedField';

/**
 * What jsdom can and cannot answer here, stated once.
 *
 * There is no GPU and no WebGL context, so nothing in this file proves a beacon
 * appears on screen — `onAdd` is never called and the renderer is never built.
 * What it does prove is everything that happens *before* the GPU: that the
 * layer declares itself the way MapLibre requires, that the instance buffer
 * counts what the field contains, and that the colour has not drifted from the
 * stylesheet. The claim "New York has beacons on it" belongs to `city.spec.ts`
 * in a real browser, for the same reason M4b's gesture claims did.
 */

const ANCHOR = [-73.98, 40.75] as const;

function signal(jobId: string, companyId = 'company-a', companyName = 'Alloy'): CitySignal {
  return {
    job_id: jobId,
    title: `Role ${jobId}`,
    company_id: companyId,
    company_name: companyName,
    employment_type: 'full_time',
    remote_policy: 'on_site',
    status: 'open',
    first_seen_at: '2026-01-01T00:00:00Z',
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
  } as CitySignal;
}

describe('createSignalLayer', () => {
  it('declares itself the way MapLibre needs to place it', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });

    expect(layer.id).toBe(SIGNAL_LAYER_ID);
    expect(layer.type).toBe('custom');
    // '3d' is what puts this layer after the extrusions with the depth buffer
    // live. As '2d' the beacons would draw over every building regardless of
    // what stands in front of them, which is the failure sharing a context
    // exists to avoid (§5.1).
    expect(layer.renderingMode).toBe('3d');
  });

  it('draws nothing before it is given anything', () => {
    expect(createSignalLayer({ anchor: ANCHOR }).drawn).toBe(0);
  });

  it('counts one instance per unresolved role', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });

    layer.setSignals([signal('a'), signal('b'), signal('c')]);

    expect(layer.drawn).toBe(3);
  });

  it('draws no beacon for a role that is standing on a building', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    const placed = signal('placed');
    const onABuilding = {
      ...placed,
      placement: {
        ...placed.placement,
        kind: 'building' as const,
        latitude: 40.755913,
        longitude: -73.989658,
        building_id: '1087186',
        location_confidence: 'verified' as const,
      },
    };

    layer.setSignals([signal('floating'), onABuilding]);

    // Not yet drawn anywhere — the building treatment is a later task. What
    // matters now is that it is not drawn *here*, floating above the city,
    // which would say the opposite of what its placement says.
    expect(layer.drawn).toBe(1);
  });

  it('empties when it is given nothing, rather than keeping the last city', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a')]);

    layer.setSignals([]);

    expect(layer.drawn).toBe(0);
  });

  it('stops at its ceiling instead of writing past the buffer it allocated', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    const tooMany = Array.from({ length: MAX_BEACONS + 10 }, (_, i) =>
      signal(`job-${i}`, `company-${i % COMPANIES_PER_ROW}`),
    );

    layer.setSignals(tooMany);

    // An InstancedMesh allocates once at its declared count. Writing past it is
    // silent in three.js and produces beacons that never appear.
    expect(layer.drawn).toBe(MAX_BEACONS);
  });

  it('uses the signal colour the stylesheet defines, not a copy of it', () => {
    // Same rule as `palette.test.ts`: a WebGL material cannot read a CSS custom
    // property, so the value is duplicated — and duplication is the thing that
    // rots. This reads the real stylesheet.
    const css = readFileSync(join(process.cwd(), 'src/app/globals.css'), 'utf8');
    const match = /--color-signal-400:\s*(#[0-9a-fA-F]{6})/.exec(css);

    expect(match).not.toBeNull();
    expect(SIGNAL_COLOR.toLowerCase()).toBe(match?.[1]?.toLowerCase());
  });
});

describe('the columns the layer exposes', () => {
  /**
   * jsdom has no 2D context, so no atlas is painted and no plate is textured.
   * What survives that — and is what these assert — is the bookkeeping: which
   * employers the field found, how many plates it would draw, and how many it
   * had to leave unnamed. The plates *appearing* is `city.spec.ts`'s claim.
   */
  it('names every employer it laid out, in the order it laid them out', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });

    layer.setSignals([
      signal('r1', 'ramp', 'Ramp'),
      signal('a1', 'alloy', 'Alloy'),
      signal('a2', 'alloy', 'Alloy'),
    ]);

    expect(layer.columns.map((c) => c.name)).toEqual(['Alloy', 'Ramp']);
    expect(layer.columns.map((c) => c.roles)).toEqual([2, 1]);
  });

  it('passes the sort through to the field rather than reordering after it', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    const signals = [
      signal('r1', 'ramp', 'Ramp'),
      signal('a1', 'alloy', 'Alloy'),
      signal('r2', 'ramp', 'Ramp'),
    ];

    layer.setSignals(signals, 'openings');

    expect(layer.columns.map((c) => c.name)).toEqual(['Ramp', 'Alloy']);
  });

  it('draws the same beacons under every sort — ordering is not filtering', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    const signals = [signal('a', 'c1', 'Alloy'), signal('b', 'c2', 'Ramp'), signal('c', 'c2')];

    layer.setSignals(signals, 'company');
    const byCompany = layer.drawn;
    layer.setSignals(signals, 'newest');

    expect(layer.drawn).toBe(byCompany);
    expect(layer.drawn).toBe(3);
  });

  it('plans one name plate per employer, not one per role', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });

    layer.setSignals([
      signal('a1', 'alloy', 'Alloy'),
      signal('a2', 'alloy', 'Alloy'),
      signal('a3', 'alloy', 'Alloy'),
    ]);

    expect(layer.drawn).toBe(3);
    expect(layer.labelled).toBe(1);
    expect(layer.unlabelled).toBe(0);
  });

  it('says how many employers it could not name rather than hiding them', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    const tooMany = Array.from({ length: MAX_LABELS + 5 }, (_, i) =>
      signal(`job-${i}`, `company-${i}`, `Company ${i}`),
    );

    layer.setSignals(tooMany);

    // The beacons are all still there — the atlas ceiling costs a name, not a
    // role. A column with no plate that is not counted anywhere reads as a
    // rendering failure.
    expect(layer.drawn).toBe(MAX_LABELS + 5);
    expect(layer.labelled).toBe(MAX_LABELS);
    expect(layer.unlabelled).toBe(5);
  });

  it('forgets the last city when it is given an empty one', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a')]);

    layer.setSignals([]);

    expect(layer.columns).toEqual([]);
    expect(layer.labelled).toBe(0);
  });
});
