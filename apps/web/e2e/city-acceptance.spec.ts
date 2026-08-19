import type { Page } from '@playwright/test';
import { expect, test } from '@playwright/test';

/**
 * M4c's acceptance walk, against a corpus this file controls.
 *
 * `city.md` §7 says M4c is done when three things are true: **no placement is
 * fabricated at any confidence**, **thousands of markers are not thousands of
 * components**, and **the list and the map cannot disagree**. The seeded suite
 * walks the third one against real data, and walks the first as far as this
 * corpus can take it — which is not far enough. Two of the three claims cannot
 * be answered by the seeded stack at all:
 *
 * - *No fabricated placement* is a claim about what happens when a payload
 *   **does** claim precision. Every one of the 31 seeded roles is `unresolved`
 *   with no coordinates (0 of 247 postings name a street — `city.md` §4.1), so
 *   the seeded assertion is "nothing lied, and nothing was drawn as though it
 *   had". That is worth having and it is not the same sentence. The failure
 *   this invariant exists to prevent needs a lie to be told first.
 *
 * - *Thousands of markers* is a claim about scale, and the corpus has 31 roles.
 *   Asserting that 30 beacons do not produce 30 components would pass just as
 *   happily against an implementation that renders one `<div>` per marker.
 *
 * Both need a corpus that is chosen rather than found, so both stub
 * `/city/signals` and neither needs an API — which is why they live in the
 * offline config beside M4b's rendering tests. The map itself is real: real
 * archives, real MapLibre, real Three.js, real instance buffers.
 */

import { CITY_DEBUG_KEY } from '../src/lib/map/debug';
import { MAX_BEACONS } from '../src/lib/city/beacon';

/**
 * Three minutes, against the two of `city.spec.ts`.
 *
 * Same reason, more of it: the tests below load the city up to four times in
 * one test, and every load rasterises New York on a software renderer. The
 * budget is spent on page loads, not on waiting for assertions — each one
 * polls and returns the moment it is satisfied.
 */
test.describe.configure({ timeout: 180_000 });

type Signal = Record<string, unknown>;

/** A UUID the schema will accept, derived from an index so it is stable. */
function uuid(prefix: string, index: number): string {
  const tail = `${prefix}${index}`.padStart(12, '0').slice(-12);
  return `00000000-0000-4000-8000-${tail}`;
}

/** The placement every role in the real corpus has: a stated city, and nothing else. */
const UNRESOLVED = {
  kind: 'unresolved',
  latitude: null,
  longitude: null,
  building_id: null,
  location_confidence: 'city_only',
  resolution_method: 'source_text_parse',
  stated: 'New York, NY',
  inherited: false,
  office_label: null,
  office_address: null,
} as const;

function role(index: number, employer: number, placement: unknown = UNRESOLVED): Signal {
  return {
    job_id: uuid('a', index),
    title: `Software Engineer ${index}`,
    company_id: uuid('c', employer),
    // Padded so the alphabetical default sort is also the numeric order — an
    // employer list that reads 1, 10, 11, 2 makes every failure message here
    // harder to read than it needs to be.
    company_name: `Employer ${String(employer).padStart(3, '0')}`,
    employment_type: 'full_time',
    remote_policy: 'on_site',
    status: 'open',
    first_seen_at: '2026-01-01T00:00:00Z',
    last_seen_at: '2026-01-01T00:00:00Z',
    last_verified_at: '2026-01-01T00:00:00Z',
    application_deadline: null,
    placement,
  };
}

/** `count` roles spread evenly over `employers` columns. */
function corpus(count: number, employers: number): Signal[] {
  return Array.from({ length: count }, (_, index) => role(index, index % employers));
}

/** The body `/city/signals` returns, with counts that agree with the signals in it. */
function body(signals: readonly Signal[]) {
  const kindOf = (signal: Signal) => (signal.placement as { kind: string }).kind;
  return {
    signals,
    counts: {
      building: signals.filter((s) => kindOf(s) === 'building').length,
      area: signals.filter((s) => kindOf(s) === 'area').length,
      unresolved: signals.filter((s) => kindOf(s) === 'unresolved').length,
      total: signals.length,
    },
    limit: MAX_BEACONS,
    truncated: false,
  };
}

/**
 * Serve one corpus, and keep serving whatever the caller last set.
 *
 * Returned as a setter rather than installed per-navigation because both tests
 * below change the corpus *between reloads of the same page*, and a second
 * `page.route` for the same pattern stacks rather than replaces.
 */
