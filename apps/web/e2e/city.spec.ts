import type { Page } from '@playwright/test';
import { expect, test } from '@playwright/test';

/**
 * M4b's acceptance criteria, in a real browser.
 *
 * `city.md` §7 asks for three things: NYC renders dark, extruded and offline;
 * every gesture in §9.3 works on trackpad and touch; every animation is
 * interruptible. None of the three can be answered by a unit test, because all
 * three are claims about a renderer and a pointing device, and `camera.test.ts`
 * drives a fake map in jsdom with no GPU. It proves the controller calls
 * `panBy`; only this file can prove that pressing an arrow key moves New York.
 *
 * The camera is read through `window.__nightshiftCity` — see `lib/map/debug` for
 * why that global exists and why it is not in production builds.
 *
 * **This suite runs in the no-API config on purpose.** The city page talks to
 * `/api/tiles/*`, which is a Next route reading a file from `~/.cache`; it needs
 * no FastAPI, no Postgres and no network. Running it here rather than in the
 * seeded config is itself the assertion.
 */

import { CITY_DEBUG_KEY } from '../src/lib/map/debug';
import { CAMERA_LIMITS, INITIAL_POSE } from '../src/lib/map/camera';

/**
 * Two minutes a test, against thirty seconds everywhere else in this repo.
 *
 * Not flake insurance. The suite loads two pmtiles archives over ranged reads
 * and rasterises a million footprints on a software renderer — headless Chromium
 * has no GPU, so every frame here is ANGLE on the CPU. Measured cold: eight to
 * twenty seconds before the opening view is complete. A thirty-second budget
 * would make this suite a machine-speed detector.
 */
test.describe.configure({ timeout: 120_000 });

/** The pose, as the browser has it right now. */
async function pose(page: Page) {
  return page.evaluate((key) => {
    const city = window[key as typeof CITY_DEBUG_KEY];
    if (!city) throw new Error('No city debug handle. Is this a production build?');
    return city.camera.getPose();
  }, CITY_DEBUG_KEY);
}

/**
 * Load the city and wait for it to be drawable.
 *
 * "Ready" is the same signal the component uses — a painted frame — and it
 * surfaces in the DOM as the camera panel, which renders only once there is a
 * camera to drive. Waiting on the panel therefore waits on the map, without
 * this file knowing anything about MapLibre's event names.
 */
async function openCity(page: Page) {
  await page.goto('/explore/city');
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeVisible({ timeout: 60_000 });
  // The failure card and the map are mutually exclusive; assert the card is not
  // there rather than trusting that the panel implies it.
  await expect(page.getByText('The map cannot be drawn')).toHaveCount(0);
  const canvas = page.locator('canvas.maplibregl-canvas');
  await expect(canvas).toBeVisible();
  return canvas;
}

/** How far apart two headings are, the short way round. */
function headingGap(a: number, b: number): number {
  return Math.abs(((a - b + 540) % 360) - 180);
}

type Pose = Awaited<ReturnType<typeof pose>>;

/**
 * Wait for the camera to *reach* a state, rather than for a number of
 * milliseconds to pass, and return the pose once it has.
 *
 * **A fixed wait after a gesture is a machine-speed detector, and it caught this
 * suite out.** Two tests — the wheel zoom and the trackpad pinch — failed inside
 * `make acceptance` with `zoom` at exactly its opening value, and passed on
 * their own seconds later. Nothing was broken. MapLibre's scroll zoom is
 * animated and driven by `requestAnimationFrame`, this browser has no GPU, and
 * two workers rasterising a million footprints between them can starve rAF for
 * longer than the 800 ms the assertion allowed. The event had arrived; the frame
 * that would have acted on it had not.
 *
 * The instrument, not the product, was wrong: "the wheel zooms" is a claim about
 * whether the camera ends up closer, not about how many milliseconds it takes.
 * Polling says exactly that. It still goes red when the handler is switched off
 * — it just spends twenty seconds finding out instead of eight hundred
 * milliseconds, which is the right trade when the alternative is a suite that
 * teaches people to re-run it rather than read it.
 */
