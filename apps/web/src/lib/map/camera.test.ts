/**
 * The camera, checked for the things that fail quietly.
 *
 * Every one of §5.4's two acceptance criteria and §9.3's gesture list is a
 * behaviour with no visible failure mode. A handler left enabled pans twice per
 * keypress, which reads as a fast map. An animation that ignores an interruption
 * reads as a slow one. A reduced-motion preference that is checked at three call
 * sites out of four reads as working, to anyone who does not have the preference
 * set. None of them throw.
 *
 * All of it runs against `FakeMap` — the fake is the point, not a shortcut. The
 * controller was written against an interface precisely so this file could exist
 * with no WebGL context, no tile archive and no frame budget, and so a
 * regression is found in eighty milliseconds instead of by looking at a city.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CameraController } from './camera';
import {
  CAMERA_LIMITS,
  clampUpdate,
  createCameraController,
  INITIAL_POSE,
  KEYBOARD_HELP,
} from './camera';
import { FakeMap, stubReducedMotion, type Call } from './camera.fixture';

let map: FakeMap;
let camera: CameraController;

function build(options: { readonly reducedMotion?: boolean } = {}) {
  stubReducedMotion(options.reducedMotion ?? false);
  map = new FakeMap();
  camera = createCameraController({ map });
  return camera;
}

/** The options of one recorded call, or a failure naming the call that is missing. */
function optionsOf(method: Call['method'], index = 0): Record<string, unknown> {
  const options = map.of(method)[index];
  if (options === undefined) throw new Error(`no ${method} call at index ${index}`);
  return options;
}

function key(init: KeyboardEventInit): void {
  map.container.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, ...init }));
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  camera?.destroy();
  map?.container.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('the gesture surface', () => {
  it('enables every direct-manipulation gesture in §9.3', () => {
    build();
    expect(map.dragPan.isEnabled()).toBe(true);
    expect(map.dragRotate.isEnabled()).toBe(true);
    expect(map.scrollZoom.isEnabled()).toBe(true);
    expect(map.touchPitch.isEnabled()).toBe(true);
    expect(map.touchZoomRotate.isEnabled()).toBe(true);
    expect(map.touchZoomRotate.rotationEnabled).toBe(true);
  });

  it('takes over the two behaviours it reimplements, so nothing happens twice', () => {
    // Not a tidiness assertion. With MapLibre's keyboard handler left on, every
    // arrow key pans once through it and once through this controller — a map
    // that moves at double the documented step, with no error anywhere.
    build();
    expect(map.keyboard.isEnabled()).toBe(false);
    expect(map.doubleClickZoom.isEnabled()).toBe(false);
  });
});

describe('reduced motion, at the controller', () => {
  it('turns a fly-to into an immediate cut', () => {
    build({ reducedMotion: true });
    camera.flyTo({ center: [-74, 40.7], zoom: 15 });
    expect(map.of('flyTo')).toHaveLength(0);
    expect(map.of('jumpTo')).toEqual([{ center: [-74, 40.7], zoom: 15 }]);
  });

  it('animates when the preference is not set', () => {
    build({ reducedMotion: false });
    camera.flyTo({ center: [-74, 40.7], zoom: 15 });
    expect(map.of('jumpTo')).toHaveLength(0);
    expect(map.of('flyTo')[0]).toMatchObject({ zoom: 15, essential: true });
  });

  it('refuses to orbit at all, and frames the point instead', () => {
    // There is no reduced version of "turn in a circle forever". Slowing it down
    // is still the motion the preference is about.
    build({ reducedMotion: true });
    map.projectTo = { x: 990, y: 780 }; // off in the corner, so focusOn moves
    camera.orbitAround([-73.98, 40.75]);
    expect(camera.orbiting).toBe(false);
    expect(map.of('easeTo')).toHaveLength(0);
    expect(map.of('jumpTo')).toHaveLength(1);
  });

  it('stops an orbit already running when the preference is turned on', () => {
    const motion = stubReducedMotion(false);
    map = new FakeMap();
    camera = createCameraController({ map });
    camera.orbitAround([-73.98, 40.75]);
    expect(camera.orbiting).toBe(true);

    motion.set(true);
    expect(camera.orbiting).toBe(false);
    expect(camera.reducedMotion).toBe(true);

    const before = map.of('easeTo').length;
    vi.advanceTimersByTime(30_000);
    expect(map.of('easeTo')).toHaveLength(before);
  });

  it('cuts keyboard steps to no duration', () => {
    build({ reducedMotion: true });
    key({ key: 'ArrowRight' });
    expect(map.of('panBy')[0]).toMatchObject({ duration: 0 });
    key({ key: '+' });
    expect(map.of('easeTo')).toHaveLength(0);
    expect(map.of('jumpTo').at(-1)).toMatchObject({ zoom: INITIAL_POSE.zoom + 0.5 });
  });
});