async function stubSignals(page: Page): Promise<(signals: readonly Signal[]) => void> {
  let current: readonly Signal[] = [];
  await page.route('**/city/signals**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body(current)),
    });
  });
  return (signals) => {
    current = signals;
  };
}

/** How many beacons are in the instance buffer, or -1 if there is no layer yet. */
async function drawn(page: Page): Promise<number> {
  return page.evaluate((key) => {
    const city = window[key as typeof CITY_DEBUG_KEY];
    if (!city) return -1;
    if (!city.map.getLayer('nightshift-signals')) return -1;
    return city.signals.drawn;
  }, CITY_DEBUG_KEY);
}

/** Wait until the layer exists at all — which it does whether or not it has data. */
async function cityHasLayer(page: Page) {
  await expect
    .poll(() => drawn(page), {
      timeout: 90_000,
      message: 'the signal layer was never added to the style',
    })
    .toBeGreaterThanOrEqual(0);
}

async function openCity(page: Page) {
  await page.goto('/explore/city');
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText('The map cannot be drawn')).toHaveCount(0);
}

/**
 * I1, from the side the seeded corpus cannot reach: a payload that *claims* a
 * position it has no right to.
 *
 * The three shapes below are the three the API's own `Placement.__post_init__`
 * refuses, restated in the browser (`schemas.ts` keeps a deliberate second copy
 * of the rule). Each one is a plausible bug rather than a hypothetical: an
 * unresolved role that picked up its company's coordinates by a join gone
 * wrong; a building placement inheriting an office nobody confirmed; an
 * approximate placement that was handed a BIN because the nearest footprint was
 * close enough.
 *
 * **What is being asserted is a refusal of the whole payload, not a filter.**
 * Dropping the bad row and drawing the other twelve would be the worse
 * behaviour: the corpus has been shown to be producing fabricated positions,
 * and a city that quietly renders the rest of it is a city asserting that its
 * remaining placements can be trusted. It cannot know that. So it draws none of
 * them and says why — and the control below proves the refusal is about the
 * fabrication rather than about the stub.
 */
test('a placement claiming more than it can prove takes the whole corpus off the city', async ({
  page,
}) => {
  const serve = await stubSignals(page);

  // The control. Same twelve roles, nothing fabricated.
  const honest = corpus(12, 3);
  serve(honest);
  await openCity(page);
  await cityHasLayer(page);
  await expect.poll(() => drawn(page), { timeout: 30_000 }).toBe(12);

  const fabrications: readonly (readonly [string, unknown])[] = [
    [
      'an unresolved role carrying coordinates',
      { ...UNRESOLVED, latitude: 40.7128, longitude: -74.006 },
    ],
    [
      'a building placement at a confidence below verified',
      {
        ...UNRESOLVED,
        kind: 'building',
        latitude: 40.7128,
        longitude: -74.006,
        building_id: '1001234',
        location_confidence: 'approximate',
      },
    ],
    [
      'an approximate placement that named a building',
      {
        ...UNRESOLVED,
        kind: 'area',
        latitude: 40.7128,
        longitude: -74.006,
        building_id: '1001234',
        location_confidence: 'approximate',
      },
    ],
  ];

  for (const [what, placement] of fabrications) {
    serve([...honest, role(99, 0, placement)]);
    await page.reload();

    // The city says the corpus could not be loaded, rather than showing an
    // empty sky. I3's habit of mind: an empty market and a refused payload are
    // different sentences.
    await expect(page.getByRole('heading', { name: 'No roles on the city' })).toBeVisible({
      timeout: 60_000,
    });
    await cityHasLayer(page);
    expect(await drawn(page), `${what} reached the instance buffer`).toBe(0);
  }
});

/**
 * The scale claim, stated as an equality rather than as a bound.
 *
 * `CLAUDE.md` §6 M4: *"thousands of markers ≠ thousands of React components"*.
 * The usual way to test that is to assert some element count stays under a
 * ceiling, which is a test that passes for the wrong reason as soon as the
 * ceiling is generous. This holds the *employer* count fixed and moves only the
 * role count — 100 roles to 5,000, fifty times as many markers — so the DOM is
 * being asked to be **identical**, not merely small. A single `<div>` per
 * marker anywhere in the tree turns 0 into 4,900.
 *
 * 5,000 is not a round number chosen for effect: it is `MAX_BEACONS`, which is
 * also the API's `MAX_SIGNALS`, so this is the largest city this product can
 * currently be asked to draw.
 */
