import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Matrix4, PerspectiveCamera, Vector3 } from 'three';
import { describe, expect, it } from 'vitest';

import type { CitySignal } from '@/lib/schemas';

import { MAX_LABELS } from './labelAtlas';
import {
  anchorTransform,
  createSignalLayer,
  MAX_BEACONS,
  SIGNAL_COLOR,
  SIGNAL_LAYER_ID,
} from './signalLayer';
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
    expect(layer.columns.map((c) => c.jobIds.length)).toEqual([2, 1]);
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

/**
 * Selection, minus the part that needs a GPU.
 *
 * The pick itself — a click on a canvas finding the beacon under it — is
 * `city.spec.ts`'s claim, for the same reason every other rendering claim is:
 * there is no context here and the layer has never drawn a frame. What is
 * provable without one is the bookkeeping that a pick depends on, and it is
 * where the silent failures live: which instance is which role, and whether the
 * reticle is still on the role it was put on after the field moves underneath
 * it.
 */
describe('selection', () => {
  /**
   * A frame's worth of MapLibre, faked at the one seam that matters.
   *
   * `render` is handed `defaultProjectionData.mainMatrix`, which takes
   * *mercator* space to clip space. The scene is in metres, so the layer
   * composes it with the anchor transform. Working backwards from a projection
   * we can reason about — `mainMatrix = composed · anchorTransform⁻¹` — gives a
   * frame the layer will compose back into exactly `composed`, so a pixel can
   * be computed by hand and the whole pick path exercised with no GPU.
   */
  function drawFrame(layer: ReturnType<typeof createSignalLayer>, composed: Matrix4): void {
    const mainMatrix = composed
      .clone()
      .multiply(anchorTransform(ANCHOR).clone().invert())
      .toArray();
    layer.render(
      null as unknown as WebGLRenderingContext,
      {
        defaultProjectionData: { mainMatrix },
      } as unknown as Parameters<typeof layer.render>[1],
    );
  }

  /** A pitched, rotated perspective — the only kind of pose this city is in. */
  function tiltedProjection(): Matrix4 {
    const camera = new PerspectiveCamera(45, 16 / 9, 1, 40_000);
    camera.position.set(900, -3_600, 2_400);
    camera.lookAt(new Vector3(0, 0, 760));
    camera.updateMatrixWorld(true);
    return new Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
  }

  const VIEWPORT = { width: 1_600, height: 900 };

  /** Where a scene point lands on the canvas, under this projection. */
  function pixelOf(composed: Matrix4, point: readonly [number, number, number]) {
    const clip = new Vector3(...point).applyMatrix4(composed);
    return {
      x: ((clip.x + 1) / 2) * VIEWPORT.width,
      y: ((1 - clip.y) / 2) * VIEWPORT.height,
    };
  }

  it('cannot pick before it has drawn a frame, and says so rather than guessing', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a')]);

    // The pick inverts the matrix the last frame drew with. Before there is a
    // frame the honest answer is "I do not know" — a projection reconstructed
    // from the map's pose instead would answer with plausible wrong roles.
    expect(layer.canPick).toBe(false);
    expect(layer.pick({ x: 400, y: 300 }, { width: 800, height: 600 })).toBeNull();
  });

  it('knows which role each instance in the buffer draws', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });

    layer.setSignals([
      signal('r1', 'ramp', 'Ramp'),
      signal('a1', 'alloy', 'Alloy'),
      signal('a2', 'alloy', 'Alloy'),
    ]);

    // Field order: Alloy's column first, then Ramp's. A pick returns an
    // instance index and nothing else, so an off-by-one here selects a
    // different company's role and looks like a working feature.
    expect([0, 1, 2].map((i) => layer.jobAt(i))).toEqual(['a1', 'a2', 'r1']);
  });

  it('names no role for an index outside what it drew', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a')]);

    expect(layer.jobAt(1)).toBeNull();
    expect(layer.jobAt(-1)).toBeNull();
  });

  it('puts the reticle on the selected role', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a1', 'alloy', 'Alloy'), signal('a2', 'alloy', 'Alloy')]);

    layer.setSelected('a2');

    expect(layer.selected).toBe('a2');
    // Second in the stack: one role-spacing above the base altitude.
    expect(layer.selectionAt?.[2]).toBe(layer.altitudeOf(1));
  });

  it('moves the reticle when a sort moves the field under it', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    const signals = [
      signal('a1', 'alloy', 'Alloy'),
      signal('r1', 'ramp', 'Ramp'),
      signal('r2', 'ramp', 'Ramp'),
    ];
    layer.setSignals(signals, 'company');
    layer.setSelected('a1');
    const before = layer.selectionAt;

    layer.setSignals(signals, 'openings');

    // Every sort reorders the columns. A reticle written once at selection
    // time stays at the old coordinates and ends up ringing whichever employer
    // now stands there — a wrong answer that looks like a working feature.
    expect(layer.selectionAt).not.toEqual(before);
    expect(layer.selectionAt?.[0]).toBe(layer.columns.find((c) => c.name === 'Alloy')?.x);
  });

  it('keeps the selection but draws no reticle when the role leaves the corpus', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a'), signal('b')]);
    layer.setSelected('b');

    layer.setSignals([signal('a')]);

    // The selection survives because it lives in the URL, and the panel has a
    // sentence for a role that is no longer here. What must not survive is the
    // mark: a reticle left on the city would ring the wrong beacon, or the
    // origin.
    expect(layer.selected).toBe('b');
    expect(layer.selectionAt).toBeNull();
  });

  it('takes the reticle off the city when the selection is cleared', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a')]);
    layer.setSelected('a');

    layer.setSelected(null);

    expect(layer.selected).toBeNull();
    expect(layer.selectionAt).toBeNull();
  });

  it('finds the role under a pixel, through the matrix the frame drew with', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([
      signal('a1', 'alloy', 'Alloy'),
      signal('a2', 'alloy', 'Alloy'),
      signal('r1', 'ramp', 'Ramp'),
    ]);
    const composed = tiltedProjection();
    drawFrame(layer, composed);

    expect(layer.canPick).toBe(true);
    for (const index of [0, 1, 2]) {
      const jobId = layer.jobAt(index)!;
      const column = layer.columns.find((c) => c.jobIds.includes(jobId))!;
      const pixel = pixelOf(composed, [column.x, column.y, layer.altitudeOf(index)!]);

      expect(layer.pick(pixel, VIEWPORT)).toBe(jobId);
    }
  });

  it('finds nothing where there is nothing, rather than the nearest thing', () => {
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a')]);
    const composed = tiltedProjection();
    drawFrame(layer, composed);

    // Far off to one side of the single column, still inside the canvas.
    expect(layer.pick({ x: 20, y: 20 }, VIEWPORT)).toBeNull();
  });

  it('can still pick the roles that arrived after the last pick', () => {
    // The bounding-sphere trap, at the level that actually ships. three caches
    // the sphere on first raycast and gates every later one on it, so a field
    // that grows keeps a sphere too small to admit its new columns — and
    // picking stops working, silently, for exactly the newest employers.
    const layer = createSignalLayer({ anchor: ANCHOR });
    layer.setSignals([signal('a1', 'alloy', 'Alloy')]);
    const composed = tiltedProjection();
    drawFrame(layer, composed);
    const first = layer.columns[0]!;
    layer.pick(pixelOf(composed, [first.x, first.y, layer.altitudeOf(0)!]), VIEWPORT);

    layer.setSignals(
      Array.from({ length: 9 }, (_, i) => signal(`j${i}`, `company-${i}`, `Company ${i}`)),
    );
    drawFrame(layer, composed);

    // The last column is on the field's second row, well outside the sphere a
    // one-column field would have left cached.
    const last = layer.columns.at(-1)!;
    const index = layer.drawn - 1;
    const pixel = pixelOf(composed, [last.x, last.y, layer.altitudeOf(index)!]);
    expect(layer.pick(pixel, VIEWPORT)).toBe(layer.jobAt(index));
  });
});
