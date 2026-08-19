/**
 * What the glow is not allowed to do — and nothing about how much of it there is.
 *
 * ADR 0031 puts M4e's look under the human's eye holding reference 02, so there
 * is no assertion here about `BLOOM_THRESHOLD`, `BLOOM_STRENGTH` or an octave
 * weight. Every one of those is tuned by looking and every one of them will
 * move again; a test holding them would be the mechanism that kept the city
 * grey for two milestones, rebuilt.
 *
 * What *is* pinned is the arithmetic underneath, which goes wrong silently:
 *
 * - The soft-knee curve passes nothing below the threshold. A curve that leaked
 *   at the bottom would lift the whole frame by a few code values, which does
 *   not look like a bug — it looks like a slightly milkier city, and it would
 *   take the black point off ADR 0029's brightness stack without changing a
 *   single colour in it.
 * - The curve never returns more than the pixel it was given. Above one, bloom
 *   amplifies rather than spreads, and a compositor that multiplies a colour by
 *   1.4 before blurring it is a colour grade nobody asked for.
 * - The octave chain never reaches a zero-sized target. A zero-width texture is
 *   an incomplete framebuffer, and an incomplete framebuffer is a black frame
 *   with a console warning nobody is watching for. Reachable on a real device:
 *   a short landscape viewport on a phone.
 *
 * The GL itself is not exercised here and cannot be — jsdom has no WebGL 2, and
 * a mock of `blitFramebuffer` would be a test of the mock. What runs the shader
 * is `e2e/city.spec.ts` in a real browser, and what judges it is a screenshot.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  BLOOM_KNEE,
  BLOOM_OCTAVE_WEIGHTS,
  BLOOM_OCTAVES,
  BLOOM_THRESHOLD,
  bloomContribution,
  octaveSizes,
} from './bloom';

const SOURCE = readFileSync(resolve(process.cwd(), 'src', 'lib', 'city', 'bloom.ts'), 'utf8');

describe('the soft-knee threshold', () => {
  it('passes nothing at all below the knee', () => {
    const floor = BLOOM_THRESHOLD - BLOOM_KNEE;
    for (const luma of [0, 0.01, 0.05, floor * 0.5, floor - 0.001]) {
      expect(bloomContribution(luma, BLOOM_THRESHOLD, BLOOM_KNEE)).toBe(0);
    }
  });

  it('never returns more than the pixel it was handed', () => {
    for (let luma = 0; luma <= 1; luma += 0.01) {
      const contribution = bloomContribution(luma, BLOOM_THRESHOLD, BLOOM_KNEE);
      expect(contribution).toBeLessThanOrEqual(1.0000001);
      expect(contribution).toBeGreaterThanOrEqual(0);
    }
  });

  it('rises monotonically, so a surface crossing the threshold cannot flicker', () => {
    let previous = -1;
    for (let luma = 0; luma <= 1; luma += 0.005) {
      const contribution = bloomContribution(luma, BLOOM_THRESHOLD, BLOOM_KNEE);
      expect(contribution).toBeGreaterThanOrEqual(previous - 1e-9);
      previous = contribution;
    }
  });

  it('is a ramp through the knee rather than a step at the threshold', () => {
    // The whole reason the knee exists: at the threshold itself the pixel is
    // already contributing something, so a rotating camera does not snap the
    // glow on along every lit edge as its shading crosses the line.
    const at = bloomContribution(BLOOM_THRESHOLD, BLOOM_THRESHOLD, BLOOM_KNEE);
    expect(at).toBeGreaterThan(0);
    expect(at).toBeLessThan(0.5);
  });

  it('is the same curve the shader computes', () => {
    // Two implementations of one formula, and the GLSL one cannot be called
    // from here. Holding the source to the same five terms is weaker than
    // running it and stronger than nothing — it catches the edit that changes
    // one of them and forgets the other.
    expect(SOURCE).toContain('soft = soft * soft / (4.0 * u_knee + 0.0001);');
    expect(SOURCE).toContain('max(soft, luma - u_threshold) / max(luma, 0.0001)');
  });
});

describe('the octave chain', () => {
  it('gives every octave a weight', () => {
    expect(BLOOM_OCTAVE_WEIGHTS).toHaveLength(BLOOM_OCTAVES);
  });

  it('halves the frame once for the copy and once per octave', () => {
    const sizes = octaveSizes(2880, 1800);
    expect(sizes).toHaveLength(BLOOM_OCTAVES + 1);
    expect(sizes[0]).toEqual({ width: 1440, height: 900 });
    expect(sizes[1]).toEqual({ width: 720, height: 450 });
    expect(sizes[3]).toEqual({ width: 180, height: 112 });
  });

  it('never produces a zero-sized target, however short the viewport', () => {
    // A phone in landscape with the browser chrome up, and then the absurd
    // case, because the clamp is the thing being tested rather than the number.
    for (const [width, height] of [
      [1600, 40],
      [8, 8],
      [1, 1],
    ] as const) {
      for (const size of octaveSizes(width, height)) {
        expect(size.width).toBeGreaterThanOrEqual(1);
        expect(size.height).toBeGreaterThanOrEqual(1);
      }
    }
  });
});

describe('what the effect refuses to assume', () => {
  it('writes back to the framebuffer that was bound, not to the default one', () => {
    // MapLibre does not always draw into framebuffer null — terrain and a
    // projection transition both put it somewhere else — and a post-process
    // that hard-codes null blooms a buffer nobody presents. The symptom is a
    // city with no glow on exactly the configurations nobody develops against.
    expect(SOURCE).toContain('gl.getParameter(gl.FRAMEBUFFER_BINDING)');
  });

  it('feature-tests the one call that needs WebGL 2', () => {
    expect(SOURCE).toContain("typeof gl2.blitFramebuffer === 'function'");
  });
});