test('fifty times the markers is the same DOM, and every one of them reaches the buffer', async ({
  page,
}) => {
  const serve = await stubSignals(page);
  const EMPLOYERS = 20;

  serve(corpus(100, EMPLOYERS));
  await openCity(page);
  await cityHasLayer(page);
  await expect.poll(() => drawn(page), { timeout: 30_000 }).toBe(100);

  // Open the legend before counting, so the count covers the panel that draws
  // one row per §6 treatment as well as the roster and the readout.
  await page.getByRole('button', { name: /what the marks mean/i }).click();
  const elementsAtHundred = await elementCount(page);

  serve(corpus(MAX_BEACONS, EMPLOYERS));
  await page.reload();
  await cityHasLayer(page);
  const settledAt = Date.now();
  await expect
    .poll(() => drawn(page), {
      timeout: 60_000,
      message: 'the buffer never reached the full corpus',
    })
    .toBe(MAX_BEACONS);
  // Not asserted — a headless software renderer is not a performance
  // measurement, and M4d is where the numbers live. Printed because a run that
  // takes minutes rather than seconds is worth noticing here first.
  console.log(`5,000 beacons settled ${Date.now() - settledAt} ms after the layer appeared`);

  await page.getByRole('button', { name: /what the marks mean/i }).click();

  expect(
    await elementCount(page),
    'the DOM grew when the corpus did — something is rendering per marker',
  ).toBe(elementsAtHundred);

  // And the markers really are one object: one canvas, one custom layer, no
  // children under the map container at all.
  expect(await page.locator('canvas.maplibregl-canvas').count()).toBe(1);
  const layerType = await page.evaluate(
    (key) => window[key as typeof CITY_DEBUG_KEY]!.map.getLayer('nightshift-signals')?.type ?? null,
    CITY_DEBUG_KEY,
  );
  expect(layerType).toBe('custom');
});

/**
 * Every element the city itself renders — `#main`, which is the whole page.
 *
 * Scoped rather than counting the document, and the two things left out are
 * both timing rather than content. `<head>` gains a `<style>` and a `<script>`
 * per route `next dev` has compiled so far, and the shell's header holds the
 * live health indicators, which move through loading → unreachable on their own
 * schedule with no API behind them. Counting either would make this a detector
 * of how recently the page was compiled. Neither can hold a marker: every
 * beacon, every roster row and every legend row is inside `#main`.
 *
 * That was not a guess — the first version of this counted the document and
 * failed by a handful of elements between two loads of the same corpus.
 */
async function elementCount(page: Page): Promise<number> {
  return page.evaluate(() => document.querySelectorAll('#main *').length);
}

/**
 * A placement this renderer cannot draw yet must be *said*, not silently
 * dropped.
 *
 * **The prediction in this comment came true on 2026-08-17 and the test was
 * rewritten rather than deleted.** It used to read: the corpus has no confirmed
 * office, so `building` and `area` are zero and M4c draws neither; the moment
 * the first address is curated this becomes a page reporting "on a building: 1"
 * over a skyline with nothing on it. The first addresses were curated that
 * morning, twenty roles reached a building, and the sentence this test guards
 * was the only thing on the page telling the truth about them.
 *
 * M4e Task 6 then built the roofs, so `building` came out of the undrawn set
 * and **`area` stayed in it** — §6 draws an approximate location as a
 * translucent radius and nothing draws one yet. The guard is the same and the
 * set it names is smaller, which is what a shrinking honest gap looks like.
 *
 * That is I7 in the form it actually arrives in — not a mock presented as
 * working, but a *renderer* presented as complete — and the fix is a sentence
 * rather than a feature.
 */