async function settles(page: Page, reached: (p: Pose) => boolean, what: string): Promise<Pose> {
  await expect
    .poll(async () => reached(await pose(page)), { message: what, timeout: 20_000 })
    .toBe(true);
  return pose(page);
}

/** Where to put the pointer so a drag lands on the map and not on a panel. */
const MAP_POINT = { x: 640, y: 480 };

test.describe('the city renders', () => {
  test('draws New York from local archives, with no network and no API', async ({ page }) => {
    // Every request the page makes, recorded. Anything that is not this origin
    // is a network call, and a network call is a failed acceptance criterion —
    // `make demo` is offline by definition.
    const foreign: string[] = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      // `blob:` is MapLibre's worker, which it builds from a string at runtime;
      // a blob URL has no host because it never leaves the tab. Excluded by
      // scheme rather than by pattern, so a real host cannot hide behind one.
      if (url.protocol === 'blob:' || url.protocol === 'data:') return;
      if (url.hostname !== 'localhost' && url.hostname !== '127.0.0.1') foreign.push(request.url());
    });

    await openCity(page);
    // Let the tile requests for the opening view finish before judging.
    await page.waitForTimeout(3_000);

    expect(foreign, 'the city must draw with no off-machine request').toEqual([]);
    // And the archives really were served: two ranged reads of the tile route,
    // at minimum, or the map drew something that did not come from disk.
    const tiles = await page.evaluate(() =>
      performance
        .getEntriesByType('resource')
        .map((entry) => entry.name)
        .filter((name) => name.includes('/api/tiles/')),
    );
    expect(tiles.some((name) => name.includes('/api/tiles/basemap'))).toBe(true);
    expect(tiles.some((name) => name.includes('/api/tiles/buildings'))).toBe(true);
  });

  test('the skyline is an extrusion with real features on screen', async ({ page }) => {
    await openCity(page);

    const layer = await page.evaluate((key) => {
      const city = window[key as typeof CITY_DEBUG_KEY]!;
      return city.map.getLayer('buildings')?.type ?? null;
    }, CITY_DEBUG_KEY);
    expect(layer, 'the buildings layer must be a fill-extrusion, not a flat fill').toBe(
      'fill-extrusion',
    );

    // Features *rendered*, not features declared. This is the assertion that
    // fails if the archive is missing, the source-layer name is wrong, or the
    // opening pose is looking at water — none of which the style tests can see.
    //
    // **The box is not a convenience and removing it makes this test always
    // fail.** MapLibre's whole-viewport query returns zero at this pitch, at
    // every zoom, while the same frame has thirty thousand building features
    // loaded and visibly drawn. Measured on 2026-08-12:
    //
    //   pitch 76, z13.6 → viewport 0, lower box 1,599, source 30,573
    //   pitch 76, z15   → viewport 0, lower box   351, source 18,533
    //   pitch  0, z13.6 → viewport 9,225
    //
    // The city opens at 76°, so most of the viewport rect is sky: the query
    // unprojects its corners onto the ground plane and the ones above the
    // horizon have no ground to land on. A box below the horizon has an answer,
    // and it is the honest place to ask the question.
    //
    // This outlives the test. M4c needs picking and list↔map sync, and the
    // obvious implementation of "which roles are on screen" is a viewport
    // query — which will return nothing here, silently, in the default view.
    await expect
      .poll(
        async () =>
          page.evaluate((key) => {
            const city = window[key as typeof CITY_DEBUG_KEY]!;
            const box = city.map.getContainer().getBoundingClientRect();
            return city.map.queryRenderedFeatures(
              [
                [box.width * 0.15, box.height * 0.65],
                [box.width * 0.85, box.height * 0.98],
              ],
              { layers: ['buildings'] },
            ).length;
          }, CITY_DEBUG_KEY),
        { timeout: 60_000, message: 'no building was ever rendered at the opening pose' },
      )
      .toBeGreaterThan(100);
  });

  test('the canvas paints, and repaints when the camera moves', async ({ page }) => {
    const canvas = await openCity(page);
    await page.waitForTimeout(2_000);
    const before = await canvas.screenshot();

    await page.evaluate((key) => {
      window[key as typeof CITY_DEBUG_KEY]!.camera.flyTo({ zoom: 16, pitch: 0 }, { duration: 0 });
    }, CITY_DEBUG_KEY);
    await page.waitForTimeout(3_000);
    const after = await canvas.screenshot();

    // A black rectangle is identical to a black rectangle. Two different frames
    // is weak evidence of beauty and strong evidence of drawing.
    expect(Buffer.compare(before, after)).not.toBe(0);
  });

  test('an empty sky with no API says it is a missing connection, not an empty market', async ({
    page,
  }) => {
    await openCity(page);

    // This suite runs with no API behind it, so the signal layer receives
    // nothing. I3's habit of mind applied to a renderer: an unreachable source
    // is not evidence that nobody is hiring, and a sky with no beacons and no
    // explanation says exactly that.
    await expect(page.getByText('No roles on the city')).toBeVisible();
    await expect(
      page.getByText('An empty sky here is a missing connection, not an empty market.'),
    ).toBeVisible();

    // And the map is still a map. The city does not need the API.
    expect(
      await page.evaluate(
        (key) => window[key as typeof CITY_DEBUG_KEY]!.signals.drawn,
        CITY_DEBUG_KEY,
      ),
    ).toBe(0);
  });
});

