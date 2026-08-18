/**
 * What the sky is *not allowed* to do — and nothing about how it looks.
 *
 * ADR 0031 puts the look of M4e under the human's eye holding reference 02, and
 * says why in the sharpest terms this repository has: "a test that pins taste is
 * how the city stayed grey for two milestones". So there is no assertion here
 * about a gradient stop, a haze density, a star count or where the sun sits in
 * frame. Every one of those is tuned by looking, and every one of them will move
 * again.
 *
 * What is pinned is the part that is a *semantic* and would go wrong silently:
 * ADR 0029's brightness stack. A sun is exactly the sort of thing that gets one
 * shade brighter during a tuning pass and quietly becomes the brightest object
 * on screen, at which point the scenery is outshining the data and no screenshot
 * looks wrong — it looks nicer. That is the failure this file exists to catch,
 * and it is the same rule `palette.test.ts` holds over the style, held here over
 * the one surface that does not go through the style at all.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { BUILDING_LAYER_ID } from './darkStyle';
import { cameraDistanceMetres, SKY_COLOURS, skyBefore, SUN, sunDirection } from './skyLayer';

const CSS = readFileSync(resolve(process.cwd(), 'src', 'app', 'globals.css'), 'utf8');
const SOURCE = readFileSync(resolve(process.cwd(), 'src', 'lib', 'map', 'skyLayer.ts'), 'utf8');

function cssToken(name: string): string {
  const hex = CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1];
  if (hex === undefined) throw new Error(`--color-${name} is not in globals.css`);
  return hex;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** CIE L*, the same measure `palette.test.ts` and `darkStyle.test.ts` use. */
function lightness(hex: string): number {
  const h = hex.replace('#', '');
  const y =
    0.2126 * channel(parseInt(h.slice(0, 2), 16)) +
    0.7152 * channel(parseInt(h.slice(2, 4), 16)) +
    0.0722 * channel(parseInt(h.slice(4, 6), 16));
  return y <= 0.008856 ? 903.3 * y : 116 * Math.cbrt(y) - 16;
}

/** ADR 0029, and 20 for the reason `palette.test.ts` spells out at length. */
const MIN_HEADROOM_L = 20;