describe('interruption', () => {
  it.each(['pointerdown', 'wheel', 'touchstart'] as const)(
    'a %s during an animation stops the camera where it is',
    (type) => {
      build();
      const told = vi.fn();
      camera.subscribe(told);
      camera.flyTo({ center: [-74, 40.7], zoom: 15 });
      expect(camera.animating).toBe(true);

      map.container.dispatchEvent(new Event(type, { bubbles: true }));

      expect(map.last?.method).toBe('stop');
      expect(camera.animating).toBe(false);
      expect(told).toHaveBeenCalledOnce();
    },
  );

  it('a keypress during an animation stops it before it does anything else', () => {
    // The ordering matters: the interruption is a capture-phase listener and the
    // keyboard is not, so the fly-to is already cancelled by the time the arrow
    // key's own pan is issued. The other order leaves the pan racing the fly.
    build();
    camera.flyTo({ center: [-74, 40.7], zoom: 15 });
    key({ key: 'ArrowRight' });
    const kinds = map.calls.map((call) => call.method);
    expect(kinds).toEqual(['flyTo', 'stop', 'panBy']);
  });

  it('does not report an interruption when nothing was moving', () => {
    build();
    const told = vi.fn();
    camera.subscribe(told);
    map.container.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    expect(told).not.toHaveBeenCalled();
    expect(map.of('stop')).toHaveLength(0);
  });

  it('stops telling a listener that has unsubscribed', () => {
    build();
    const told = vi.fn();
    camera.subscribe(told)();
    camera.orbitAround([-73.98, 40.75]);
    expect(told).not.toHaveBeenCalled();
  });

  it('ends an orbit for good rather than resuming it', () => {
    // The failure this guards is a queue: the leg in flight is cancelled, its
    // timer fires anyway, and the camera silently starts turning again a few
    // seconds after the user grabbed it.
    build();
    camera.orbitAround([-73.98, 40.75]);
    map.container.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    expect(camera.orbiting).toBe(false);

    const before = map.of('easeTo').length;
    vi.advanceTimersByTime(60_000);
    expect(map.of('easeTo')).toHaveLength(before);
  });
});

describe('the orbit', () => {
  it('turns around the point, in legs, at the rate asked for', () => {
    build();
    camera.orbitAround([-73.98, 40.75], { degreesPerSecond: 15 });

    const first = optionsOf('easeTo');
    expect(first).toMatchObject({
      around: [-73.98, 40.75],
      bearing: INITIAL_POSE.bearing + 90,
      duration: 6000,
    });
    // Linear: an eased leg would slow to a stop four times a revolution.
    expect((first.easing as (t: number) => number)(0.25)).toBe(0.25);

    vi.advanceTimersByTime(6000);
    // 202 + 180 = 382, which is 22. Normalised, because a bearing is an angle.
    expect(map.of('easeTo')[1]).toMatchObject({ bearing: (INITIAL_POSE.bearing + 180) % 360 });

    vi.advanceTimersByTime(12_000);
    expect(map.of('easeTo')).toHaveLength(4);
  });

  it('never sends a bearing outside a circle', () => {
    build();
    map.bearing = 350;
    camera.orbitAround([-73.98, 40.75]);
    for (const call of map.of('easeTo')) {
      expect(call.bearing).toBeGreaterThanOrEqual(0);
      expect(call.bearing).toBeLessThan(360);
    }
  });
});

