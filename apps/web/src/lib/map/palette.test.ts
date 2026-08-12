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

  it('holds no paper shade, because this style draws no text', () => {
    const text = ['paper', 'paper-dim', 'paper-faint']
      .map((name) => CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1])
      .filter((hex): hex is string => hex !== undefined)
      .map((hex) => hex.toLowerCase());
    const used = Object.values(MAP_PALETTE).map((hex) => hex.toLowerCase());
    expect(used.filter((hex) => text.includes(hex))).toEqual([]);
  });
});
