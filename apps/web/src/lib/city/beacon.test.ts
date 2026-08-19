import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { ROOF_ROLE_SPACING } from './buildingField';
import { ROLE_SPACING } from './unresolvedField';

import {
  ARCHIVED_COLOR,
  COLUMN_BASE,
  COLUMN_HEIGHT,
  COLUMN_RADIUS,
  FLOW_BANDS,
  FLOW_HZ,
  MIN_COLUMN_HEIGHT_PX,
  MIN_COLUMN_WIDTH_PX,
  PICK_HEIGHT,
  PICK_RADIUS,
  RISE_HZ,
  createBeaconMesh,
  DIM_FACTOR,
  NEW_SCALE,
  PULSE_HZ,
  SIGNAL_COLOR,
  type Beacon,
} from './beacon';

/**
 * The beacon buffer: colour, strength and pulse, per instance.
 *
 * There is no GL here, so the shader itself is never compiled — what is checked
 * is everything the shader is *fed*, which is where the encoding lives. A pulse
 * rate of zero on a role first seen this morning is a §6 row that has silently
 * stopped meaning anything, and no screenshot would show it.
 */

const CSS = readFileSync(join(process.cwd(), 'src', 'app', 'globals.css'), 'utf8');

function beacon(overrides: Partial<Beacon> = {}): Beacon {
  return { x: 0, y: 0, z: 700, tint: SIGNAL_COLOR, alpha: 0.85, pulse: 0, scale: 1, ...overrides };
}

describe('createBeaconMesh', () => {
  it('draws nothing until it is given something', () => {
    const beacons = createBeaconMesh(16);

    expect(beacons.drawn).toBe(0);
  });

  it('writes each instance’s colour, strength and pulse where the shader reads them', () => {
    const beacons = createBeaconMesh(16);

    beacons.set([beacon({ tint: ARCHIVED_COLOR, alpha: 0.3, pulse: PULSE_HZ.rapid })]);

    expect(beacons.tintAt(0)).toBe(ARCHIVED_COLOR);
    expect(beacons.alphaAt(0)).toBeCloseTo(0.3);
    expect(beacons.pulseAt(0)).toBeCloseTo(PULSE_HZ.rapid);
  });

  it('reads back the altitude the buffer actually holds', () => {
    // Not the altitude it was handed — the one written into the matrix. A
    // transform that mirrored the whole field still produces the right *count*
    // of beacons, in entirely the wrong place.
    const beacons = createBeaconMesh(16);

    beacons.set([beacon({ z: 745 })]);

    expect(beacons.altitudeAt(0)).toBeCloseTo(745);
  });

  it('scales a new role up, so the pulse is not the only thing carrying it', () => {
    // Reduced motion turns the pulse off. If "new" were motion alone it would
    // vanish for the people who asked for less of it, so the size carries it
    // too and survives with the animation switched off.
    const beacons = createBeaconMesh(16);

    beacons.set([beacon({ scale: NEW_SCALE })]);

    expect(beacons.scaleAt(0)).toBeCloseTo(NEW_SCALE);
    expect(NEW_SCALE).toBeGreaterThan(1);
  });

  it('forgets the beacons it is no longer given', () => {
    const beacons = createBeaconMesh(16);

    beacons.set([beacon(), beacon({ z: 745 })]);
    beacons.set([beacon()]);

    expect(beacons.drawn).toBe(1);
    expect(beacons.altitudeAt(1)).toBeNull();
  });

  it('stops at its capacity rather than writing past the buffer', () => {
    const beacons = createBeaconMesh(2);

    beacons.set([beacon(), beacon(), beacon(), beacon()]);

    expect(beacons.drawn).toBe(2);
  });

  it('advances a clock the shader can read, and nothing else per frame', () => {
    const beacons = createBeaconMesh(16);

    beacons.tick(12.5);

    expect(beacons.timeAt).toBeCloseTo(12.5);
  });

  it('reports a drawn column as animating even when no role is new', () => {
    // ADR 0034 made the rise ambient — every column, all the time — and this
    // getter went on answering the question it answered before that ADR: is
    // some role new enough to earn a recency pulse?
    //
    // The seeded corpus hid it. 27 of its 30 roles are inside
    // `NEW_WINDOW_DAYS`, so something was always pulsing and the frames always
    // came. A corpus a week older — which is the same corpus, later — would
    // have gone still with a shader fully able to animate it, and nothing in
    // the suite or in a screenshot would have reported that.
    //
    // Restoring `pulse > 0` here turns this red, which is the point: "nothing
    // is new" and "nothing is moving" have stopped being the same sentence.
    const beacons = createBeaconMesh(16);

    beacons.set([beacon({ pulse: 0 })]);
    expect(beacons.animating).toBe(true);

    beacons.set([beacon({ pulse: PULSE_HZ.slow })]);
    expect(beacons.animating).toBe(true);
  });

  it('stops animating when there is nothing drawn', () => {
    // The other half: an empty city must not hold a repaint loop open.
    const beacons = createBeaconMesh(16);

    beacons.set([]);
    expect(beacons.animating).toBe(false);
  });

  it('goes still when motion is switched off, whatever is in the buffer', () => {
    // `prefers-reduced-motion`. The pulses are zeroed in the buffer by the
    // layer above; the ambient rise is not a fact about any role, so it is
    // switched off here instead — and switching it off has to stop the frames
    // as well as the shader, or the city repaints forever to draw one image.
    const beacons = createBeaconMesh(16);

    beacons.set([beacon({ pulse: 0 })]);
    beacons.setMotion(false);
    expect(beacons.animating).toBe(false);

    beacons.setMotion(true);
    expect(beacons.animating).toBe(true);
  });
});

