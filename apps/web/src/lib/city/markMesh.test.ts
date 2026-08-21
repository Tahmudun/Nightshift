import { Matrix4, Vector3 } from 'three';
import { describe, expect, it } from 'vitest';

import {
  BEAM_LENGTH,
  createMarkMesh,
  MARK_KINDS,
  markGeometry,
  markMaterial,
  RING_ARC,
} from './markMesh';
import { COLUMN_HEIGHT } from './beacon';
import { FIELD_BASE_ALTITUDE } from './unresolvedField';

/**
 * The §6 marks, as buffers.
 *
 * No GPU here, so nothing in this file proves a ring is visible — it proves the
 * ring is at the coordinates the field put the role at, in the colour the table
 * chose, and that it goes away when the role does. `city.spec.ts` owns the
 * pixels.
 */

describe('createMarkMesh', () => {
  it('draws nothing until it is given something', () => {
    const marks = createMarkMesh({ kind: 'outline', capacity: 8 });

    expect(marks.drawn).toBe(0);
    expect(marks.mesh.count).toBe(0);
  });

  it('puts each mark where the field put its role', () => {
    const marks = createMarkMesh({ kind: 'outline', capacity: 8 });

    marks.set([{ x: 620, y: -620, z: FIELD_BASE_ALTITUDE, tint: '#eaf1fa' }]);

    expect(marks.drawn).toBe(1);
    expect(marks.positionAt(0)).toEqual([620, -620, FIELD_BASE_ALTITUDE]);
  });

  it('gives each instance its own colour', () => {
    // One mesh serves two rows of §6 — an applied role and an offer are the
    // same shape in different colours — so a per-instance tint is what keeps
    // that from being two meshes.
    const marks = createMarkMesh({ kind: 'core', capacity: 8 });

    marks.set([
      { x: 0, y: 0, z: 700, tint: '#5ce8ff' },
      { x: 0, y: 0, z: 745, tint: '#5cf0a8' },
    ]);

    expect(marks.tintAt(0)).toBe('#5ce8ff');
    expect(marks.tintAt(1)).toBe('#5cf0a8');
  });

  it('forgets the marks it is no longer given', () => {
    // The failure this catches is a role that keeps its ring after the
    // interview is over — a stale mark that reads as a live one.
    const marks = createMarkMesh({ kind: 'ring', capacity: 8 });

    marks.set([
      { x: 0, y: 0, z: 700, tint: '#5ce8ff' },
      { x: 0, y: 0, z: 745, tint: '#5ce8ff' },
    ]);
    marks.set([{ x: 0, y: 0, z: 700, tint: '#5ce8ff' }]);

    expect(marks.drawn).toBe(1);
    expect(marks.positionAt(1)).toBeNull();
  });

  it('stops at its capacity rather than writing past the buffer', () => {
    // An `InstancedMesh` allocates once at its declared count, so this is a
    // real ceiling. Writing past it corrupts the instances that are drawn.
    const marks = createMarkMesh({ kind: 'beam', capacity: 2 });

    marks.set(Array.from({ length: 5 }, (_, i) => ({ x: 0, y: 0, z: 700 + i, tint: '#ffcf5c' })));

    expect(marks.drawn).toBe(2);
  });

  it('spins only what it is asked to spin', () => {
    const marks = createMarkMesh({ kind: 'ring', capacity: 8 });
    marks.set([{ x: 100, y: 200, z: 700, tint: '#5ce8ff' }]);

    marks.orient(Math.PI / 2, 0, 0);

    // Still where the role is: a rotation that moves the mark off its own
    // beacon is a mark pointing at nothing.
    expect(marks.positionAt(0)).toEqual([100, 200, 700]);
    expect(marks.spunTo).toBeCloseTo(Math.PI / 2);
  });

  it('re-places every mark when the field is rewritten under it', () => {
    // The same trap the reticle has: a sort moves every role, and a mark
    // written once ends up decorating whichever role now stands there.
    const marks = createMarkMesh({ kind: 'outline', capacity: 8 });

    marks.set([{ x: 0, y: 0, z: 700, tint: '#eaf1fa' }]);
    marks.set([{ x: 620, y: 0, z: 700, tint: '#eaf1fa' }]);

    expect(marks.positionAt(0)).toEqual([620, 0, 700]);
  });
});

