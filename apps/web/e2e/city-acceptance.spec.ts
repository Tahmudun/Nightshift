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
