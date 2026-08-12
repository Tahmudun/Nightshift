import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  ARCHIVED_COLOR,
  BEACON_RADIUS,
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

  it('says whether anything in the buffer is actually animating', () => {
    // This is what decides whether the map asks for another frame. A layer that
    // repaints unconditionally pins a core at 60fps to redraw an identical
    // image; one that never repaints leaves the pulses frozen.
    const beacons = createBeaconMesh(16);

    beacons.set([beacon({ pulse: 0 })]);
    expect(beacons.animating).toBe(false);

    beacons.set([beacon({ pulse: PULSE_HZ.slow })]);
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

  it('keeps the beacon big enough to be seen from the pose the city opens at', () => {
    // Roughly a twelve-storey building. A marker sized like a map pin is a
    // single pixel at 76° of pitch from kilometres away.
    expect(BEACON_RADIUS).toBeGreaterThan(20);
  });
});