describe('the sky stays under the things that mean something', () => {
  it('leaves a job somewhere brighter to be, colour by colour', () => {
    const beacon = lightness(cssToken('signal-400'));
    for (const [key, value] of Object.entries(SKY_COLOURS)) {
      const headroom = beacon - lightness(value);
      expect(
        headroom,
        `sky ${key} (${value}) leaves only ${headroom.toFixed(1)} L*`,
      ).toBeGreaterThan(MIN_HEADROOM_L);
    }
  });

  it('stays under a hiring building, which is the dimmest thing that carries a state', () => {
    // The stack, stated where it can fail: city < hiring building < open role.
    // The sun is the sky's brightest colour and `alert-400` is the brightest the
    // city itself may draw, so this is the assertion that stops a tuning pass
    // from putting the weather above the data.
    const alert = lightness(cssToken('alert-400'));
    const brightest = Math.max(...Object.values(SKY_COLOURS).map(lightness));
    expect(
      brightest,
      `the sky reaches ${brightest.toFixed(1)} L*, alert-400 is ${alert.toFixed(1)}`,
    ).toBeLessThan(alert);
  });

  it('is a real ceiling, and something is actually near it', () => {
    // The other half, and the one that would have caught four milestones of
    // grey: every brightness rule this project has ever written is satisfied
    // perfectly by a sky painted entirely in `ink-950`. A one-sided bound
    // cannot fail in the direction this milestone actually went wrong.
    const alert = lightness(cssToken('alert-400'));
    const brightest = Math.max(...Object.values(SKY_COLOURS).map(lightness));
    expect(
      alert - brightest,
      'nothing in the sky is within reach of the ceiling; the sky has gone dark again',
    ).toBeLessThan(MIN_HEADROOM_L);
  });

  it('holds no colour that carries a meaning', () => {
    // `city.md` §3: `dusk-*` is atmosphere and may never be a mark, and the
    // families that *are* marks may never be the weather. A sky that reached for
    // the signal cyan would put "an open role" in the scenery, where there are
    // several thousand square pixels of it and no role at all.
    const meaningful = ['signal-400', 'signal-500', 'signal-600', 'alert-400', 'gold-400'];
    const reserved = meaningful.map((name) => cssToken(name).toLowerCase());
    const used = Object.values(SKY_COLOURS).map((hex) => hex.toLowerCase());
    expect(used.filter((hex) => reserved.includes(hex))).toEqual([]);
  });

  it('types no colour straight into the shader', () => {
    // The structural half of the rule, and the one that makes the numeric half
    // hold. Every assertion above reads `SKY_COLOURS`; a `vec3(...)` written
    // inline in the GLSL would be a colour on screen that no test has ever
    // seen. So the shader may only name constants, and this counts them.
    //
    // Matches float literals only, so `vec3(0.2)` — an offset inside the star
    // lattice, not a colour — is deliberately in scope too: it is cheaper to
    // list the two non-colour vectors here than to let a real colour hide
    // behind a clever regex.
    const shader = SOURCE.slice(SOURCE.indexOf('const FRAGMENT_SOURCE'));
    const inline = shader.match(/vec3\(\s*[\d.]+/g) ?? [];
    const allowed = [
      'vec3(12.9898', // the hash constants
      'vec3(19.19',
      'vec3(41.03',
      'vec3(0.2)', // the star's offset inside its cell
    ];
    const unexplained = inline.filter((match) => !allowed.some((ok) => ok.startsWith(match)));
    expect(unexplained, 'a literal vector in the shader that no test can read').toEqual([]);
  });

  it('draws its colours from the constants, so the shader and the tests agree', () => {
    const shader = SOURCE.slice(SOURCE.indexOf('const FRAGMENT_SOURCE'));
    for (const key of Object.keys(SKY_COLOURS)) {
      expect(shader, `SKY_COLOURS.${key} never reaches the shader`).toContain(`SKY_COLOURS.${key}`);
    }
  });
});

describe('the sun is where the product says it is', () => {
  it('sets in the west, over the Hudson', () => {
    // Not taste: "low in the west" is a statement about New York, and the sign
    // of one component is the difference between a sunset over the Hudson and
    // one over Queens. The mercator y-flip in the shader is the kind of thing
    // that silently mirrors this, and a screenshot of the wrong side of the
    // island looks exactly as pretty as the right one.
    const [east, north, up] = sunDirection(SUN.azimuthDeg, SUN.elevationDeg);
    expect(east, 'the sun is not in the west').toBeLessThan(-0.9);
    expect(Math.abs(north), 'the sun is far off due west').toBeLessThan(0.4);
    expect(up, 'the sun has set').toBeGreaterThan(0);
  });

  it('is low enough that the city stands in front of it', () => {
    expect(SUN.elevationDeg).toBeGreaterThan(0);
    expect(SUN.elevationDeg).toBeLessThan(5);
  });

  it('is a unit vector, so the shader can compare it with a ray directly', () => {
    const d = sunDirection(SUN.azimuthDeg, SUN.elevationDeg);
    const length = Math.hypot(...d);
    expect(length).toBeCloseTo(1, 12);
  });
});

describe('the haze knows how far away the camera is', () => {
  const FOV = (36.87 * Math.PI) / 180;

  it('measures the opening pose in kilometres, not metres', () => {
    // The first draft used a fixed 5,200 m and washed the whole island flat
    // magenta, because at zoom 13.6 the ground under the *bottom* of the frame
    // is already kilometres away. This is the number that mistake was made of.
    const metres = cameraDistanceMetres(13.6, 40.7449, 900, FOV);
    expect(metres).toBeGreaterThan(8_000);
    expect(metres).toBeLessThan(20_000);
  });

  it('halves for every zoom level in, which is what makes one density work everywhere', () => {
    const far = cameraDistanceMetres(13, 40.7449, 900, FOV);
    const near = cameraDistanceMetres(14, 40.7449, 900, FOV);
    expect(near).toBeCloseTo(far / 2, 6);
  });

  it('grows with a taller viewport, because a taller frame sees further', () => {
    const short = cameraDistanceMetres(13.6, 40.7449, 600, FOV);
    const tall = cameraDistanceMetres(13.6, 40.7449, 1200, FOV);
    expect(tall).toBeCloseTo(short * 2, 6);
  });
});

describe('the sky goes under the buildings', () => {
  it('names the building layer when there is one', () => {
    // The haze lands on ground MapLibre has already drawn, so what is above
    // this layer is unhazed by construction. Getting this wrong puts weather in
    // front of the skyline instead of behind it.
    expect(skyBefore({ getLayer: () => ({}) })).toBe(BUILDING_LAYER_ID);
  });

  it('goes on top when the archive is missing and there is no skyline', () => {
    // `buildDarkStyle({ buildings: false })` is a real state — the city says so
    // on screen — and `addLayer` throws on a `beforeId` that is not there, which
    // would take the whole map down rather than the skyline.
    expect(skyBefore({ getLayer: () => undefined })).toBeUndefined();
  });
});