test('a role the renderer cannot place yet is counted and named, not quietly dropped', async ({
  page,
}) => {
  const serve = await stubSignals(page);
  const onBuilding = role(50, 0, {
    ...UNRESOLVED,
    kind: 'building',
    latitude: 40.7128,
    longitude: -74.006,
    building_id: '1001234',
    location_confidence: 'verified',
    resolution_method: 'company_office',
    inherited: true,
    office_label: 'Headquarters',
    office_address: '1 Example Plaza, New York, NY',
  });
  const inArea = role(51, 1, {
    ...UNRESOLVED,
    kind: 'area',
    latitude: 40.7128,
    longitude: -74.006,
    location_confidence: 'approximate',
  });

  serve([...corpus(5, 2), onBuilding, inArea]);
  await openCity(page);
  await cityHasLayer(page);

  // Six drawn, seven in the corpus: five floating plus the one standing on a
  // roof. The one that is not drawn is the area, which is the only placement
  // this renderer still has no treatment for.
  await expect.poll(() => drawn(page), { timeout: 30_000 }).toBe(6);

  const readout = page.getByRole('region', { name: /what is on the city/i });
  // The floating line counts the field, not the city: five of seven roles are
  // in it, and the sixth is on a building rather than missing.
  await expect(readout).toContainText('5 of 7');
  await expect(readout).toContainText(/1 of these is not drawn/i);
});

/**
 * M4d Task 1 — the instrument, in the browser it will be used from.
 *
 * Deliberately **not** a threshold. This machine is headless Chromium with no
 * GPU: every frame here is drawn by SwiftShader on the CPU, so `expect(p95)
 * .toBeLessThan(16.7)` would either fail on a correct city or pass on a slow
 * one, and either way it would be an assertion about a software rasteriser
 * wearing the words "60fps desktop". The numbers for `PROGRESS.md` come from a
 * headed run on real hardware.
 *
 * What is asserted here is the part that must hold everywhere: the timer sees
 * frames the map actually presented, and **the page says what drew them**.
 */
test('the frame timer measures frames the map really presented, and names what drew them', async ({
  page,
}) => {
  const serve = await stubSignals(page);
  serve(corpus(200, 20));
  await openCity(page);
  await cityHasLayer(page);

  const readout = page.getByRole('region', { name: /how this is drawing/i });
  await expect(readout).toBeVisible();

  // Move the city, which is the only thing that makes it paint: an idle map
  // with nothing animating presents no frames at all, on purpose.
  for (let i = 0; i < 3; i += 1) {
    await page.mouse.move(640, 480);
    await page.mouse.down();
    await page.mouse.move(500, 380, { steps: 24 });
    await page.mouse.up();
  }

  const report = await expect
    .poll(
      () =>
        page.evaluate(
          (key) => window[key as typeof CITY_DEBUG_KEY]!.frames.report(),
          CITY_DEBUG_KEY,
        ),
      { timeout: 30_000, message: 'the timer never saw a window of frames' },
    )
    .not.toBeNull();
  void report;

  const measured = await page.evaluate(
    (key) => window[key as typeof CITY_DEBUG_KEY]!.frames.report(),
    CITY_DEBUG_KEY,
  );
  expect(measured!.frames).toBeGreaterThanOrEqual(12);
  // Every interval is a real gap between two presented frames: positive, and
  // below the stall threshold that would have discarded it.
  expect(measured!.p50).toBeGreaterThan(0);
  expect(measured!.worst).toBeLessThan(1_000);

  // The assertion this whole task is shaped around. Headless Chromium has no
  // GPU, and a panel that let these numbers pass as hardware numbers would be
  // the M4c review's finding repeated one milestone later.
  await expect(readout).toContainText(/software rasteriser on the CPU/i);
});

/**
 * Keep the map's current frame, and count how many pixels the next one moved.
 *
 * Read out of the drawing buffer inside a `render` event, which is the one
 * moment it is guaranteed to still hold the frame — this map does not set
 * `preserveDrawingBuffer`, and outside that window the canvas reads back
 * empty. Playwright's own screenshot would do for whole-frame equality, but
 * equality is what the first draft of this test used and it passed with the
 * bodies drawing nothing: three name plates disappearing was difference
 * enough. Counting the pixels is what separates a field of columns from a
 * field of captions, and decoding a PNG in Node to do it would mean a
 * dependency for one assertion.
 *
 * A colour test was the other candidate and it does not survive contact with
 * this renderer: the beacons are additive over a lit sky, so a column crossing
 * the horizon band comes out white rather than cyan and a hue filter throws
 * most of it away. What the field paints is measured by taking the field away.
 */
