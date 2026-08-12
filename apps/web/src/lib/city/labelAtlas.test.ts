import { describe, expect, it } from 'vitest';

import {
  ATLAS_SIZE,
  atlasCell,
  CELL_HEIGHT,
  CELL_WIDTH,
  LABELS_PER_ROW,
  MAX_LABEL_CHARS,
  MAX_LABELS,
  planAtlas,
  truncateLabel,
} from './labelAtlas';

/**
 * Everything here is arithmetic, and that is the point of the file it tests.
 * The painting needs a 2D context and is proven in `city.spec.ts`; the layout
 * is what silently puts a label in the wrong half of a texture, and it can be
 * proven at a desk.
 */

describe('atlasCell', () => {
  it('lays cells left to right, then wraps down a row', () => {
    expect(atlasCell(0)).toMatchObject({ px: 0, py: 0 });
    expect(atlasCell(1)).toMatchObject({ px: CELL_WIDTH, py: 0 });
    expect(atlasCell(LABELS_PER_ROW)).toMatchObject({ px: 0, py: CELL_HEIGHT });
    expect(atlasCell(LABELS_PER_ROW + 1)).toMatchObject({ px: CELL_WIDTH, py: CELL_HEIGHT });
  });

  it('measures v from the opposite edge of the texture to py', () => {
    // The flip that silently renders every name upside down. A 2D canvas
    // paints downward from the top-left; a sampler reads upward from the
    // bottom-left. The first cell is at the *top* of the canvas, so its uv
    // origin is at the far side of the texture.
    const first = atlasCell(0);
    expect(first?.py).toBe(0);
    expect(first?.v).toBeCloseTo((ATLAS_SIZE - CELL_HEIGHT) / ATLAS_SIZE);

    const secondRow = atlasCell(LABELS_PER_ROW);
    expect(secondRow?.py).toBe(CELL_HEIGHT);
    // One row further down the canvas is one row *lower* in v.
    expect(secondRow!.v).toBeLessThan(first!.v);
    expect(first!.v - secondRow!.v).toBeCloseTo(CELL_HEIGHT / ATLAS_SIZE);
  });

  it('keeps every cell inside the texture', () => {
    for (let i = 0; i < MAX_LABELS; i += 1) {
      const cell = atlasCell(i);
      expect(cell).not.toBeNull();
      expect(cell!.px + CELL_WIDTH).toBeLessThanOrEqual(ATLAS_SIZE);
      expect(cell!.py + CELL_HEIGHT).toBeLessThanOrEqual(ATLAS_SIZE);
      expect(cell!.u).toBeGreaterThanOrEqual(0);
      expect(cell!.v).toBeGreaterThanOrEqual(0);
      expect(cell!.u + cell!.uw).toBeLessThanOrEqual(1);
      expect(cell!.v + cell!.vh).toBeLessThanOrEqual(1);
    }
  });

  it('gives no two labels the same rectangle', () => {
    // An overlap is two employers sharing a name plate, which is worse than no
    // plate: it is a confident wrong answer.
    const seen = new Set<string>();
    for (let i = 0; i < MAX_LABELS; i += 1) {
      const cell = atlasCell(i)!;
      const key = `${cell.px},${cell.py}`;
      expect(seen.has(key)).toBe(false);
      seen.add(key);
    }
    expect(seen.size).toBe(MAX_LABELS);
  });

  it('refuses an index the atlas has no room for', () => {
    expect(atlasCell(MAX_LABELS)).toBeNull();
    expect(atlasCell(-1)).toBeNull();
    expect(atlasCell(1.5)).toBeNull();
  });
});

describe('planAtlas', () => {
  it('reports what it could not fit rather than dropping it quietly', () => {
    const plan = planAtlas(MAX_LABELS + 7);

    expect(plan.drawn).toBe(MAX_LABELS);
    expect(plan.cells).toHaveLength(MAX_LABELS);
    // The count the interface prints. Without it, an unlabelled column is
    // indistinguishable from a column whose label failed to render.
    expect(plan.dropped).toBe(7);
  });

  it('drops nothing it has room for', () => {
    const plan = planAtlas(3);

    expect(plan.drawn).toBe(3);
    expect(plan.dropped).toBe(0);
  });

  it('plans nothing for an empty field', () => {
    expect(planAtlas(0)).toEqual({ cells: [], drawn: 0, dropped: 0 });
  });
});

describe('truncateLabel', () => {
  it('leaves a name that fits exactly as it is', () => {
    expect(truncateLabel('Ramp')).toBe('Ramp');
    expect(truncateLabel('x'.repeat(MAX_LABEL_CHARS))).toBe('x'.repeat(MAX_LABEL_CHARS));
  });

  it('marks a cut name so the cut is visible', () => {
    const long = 'Extremely Long Company Name LLC';
    const cut = truncateLabel(long);

    expect(cut).not.toBe(long);
    expect(cut.endsWith('…')).toBe(true);
    // A silently shortened name reads as the company's real name.
    expect(cut.length).toBeLessThanOrEqual(MAX_LABEL_CHARS);
  });

  it('never returns something wider than an untruncated name', () => {
    // The ellipsis has to come out of the budget, not be added to it, or a cut
    // name overflows its cell into the neighbouring company's plate.
    for (const length of [MAX_LABEL_CHARS + 1, MAX_LABEL_CHARS + 50]) {
      expect(truncateLabel('y'.repeat(length)).length).toBeLessThanOrEqual(MAX_LABEL_CHARS);
    }
  });

  it('does not leave a dangling space before the ellipsis', () => {
    const cut = truncateLabel('Company With Words Here And More', MAX_LABEL_CHARS);
    expect(cut).not.toMatch(/ …$/);
  });
});