describe('the palette the beacons are drawn from', () => {
  it('uses the signal cyan the stylesheet defines', () => {
    expect(CSS).toContain(`--color-signal-400: ${SIGNAL_COLOR}`);
  });

  it('uses a surface shade for an archived role, because it is not a signal', () => {
    // §6: a dim neutral archived state, deliberately not a red fracture. The
    // ink family is the one that carries no meaning of its own.
    expect(CSS).toContain(`--color-ink-450: ${ARCHIVED_COLOR}`);
  });

  it('keeps a dimmed role visible rather than invisible', () => {
    // §6 again: "not a glitch — a glitch reads as a bug, gets reported as one,
    // and then gets ignored". A stale role that faded to nothing would be
    // indistinguishable from a role that had closed.
    expect(DIM_FACTOR).toBeGreaterThan(0.3);
    expect(DIM_FACTOR).toBeLessThan(1);
  });

  it('pulses an internship faster than anything else', () => {
    expect(PULSE_HZ.rapid).toBeGreaterThan(PULSE_HZ.slow);
    expect(PULSE_HZ.none).toBe(0);
  });

  it('keeps every pulse slow enough not to be a flash', () => {
    // Three flashes a second is the seizure threshold in WCAG 2.3.1, and this
    // is nowhere near it — but the number is worth pinning, because "make the
    // new ones more obvious" is the most natural change anyone will ever make
    // to this file.
    expect(PULSE_HZ.rapid).toBeLessThan(1.5);
  });

  it('keeps the column narrow enough to belong to the building it stands on', () => {
    // The half of the M4c defect that is a *world* size. A beacon was a fixed
    // 34 m across from M4c, which nothing noticed while the whole field sat
    // 700 m up and was never approached; at street zoom it was several times
    // the width of the building underneath it. Nine metres is narrower than
    // any tower in New York, so a role standing on a roof reads as standing
    // on it.
    expect(COLUMN_RADIUS).toBeLessThan(12);
  });

  it('spires past every roof in New York', () => {
    // This assertion is the inverse of the one it replaces, which required the
    // column to be *under* 120 m. That rule was the width rule applied to the
    // wrong axis and it produced a fifty-pixel tick mark at the pose the city
    // opens on — a beacon that has to be pointed out is not one.
    //
    // One World Trade's roof is 417 m and its spire 541. A mark that does not
    // clear those is competing with the architecture instead of flagging it,
    // and `docs/design/references/02-*.jpg` is unambiguous that the columns
    // leave the skyline entirely.
    expect(COLUMN_HEIGHT).toBeGreaterThan(541 * 2);
  });

  it('keeps the marks on the body rather than spread up the spire', () => {
    // The saved collar, the interview arc and the selection reticle are all
    // cut against `COLUMN_BASE`. The job is at the bottom of the column; the
    // spire is the flag. Marks distributed over the spire's full length would
    // be three unrelated objects hanging in the sky above an employer.
    expect(COLUMN_BASE).toBeLessThan(COLUMN_HEIGHT / 5);
  });

  it('gives a click target the geometry actually carries', () => {
    // `pick.ts` raycasts three's geometry, and ADR 0034 moved the column's size
    // into the vertex shader — where the pixel floor can see how far away it
    // is, which is the whole point. What was left on the CPU was a *unit*
    // cylinder: a metre across at a city where a metre is a sixth of a pixel.
    // Every beacon was unclickable from the day the column shipped.
    //
    // So the geometry is the target and the shader scales to the light. The
    // target has to be wide enough to hit and not so wide that two employers
    // share one.
    expect(PICK_RADIUS).toBeGreaterThan(COLUMN_RADIUS * 2);
    expect(PICK_RADIUS).toBeLessThan(COLUMN_RADIUS * 4);
  });

  it('tiles the click targets of a stack instead of overlapping them', () => {
    // Roles at one employer stack *coaxially*, 45 m apart. A target as tall as
    // the spire puts every role in a stack inside every other role's target,
    // and one of them answers for the whole company — which is what happened
    // when this was first tried.
    //
    // Asserted against the two spacings rather than against 45, so a field
    // that spreads its roles further apart comes here rather than quietly
    // leaving gaps between the targets.
    expect(PICK_HEIGHT).toBe(ROOF_ROLE_SPACING);
    expect(PICK_HEIGHT).toBe(ROLE_SPACING);
    // And it is the light that is the flag, not the target.
    expect(PICK_HEIGHT).toBeLessThan(COLUMN_HEIGHT / 10);
  });

  it('keeps both floors in pixels, because metres alone vanish at the opening pose', () => {
    // The *screen* sizes, and they pair with the world sizes above: without
    // them a column honest in metres is a third of a pixel wide from twelve
    // kilometres. `cityBuildings.ts` solves the same problem for its edge
    // lines the same way.
    //
    // Two numbers rather than one factor applied to both axes: they were one
    // number, and the only way a distant column could get taller was by
    // getting fatter, which turns a light shaft into a lozenge.
    expect(MIN_COLUMN_WIDTH_PX).toBeGreaterThan(3);
    expect(MIN_COLUMN_HEIGHT_PX).toBeGreaterThan(MIN_COLUMN_WIDTH_PX * 8);
  });

  it('rises slowly enough to read as breathing rather than as a progress bar', () => {
    // And far under WCAG 2.3.1's three-a-second threshold, which it shares
    // with the two recency pulses it runs alongside.
    expect(RISE_HZ).toBeGreaterThan(0);
    expect(RISE_HZ).toBeLessThan(0.5);
  });

  it('keeps the travelling bands under the flash threshold too', () => {
    // The flow is the fastest thing on a beacon and the one somebody will
    // reach for when asked to make the city feel more alive, so it is the one
    // worth pinning. A band passing a fixed point at `FLOW_HZ` is that point's
    // flicker rate; WCAG 2.3.1's limit is three a second.
    expect(FLOW_HZ).toBeGreaterThan(0);
    expect(FLOW_HZ).toBeLessThan(1.5);
  });

  it('puts several bands on a spire, so motion is visible near the roof', () => {
    // One band per column is one band that spends most of its cycle above the
    // top of the frame — which is exactly how the envelope failed. Enough
    // bands that a few are always inside the first few hundred metres, where
    // the role is.
    expect(FLOW_BANDS).toBeGreaterThan(4);
    // And a wavelength no shorter than a tall building, or the shaft reads as
    // hatched rather than as flowing.
    expect(COLUMN_HEIGHT / FLOW_BANDS).toBeGreaterThan(100);
  });
});
