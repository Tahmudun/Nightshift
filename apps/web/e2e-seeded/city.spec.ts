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
  readonly signals: readonly {
    readonly job_id: string;
    readonly company_name: string;
    readonly placement: { readonly kind: string };
  }[];
}

/**
 * How many roles the city should actually be drawing right now.
 *
 * **Every placement, not only the unresolved ones.** This counted `kind ===
 * 'unresolved'` from M4c until M5a, which was the whole corpus while no
 * company had a confirmed office. The offices came back on 2026-08-19 (ADR
 * 0036) and twenty roles moved onto two roofs — so this started returning a
 * number twenty short of what the renderer correctly drew, and three tests
 * below have been red ever since, describing a city this product stopped
 * being. The seeded suite needs a database, so nothing re-ran it.
 */
async function expectedBeacons(): Promise<number> {
  const [body, archived] = await Promise.all([signalsFromApi(), archivedJobIds()]);
  return body.signals.filter((signal) => !archived.has(signal.job_id)).length;
}

/** The first instance in the buffer that is a role standing on nothing. */
async function firstUnresolvedInstance(page: Page): Promise<number> {
  const unresolved = new Set(
    (await signalsFromApi()).signals
      .filter((signal) => signal.placement.kind === 'unresolved')
      .map((signal) => signal.job_id),
  );
  expect(unresolved.size, 'a corpus with nothing floating cannot check the field').toBeGreaterThan(
    0,
  );
  const index = await page.evaluate(
    ([key, ids]) => {
      const city = window[key as typeof CITY_DEBUG_KEY]!;
      for (let i = 0; i < city.signals.drawn; i += 1) {
        const jobId = city.signals.jobAt(i);
        if (jobId !== null && (ids as string[]).includes(jobId)) return i;
      }
      return -1;
    },
    [CITY_DEBUG_KEY, [...unresolved]] as const,
  );
  expect(index, 'no instance in the buffer draws an unresolved role').toBeGreaterThanOrEqual(0);
  return index;
}

/**
 * The roles §6 keeps off the city: rejected, withdrawn, or a closed
 * application.
 *
 * Subtracted from the endpoint's own counts by every assertion below that
 * compares the corpus against the buffer. Task 5 made the archive toggle real
 * and default-off, so "every role the API returned is drawn" stopped being
 * true — correctly. Reading the applications here rather than hard-coding a
 * number keeps these tests tracking the seed rather than a snapshot of it.
 */