test.describe('§9.3 — the gesture surface, with a mouse and a trackpad', () => {
  test('mouse drag pans the city', async ({ page }) => {
    await openCity(page);
    const before = await pose(page);

    await page.mouse.move(MAP_POINT.x, MAP_POINT.y);
    await page.mouse.down();
    await page.mouse.move(MAP_POINT.x - 220, MAP_POINT.y - 120, { steps: 12 });
    await page.mouse.up();

    const after = await settles(
      page,
      (p) => p.center[0] !== before.center[0] || p.center[1] !== before.center[1],
      'the drag moves the centre',
    );
    expect(after.center).not.toEqual(before.center);
    // A pan is a pan: it must not have rotated or zoomed on the way.
    expect(after.bearing).toBeCloseTo(before.bearing, 3);
    expect(after.zoom).toBeCloseTo(before.zoom, 3);
  });

  test('right-drag orbits — bearing and pitch, not position', async ({ page }) => {
    await openCity(page);
    const before = await pose(page);

    await page.mouse.move(MAP_POINT.x, MAP_POINT.y);
    await page.mouse.down({ button: 'right' });
    await page.mouse.move(MAP_POINT.x - 200, MAP_POINT.y + 60, { steps: 12 });
    await page.mouse.up({ button: 'right' });

    const after = await settles(
      page,
      (p) => headingGap(p.bearing, before.bearing) > 1,
      'the right-drag turns the camera',
    );
    expect(headingGap(after.bearing, before.bearing)).toBeGreaterThan(1);
  });

  test('the wheel zooms', async ({ page }) => {
    await openCity(page);
    const before = await pose(page);

    await page.mouse.move(MAP_POINT.x, MAP_POINT.y);
    await page.mouse.wheel(0, -600);

    const after = await settles(page, (p) => p.zoom > before.zoom, 'the wheel zooms in');
    expect(after.zoom).toBeGreaterThan(before.zoom);
  });

  test('a trackpad pinch zooms — ctrl+wheel, which is how the browser reports it', async ({
    page,
  }) => {
    await openCity(page);
    const before = await pose(page);

    // Playwright's `mouse.wheel` cannot set a modifier, and the modifier is the
    // entire difference between a scroll and a pinch: every browser delivers a
    // trackpad pinch as a wheel event with ctrlKey set, whether or not ctrl is
    // held. So this goes through CDP, which is the same input path a real
    // gesture takes.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseWheel',
      x: MAP_POINT.x,
      y: MAP_POINT.y,
      deltaX: 0,
      deltaY: -120,
      modifiers: 2, // ctrl
    });

    const after = await settles(page, (p) => p.zoom > before.zoom, 'the pinch zooms in');
    expect(after.zoom).toBeGreaterThan(before.zoom);
    await cdp.detach();
  });

  test('a double-click focuses the point under the pointer and keeps the frame', async ({
    page,
  }) => {
    await openCity(page);
    const before = await pose(page);
    const target = { x: MAP_POINT.x + 240, y: MAP_POINT.y - 150 };
    const where = await page.evaluate(
      ({ key, point }) => {
        const map = window[key as typeof CITY_DEBUG_KEY]!.map;
        const rect = map.getContainer().getBoundingClientRect();
        const at = map.unproject([point.x - rect.left, point.y - rect.top]);
        return [at.lng, at.lat] as [number, number];
      },
      { key: CITY_DEBUG_KEY, point: target },
    );

    // Closer to the clicked coordinate than it started, which is the whole
    // claim — and the pitch and bearing hold at every sample of a fly-to that
    // changes neither, so this can be read the moment it is true.
    const gap = (a: readonly [number, number]) => Math.hypot(a[0] - where[0], a[1] - where[1]);

    await page.mouse.dblclick(target.x, target.y);

    const after = await settles(
      page,
      (p) => gap(p.center) < gap(before.center),
      'the double-click moves the camera towards the point under it',
    );
    // §9.3: preserve spatial orientation. A double-click here is a focus, not a
    // zoom-around-centre, so the frame's angles survive it.
    expect(after.pitch).toBeCloseTo(before.pitch, 1);
    expect(after.bearing).toBeCloseTo(before.bearing, 1);
    expect(gap(after.center)).toBeLessThan(gap(before.center));
  });

  test('the keyboard pans in screen space, rotates, tilts, zooms and resets', async ({ page }) => {
    await openCity(page);
    await page.locator('.maplibregl-map').click({ position: { x: 400, y: 500 } });

    const start = await pose(page);

    // Up is up the screen, whatever the bearing is. The city opens at 202°, so a
    // keyboard that panned north would move the camera down and to the right —
    // the bug this controller took MapLibre's keyboard handler over to avoid.
    const before = await page.evaluate((key) => {
      const map = window[key as typeof CITY_DEBUG_KEY]!.map;
      const c = map.getCenter();
      return map.project([c.lng, c.lat]);
    }, CITY_DEBUG_KEY);
    await page.keyboard.press('ArrowUp');
    await page.waitForTimeout(600);
    const moved = await page.evaluate(
      ({ key, from }) => {
        const map = window[key as typeof CITY_DEBUG_KEY]!.map;
        return map.project(from as [number, number]);
      },
      { key: CITY_DEBUG_KEY, from: start.center },
    );
    // The old centre is now *below* where it was: the view moved up the screen.
    expect(moved.y).toBeGreaterThan(before.y + 20);
    expect(Math.abs(moved.x - before.x)).toBeLessThan(Math.abs(moved.y - before.y));

    const panned = await pose(page);
    await page.keyboard.press('Shift+ArrowLeft');
    await page.waitForTimeout(600);
    expect((await pose(page)).bearing).not.toBeCloseTo(panned.bearing, 2);

    const rotated = await pose(page);
    await page.keyboard.press('Shift+ArrowUp');
    await page.waitForTimeout(600);
    expect((await pose(page)).pitch).not.toBeCloseTo(rotated.pitch, 2);

    const tilted = await pose(page);
    await page.keyboard.press('+');
    await page.waitForTimeout(600);
    expect((await pose(page)).zoom).toBeGreaterThan(tilted.zoom);

    const zoomed = await pose(page);
    await page.keyboard.press('-');
    await page.waitForTimeout(600);
    expect((await pose(page)).zoom).toBeLessThan(zoomed.zoom);

    // Home. Every number back to the opening view, which is the only place the
    // reset key is allowed to land.
    await page.keyboard.press('0');
    await page.waitForTimeout(2_500);
    const home = await pose(page);
    expect(home.zoom).toBeCloseTo(INITIAL_POSE.zoom, 1);
    expect(home.pitch).toBeCloseTo(INITIAL_POSE.pitch, 0);
    // MapLibre reports bearing in (-180, 180], so the opening 202° comes back as
    // -158°. Compared as an angle, because "the camera is pointing the wrong way
    // by exactly one full turn" is not a real failure and asserting it would be
    // a test that fails for being right.
    expect(headingGap(home.bearing, INITIAL_POSE.bearing)).toBeLessThan(0.5);
    expect(home.center[0]).toBeCloseTo(INITIAL_POSE.center[0], 2);
    expect(home.center[1]).toBeCloseTo(INITIAL_POSE.center[1], 2);
  });

  test('a keyboard alone reaches the city and drives it', async ({ page }) => {
    await openCity(page);

    // No click anywhere. This is the whole path a keyboard-only user has: tab
    // until the map has focus, then steer. Found during the M4b review that the
    // node focus lands on is MapLibre's canvas, not the wrapper — which is why
    // the label is set on the canvas, and why this asserts the name as well as
    // the movement. A map that steers but announces itself as "Map" is only
    // half reachable.
    let focused = false;
    for (let i = 0; i < 14 && !focused; i++) {
      await page.keyboard.press('Tab');
      focused = await page.evaluate(() => document.activeElement?.tagName === 'CANVAS');
    }
    expect(focused, 'the map never took focus from the keyboard').toBe(true);

    const named = await page.evaluate(() => ({
      role: document.activeElement?.getAttribute('role'),
      label: document.activeElement?.getAttribute('aria-label'),
      outline: getComputedStyle(document.activeElement!).outlineStyle,
    }));
    expect(named.role).toBe('application');
    expect(named.label).toContain('also in the list view');
    // §12.4: focus is never invisible. The global `:focus-visible` rule has to
    // reach a canvas too, and a canvas is unusual enough to be worth checking.
    expect(named.outline).not.toBe('none');

    const before = await pose(page);
    await page.keyboard.press('ArrowUp');
    await page.waitForTimeout(700);
    expect((await pose(page)).center).not.toEqual(before.center);
  });

  test('the camera stays inside its limits', async ({ page }) => {
    await openCity(page);

    // Zoom out past the floor and tilt past the ceiling, then check the camera
    // refused. Bounds, pitch limits: §9.3's last two lines.
    await page.evaluate(
      ({ key, limits }) => {
        const camera = window[key as typeof CITY_DEBUG_KEY]!.camera;
        camera.flyTo({ zoom: limits.minZoom - 4, pitch: limits.maxPitch + 20 }, { duration: 0 });
      },
      { key: CITY_DEBUG_KEY, limits: CAMERA_LIMITS },
    );
    await page.waitForTimeout(1_000);

    const after = await pose(page);
    expect(after.zoom).toBeGreaterThanOrEqual(CAMERA_LIMITS.minZoom - 0.001);
    expect(after.pitch).toBeLessThanOrEqual(CAMERA_LIMITS.maxPitch + 0.001);
  });
});