describe('focus', () => {
  it('does not move when the point is already on screen and close enough', () => {
    // §5.6. A camera that flies on every selection makes a result list unusable.
    build();
    map.zoom = 16;
    map.projectTo = { x: 500, y: 400 };
    expect(camera.focusOn([-73.98, 40.75])).toBe(false);
    expect(map.calls).toHaveLength(0);
  });

  it('moves when the point is behind the edge of the window', () => {
    build();
    map.zoom = 16;
    map.projectTo = { x: 40, y: 400 }; // inside the viewport, inside the margin
    expect(camera.focusOn([-73.98, 40.75])).toBe(true);
    expect(map.of('flyTo')[0]).toMatchObject({ center: [-73.98, 40.75] });
  });

  it('moves when the point is on screen but the whole city is', () => {
    build();
    map.zoom = 11;
    map.projectTo = { x: 500, y: 400 };
    expect(camera.focusOn([-73.98, 40.75])).toBe(true);
    expect(map.of('flyTo')[0]).toMatchObject({ zoom: 15.5 });
  });

  it('never zooms out to focus', () => {
    build();
    map.zoom = 17;
    map.projectTo = { x: 10, y: 10 };
    camera.focusOn([-73.98, 40.75], { zoom: 15.5 });
    expect(map.of('flyTo')[0]).toMatchObject({ zoom: 17 });
  });
});

describe('double-click', () => {
  it('flies to the point under the pointer and keeps the orientation', () => {
    build();
    map.unprojectTo = { lng: -73.95, lat: 40.72 };
    map.container.dispatchEvent(
      new MouseEvent('dblclick', { bubbles: true, clientX: 300, clientY: 200 }),
    );
    const call = optionsOf('flyTo');
    expect(call).toMatchObject({ center: [-73.95, 40.72], zoom: INITIAL_POSE.zoom + 1.4 });
    // Preserving spatial orientation (§9.3) means not sending a pitch or a
    // bearing at all — MapLibre keeps what it has.
    expect(call.pitch).toBeUndefined();
    expect(call.bearing).toBeUndefined();
  });

  it('zooms out with shift held', () => {
    build();
    map.container.dispatchEvent(
      new MouseEvent('dblclick', { bubbles: true, clientX: 300, clientY: 200, shiftKey: true }),
    );
    expect(map.of('flyTo')[0]).toMatchObject({ zoom: INITIAL_POSE.zoom - 1.4 });
  });
});

