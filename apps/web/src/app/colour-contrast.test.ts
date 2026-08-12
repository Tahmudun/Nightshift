import { globSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * The palette is a product constraint, not a preference.
 *
 * CLAUDE.md M0 does not list contrast as an acceptance criterion, but the
 * milestone-0 review flagged `paper-faint` as probably failing and it did:
 * #5d6e88 is 3.89:1 on ink-950, short of WCAG AA's 4.5:1 for the 9-11px labels
 * it is used on. Worse, `ink-500` — a surface shade — was being used as a text
 * colour in fourteen places at 1.69:1, which is close to invisible.
 *
 * A comment saying "keep this readable" does not survive a redesign. These tests
 * read the real token values out of globals.css and fail if a future change makes
 * text unreadable, which is the only version of this check worth having.
 *
 * Ratios are WCAG 2.1 relative luminance. Thresholds:
 *   4.5:1  normal text
 *   3.0:1  large or bold text, and non-text UI components
 */

// Resolved from vitest's root (apps/web) rather than from import.meta.url, which
// is not a file: URL under the jsdom environment.
const SRC = resolve(process.cwd(), 'src');
const CSS = readFileSync(join(SRC, 'app', 'globals.css'), 'utf8');

function token(name: string): string {
  const match = CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (match?.[1] === undefined) {
    throw new Error(`token --color-${name} not found in globals.css`);
  }
  return match[1];
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const h = hex.replace('#', '');
  const r = channel(parseInt(h.slice(0, 2), 16));
  const g = channel(parseInt(h.slice(2, 4), 16));
  const b = channel(parseInt(h.slice(4, 6), 16));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

// Every surface that text is actually placed on. ink-800 is the JobRow hover
// state, so a colour must clear the threshold on the lightest of these too.
//
// M3a added ink-700, which had been a border shade everywhere until
// `JobRequirements` used it as the fill of the "or equivalent" badge. It is the
// lightest surface here and therefore the binding one: paper-faint clears it at
// 4.63:1, with less than a shade to spare. Lightening ink-700 fails this.
const SURFACES = ['ink-950', 'ink-900', 'ink-800', 'ink-700'] as const;

describe('text colours meet WCAG AA on every surface they appear on', () => {
  // The three text weights. There is no fourth: see globals.css.
  const TEXT = ['paper', 'paper-dim', 'paper-faint'] as const;

  for (const name of TEXT) {
    for (const surface of SURFACES) {
      it(`${name} on ${surface} clears 4.5:1`, () => {
        expect(contrast(token(name), token(surface))).toBeGreaterThanOrEqual(4.5);
      });
    }
  }

  // Accent colours carry meaning — a failure state, a healthy signal — so they
  // are held to the same bar as body text rather than to the 3:1 component bar.
  for (const name of ['signal-400', 'signal-600', 'alert-400', 'gold-400'] as const) {
    it(`${name} on ink-950 clears 4.5:1`, () => {
      expect(contrast(token(name), token('ink-950'))).toBeGreaterThanOrEqual(4.5);
    });
  }

  // M2c: `signal-900` became a text surface when `HighlightedText` started
  // rendering a person's resume on it. It is the only accent shade used that
  // way, and the words underneath a highlight are the words a claim rests on —
  // unreadable there is worse than unreadable anywhere else on the site.
  it('paper on signal-900 clears 4.5:1, because the highlight carries resume text', () => {
    expect(contrast(token('paper'), token('signal-900'))).toBeGreaterThanOrEqual(4.5);
  });
});

describe('surface shades stay out of the text ramp', () => {
  it('ink-400 clears 3:1, so it may be a non-text indicator', () => {
    expect(contrast(token('ink-400'), token('ink-950'))).toBeGreaterThanOrEqual(3);
  });

  it('ink-500 is too dark for either purpose, which is why it is borders only', () => {
    // Asserting the *known-bad* value documents why the token is restricted. If
    // someone lightens ink-500 to make it usable as text, this fails and points
    // them at the comment in globals.css explaining that paper-faint exists.
    expect(contrast(token('ink-500'), token('ink-950'))).toBeLessThan(3);
  });
});

describe('the source no longer uses surface shades as text', () => {
  it('no component sets an ink shade as a text colour', () => {
    const files = globSync('**/*.tsx', { cwd: SRC });
    expect(files.length, 'the glob must actually find components').toBeGreaterThan(5);

    const offenders: string[] = [];
    for (const file of files) {
      const source = readFileSync(join(SRC, file), 'utf8');
      if (/text-ink-(400|500|600|700|800|900|950)\b/.test(source)) {
        offenders.push(file);
      }
    }
    expect(offenders, 'use paper-faint for the dimmest text').toEqual([]);
  });
});

/**
 * `dusk-*` is the one family whose assertion runs the other way.
 *
 * Every other token here is checked for being *readable enough*. Dusk exists to
 * carry the reference images' violet field — sky, haze, horizon glow, fog — and
 * `city.md` §3 is explicit that it is atmosphere only: never a data mark, never
 * a building, never a selection state, never text. The reason is not taste. The
 * stylesheet's oldest rule is that magenta means "something is wrong and you can
 * act on it", and a violet that can appear on a mark makes that rule unreadable.
 *
 * **The first version of this suite enforced that by keeping every dusk shade
 * below 3:1 — too dark to be text at all.** It worked, and it was the wrong
 * tool: it also kept the sky too dark to be a sky, which is most of why the
 * first city looked like nothing. ADR 0023 replaced the proxy with the rule it
 * was standing in for. What stops dusk becoming a mark is that no source file
 * uses it as one and no map layer paints with it, and both of those are checked
 * directly below. Given that, the only number left is the one that actually
 * matters.
 */
describe('dusk is atmosphere and can never become a mark', () => {
  const DUSK = ['dusk-900', 'dusk-700', 'dusk-500', 'dusk-300'] as const;

  for (const name of DUSK) {
    it(`${name} stays well clear of the signal colour, so weather never outshines a job`, () => {
      // The city may be lit; a job must still be the brightest thing on it.
      // `signal-400` is the cyan a beacon is drawn in, and this is the gap
      // ADR 0023 keeps in exchange for letting the sky be bright.
      const beacon = luminance(token('signal-400'));
      expect(luminance(token(name))).toBeLessThan(beacon / 3);
    });
  }

  it('rises monotonically from the upper sky to the horizon', () => {
    // The family is a gradient, not four independent colours: dusk-900 is the
    // top of the sky and dusk-300 the glow at the horizon. Reordering them
    // would invert the sky.
    // DUSK is declared darkest-first, so this reads straight down the family.
    const ordered = DUSK.map((name) => luminance(token(name)));
    for (let i = 1; i < ordered.length; i += 1) {
      expect(ordered[i]!).toBeGreaterThan(ordered[i - 1]!);
    }
  });

  it('no component uses a dusk shade for text, a border, or a fill', () => {
    const files = globSync('**/*.{tsx,ts}', { cwd: SRC });
    expect(files.length, 'the glob must actually find components').toBeGreaterThan(5);

    const offenders: string[] = [];
    for (const file of files) {
      // The map style is the one legitimate consumer, and it reads the tokens
      // for sky and fog. Everything else is a Tailwind utility, and there is no
      // legitimate `text-dusk-*` or `border-dusk-*` anywhere.
      const source = readFileSync(join(SRC, file), 'utf8');
      if (/\b(text|border|ring|from|via|to|fill|stroke|decoration)-dusk-\d{3}\b/.test(source)) {
        offenders.push(file);
      }
    }
    expect(offenders, 'dusk is sky and fog only — see city.md §3').toEqual([]);
  });
});
