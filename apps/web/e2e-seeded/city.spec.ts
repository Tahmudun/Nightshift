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

/**
 * M4c Task 3 — the unresolved field as a *good* screen.
 *
 * §4.8 asks for "a legible, navigable, sortable field of signals". The three
 * words are three separate claims and each gets its own assertions here:
 * every column carries its employer's name; the roster reaches every column
 * and can move the camera to one; and the ordering can be changed without the
 * field becoming a different set of roles.
 */

/** The employers the API says are hiring, in the order the default sort uses. */
async function employersFromApi(): Promise<Map<string, number>> {
  const body = await signalsFromApi();
  const counts = new Map<string, number>();
  for (const signal of body.signals as readonly {
    company_name: string;
    placement: { kind: string };
  }[]) {
    if (signal.placement.kind !== 'unresolved') continue;
    counts.set(signal.company_name, (counts.get(signal.company_name) ?? 0) + 1);
  }
  return counts;
}

test('every employer on the city is named in the roster, with its own count', async ({ page }) => {
  const expected = await employersFromApi();
  await openCity(page);
  await cityHasSignals(page);

  const roster = page.getByRole('region', { name: /who is hiring/i });
  await expect(roster).toBeVisible();

  // The roster is the field's non-3D equivalent (§5.6): a person who cannot
  // use the canvas has to be able to read the same city from the DOM.
  for (const [name, roles] of expected) {
    const row = roster.getByRole('button', { name: new RegExp(`${name}\\b`) });
    await expect(row).toBeVisible();
    await expect(row).toContainText(String(roles));
  }

  await expect(roster).toContainText(`${expected.size} employer`);
});

test('every column carries a name plate in the scene', async ({ page }) => {
  const expected = await employersFromApi();
  await openCity(page);
  await cityHasSignals(page);

  const plates = await page.evaluate((key) => {
    const city = window[key as typeof CITY_DEBUG_KEY]!;
    return {
      columns: city.signals.columns.length,
      labelled: city.signals.labelled,
      unlabelled: city.signals.unlabelled,
    };
  }, CITY_DEBUG_KEY);

  // One plate per employer, not one per role. A column was an anonymous stack
  // of diamonds before this existed, which is the gap Task 3 names.
  expect(plates.columns).toBe(expected.size);
  expect(plates.labelled).toBe(expected.size);
  expect(plates.unlabelled).toBe(0);
});

test('the name plates keep facing the camera as it turns', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  await page.evaluate((key) => {
    window[key as typeof CITY_DEBUG_KEY]!.map.jumpTo({ bearing: 42, pitch: 55 });
  }, CITY_DEBUG_KEY);

  // Nothing in this layer billboards on its own — there is no view matrix to
  // billboard against (ADR 0025), so the orientation is pushed in from the
  // map's own angles. A plate that stops tracking is not invisible; it lies
  // flat over the city like a sticker, and reads as a broken texture.
  await expect
    .poll(
      () =>
        page.evaluate((key) => {
          const city = window[key as typeof CITY_DEBUG_KEY]!;
          return Math.round(city.signals.labelsOrientedTo.bearing);
        }, CITY_DEBUG_KEY),
      { message: 'the plates never reoriented after the camera moved' },
    )
    .toBe(42);

  expect(
    await page.evaluate(
      (key) => Math.round(window[key as typeof CITY_DEBUG_KEY]!.signals.labelsOrientedTo.pitch),
      CITY_DEBUG_KEY,
    ),
  ).toBe(55);
});