/**
 * Touch, dispatched through CDP rather than through Playwright's touchscreen —
 * which taps with one finger, and every gesture that matters here needs two.
 *
 * `Input.dispatchTouchEvent` is the same entry point the browser uses for a real
 * finger; the events MapLibre receives are trusted and indistinguishable from
 * hardware. What this still does not prove is a phone: the browser is a desktop
 * Chromium with touch emulation on, so it cannot catch a gesture that fails
 * because of a mobile browser's own pan/zoom handling. That limit is recorded in
 * PROGRESS rather than papered over.
 */
test.describe('§9.3 — the gesture surface, with two fingers', () => {
  test.use({ hasTouch: true });

  type Point = { x: number; y: number };

  async function touch(page: Page, frames: readonly (readonly Point[])[]) {
    const cdp = await page.context().newCDPSession(page);
    const send = (type: 'touchStart' | 'touchMove' | 'touchEnd', points: readonly Point[]) =>
      cdp.send('Input.dispatchTouchEvent', {
        type,
        touchPoints: points.map((point) => ({ x: point.x, y: point.y })),
      });

    await send('touchStart', frames[0]);
    for (const frame of frames.slice(1)) {
      await send('touchMove', frame);
      await page.waitForTimeout(40);
    }
    await send('touchEnd', []);
    await page.waitForTimeout(600);
    await cdp.detach();
  }

  test('one finger pans', async ({ page }) => {
    await openCity(page);
    const before = await pose(page);

    await touch(
      page,
      Array.from({ length: 8 }, (_, i) => [{ x: MAP_POINT.x - i * 20, y: MAP_POINT.y - i * 12 }]),
    );

    const after = await settles(
      page,
      (p) => p.center[0] !== before.center[0] || p.center[1] !== before.center[1],
      'one finger moves the centre',
    );
    expect(after.center).not.toEqual(before.center);
  });

  test('two fingers pinch to zoom', async ({ page }) => {
    await openCity(page);
    const before = await pose(page);

    // Fingers apart: a spread, which zooms in.
    await touch(
      page,
      Array.from({ length: 10 }, (_, i) => [
        { x: MAP_POINT.x - 40 - i * 18, y: MAP_POINT.y },
        { x: MAP_POINT.x + 40 + i * 18, y: MAP_POINT.y },
      ]),
    );

    const after = await settles(page, (p) => p.zoom > before.zoom, 'two fingers spreading zoom in');
    expect(after.zoom).toBeGreaterThan(before.zoom);
  });

  test('two fingers rotate', async ({ page }) => {
    await openCity(page);
    const before = await pose(page);

    // The same pair of fingers swept around their midpoint, distance held so the
    // gesture is a rotation and not a pinch.
    const radius = 120;
    await touch(
      page,
      Array.from({ length: 14 }, (_, i) => {
        const angle = (i * 7 * Math.PI) / 180;
        return [
          {
            x: MAP_POINT.x + radius * Math.cos(angle),
            y: MAP_POINT.y + radius * Math.sin(angle),
          },
          {
            x: MAP_POINT.x - radius * Math.cos(angle),
            y: MAP_POINT.y - radius * Math.sin(angle),
          },
        ];
      }),
    );

    const after = await settles(
      page,
      (p) => headingGap(p.bearing, before.bearing) > 2,
      'two fingers sweeping turn the camera',
    );
    expect(headingGap(after.bearing, before.bearing)).toBeGreaterThan(2);
  });
});