async function archivedJobIds(): Promise<ReadonlySet<string>> {
  const response = await fetch(`${API}/applications?archived=true`);
  expect(response.ok, `GET ${API}/applications failed — is the API running?`).toBe(true);
  const body = (await response.json()) as {
    items: readonly { current_stage: string; job: { id: string } }[];
  };
  return new Set(
    body.items
      .filter((item) => ['rejected', 'withdrawn', 'closed'].includes(item.current_stage))
      .map((item) => item.job.id),
  );
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

test('every role reaches the instance buffer', async ({ page }) => {
  // Every one the archive toggle is not hiding, since Task 5: §6 keeps
  // rejections off the skyline by default, so the endpoint's own total is no
  // longer the number that should be drawn.
  const expected = await expectedBeacons();
  await openCity(page);

  // Read from the renderer, not from the DOM. A count in the overlay would
  // prove the fetch worked; this is the only number that proves Three.js
  // received them.
  await cityHasSignals(page);
  await expect
    .poll(
      () =>
        page.evaluate((key) => window[key as typeof CITY_DEBUG_KEY]!.signals.drawn, CITY_DEBUG_KEY),
      { timeout: 15_000, message: 'the buffer never settled at the visible corpus' },
    )
    .toBe(expected);
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

  // Read back the altitude of an instance the field placed — not instance 0.
  // This asked for instance 0 until M5a, which was an unresolved role while
  // every role was unresolved; the offices came back and instance 0 became a
  // role standing on a roof at 310 m, so this asserted the unresolved field's
  // floor against a building placement that is entitled to be below it.
  //
  // The assertion itself is the one that catches the anchor transform being
  // wrong — a mirrored or mis-scaled field still produces the right *number*
  // of beacons, in entirely the wrong place.
  const index = await firstUnresolvedInstance(page);
  const altitude = await page.evaluate(
    ([key, i]) => window[key as typeof CITY_DEBUG_KEY]!.signals.altitudeOf(i as number),
    [CITY_DEBUG_KEY, index] as const,
  );

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
  await expect
    .poll(
      () =>
        page.evaluate((key) => window[key as typeof CITY_DEBUG_KEY]!.signals.drawn, CITY_DEBUG_KEY),
      { timeout: 15_000 },
    )
    .toBe(await expectedBeacons());
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
  const [body, archived] = await Promise.all([signalsFromApi(), archivedJobIds()]);
  const counts = new Map<string, number>();
  for (const signal of body.signals) {
    if (signal.placement.kind !== 'unresolved') continue;
    // The roster reads the same filtered list the renderer does — that shared
    // filter is what §5.6's "the list and the map cannot disagree" means once
    // §6's archive toggle exists.
    if (archived.has(signal.job_id)) continue;
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

test('the sort control is served the whole corpus, whichever order it asks for', async ({
  page,
}) => {
  // **The ordering claim itself moved to `e2e/city-acceptance.spec.ts` at
  // M5a**, and the move is the finding. This test used to require that
  // choosing Openings produced a *different* order from the default, and it
  // had stopped being able to fail: the unresolved field in the seeded corpus
  // is four employers holding 9, 1, 1 and 1 roles, and the one with 9 is also
  // the alphabetically first — so ordering by openings is a stable sort over
  // three ties and correctly returns the order the name sort already gave.
  // The test asked the product for a change that could not happen.
  //
  // A corpus that cannot produce a failure cannot test the guard against it
  // (M4c Task 6), so the guard is now tested against a corpus chosen to tell
  // the two orderings apart, and what stays here is what the *real* corpus can
  // still say: the default order is alphabetical, and switching the sort is
  // not a filter.
  await openCity(page);
  await cityHasSignals(page);

  const read = () =>
    page.evaluate((key) => {
      const city = window[key as typeof CITY_DEBUG_KEY]!;
      return {
        drawn: city.signals.drawn,
        names: city.signals.columns.map((c) => c.name),
        // Parallel to `names`, in column order. It used to be returned sorted
        // and then indexed as though it were parallel, which made a "tallest
        // first" assertion compare a name's position against somebody else's
        // height — an assertion that could only pass or fail by accident.
        counts: city.signals.columns.map((c) => c.jobIds.length),
      };
    }, CITY_DEBUG_KEY);

  const byName = await read();
  expect(byName.names).toEqual([...byName.names].sort((a, b) => a.localeCompare(b)));

  await page.getByRole('radio', { name: 'Openings' }).click();
  // Settle on the count rather than on the order: this corpus is entitled to
  // return the same order, and waiting for one it cannot produce is what the
  // old version of this test did for fifteen seconds before failing.
  await expect.poll(async () => (await read()).drawn).toBe(byName.drawn);

  // An ordering is not a filter. The same roles are on the city before and
  // after, or the sort control is quietly hiding part of the corpus.
  const byOpenings = await read();
  expect([...byOpenings.counts].sort()).toEqual([...byName.counts].sort());
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

test('every control in the right rail can actually be clicked', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  // The regression this exists for: the camera panel placed itself at
  // `top-24 right-4`, the roster was later given the same corner, and the
  // buttons disappeared underneath it. Nothing went red — `toBeVisible` means
  // a non-empty bounding box, not a reachable element, so a green suite sat on
  // top of controls no pointer could touch. Clicking is what tells them apart,
  // and this is the seeded suite, where the rail is at its fullest: the
  // controls, a roster of employers, and the counts.
  //
  // Playwright's actionability check fails a click that another element would
  // intercept, so each of these is an occlusion assertion.
  await page.getByRole('button', { name: 'Reset view' }).click({ timeout: 10_000 });
  await page.getByRole('button', { name: 'Keyboard' }).click({ timeout: 10_000 });
  await page.getByRole('button', { name: 'Hide keys' }).click({ timeout: 10_000 });
  await page.getByRole('radio', { name: 'Openings' }).click({ timeout: 10_000 });

  const roster = page.getByRole('region', { name: /who is hiring/i });
  await roster.getByRole('button').first().click({ timeout: 10_000 });

  // And the counts panel at the foot of the rail is still on screen with all
  // of that above it, rather than pushed off the bottom.
  await expect(page.getByRole('region', { name: /what is on the city/i })).toBeVisible();
});

test('the rail is still usable with a role selected', async ({ page }) => {
  // Task 4 adds a fourth panel to the rail, and Task 3's worst defect was a
  // panel that covered another one completely while a full browser suite went
  // green over it. That panel was present on every load; this one appears only
  // once something is selected, so the previous test — which never selects
  // anything — cannot see it at all.
  await openCity(page);
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);
  await expect(page.getByTestId('city-detail')).toBeVisible({ timeout: 15_000 });

  await page.getByRole('button', { name: 'Reset view' }).click({ timeout: 10_000 });
  await page.getByRole('button', { name: 'Keyboard' }).click({ timeout: 10_000 });
  await page.getByRole('button', { name: 'Hide keys' }).click({ timeout: 10_000 });
  await page.getByRole('radio', { name: 'Newest' }).click({ timeout: 10_000 });
  await page.getByTestId('city-detail').getByRole('button', { name: 'Close' }).click({
    timeout: 10_000,
  });

  await expect(page.getByTestId('city-detail')).toHaveCount(0);
});

/**
 * Selection — Task 4, and the part of §5.6 that needs a real canvas.
 *
 * The unit tests prove the ray maths, the instance↔role mapping and the URL
 * round trip. None of them can prove that a *mouse click on a canvas* lands on
 * the beacon under the pointer, because the projection they use is one the test
 * built. These use the matrix MapLibre actually handed the layer.
 *
 * The beacons are not MapLibre features, so there is no `queryRenderedFeatures`
 * shortcut for finding one to click — and M4b measured that query answering
 * zero at this city's pitch even for features it does know about. The scan
 * below is the honest way to find a pixel with a role behind it: if the pick is
 * broken it finds nothing and every test here fails at its first line.
 */

/**
 * Scan the canvas for a pixel a mouse can actually reach, with or without a
 * role behind it.
 *
 * **`elementFromPoint` is the load-bearing half of this.** The city is a fixed
 * canvas with panels floating over it, and a pixel that picks a beacon is not
 * the same thing as a pixel a click reaches: the title panel occupies the top
 * left and the rail the right. The first draft of the empty-sky test below
 * clicked (30, 130), verified it picked nothing, and failed — because that
 * point is inside the title card, so the click never got to the map at all.
 * That is the same class of bug as the rail covering the camera panel in Task
 * 3, arriving in the test this time rather than in the product.
 */
async function findPixel(
  page: Page,
  want: 'beacon' | 'sky',
): Promise<{ x: number; y: number; jobId: string | null }> {
  const found = await page.evaluate(
    ([key, wanted]) => {
      const city = window[key as typeof CITY_DEBUG_KEY]!;
      const canvas = city.map.getCanvas();
      const viewport = { width: canvas.clientWidth, height: canvas.clientHeight };
      for (let y = 20; y < viewport.height - 20; y += 6) {
        for (let x = 20; x < viewport.width - 20; x += 6) {
          // Topmost element at this point. Anything but the canvas means a
          // panel would swallow the click.
          if (document.elementFromPoint(x, y) !== canvas) continue;
          const jobId = city.signals.pick({ x, y }, viewport);
          if (wanted === 'beacon' ? jobId !== null : jobId === null) return { x, y, jobId };
        }
      }
      return null;
    },
    [CITY_DEBUG_KEY, want] as const,
  );

  expect(found, `no reachable pixel on the canvas was ${want}`).not.toBeNull();
  return found!;
}

/** A pixel with a role behind it, reachable by a real mouse. */
async function findBeacon(page: Page): Promise<{ x: number; y: number; jobId: string }> {
  const found = await findPixel(page, 'beacon');
  return { x: found.x, y: found.y, jobId: found.jobId! };
}

const selectionState = (page: Page) =>
  page.evaluate((key) => {
    const signals = window[key as typeof CITY_DEBUG_KEY]!.signals;
    return { selected: signals.selected, at: signals.selectionAt };
  }, CITY_DEBUG_KEY);

test('clicking a beacon selects the role it draws', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);

  // The claim is end to end: a real click, through MapLibre's own event, to a
  // raycast against the matrix the last frame drew with, to the scene store.
  await expect
    .poll(async () => (await selectionState(page)).selected, {
      timeout: 15_000,
      message: 'a click on a beacon selected nothing',
    })
    .toBe(beacon.jobId);

  // And the reticle went with it. A selection the scene does not show is a
  // selection a person cannot see they made.
  expect((await selectionState(page)).at).not.toBeNull();
});

test('the selected role opens the panel that describes it', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);

  const panel = page.getByTestId('city-detail');
  await expect(panel).toBeVisible({ timeout: 15_000 });
  // I1 in the one place a person is actually reading about this role's
  // position. The beacon *is* somewhere on screen, above New York, and without
  // this sentence a position reads as a location.
  await expect(panel).toContainText(/nothing whatsoever about where in New York/);
  await expect(panel.getByRole('link', { name: 'Open the full role' })).toBeVisible();
});