describe('the keyboard', () => {
  it('pans in screen space, so up is up whatever the bearing is', () => {
    // The city opens at bearing 202°. A keyboard that pans north would send the
    // camera down and to the right when the user presses up.
    build();
    key({ key: 'ArrowUp' });
    expect(map.of('panBy')[0]).toMatchObject({ offset: [0, -144], duration: 220 });
    key({ key: 'ArrowRight' });
    expect(map.of('panBy')[1]).toMatchObject({ offset: [144, 0] });
  });

  it('rotates and tilts with shift', () => {
    build();
    key({ key: 'ArrowLeft', shiftKey: true });
    expect(map.of('easeTo')[0]).toMatchObject({ bearing: INITIAL_POSE.bearing - 15 });
    key({ key: 'ArrowUp', shiftKey: true });
    expect(map.of('easeTo')[1]).toMatchObject({ pitch: CAMERA_LIMITS.maxPitch });
  });

  it('zooms, and stays inside the limits', () => {
    build();
    map.zoom = CAMERA_LIMITS.maxZoom;
    key({ key: '+' });
    expect(map.of('easeTo')[0]).toMatchObject({ zoom: CAMERA_LIMITS.maxZoom });
    key({ key: '-' });
    expect(map.of('easeTo')[1]).toMatchObject({ zoom: CAMERA_LIMITS.maxZoom - 0.5 });
  });

  it('goes home on 0', () => {
    build();
    map.zoom = 17;
    key({ key: '0' });
    expect(map.of('flyTo')[0]).toMatchObject({ ...INITIAL_POSE, duration: 1400 });
  });

  it('ends an orbit on Escape', () => {
    build();
    camera.orbitAround([-73.98, 40.75]);
    key({ key: 'Escape' });
    expect(camera.orbiting).toBe(false);
  });

  it('reaches the map on Escape even when the controller started nothing', () => {
    // The controller does not know about MapLibre's own inertia: a flick pan is
    // still gliding for half a second after the finger leaves, and Escape has to
    // stop that too. So Escape calls `stop()` unconditionally rather than only
    // when this controller believes something is animating.
    build();
    key({ key: 'Escape' });
    expect(map.of('stop')).toHaveLength(1);
  });

  it('leaves a text field alone', () => {
    build();
    const input = document.createElement('input');
    map.container.append(input);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(map.of('panBy')).toHaveLength(0);
  });

  it('leaves browser and OS shortcuts alone', () => {
    build();
    key({ key: 'ArrowRight', metaKey: true });
    key({ key: '+', ctrlKey: true });
    expect(map.calls).toHaveLength(0);
  });

  it('claims the keys it handles and no others', () => {
    build();
    const handled = new KeyboardEvent('keydown', {
      key: 'ArrowRight',
      bubbles: true,
      cancelable: true,
    });
    map.container.dispatchEvent(handled);
    expect(handled.defaultPrevented).toBe(true);

    const ignored = new KeyboardEvent('keydown', { key: 'k', bubbles: true, cancelable: true });
    map.container.dispatchEvent(ignored);
    expect(ignored.defaultPrevented).toBe(false);
  });

  it('documents exactly the keys it implements', () => {
    // The on-screen help is generated from this table, so the failure it
    // prevents is a legend that promises a key the controller does not have.
    expect(KEYBOARD_HELP.map((row) => row.does)).toEqual([
      'Pan',
      'Rotate',
      'Tilt',
      'Zoom',
      'Reset the view',
      'Stop the camera',
    ]);
  });
});

describe('trackpad rotation, where supported', () => {
  it('rotates on Safari gesture events without also zooming', () => {
    // Safari emits `gesturechange` *and* a ctrl+wheel for the same pinch, and
    // MapLibre's scrollZoom already answers the wheel. Reading `scale` here too
    // would zoom twice per pinch.
    build();
    const event = new Event('gesturechange', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'rotation', { value: 20 });
    Object.defineProperty(event, 'scale', { value: 1.5 });
    map.container.dispatchEvent(event);

    const call = optionsOf('jumpTo');
    expect(call).toMatchObject({ bearing: INITIAL_POSE.bearing + 10 });
    expect(call.zoom).toBeUndefined();
  });
});

describe('limits', () => {
  it('clamps a programmatic move to the same edges a gesture has', () => {
    // Two sets of limits depending on how the camera got somewhere is none.
    expect(clampUpdate({ zoom: 40, pitch: 90, bearing: 375 })).toEqual({
      zoom: CAMERA_LIMITS.maxZoom,
      pitch: CAMERA_LIMITS.maxPitch,
      bearing: 15,
    });
    expect(clampUpdate({ zoom: 1, pitch: -20 })).toEqual({
      zoom: CAMERA_LIMITS.minZoom,
      pitch: CAMERA_LIMITS.minPitch,
    });
  });

  it('leaves out what was not asked for', () => {
    expect(clampUpdate({ center: [-74, 40.7] })).toEqual({ center: [-74, 40.7] });
  });

  it('opens inside its own limits', () => {
    expect(INITIAL_POSE.zoom).toBeGreaterThanOrEqual(CAMERA_LIMITS.minZoom);
    expect(INITIAL_POSE.zoom).toBeLessThanOrEqual(CAMERA_LIMITS.maxZoom);
    expect(INITIAL_POSE.pitch).toBeLessThanOrEqual(CAMERA_LIMITS.maxPitch);
  });
});

describe('teardown', () => {
  it('stops listening, so a remounted map is not driven by a dead controller', () => {
    build();
    camera.orbitAround([-73.98, 40.75]);
    camera.destroy();
    const before = map.calls.length;

    vi.advanceTimersByTime(60_000);
    key({ key: 'ArrowRight' });
    map.container.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    map.container.dispatchEvent(new Event('pointerdown', { bubbles: true }));

    expect(map.calls).toHaveLength(before);
  });
});
