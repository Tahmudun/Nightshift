import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  createSelectionMesh,
  SELECTION_COLOR,
  SELECTION_INNER_RADIUS,
  SELECTION_OUTER_RADIUS,
} from './selectionMesh';
import { BEACON_RADIUS } from './signalLayer';
import { ROLE_SPACING } from './unresolvedField';

describe('the selection reticle’s size', () => {
  it('is a ring around the beacon rather than a disc over it', () => {
    // Drawn inside the beacon it is invisible; drawn over it, it hides the very
    // thing it is pointing at. The relationship is asserted rather than the
    // numbers, so enlarging a beacon goes red here instead of quietly swallowing
    // the reticle.
    expect(SELECTION_INNER_RADIUS).toBeGreaterThan(BEACON_RADIUS);
    expect(SELECTION_OUTER_RADIUS).toBeGreaterThan(SELECTION_INNER_RADIUS);
  });

  it('is large enough to be found at the range this field is read at', () => {
    // A reticle that fits between two roles in a stack is a reticle nobody can
    // see from a camera kilometres away — the same lesson the name plates cost
    // (55 m looked fine in a screenshot and was too small on a screen).
    expect(SELECTION_OUTER_RADIUS).toBeGreaterThan(ROLE_SPACING);
  });

  it('uses the foreground colour the stylesheet defines, not a copy of it', () => {
    const css = readFileSync(join(process.cwd(), 'src/app/globals.css'), 'utf8');
    const match = /--color-paper:\s*(#[0-9a-fA-F]{6})/.exec(css);

    expect(match).not.toBeNull();
    expect(SELECTION_COLOR.toLowerCase()).toBe(match?.[1]?.toLowerCase());
  });
});

describe('createSelectionMesh', () => {
  it('is off the city until something is selected', () => {
    const reticle = createSelectionMesh();

    expect(reticle.visible).toBe(false);
    expect(reticle.at).toBeNull();
  });

  it('goes where it is put, and says so', () => {
    const reticle = createSelectionMesh();

    reticle.moveTo(620, -620, 745);

    expect(reticle.visible).toBe(true);
    expect(reticle.at).toEqual([620, -620, 745]);
    expect(reticle.mesh.position.toArray()).toEqual([620, -620, 745]);
  });

  it('comes off the city entirely when the selection is cleared', () => {
    const reticle = createSelectionMesh();
    reticle.moveTo(0, 0, 700);

    reticle.clear();

    // Not "moved out of sight". A hidden mesh at a stale position is a mesh
    // that reappears in the wrong place the next time anything touches it.
    expect(reticle.visible).toBe(false);
    expect(reticle.at).toBeNull();
  });

  it('turns to the camera, in the direction a rotating map actually turns', () => {
    const reticle = createSelectionMesh();

    reticle.orient(90, 60);

    // The same negated z as the name plates: the scene reaches mercator through
    // a transform that flips y, which reverses the apparent direction of every
    // rotation about z. Derived on paper this comes out backwards, and a ring
    // turning the wrong way looks correct from the opening pose.
    expect(reticle.mesh.rotation.z).toBeCloseTo(-Math.PI / 2, 6);
    expect(reticle.mesh.rotation.x).toBeCloseTo(Math.PI / 3, 6);
  });

  it('keeps facing the camera when it moves to a new role', () => {
    // `focusOn` deliberately does not move a camera that is already looking at
    // the thing selected, so most selections are followed by no map movement
    // and therefore no `orient` call at all. A reticle that lost its angles on
    // a move would spend that whole time as a circle painted flat over New
    // York, which is the one thing an unresolved role must never appear to be.
    const reticle = createSelectionMesh();
    reticle.orient(120, 76);

    reticle.moveTo(0, 0, 700);

    expect(reticle.mesh.rotation.z).toBeCloseTo((-120 * Math.PI) / 180, 6);
    expect(reticle.mesh.rotation.x).toBeCloseTo((76 * Math.PI) / 180, 6);
  });

  it('does no work when the camera has not actually turned', () => {
    const reticle = createSelectionMesh();
    reticle.orient(45, 60);
    const before = reticle.mesh.matrix.elements.slice();

    reticle.orient(45, 60);

    expect(reticle.mesh.matrix.elements.slice()).toEqual(before);
  });
});