test('a selection is a link you can send — §5.6', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);

  await expect
    .poll(() => new URL(page.url()).searchParams.get('job'), {
      timeout: 15_000,
      message: 'the selection never reached the URL',
    })
    .toBe(beacon.jobId);

  // The whole point of it being in the URL: open it cold and get the same role,
  // marked on the same beacon.
  await page.goto(`/explore/city?job=${beacon.jobId}`);
  await cityHasSignals(page);

  await expect(page.getByTestId('city-detail')).toBeVisible({ timeout: 30_000 });
  await expect
    .poll(async () => (await selectionState(page)).selected, { timeout: 20_000 })
    .toBe(beacon.jobId);
  expect((await selectionState(page)).at).not.toBeNull();
});

test('a selection keeps the query it was made under', async ({ page }) => {
  // §5.6 asks selection to preserve filters. The city does not read `q` today,
  // which is exactly why this is worth pinning: the failure mode is a href
  // built from scratch, and it destroys a parameter nobody on this page was
  // looking at.
  await page.goto('/explore/city?q=infrastructure');
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeVisible({ timeout: 60_000 });
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);

  await expect
    .poll(() => new URL(page.url()).searchParams.get('job'), { timeout: 15_000 })
    .toBe(beacon.jobId);
  expect(new URL(page.url()).searchParams.get('q')).toBe('infrastructure');
});

