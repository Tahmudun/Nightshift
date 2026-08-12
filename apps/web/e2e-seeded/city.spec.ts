import type { Page } from '@playwright/test';
import { expect, test } from '@playwright/test';

/**
 * M4c's signal layer, against the real corpus in a real browser.
 *
 * The unit tests prove that `arrangeUnresolved` computes the right transforms
 * and that `setSignals` writes the right number of instances. Neither can prove
 * that Three.js drew anything into MapLibre's context, that the beacons landed
 * where the field put them, or that the page's account of what is on screen
 * matches what the endpoint returned. Those need a GPU-less Chromium, the real
 * archives, and a seeded database — which is this config.
 *
 * The counts come from the API at run time rather than being written down here,
 * so this tracks the real corpus instead of a snapshot of it. Hard-coding "62"
 * would turn every future ingestion into a failing test that named the wrong
 * thing.
 */

import { CITY_DEBUG_KEY } from '../src/lib/map/debug';
import { FIELD_BASE_ALTITUDE } from '../src/lib/city/unresolvedField';

test.describe.configure({ timeout: 120_000 });

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface Signals {
  readonly counts: { building: number; area: number; unresolved: number; total: number };
  readonly signals: readonly { readonly placement: { readonly kind: string } }[];
}

async function signalsFromApi(): Promise<Signals> {
  const response = await fetch(`${API}/city/signals`);
  expect(response.ok, `GET ${API}/city/signals failed — is the API running?`).toBe(true);
  const body = (await response.json()) as Signals;
  expect(body.counts.total, 'a city with no roles in it proves nothing below').toBeGreaterThan(0);
  return body;
}

async function openCity(page: Page) {
  await page.goto('/explore/city');
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('The map cannot be drawn')).toHaveCount(0);
}

/**
 * Wait until the signal layer has both been added to the style and filled.
 *
 * Two separate things happen asynchronously — the style is applied, and the
 * fetch resolves — and a test that reads either the moment the camera panel
 * appears is racing both. The first draft did exactly that and reported
 * "0 beacons" and "no such layer" for a city that had both a second later.
 */
async function cityHasSignals(page: Page) {
  await expect
    .poll(
      () =>
        page.evaluate((key) => {
          const city = window[key as typeof CITY_DEBUG_KEY];
          if (!city) return -1;
          if (!city.map.getLayer('nightshift-signals')) return -1;
          return city.signals.drawn;
        }, CITY_DEBUG_KEY),
      { timeout: 30_000, message: 'the signal layer was never added, or never filled' },
    )
    .toBeGreaterThan(0);
}

test('every unresolved role reaches the instance buffer', async ({ page }) => {
  const expected = await signalsFromApi();
  await openCity(page);

  // Read from the renderer, not from the DOM. A count in the overlay would
  // prove the fetch worked; this is the only number that proves Three.js
  // received them.
  await cityHasSignals(page);
  expect(
    await page.evaluate(
      (key) => window[key as typeof CITY_DEBUG_KEY]!.signals.drawn,
      CITY_DEBUG_KEY,
    ),
  ).toBe(expected.counts.unresolved);
});

test('the layer is a custom 3d layer in the map’s own style', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  // §5.1: one context, one camera, one depth buffer. If this were a second
  // canvas stacked over the map there would be no layer here at all, and the
  // beacons would drift out of register on every gesture.
  const layer = await page.evaluate(
    (key) => window[key as typeof CITY_DEBUG_KEY]!.map.getLayer('nightshift-signals')?.type ?? null,
    CITY_DEBUG_KEY,
  );
  expect(layer).toBe('custom');
});

test('the beacons are drawn where the field put them, above every building', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  // Project the first instance back through MapLibre's own camera and ask what
  // altitude it is at. This is the assertion that catches the anchor transform
  // being wrong — a mirrored or mis-scaled field still produces the right
  // *number* of beacons, in entirely the wrong place.
  const altitude = await page.evaluate((key) => {
    const city = window[key as typeof CITY_DEBUG_KEY]!;
    // The scene stores metres relative to the anchor; instance 0 is the first
    // role of the alphabetically first employer.
    return city.signals.altitudeOf(0);
  }, CITY_DEBUG_KEY);

  // §4.8: the absence of a ground connection is the whole message, and One
  // World Trade is 541 m. A signal that can hide behind a tower reads as being
  // *at* that tower.
  expect(altitude).toBeGreaterThanOrEqual(FIELD_BASE_ALTITUDE);
  expect(altitude).toBeGreaterThan(541);
});

test('the page’s account of the city matches what the API returned', async ({ page }) => {
  const expected = await signalsFromApi();
  await openCity(page);

  const readout = page.getByRole('region', { name: /what is on the city/i });
  await expect(readout).toContainText(
    `${expected.counts.unresolved.toLocaleString('en-US')} of ${expected.counts.total.toLocaleString('en-US')}`,
  );

  // The claim this milestone is actually about. With no confirmed office in
  // the database nothing may stand on a building, and the page has to say so
  // rather than leaving a viewer to infer it from an empty skyline.
  if (expected.counts.building === 0) {
    await expect(readout).toContainText('Nothing is on a building yet');
  }
});

test('nothing on the city claims a precision the corpus does not have (I1)', async ({ page }) => {
  const expected = await signalsFromApi();

  // The endpoint's own guarantee, restated where a browser can see it: not one
  // role in this corpus carries coordinates, so not one beacon can be standing
  // anywhere real.
  for (const signal of expected.signals) {
    expect(['building', 'area', 'unresolved']).toContain(signal.placement.kind);
  }
  expect(expected.counts.unresolved + expected.counts.area + expected.counts.building).toBe(
    expected.counts.total,
  );

  await openCity(page);
  await cityHasSignals(page);
  const placed = await page.evaluate(
    (key) => window[key as typeof CITY_DEBUG_KEY]!.signals.drawn,
    CITY_DEBUG_KEY,
  );
  expect(placed).toBe(expected.counts.unresolved);
});
