/**
 * Company names, painted into one texture so the field can say what it is.
 *
 * `city.md` §4.8 asks for a field that is **legible**, and until this file
 * existed it was not: a column was an anonymous stack of diamonds, and a viewer
 * could see that three employers were hiring without being able to learn which
 * three. The name plate is the whole difference between a diagram and an index.
 *
 * **One texture, not one per label.** The obvious implementation gives every
 * company its own small canvas and its own `CanvasTexture`, which is one GPU
 * allocation per employer — fine at the three in today's corpus and roughly
 * 160 MB of texture memory at the 2,605 boards M1 measured as discoverable.
 * `CLAUDE.md` §8 names one-object-per-job as an anti-pattern for the same
 * reason, one floor down. Every name goes into a single 2048×2048 atlas and
 * every plate samples a rectangle of it, so the whole field costs one texture
 * and one draw call however many employers are hiring.
 *
 * **The layout is separated from the painting on purpose.** Everything above
 * `paintAtlas` is arithmetic and is unit-tested with no canvas, no GPU and no
 * browser; `paintAtlas` is the only part that needs a 2D context, and what it
 * produces is checked in `city.spec.ts` where there is a real one. That split
 * is the same one `signalLayer.ts` makes, and for the same reason: the parts of
 * a renderer that can be proven without a GPU should not need one.
 */

/** The atlas is square and a power of two, which every GL implementation likes. */
export const ATLAS_SIZE = 2048;

/**
 * One name plate's cell, in atlas pixels.
 *
 * 8:1 because a company name is a wide, short thing, and a cell shaped like
 * the text wastes no atlas on empty margin. The height is what sets legibility
 * — 64 px holds a ~40 px face, which is sharp at the distance these are read
 * from and still leaves 128 cells in a single texture.
 */
export const CELL_WIDTH = 512;
export const CELL_HEIGHT = 64;

/** Cells across, and the ceiling that falls out of the atlas size. */
export const LABELS_PER_ROW = ATLAS_SIZE / CELL_WIDTH;
export const MAX_LABELS = LABELS_PER_ROW * (ATLAS_SIZE / CELL_HEIGHT);

/**
 * How many characters a plate holds before it is cut.
 *
 * Measured against the cell rather than guessed: a 40 px monospace face is
 * about 24 px per character, and 512 px of cell less a margin holds 24 of them.
 * A name longer than that is truncated **on the plate only** — the roster panel
 * carries every name in full, so nothing is lost, and a plate that overflowed
 * its cell would bleed into the neighbouring company's name instead.
 */
export const MAX_LABEL_CHARS = 24;

/** The face. A system stack, because a web font is a network call (§5.2). */
export const LABEL_FONT = '600 40px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

/**
 * Where one plate's pixels live, and the rectangle of the texture it samples.
 *
 * Both coordinate systems are here because they disagree about which way is
 * up: a 2D canvas paints downward from the top-left, and WebGL samples upward
 * from the bottom-left. Keeping the conversion in one tested function is
 * cheaper than finding out later that every label is upside down.
 */
export interface AtlasCell {
  /** Pixel origin in the canvas, from the top-left. */
  readonly px: number;
  readonly py: number;
  /** UV origin, from the bottom-left, as the sampler reads it. */
  readonly u: number;
  readonly v: number;
  /** UV extent of one cell. */
  readonly uw: number;
  readonly vh: number;
}

/** The cell for the nth label, or `null` past the atlas's ceiling. */
export function atlasCell(index: number): AtlasCell | null {
  if (!Number.isInteger(index) || index < 0 || index >= MAX_LABELS) return null;

  const column = index % LABELS_PER_ROW;
  const row = Math.floor(index / LABELS_PER_ROW);
  const px = column * CELL_WIDTH;
  const py = row * CELL_HEIGHT;

  return {
    px,
    py,
    u: px / ATLAS_SIZE,
    // The flip. `CanvasTexture` defaults to `flipY: true`, so v = 0 is the
    // *bottom* of the canvas: a cell's uv origin is measured from the far side
    // of the texture from its pixel origin.
    v: (ATLAS_SIZE - py - CELL_HEIGHT) / ATLAS_SIZE,
    uw: CELL_WIDTH / ATLAS_SIZE,
    vh: CELL_HEIGHT / ATLAS_SIZE,
  };
}

/**
 * Cut a name to what a plate can hold, with an ellipsis so the cut is visible.
 *
 * A silently truncated name reads as the company's actual name, which is a
 * small lie of exactly the kind §5.3 refused for building heights.
 */
export function truncateLabel(text: string, max: number = MAX_LABEL_CHARS): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  // `max - 1` leaves room for the ellipsis, so the result is never wider than
  // a name that was not truncated at all.
  return `${trimmed.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

/** What an atlas covers, and what it had to leave out. */
export interface AtlasPlan {
  readonly cells: readonly AtlasCell[];
  /** Labels that got a plate. */
  readonly drawn: number;
  /**
   * Labels past the ceiling, which get no plate at all.
   *
   * Reported rather than swallowed. A column with no name is a column a person
   * cannot identify, and the interface says how many there are instead of
   * letting them look like columns that failed to render.
   */
  readonly dropped: number;
}

export function planAtlas(count: number): AtlasPlan {
  const drawn = Math.max(0, Math.min(count, MAX_LABELS));
  const cells: AtlasCell[] = [];
  for (let i = 0; i < drawn; i += 1) {
    const cell = atlasCell(i);
    if (cell) cells.push(cell);
  }
  return { cells, drawn, dropped: Math.max(0, count - drawn) };
}

/**
 * Paint the names into a canvas. The only part of this file that needs a DOM.
 *
 * Returns `null` where there is no 2D context to paint into — jsdom, mostly —
 * so the caller degrades to a field with no plates rather than throwing inside
 * a render method, where an exception would take the whole map down with it.
 */
export function paintAtlas(labels: readonly string[], colour: string): HTMLCanvasElement | null {
  if (typeof document === 'undefined') return null;

  const canvas = document.createElement('canvas');
  canvas.width = ATLAS_SIZE;
  canvas.height = ATLAS_SIZE;

  // `getContext` does not merely return null when there is no 2D context —
  // jsdom throws, and a throw here would propagate out of `setSignals` and
  // take the map down rather than costing it its name plates.
  let ctx: CanvasRenderingContext2D | null = null;
  try {
    ctx = canvas.getContext('2d');
  } catch {
    return null;
  }
  if (!ctx) return null;

  ctx.clearRect(0, 0, ATLAS_SIZE, ATLAS_SIZE);
  ctx.font = LABEL_FONT;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  const plan = planAtlas(labels.length);
  plan.cells.forEach((cell, index) => {
    const text = truncateLabel(labels[index] ?? '');
    const x = cell.px + CELL_WIDTH / 2;
    const y = cell.py + CELL_HEIGHT / 2;

    // A dark halo under the text, because a plate is read against whatever
    // happens to be behind it — sky, a lit tower, or another employer's
    // beacons — and cyan on a bright roof is unreadable at any size.
    ctx.lineWidth = 6;
    ctx.strokeStyle = 'rgba(2, 6, 12, 0.92)';
    ctx.strokeText(text, x, y);

    ctx.fillStyle = colour;
    ctx.fillText(text, x, y);
  });

  return canvas;
}