test('escape clears the selection, and the URL with it', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);
  await expect(page.getByTestId('city-detail')).toBeVisible({ timeout: 15_000 });

  await page.keyboard.press('Escape');

  await expect(page.getByTestId('city-detail')).toHaveCount(0);
  await expect
    .poll(() => new URL(page.url()).searchParams.has('job'), { timeout: 10_000 })
    .toBe(false);
  // And the mark comes off the city rather than being left ringing a beacon
  // nothing is selecting.
  expect((await selectionState(page)).at).toBeNull();
});

test('clicking empty sky puts the selection down', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);
  await expect(page.getByTestId('city-detail')).toBeVisible({ timeout: 15_000 });

  // A pixel with no role behind it *and* nothing floating over it. Both halves
  // matter: the first draft asserted only the first, clicked a point inside the
  // title card, and failed because the click never reached the map.
  const sky = await findPixel(page, 'sky');
  expect(sky.jobId).toBeNull();

  await page.mouse.click(sky.x, sky.y);

  await expect(page.getByTestId('city-detail')).toHaveCount(0);
  await expect
    .poll(() => new URL(page.url()).searchParams.has('job'), { timeout: 10_000 })
    .toBe(false);
});

test('the list and the map cannot disagree about what is selected', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);

  // The roster opens the employer the role belongs to and marks the row. This
  // is the criterion §5.6 states as "the list and the map stay synchronized",
  // and the way it breaks is silent: the beacon lights up, the row it
  // corresponds to is inside a collapsed group, and nothing looks wrong.
  const roster = page.getByRole('region', { name: /who is hiring/i });
  const row = roster.locator('[aria-current="true"]');
  await expect(row).toHaveCount(1, { timeout: 15_000 });

  // Exactly one row is marked, and it names the same role the panel does.
  // Comparing the two pieces of interface is the assertion — a highlight in
  // the scene and a highlight in the list that came from different state
  // could each look right on their own.
  const panelTitle = await page
    .getByTestId('city-detail')
    .getByRole('heading', { level: 2 })
    .textContent();
  expect((await row.textContent())?.trim()).toContain(panelTitle?.trim());
});