async function keepFrame(page: Page): Promise<void> {
  await page.evaluate(
    (key) =>
      new Promise<void>((resolve) => {
        const map = window[key as typeof CITY_DEBUG_KEY]!.map;
        map.once('render', () => {
          const canvas = map.getCanvas();
          const off = document.createElement('canvas');
          off.width = canvas.width;
          off.height = canvas.height;
          const context = off.getContext('2d')!;
          context.drawImage(canvas, 0, 0);
          (window as unknown as { __keptFrame?: ImageData }).__keptFrame = context.getImageData(
            0,
            0,
            off.width,
            off.height,
          );
          resolve();
        });
        map.triggerRepaint();
      }),
    CITY_DEBUG_KEY,
  );
}

/**
 * What fraction of the map differs from the kept frame, ignoring rasteriser
 * noise.
 *
 * A fraction rather than a count so the thresholds below mean the same thing
 * at any viewport, and so an upper bound can be written at all: one of the two
 * defects this test exists for made every column thousands of times too large,
 * and the frame it produced was solid white. A floor alone welcomes that.
 */
async function fractionMovedSince(page: Page): Promise<number> {
  return page.evaluate(
    (key) =>
      new Promise<number>((resolve) => {
        const map = window[key as typeof CITY_DEBUG_KEY]!.map;
        map.once('render', () => {
          const kept = (window as unknown as { __keptFrame?: ImageData }).__keptFrame;
          if (kept === undefined) {
            resolve(-1);
            return;
          }
          const canvas = map.getCanvas();
          const off = document.createElement('canvas');
          off.width = canvas.width;
          off.height = canvas.height;
          const context = off.getContext('2d')!;
          context.drawImage(canvas, 0, 0);
          const now = context.getImageData(0, 0, off.width, off.height).data;
          const before = kept.data;
          let moved = 0;
          for (let i = 0; i < now.length; i += 4) {
            const delta =
              Math.abs(now[i]! - before[i]!) +
              Math.abs(now[i + 1]! - before[i + 1]!) +
              Math.abs(now[i + 2]! - before[i + 2]!);
            if (delta > 24) moved += 1;
          }
          resolve(moved / (now.length / 4));
        });
        map.triggerRepaint();
      }),
    CITY_DEBUG_KEY,
  );
}

/**
 * The two failures ADR 0034's column shipped with, and neither one raised
 * anything: no error, no warning, no red test, no visibly broken frame.
 *
 * **The bodies drew nothing at all.** The shader asked two questions that only
 * have answers in a renderer with a view matrix — `normalMatrix * normal` for
 * the soft edge, `projectionMatrix[1][1]` for the pixel floor — and ADR 0025
 * says this renderer has neither: MapLibre hands over one composed matrix and
 * the model-view is left alone. The first came out exactly zero at every
 * vertex, so every column was alpha 0; the second came out about 7,000x, so
 * every column was scaled to hundreds of kilometres and clipped out of frame.
 * The city looked fine, because §6's marks and the roof beams are also
 * vertical cyan things standing on the same anchors, and they were what
 * everybody had been looking at for two days.
 *
 * **And the ambient rise was gated on the recency pulse.** ADR 0034 made the
 * rise identical on every role; the repaint request still asked whether some
 * role was new. The seeded corpus is 90% new, so frames kept arriving and it
 * never showed.
 *
 * A corpus is what separates them, and it is why this test is here rather than
 * in the seeded suite. Every role below is **old** — outside
 * `NEW_WINDOW_DAYS`, so no pulse — and **unresolved and untouched**, so §6
 * draws no outline, no core, no ring, no arc, and no roof beam stands under
 * it. On this corpus the beacon column is the only thing on the city that can
 * move. If it is missing, or frozen, nothing else covers for it.
 */
/**
 * How much of the map the field has to paint, and how much of it has to move.
 *
 * Every number here was measured against the broken renderer rather than
 * guessed, by running this test against it. ADR 0034's column shipped with two
 * defects in one shader, and they hid each other:
 *
 * | state                        | field paints | moves per frame |
 * |------------------------------|--------------|-----------------|
 * | as shipped (both defects)    | 0.5%         | **0.0%**        |
 * | size fixed, soft edge broken | 0.5%         | 0.0%            |
 * | soft edge fixed, size broken | **100%**     | — (solid white) |
 * | both fixed                   | 2.9%         | 0.46%           |
 *
 * The 0.5% in the broken rows is three name plates. The bodies contributed
 * nothing at all, which is why every threshold has daylight around it.
 *
 * A moving threshold of zero would have caught this and is still the wrong
 * number: a rasteriser that dithers, or a sky that ever animates, clears zero
 * with the columns standing still.
 */