describe('the geometry each mark is drawn with', () => {
  it('has one for every kind, so a new kind cannot silently draw nothing', () => {
    for (const kind of MARK_KINDS) {
      expect(markGeometry(kind)).toBeDefined();
      expect(markMaterial(kind)).toBeDefined();
    }
  });

  it('never lets the gold spine descend below the role it belongs to', () => {
    // The one rule in this file that an invariant depends on. §4.8: nothing in
    // the unresolved field touches the ground, and "the absence of a ground
    // connection is the entire message". A spine long enough to reach the
    // street would draw a line from a floating role to a building nobody
    // confirmed — I1 broken by a decoration.
    //
    // **This asserts the direction, not the arithmetic.** It used to demand
    // `BEAM_LENGTH / 2 < FIELD_BASE_ALTITUDE`, which was the right sum while
    // the shaft was centred on the beacon and reached half its length
    // downward. ADR 0034 made it stand on the anchor and rise, and left this
    // assertion behind describing geometry that no longer exists — it passed
    // for a length that could not have failed it and went red the first time a
    // length changed, for a reason that had nothing to do with the ground.
    //
    // A spine that only goes up cannot reach the street at any length, and
    // that is what is checked: the shape's own lowest point, read off the
    // geometry rather than computed a second time here.
    const beam = markGeometry('beam');
    beam.computeBoundingBox();

    expect(beam.boundingBox?.min.z).toBeGreaterThanOrEqual(0);
    // And the field's clearance is still real, so a future centred geometry
    // would be caught by the sum as well as by the direction.
    expect(FIELD_BASE_ALTITUDE).toBeGreaterThan(0);
  });

  it('lets the gold spine emerge from the column without standing above it', () => {
    // ADR 0034 deleted the exceptional-match mark as a separate object: the
    // gold runs up *inside* the role's own column and out past the top of it.
    // Both bounds are that sentence. Too short and there is no gold to see;
    // too long and it is a second vertical mark hanging over a first one,
    // which is the arrangement the ADR removed.
    //
    // The factor was 1.55 while a column was 90 m, where half again was 50 m
    // of tip. Against a 1.65 km spire the same factor is 900 m of gold
    // standing alone, so it moved rather than the rule.
    expect(BEAM_LENGTH).toBeGreaterThan(COLUMN_HEIGHT);
    expect(BEAM_LENGTH).toBeLessThan(COLUMN_HEIGHT * 1.3);
  });

  it('draws the saved outline as lines rather than as a surface', () => {
    // §6 asks for a *thin outline*. A filled shell at this size would read as a
    // bigger beacon, which is the applied treatment.
    expect(markMaterial('outline').wireframe).toBe(true);
  });

  it('does not let a mark write depth over the beacon it decorates', () => {
    for (const kind of MARK_KINDS) {
      expect(markMaterial(kind).depthWrite).toBe(false);
    }
  });
});

describe('the two rotations a mark carries', () => {
  /** Where instance 0's own normal points, in scene space. */
  function normalOf(marks: ReturnType<typeof createMarkMesh>): Vector3 {
    const matrix = new Matrix4();
    marks.mesh.getMatrixAt(0, matrix);
    return new Vector3(0, 0, 1).applyMatrix4(new Matrix4().extractRotation(matrix));
  }

  it('leaves the gold spine vertical at every camera pose', () => {
    // The assertion this file was missing, and the reason a defect survived
    // three milestones: §6 asks for a "gold vertical beacon" and the renderer
    // drew a slowly rotating diagonal bar, because every mark was billboarded
    // and spun for the sake of the one mark that needs it. A human found it in
    // a screenshot. Nothing here could have.
    //
    // Vertical in the *world*, checked at a pose that would tilt it — a pitched
    // and rotated camera is exactly the case a billboard would break.
    const marks = createMarkMesh({ kind: 'beam', capacity: 4 });
    marks.set([{ x: 0, y: 0, z: 700, tint: '#ffcf5c' }]);

    marks.orient(Math.PI / 3, 40, 76);

    const up = normalOf(marks);
    expect(up.x).toBeCloseTo(0, 6);
    expect(up.y).toBeCloseTo(0, 6);
    expect(Math.abs(up.z)).toBeCloseTo(1, 6);
  });

  it('leaves the collar and the core in the world too', () => {
    for (const kind of ['outline', 'core'] as const) {
      const marks = createMarkMesh({ kind, capacity: 4 });
      marks.set([{ x: 0, y: 0, z: 700, tint: '#eaf1fa' }]);
      marks.orient(Math.PI / 3, 40, 76);
      const up = normalOf(marks);
      expect(Math.abs(up.z), `${kind} was turned to face the camera`).toBeCloseTo(1, 6);
    }
  });

  it('spins a mark without changing where it faces', () => {
    // The bug this exists for was visible and wrong rather than subtle: folding
    // the spin into the billboard Euler as a y-rotation puts it *between* the
    // tilt and the turn, and rolls the arc out of the camera plane — on screen
    // it stops being a ring around a beacon and becomes a flat ellipse lying
    // across it.
    const marks = createMarkMesh({ kind: 'ring', capacity: 4 });
    marks.set([{ x: 0, y: 0, z: 700, tint: '#5ce8ff' }]);

    marks.orient(0, 40, 76);
    const still = normalOf(marks);
    marks.orient(Math.PI / 3, 40, 76);
    const spinning = normalOf(marks);

    expect(spinning.x).toBeCloseTo(still.x, 5);
    expect(spinning.y).toBeCloseTo(still.y, 5);
    expect(spinning.z).toBeCloseTo(still.z, 5);
  });

  it('turns a mark to face a camera that has moved', () => {
    // The other half, so the test above cannot be satisfied by a mark that
    // never rotates at all.
    const marks = createMarkMesh({ kind: 'ring', capacity: 4 });
    marks.set([{ x: 0, y: 0, z: 700, tint: '#5ce8ff' }]);

    marks.orient(0, 0, 0);
    const flat = normalOf(marks);
    marks.orient(0, 0, 76);
    const pitched = normalOf(marks);

    expect(pitched.equals(flat)).toBe(false);
  });

  it('leaves the arc open, so its rotation is something you can see', () => {
    // A closed torus is rotationally symmetric about its own axis: spinning it
    // draws an identical image every frame, and §6's "rotating ring" would be
    // a still ring nobody could tell from a decoration.
    expect(RING_ARC).toBeLessThan(Math.PI * 2);
    expect(RING_ARC).toBeGreaterThan(Math.PI);
  });
});