test('a role can be selected without touching the canvas at all', async ({ page }) => {
  // §5.6's hard rule: every action on the map has a non-3D equivalent. Picking
  // a beacon needs a pointer on a WebGL surface; this is the same selection
  // reached by keyboard through the roster, which is the only path available
  // to somebody who cannot use the canvas.
  await openCity(page);
  await cityHasSignals(page);

  const roster = page.getByRole('region', { name: /who is hiring/i });
  const employer = roster.getByRole('button', { expanded: false }).first();
  await employer.focus();
  await page.keyboard.press('Enter');

  const role = roster.locator('ul ul button').first();
  await role.focus();
  await page.keyboard.press('Enter');

  await expect(page.getByTestId('city-detail')).toBeVisible({ timeout: 15_000 });
  // And it reached the scene, not just the panel: the reticle is on the city.
  await expect
    .poll(async () => (await selectionState(page)).at !== null, { timeout: 15_000 })
    .toBe(true);
});

test('the reticle moves with the field when the ordering changes', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);

  const beacon = await findBeacon(page);
  await page.mouse.click(beacon.x, beacon.y);
  await expect
    .poll(async () => (await selectionState(page)).selected, { timeout: 15_000 })
    .toBe(beacon.jobId);
  const before = await selectionState(page);

  await page.getByRole('radio', { name: 'Openings' }).click();

  // Every sort reorders the columns. A reticle written once at selection time
  // stays where it was and ends up ringing whichever employer now stands
  // there — right count, right role selected, wrong beacon marked.
  await expect
    .poll(
      async () => {
        const after = await selectionState(page);
        return after.selected === beacon.jobId && after.at !== null;
      },
      { timeout: 15_000 },
    )
    .toBe(true);

  const after = await selectionState(page);
  const placement = await page.evaluate(
    ([key, jobId]) => {
      const signals = window[key as typeof CITY_DEBUG_KEY]!;
      for (let i = 0; i < signals.signals.drawn; i += 1) {
        if (signals.signals.jobAt(i) === jobId) return signals.signals.altitudeOf(i);
      }
      return null;
    },
    [CITY_DEBUG_KEY, beacon.jobId] as const,
  );
  // Read back from the buffer rather than recomputed: the reticle is on the
  // instance the layer actually drew for this role.
  expect(after.at?.[2]).toBe(placement);
  expect(before.at).not.toBeNull();
});

/**
 * §6's treatments, in a real browser against the seeded applications.
 *
 * The unit tests prove the buffers hold the right colours and counts. What they
 * cannot see is the whole chain in one piece: two fetches landing in either
 * order, the treatment map reaching the store, the layer picking it up outside
 * React, and the archive toggle removing a role from both the field and the
 * list. Every one of those seams is a place where a mark can be right in a
 * buffer and absent from the city.
 */

/** What §6 has actually put on the city right now. */
async function marksOnCity(page: Page) {
  return page.evaluate((key) => {
    const city = window[key as typeof CITY_DEBUG_KEY]!;
    return { ...city.signals.marks, drawn: city.signals.drawn };
  }, CITY_DEBUG_KEY);
}

async function cityHasMarks(page: Page) {
  await expect
    .poll(
      async () => {
        const marks = await marksOnCity(page);
        return marks.outline + marks.core + marks.ring + marks.beam;
      },
      { timeout: 30_000, message: 'no §6 mark ever reached the city — is the seed tracking any?' },
    )
    .toBeGreaterThan(0);
}

test('the seeded applications reach the skyline as §6 marks', async ({ page }) => {
  await openCity(page);
  await cityHasSignals(page);
  await cityHasMarks(page);

  const marks = await marksOnCity(page);
  // One application at each stage the city draws: saved is an outline, applied
  // and offer share the core mesh, interview is the arc.
  expect(marks.outline).toBeGreaterThan(0);
  expect(marks.core).toBeGreaterThan(1);
  expect(marks.ring).toBeGreaterThan(0);
});

test('an archived role is off the city and out of the list, until it is asked for', async ({
  page,
}) => {
  await openCity(page);
  await cityHasSignals(page);
  await cityHasMarks(page);

  const hidden = await marksOnCity(page);

  await page.getByRole('button', { name: /what the marks mean/i }).click();
  const toggle = page.getByRole('checkbox', { name: /rejected and withdrawn/i });
  await expect(toggle).not.toBeChecked();
  await toggle.check();

  // §6 keeps rejections off the skyline by default and the toggle puts them
  // back — in the buffer, not only in a React list.
  await expect
    .poll(async () => (await marksOnCity(page)).drawn, { timeout: 15_000 })
    .toBe(hidden.drawn + 1);
});

