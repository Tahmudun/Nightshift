/**
 * The map palette is a copy, so it gets a test that the copy is still true.
 *
 * MapLibre cannot read a CSS custom property, so `palette.ts` restates the
 * tokens as literals. That is duplication, and duplication in this repository
 * has a track record: six times now a description has outlived the thing it
 * described. A colour changed in `globals.css` and not here would leave the
 * whole city drawn in the old palette, and nothing would look broken enough to
 * report.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { MAP_PALETTE } from './palette';

const CSS = readFileSync(resolve(process.cwd(), 'src', 'app', 'globals.css'), 'utf8');

/** `ink950` -> `--color-ink-950`. */
function tokenName(key: string): string {
  return `--color-${key.replace(/(\d+)$/, '-$1')}`;
}

function token(key: string): string | undefined {
  return CSS.match(new RegExp(`${tokenName(key)}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1]?.toLowerCase();
}

/** A token by its CSS name (`signal-400`), for the families the palette excludes. */
function cssToken(name: string): string {
  const hex = CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1];
  if (hex === undefined) throw new Error(`--color-${name} is not in globals.css`);
  return hex;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/**
 * CIE L*, not a WCAG contrast ratio — the same measure `darkStyle.test.ts` uses
 * and for the same reason: the ratio's flare term dominates at these
 * luminances, and L* is perceptually uniform, so a margin stated in it means
 * something a person can see.
 */
function lightness(hex: string): number {
  const h = hex.replace('#', '');
  const y =
    0.2126 * channel(parseInt(h.slice(0, 2), 16)) +
    0.7152 * channel(parseInt(h.slice(2, 4), 16)) +
    0.0722 * channel(parseInt(h.slice(4, 6), 16));
  return y <= 0.008856 ? 903.3 * y : 116 * Math.cbrt(y) - 16;
}

/** ADR 0029. See the assertion below for why it is 20 and not a rounder number. */
const MIN_HEADROOM_L = 20;

describe('every map colour is the token it claims to be', () => {
  for (const [key, value] of Object.entries(MAP_PALETTE)) {
    it(`${key} matches ${tokenName(key)}`, () => {
      expect(token(key), `${tokenName(key)} is not in globals.css`).toBeDefined();
      expect(value.toLowerCase()).toBe(token(key));
    });
  }
});

describe('the palette stays out of the families that carry meaning', () => {
  it('holds no signal, alert or gold shade', () => {
    // The basemap is the surface data is read against. A basemap that reached
    // for the signal colour would be spending the encoding on scenery, and by
    // M4c there would be cyan on the map that means nothing.
    const meaningful = ['signal-400', 'signal-500', 'signal-600', 'alert-400', 'gold-400'];
    const reserved = meaningful
      .map((name) => CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1])
      .filter((hex): hex is string => hex !== undefined)
      .map((hex) => hex.toLowerCase());
    expect(reserved.length, 'the meaning-carrying tokens must exist to be excluded').toBe(
      meaningful.length,
    );

    const used = Object.values(MAP_PALETTE).map((hex) => hex.toLowerCase());
    expect(used.filter((hex) => reserved.includes(hex))).toEqual([]);
  });

  it('leaves a job somewhere brighter to be, entry by entry', () => {
    // The ceiling, asserted at the source rather than at the point of use.
    //
    // ADR 0023 set this at 40 L* when the only thing being held down was a grey
    // skyline; ADR 0029 lit the city and moved it to 20, which is the number the
    // encoding actually needs. 20 is not a round guess: `alert-400` — the
    // hiring building, the brightest thing the city itself is allowed to draw —
    // sits 22.0 L* below `signal-400`, so 20 admits it and admits nothing above
    // it. The stack the product depends on, in order: scenery < a company that
    // is hiring < an open role.
    //
    // Held over every entry rather than over the maximum, so a single shade
    // creeping up is a named failure instead of a number that moved.
    const beacon = lightness(cssToken('signal-400'));
    for (const [key, value] of Object.entries(MAP_PALETTE)) {
      const headroom = beacon - lightness(value);
      expect(headroom, `${key} (${value}) leaves only ${headroom.toFixed(1)} L*`).toBeGreaterThan(
        MIN_HEADROOM_L,
      );
    }
  });

  it('is a real ceiling, and something is actually near it', () => {
    // The other direction. A palette that passed the rule above by being
    // uniformly near-black would satisfy every assertion in this file and be
    // exactly the city M4e exists to replace — the failure ADR 0029 names, with
    // a green suite over it.
    const beacon = lightness(cssToken('signal-400'));
    const brightest = Math.max(...Object.values(MAP_PALETTE).map(lightness));
    expect(
      beacon - brightest,
      'nothing in the palette is within reach of the ceiling; the city has gone dark again',
    ).toBeLessThan(MIN_HEADROOM_L + 20);
  });

  it('holds no paper shade, because this style draws no text', () => {
    const text = ['paper', 'paper-dim', 'paper-faint']
      .map((name) => CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1])
      .filter((hex): hex is string => hex !== undefined)
      .map((hex) => hex.toLowerCase());
    const used = Object.values(MAP_PALETTE).map((hex) => hex.toLowerCase());
    expect(used.filter((hex) => text.includes(hex))).toEqual([]);
  });
});