test.describe('§5.4 — nothing the camera does cannot be stopped', () => {
  test('a fly-to stops where it is when the user takes hold', async ({ page }) => {
    await openCity(page);
    const start = await pose(page);

    await page.evaluate((key) => {
      window[key as typeof CITY_DEBUG_KEY]!.camera.flyTo(
        { center: [-73.79, 40.66], zoom: 15 },
        { duration: 8_000 },
      );
    }, CITY_DEBUG_KEY);
    await page.waitForTimeout(1_200);
    const midway = await pose(page);
    expect(midway.center, 'the fly-to did not start').not.toEqual(start.center);

    await page.mouse.move(MAP_POINT.x, MAP_POINT.y);
    await page.mouse.down();
    await page.mouse.up();
    await page.waitForTimeout(400);

    const stopped = await pose(page);
    // It stopped, and it stopped *here* — no snapping back to the start and no
    // continuing to the target.
    const state = await page.evaluate((key) => {
      const city = window[key as typeof CITY_DEBUG_KEY]!;
      return { moving: city.map.isMoving(), animating: city.camera.animating };
    }, CITY_DEBUG_KEY);
    expect(state.moving).toBe(false);
    // **`animating` is the half of this that is ours, and the reason it is
    // asserted separately.** Red-green, 2026-08-12: with `#handleUserInput`
    // stubbed out to do nothing, `moving` still came back false and this test
    // still passed — MapLibre's own drag handler stops an in-flight camera the
    // moment you grab the map, so the criterion was being met by the library
    // while the test claimed to be watching the controller. `animating` is the
    // controller's own record of a move it started, nothing else clears it, and
    // it stays true for the full eight seconds without the handler. One line,
    // and the test discriminates again.
    expect(state.animating).toBe(false);
    await page.waitForTimeout(1_000);
    const later = await pose(page);
    expect(later.center[0]).toBeCloseTo(stopped.center[0], 4);
    expect(later.center[1]).toBeCloseTo(stopped.center[1], 4);
    expect(Math.abs(later.center[0] - -73.79)).toBeGreaterThan(0.02);
  });

  test('a keypress during a fly-to is enough to stop it', async ({ page }) => {
    await openCity(page);
    await page.locator('.maplibregl-map').click({ position: { x: 400, y: 500 } });

    await page.evaluate((key) => {
      window[key as typeof CITY_DEBUG_KEY]!.camera.flyTo(
        { center: [-73.79, 40.66], zoom: 15 },
        { duration: 8_000 },
      );
    }, CITY_DEBUG_KEY);
    await page.waitForTimeout(800);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    const stopped = await pose(page);
    await page.waitForTimeout(1_000);
    expect((await pose(page)).center[0]).toBeCloseTo(stopped.center[0], 4);
  });

  test('the orbit turns, and any input ends it', async ({ page }) => {
    await openCity(page);

    await page.getByRole('button', { name: 'Orbit', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Stop orbit' })).toBeVisible();
    const started = await pose(page);
    await page.waitForTimeout(2_000);
    expect(headingGap((await pose(page)).bearing, started.bearing)).toBeGreaterThan(1);

    await page.mouse.move(MAP_POINT.x, MAP_POINT.y);
    await page.mouse.down();
    await page.mouse.up();

    // The panel is the user-visible half of this: the button must stop claiming
    // the camera is turning the moment it is not.
    await expect(page.getByRole('button', { name: 'Orbit', exact: true })).toBeVisible();
    const halted = await pose(page);
    await page.waitForTimeout(1_500);
    expect(headingGap((await pose(page)).bearing, halted.bearing)).toBeLessThan(0.01);
  });
});

test.describe('reduced motion', () => {
  test('the camera cuts instead of flying, and offers no orbit', async ({ page }) => {
    // `test.use({ reducedMotion: 'reduce' })` is the documented way to do this
    // and it does not arrive: measured here on 2026-08-12, the page still reads
    // `matchMedia('(prefers-reduced-motion: reduce)').matches === false` and the
    // controller therefore builds itself with the preference off. Called on the
    // page, before navigation, it lands. Worth the four lines of comment because
    // the failure is a test that exercises the ordinary camera while claiming to
    // exercise the reduced one — it would have passed had these assertions been
    // written the other way round.
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await openCity(page);

    // No orbit button at all — the controller refuses to orbit under this
    // preference, so a button would be a control that does nothing.
    await expect(page.getByRole('button', { name: 'Orbit', exact: true })).toHaveCount(0);
    await expect(page.getByText('Reduced motion is on')).toBeVisible();

    await page.evaluate((key) => {
      window[key as typeof CITY_DEBUG_KEY]!.camera.flyTo(
        { center: [-73.79, 40.66], zoom: 15 },
        { duration: 8_000 },
      );
    }, CITY_DEBUG_KEY);
    // Immediately: a jump, not a journey. 150ms is far inside the 8s animation
    // this would otherwise have started.
    await page.waitForTimeout(150);
    const after = await pose(page);
    expect(after.center[0]).toBeCloseTo(-73.79, 3);
    expect(after.zoom).toBeCloseTo(15, 3);
  });
});
