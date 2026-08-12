import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import type { CitySignal } from '@/lib/schemas';

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

function signal(jobId: string, companyId = 'company-a'): CitySignal {
  return {
    job_id: jobId,
    title: `Role ${jobId}`,
    company_id: companyId,
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