const FIELD_FRACTION_MIN = 0.012;
const FIELD_FRACTION_MAX = 0.4;
const MOVING_FRACTION = 0.001;

test('a role nobody applied to and nobody posted this week still draws, and still moves', async ({
  page,
}) => {
  const serve = await stubSignals(page);
  serve(corpus(9, 3));
  await openCity(page);
  await cityHasLayer(page);
  await expect.poll(() => drawn(page), { timeout: 60_000 }).toBe(9);

  // Every measurement below is a difference between two frames, so the city
  // has to have stopped arriving in them first. New York is assembled on a
  // share of each frame — 35,000 footprints over hundreds of frames — and a
  // frame taken mid-build differs from the next one by two thirds of the
  // canvas, which would swamp anything a beacon does and pass every assertion
  // here for the wrong reason. Measured: 354,665 pixels moving per frame
  // during the build, against the few thousand a field of columns moves.
  await expect
    .poll(
      () =>
        page.evaluate(
          (key) => window[key as typeof CITY_DEBUG_KEY]!.signals.city.ready === true,
          CITY_DEBUG_KEY,
        ),
      { timeout: 120_000, message: 'the city never finished building' },
    )
    .toBe(true);

  // Not one of them is new, so not one of them pulses. This is the state the
  // old repaint gate answered "nothing is moving" to.
  const pulses = await page.evaluate((key) => {
    const layer = window[key as typeof CITY_DEBUG_KEY]!.signals;
    return Array.from({ length: layer.drawn }, (_, i) => layer.pulseAt(i) ?? -1);
  }, CITY_DEBUG_KEY);
  expect(pulses).toHaveLength(9);
  expect(pulses.every((hz) => hz === 0)).toBe(true);

  // The city still considers itself animating, and its clock still advances.
  expect(
    await page.evaluate(
      (key) => window[key as typeof CITY_DEBUG_KEY]!.signals.animating,
      CITY_DEBUG_KEY,
    ),
  ).toBe(true);

  const clockAt = () =>
    page.evaluate((key) => window[key as typeof CITY_DEBUG_KEY]!.signals.clockAt, CITY_DEBUG_KEY);
  const before = await clockAt();
  await expect
    .poll(clockAt, { timeout: 30_000, message: 'the beacon clock never advanced' })
    .toBeGreaterThan(before + 1);

  // The clock advancing is not the claim either — a uniform can advance in
  // front of a shader that ignores it, which is the other half of what went
  // wrong here. The claim is that the picture changes, by more than a
  // rasteriser's noise, with nothing on this city moving but the columns.
  await keepFrame(page);
  await expect
    .poll(() => fractionMovedSince(page), {
      timeout: 30_000,
      message: 'the columns drew an identical frame for thirty seconds',
    })
    .toBeGreaterThan(MOVING_FRACTION);

  // And a clock advancing is not the claim — a uniform can advance in front of
  // a shader that ignores it, which is exactly half of what went wrong here.
  //
  // So: count the signal cyan on the canvas, with the field and without it.
  // Nothing else in the city is allowed to be this colour (ADR 0034 reserves
  // the hue, and `cityBuildings.test.ts` holds the scenery 27 L* below it), so
  // the difference between the two counts is the field and only the field —
  // and on this corpus the field is nine bodies, three name plates and nothing
  // else. An earlier draft of this compared whole screenshots for inequality
  // and passed with the bodies drawing zero pixels, because the plates
  // vanishing was difference enough. Counting separates them.
  //
  // So: keep the frame, take the field away, and count what changed. On this
  // corpus the field is nine bodies and three name plates and nothing else, so
  // what changed is the field — and the two parts of it are separated by an
  // order of magnitude. An earlier draft compared whole screenshots for
  // inequality and passed with the bodies drawing zero pixels, because the
  // plates vanishing was difference enough.
  await keepFrame(page);
  await page.evaluate((key) => {
    window[key as typeof CITY_DEBUG_KEY]!.signals.setSignals([]);
  }, CITY_DEBUG_KEY);
  await expect.poll(() => drawn(page), { timeout: 30_000 }).toBe(0);

  const field = await fractionMovedSince(page);
  expect(field).toBeGreaterThan(FIELD_FRACTION_MIN);
  // And the ceiling, which is the other defect: a column that is thousands of
  // times too large paints the whole window white, and a floor alone calls
  // that a healthy field.
  expect(field).toBeLessThan(FIELD_FRACTION_MAX);
});
