import { describe, expect, it } from 'vitest';

import { CELL_HEIGHT, CELL_WIDTH, MAX_LABELS } from './labelAtlas';
import { createLabelMesh, LABEL_HEIGHT, LABEL_WIDTH } from './labelMesh';
import { COMPANY_SPACING, LABEL_GAP, type FieldColumn } from './unresolvedField';

/**
 * jsdom has no 2D context and no GPU, so no atlas is painted and nothing is
 * drawn — `vitest.setup.ts` makes `getContext` return null on purpose. What is
 * provable here is the geometry and the bookkeeping: that a plate cannot be
 * wide enough to label its neighbour, that the instance count follows the
 * columns, and that disposal is complete. The plates *appearing*, and facing
 * the camera, are `city.spec.ts`'s claims.
 */

function column(name: string, x: number, roles = 1): FieldColumn {
  return { companyId: name.toLowerCase(), name, roles, x, y: 0, labelAltitude: 700 + LABEL_GAP };
}

describe('a name plate’s size', () => {
  it('cannot reach into the next employer’s airspace', () => {
    // The whole reason a plate is allowed to be as large as it is. If the field
    // is ever tightened or the plate enlarged, this goes red rather than the
    // city quietly starting to caption the wrong columns.
    expect(LABEL_WIDTH).toBeLessThan(COMPANY_SPACING);
  });

  it('keeps the cell’s aspect, so the text is not stretched', () => {
    expect(LABEL_WIDTH / LABEL_HEIGHT).toBeCloseTo(CELL_WIDTH / CELL_HEIGHT, 10);
  });
});

describe('createLabelMesh', () => {
  it('draws nothing before it is given anything', () => {
    const labels = createLabelMesh();

    expect(labels.drawn).toBe(0);
    expect(labels.mesh.count).toBe(0);
    labels.dispose();
  });

  it('draws one plate per column', () => {
    const labels = createLabelMesh();

    labels.setColumns([column('Alloy', -620, 9), column('Ramp', 620, 12)], '#5ce8ff');

    expect(labels.drawn).toBe(2);
    expect(labels.mesh.count).toBe(2);
    expect(labels.unlabelled).toBe(0);
    labels.dispose();
  });

  it('stops at the atlas ceiling and says how many it left unnamed', () => {
    const labels = createLabelMesh();
    const tooMany = Array.from({ length: MAX_LABELS + 4 }, (_, i) =>
      column(`Company ${i}`, i * 620),
    );

    labels.setColumns(tooMany, '#5ce8ff');

    // An InstancedMesh allocates once at its declared count; writing past it is
    // silent in three.js. The overflow has to be counted, not clipped.
    expect(labels.drawn).toBe(MAX_LABELS);
    expect(labels.mesh.count).toBe(MAX_LABELS);
    expect(labels.unlabelled).toBe(4);
    labels.dispose();
  });

  it('forgets the last field rather than keeping its plates', () => {
    const labels = createLabelMesh();
    labels.setColumns([column('Alloy', 0)], '#5ce8ff');

    labels.setColumns([], '#5ce8ff');

    expect(labels.drawn).toBe(0);
    expect(labels.mesh.count).toBe(0);
    labels.dispose();
  });

  it('hangs each plate over its own column', () => {
    const labels = createLabelMesh();
    const columns = [column('Alloy', -620, 3), column('Ramp', 620, 1)];

    labels.setColumns(columns, '#5ce8ff');

    // Read back out of the instance matrix rather than recomputed, so a
    // transform that mirrored or mis-scaled the whole set — which still
    // produces the right *number* of plates, in the wrong place — is caught.
    for (const [index, expected] of columns.entries()) {
      const matrix = labels.mesh.matrixWorld.clone();
      labels.mesh.getMatrixAt(index, matrix);
      expect(matrix.elements[12]).toBeCloseTo(expected.x, 6);
      expect(matrix.elements[13]).toBeCloseTo(expected.y, 6);
      expect(matrix.elements[14]).toBeCloseTo(expected.labelAltitude, 6);
    }
    labels.dispose();
  });

  it('reorients without moving a plate off its column', () => {
    const labels = createLabelMesh();
    labels.setColumns([column('Alloy', -620, 3)], '#5ce8ff');

    labels.orient(137, 42);

    const matrix = labels.mesh.matrixWorld.clone();
    labels.mesh.getMatrixAt(0, matrix);
    // A billboard rotates about its own anchor. If the rotation were applied
    // before the translation instead, every plate would swing around the scene
    // origin and leave its column behind as soon as the map was turned.
    expect(matrix.elements[12]).toBeCloseTo(-620, 6);
    expect(matrix.elements[14]).toBeCloseTo(700 + LABEL_GAP, 6);
    labels.dispose();
  });
});
