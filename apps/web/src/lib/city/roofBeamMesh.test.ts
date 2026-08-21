import { Vector3 } from 'three';
import { describe, expect, it } from 'vitest';

import { createRoofBeamMesh, MAX_ROOF_BEAMS } from './roofBeamMesh';

import type { HiringBuilding } from './buildingField';

function building(overrides: Partial<HiringBuilding> = {}): HiringBuilding {
  return {
    buildingId: '1087186',
    name: 'Datadog',
    jobIds: ['a'],
    x: 100,
    y: 200,
    roofAltitude: 230,
    labelAltitude: 400,
    beamHeight: 260,
    ...overrides,
  };
}

/** Where instance `index` actually sits, read back out of the matrix. */
function positionOf(mesh: ReturnType<typeof createRoofBeamMesh>, index: number): Vector3 {
  const matrix = mesh.matrixAt(index);
  return matrix === null ? new Vector3(NaN, NaN, NaN) : new Vector3().setFromMatrixPosition(matrix);
}

describe('the beam over a hiring building', () => {
  it('draws nothing until a building is hiring', () => {
    expect(createRoofBeamMesh().drawn).toBe(0);
  });

  it('draws one beam per building rather than one per role', () => {
    const mesh = createRoofBeamMesh();

    mesh.set([
      building({ buildingId: 'a', jobIds: ['1', '2', '3'] }),
      building({ buildingId: 'b' }),
    ]);

    // §5.5's rule at the building's scale: the beam says "somebody is hiring
    // here", which is one fact about a structure however many roles are open
    // in it. Two beams stacked in the same column would also be twice as
    // bright as one, which would encode a number nobody asked it to.
    expect(mesh.drawn).toBe(2);
  });

  it('puts the lit rim exactly on the roofline it describes', () => {
    const mesh = createRoofBeamMesh();

    mesh.set([building({ roofAltitude: 230, beamHeight: 260 })]);

    // ADR 0034: the geometry stands on its own base, so the anchor *is* the
    // roof. It used to be centred and lifted half a height by the caller,
    // which was right for a shaft of even brightness and is wrong for a wash
    // — the brightest thing a wash draws is the band at its foot, and a
    // centred geometry buries that band inside the building it is marking.
    //
    // This is the assertion that caught the change, and it is worth keeping in
    // that form: the offset is not arithmetic anybody should have to redo, it
    // is the statement that the light starts where the structure ends.
    expect(positionOf(mesh, 0).z).toBeCloseTo(230, 3);
  });

  it('stands it over the building and nowhere else', () => {
    const mesh = createRoofBeamMesh();

    mesh.set([building({ x: 100, y: 200 })]);

    const at = positionOf(mesh, 0);
    expect([at.x, at.y]).toEqual([100, 200]);
  });

  it('is as tall as the stack it carries', () => {
    const mesh = createRoofBeamMesh();

    mesh.set([building({ beamHeight: 260 })]);

    expect(mesh.heightAt(0)).toBeCloseTo(260, 3);
  });

  it('forgets the last city when it is given a new one', () => {
    const mesh = createRoofBeamMesh();
    mesh.set([building({ buildingId: 'a' }), building({ buildingId: 'b' })]);

    mesh.set([building({ buildingId: 'c' })]);

    // The trap every instanced mesh in this directory has: `count` shrinks and
    // the stale matrices past it stay in the buffer, so the next longer city
    // draws a beam over a building nobody is hiring in any more.
    expect(mesh.drawn).toBe(1);
    expect(positionOf(mesh, 1).x).toBeNaN();
  });

  it('stops at its ceiling instead of writing past the buffer it allocated', () => {
    const mesh = createRoofBeamMesh();

    mesh.set(
      Array.from({ length: MAX_ROOF_BEAMS + 5 }, (_, i) => building({ buildingId: `b-${i}` })),
    );

    expect(mesh.drawn).toBe(MAX_ROOF_BEAMS);
  });
});
