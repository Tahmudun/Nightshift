import { expect, test } from '@playwright/test';

/**
 * M1 acceptance criterion 12: "The coverage page names what is *not* covered,
 * not only what is."
 *
 * That is the criterion, so that is what this file asserts. It deliberately
 * does not check the covered counts — those are `/coverage`'s unit tests' job.
 * What only a browser can prove is that the disclosure actually reaches a
 * screen: present in the DOM, inside a landmark a screen reader announces, and
 * not hidden behind a disclosure widget somebody has to think to open.
 *
 * Expectations come from the API at run time rather than being hard-coded, so
 * the suite tracks the real blind-spot list rather than a snapshot of it.
 */

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface BlindSpot {
  readonly id: string;
  readonly title: string;
  readonly explanation: string;
  readonly count: number | null;
}

async function blindSpots(): Promise<BlindSpot[]> {
  const response = await fetch(`${API}/coverage`);
  expect(response.ok, `GET ${API}/coverage failed — is the API running?`).toBe(true);
  const body = (await response.json()) as { blind_spots: BlindSpot[] };
  expect(
    body.blind_spots.length,
    'a coverage report with no named gaps proves nothing',
  ).toBeGreaterThan(0);
  return body.blind_spots;
}

test('the coverage page names what it does not cover', async ({ page }) => {
  await page.goto('/analyze/coverage');

  const gaps = page.getByRole('region', { name: /what is not covered/i });
  await expect(gaps).toBeVisible();
  await expect(gaps).toContainText(/lever/i);
  await expect(gaps).toContainText(/workday/i);
});

test('every gap the API names actually reaches the page', async ({ page }) => {
  const spots = await blindSpots();
  await page.goto('/analyze/coverage');
  const gaps = page.getByRole('region', { name: /what is not covered/i });

  for (const spot of spots) {
    await expect(gaps, `blind spot "${spot.id}" is missing from the page`).toContainText(
      spot.title,
    );
  }
});

test('a gap of unknowable size says "unknown" rather than showing a zero', async ({ page }) => {
  const spots = await blindSpots();
  const unknown = spots.filter((spot) => spot.count === null);
  expect(
    unknown.length,
    'no null-count gap to check — this test would pass vacuously',
  ).toBeGreaterThan(0);

  await page.goto('/analyze/coverage');
  const gaps = page.getByRole('region', { name: /what is not covered/i });
  await expect(gaps).toContainText(/unknown/i);
});

test('the page never reports a percentage of the market', async ({ page }) => {
  /**
   * There is no denominator. Nobody knows how many tech roles open in New
   * York, so any percentage here would be arithmetic on a number that does not
   * exist — the confident-sounding fabrication the invariants forbid.
   */
  await page.goto('/analyze/coverage');
  const body = await page.locator('body').innerText();
  expect(body).not.toMatch(/\d+(\.\d+)?%/);
});

test('what is not covered is not hidden behind a disclosure widget', async ({ page }) => {
  /**
   * The criterion is that the page *names* the gaps. A section collapsed by
   * default satisfies a DOM check while showing a reader nothing, so assert the
   * text is visible without anyone having to expand anything first.
   */
  await page.goto('/analyze/coverage');
  const gaps = page.getByRole('region', { name: /what is not covered/i });
  await expect(gaps.locator('details')).toHaveCount(0);
  await expect(gaps.getByText(/robots\.txt|CCBot/i).first()).toBeVisible();
});