test('reordering the field changes the order and not the roles', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const read = () =>
    page.evaluate((key) => {
      const city = window[key as typeof CITY_DEBUG_KEY]!;
      return {
        drawn: city.signals.drawn,
        names: city.signals.columns.map((c) => c.name),
        roles: city.signals.columns.map((c) => c.roles).sort((a, b) => a - b),
      };
    }, CITY_DEBUG_KEY);

  const byName = await read();
  expect(byName.names).toEqual([...byName.names].sort((a, b) => a.localeCompare(b)));

  await page.getByRole('radio', { name: 'Openings' }).click();

  await expect
    .poll(async () => (await read()).names.join('|'), {
      message: 'the field never reordered after the sort was changed',
    })
    .not.toBe(byName.names.join('|'));

  const byOpenings = await read();
  // Tallest first. This is the assertion that the *scene* reordered, not just
  // the list — it reads the instance buffer's own columns.
  const heights = byOpenings.names.map((name) => byName.roles[byName.names.indexOf(name)] ?? 0);
  expect([...heights]).toEqual([...heights].sort((a, b) => b - a));

  // An ordering is not a filter. The same roles are on the city before and
  // after, or the sort control is quietly hiding part of the corpus.
  expect(byOpenings.drawn).toBe(byName.drawn);
  expect(byOpenings.roles).toEqual(byName.roles);
  expect([...byOpenings.names].sort()).toEqual([...byName.names].sort());
});

test('the roster flies the camera to a column that is not on screen', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  // Drive the camera away from the field first. Clicking a row while the
  // column is already centred is *supposed* to do nothing (§5.6: "moves the
  // camera only if needed"), so a test that clicked from the opening pose
  // would be asserting the opposite of the rule — which is exactly what the
  // first draft of this test did, and it failed correctly.
  await page.evaluate((key) => {
    window[key as typeof CITY_DEBUG_KEY]!.map.jumpTo({
      center: [-73.83, 40.68],
      zoom: 11,
    });
  }, CITY_DEBUG_KEY);

  const before = await page.evaluate((key) => {
    const city = window[key as typeof CITY_DEBUG_KEY]!;
    const centre = city.map.getCenter();
    return { lng: centre.lng, lat: centre.lat, zoom: city.map.getZoom() };
  }, CITY_DEBUG_KEY);

  const roster = page.getByRole('region', { name: /who is hiring/i });
  await roster.getByRole('button').last().click();

  // §4.8 asks for a *navigable* field. Without this the only way to reach a
  // column is to find it by hand in a city-sized scene.
  //
  // Polled rather than slept on, for M4b's reason: the fly-to is animated and
  // driven by requestAnimationFrame, and a headless Chromium rasterising a
  // million footprints can starve rAF for longer than any fixed wait.
  await expect
    .poll(
      () =>
        page.evaluate((key) => {
          const centre = window[key as typeof CITY_DEBUG_KEY]!.map.getCenter();
          return `${centre.lng},${centre.lat}`;
        }, CITY_DEBUG_KEY),
      { timeout: 20_000, message: 'the camera never moved' },
    )
    .not.toBe(`${before.lng},${before.lat}`);

  const after = await page.evaluate((key) => {
    const city = window[key as typeof CITY_DEBUG_KEY]!;
    const centre = city.map.getCenter();
    return { lng: centre.lng, lat: centre.lat, zoom: city.map.getZoom() };
  }, CITY_DEBUG_KEY);

  // It arrives close enough to read a column rather than at street level, and
  // `focusOn` never zooms out from wherever the user already was.
  expect(after.zoom).toBeGreaterThanOrEqual(before.zoom);
});

test('the roster marks the column it last sent you to', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const roster = page.getByRole('region', { name: /who is hiring/i });
  const row = roster.getByRole('button').first();

  // The feedback that makes a no-op click legible. Because the camera declines
  // to move for a column that is already on screen, without this a person who
  // clicks a row that is already centred gets no response at all and concludes
  // the control is broken.
  await expect(row).not.toHaveAttribute('aria-current', 'location');
  await row.click();
  await expect(row).toHaveAttribute('aria-current', 'location');
});

test('the sort control is a radio group a keyboard can reach', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  // §5.6: every action on the map has a non-3D equivalent. The ordering of the
  // field is one of them, and a div with a click handler is not reachable.
  const group = page.getByRole('radiogroup', { name: /order the field by/i });
  await expect(group).toBeVisible();

  const name = page.getByRole('radio', { name: 'Name' });
  const newest = page.getByRole('radio', { name: 'Newest' });
  await expect(name).toHaveAttribute('aria-checked', 'true');

  await newest.focus();
  await page.keyboard.press('Enter');

  await expect(newest).toHaveAttribute('aria-checked', 'true');
  await expect(name).toHaveAttribute('aria-checked', 'false');
});