test('the city stops moving under prefers-reduced-motion', async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' });
  const page = await context.newPage();
  await openCity(page);
  await cityHasSignals(page);

  // Every pulse is a zero in the instance buffer rather than a uniform the
  // shader ignores, so this is the data saying it is still — not a flag
  // claiming it while the city animates anyway.
  await expect
    .poll(
      () =>
        page.evaluate((key) => {
          const city = window[key as typeof CITY_DEBUG_KEY]!;
          return city.signals.animating;
        }, CITY_DEBUG_KEY),
      { timeout: 15_000 },
    )
    .toBe(false);
  expect(
    await page.evaluate(
      (key) => window[key as typeof CITY_DEBUG_KEY]!.signals.pulseAt(0),
      CITY_DEBUG_KEY,
    ),
  ).toBe(0);

  await context.close();
});

test('the legend documents every row of §6, including the ones it cannot draw', async ({
  page,
}) => {
  await openCity(page);
  await cityHasSignals(page);

  await page.getByRole('button', { name: /what the marks mean/i }).click();

  // PRODUCT-SPEC §4.3's last line is a deliverable. The undrawable rows are the
  // half that is easy to quietly omit, and omitting them would document the
  // renderer rather than the language.
  await expect(page.getByText('New internship')).toBeVisible();
  await expect(page.getByText('Approximate location')).toBeVisible();
  await expect(page.getByText(/Not drawn on this city/).first()).toBeVisible();
});

/**
 * The hardest edge of "the list and the map cannot disagree", and the one Task
 * 5 created.
 *
 * §6 keeps rejected and withdrawn roles off the city by default. That gives the
 * interface a state it did not have before: a role that is **selected and not
 * drawn** — reachable by a link somebody sent you, or by rejecting a role while
 * its panel is open. Three things could disagree about it and each would be a
 * different bug. The panel could describe a role as though it were on screen.
 * The reticle could be left ringing whichever beacon now stands where that role
 * used to. The toggle could put the beacon back without the reticle following
 * it.
 *
 * All three are one assertion here because they are one piece of state: the
 * panel, the roster and the layer all read `selected` and all filter through
 * `visibleSignalsOf`.
 */
async function archivedJobId(): Promise<string> {
  const archived = await archivedJobIds();
  const [first] = [...archived];
  expect(first, 'the seed has no archived application — §6 has nothing to hide').toBeDefined();
  return first!;
}

test('a selected role that §6 is hiding says so, and the reticle is not on somebody else', async ({
  page,
}) => {
  const jobId = await archivedJobId();

  await page.goto(`/explore/city?job=${jobId}`);
  await expect(page.getByRole('button', { name: 'Reset view' })).toBeVisible({ timeout: 60_000 });
  await cityHasSignals(page);

  // The panel opens, and it is the panel for that role — not the "not on this
  // city" card, which would be the wrong sentence: the role is in the corpus.
  const panel = page.getByTestId('city-detail');
  await expect(panel).toBeVisible({ timeout: 15_000 });
  await expect(panel).toContainText(/hidden unless you ask for it/i);

  // Selected, and deliberately unmarked. A reticle drawn at the origin, or left
  // on the beacon that now occupies that place in the field, is a right answer
  // in the panel and a wrong one on the canvas.
  await expect
    .poll(async () => (await selectionState(page)).selected, { timeout: 15_000 })
    .toBe(jobId);
  expect((await selectionState(page)).at).toBeNull();

  const hidden = await marksOnCity(page);
  expect(await drawnJobIds(page)).not.toContain(jobId);

  // Ask for it, and both sides move together.
  await page.getByRole('button', { name: /what the marks mean/i }).click();
  await page.getByRole('checkbox', { name: /rejected and withdrawn/i }).check();

  await expect
    .poll(async () => (await marksOnCity(page)).drawn, { timeout: 15_000 })
    .toBe(hidden.drawn + 1);
  expect(await drawnJobIds(page)).toContain(jobId);
  await expect
    .poll(async () => (await selectionState(page)).at, { timeout: 15_000 })
    .not.toBeNull();
});

/** Every role the instance buffer is currently holding, by id. */
async function drawnJobIds(page: Page): Promise<string[]> {
  return page.evaluate((key) => {
    const signals = window[key as typeof CITY_DEBUG_KEY]!.signals;
    const ids: string[] = [];
    for (let i = 0; i < signals.drawn; i += 1) {
      const id = signals.jobAt(i);
      if (id !== null) ids.push(id);
    }
    return ids;
  }, CITY_DEBUG_KEY);
}
