import { expect, test } from '@playwright/test';

/**
 * M0 acceptance criterion 5: "One real Greenhouse board's jobs appear in the
 * browser."
 *
 * The suite in `e2e/` deliberately runs with no API behind it, so it proves the
 * app degrades honestly but says nothing about real data ever reaching a screen.
 * This file is the other half. It requires a seeded stack — `make up && make
 * migrate && make seed` — and it fails loudly rather than skipping if that stack
 * is absent, because a test that quietly skips is a test that asserts nothing.
 *
 * Every expectation is derived from the API at run time instead of hard-coded, so
 * the suite tracks the committed fixture rather than a snapshot of it.
 */

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface Location {
  readonly raw_text: string;
  readonly location_confidence: string;
  readonly latitude: number | null;
  readonly longitude: number | null;
}
interface Job {
  readonly title: string;
  readonly company: { readonly canonical_name: string };
  readonly locations: readonly Location[];
}

/** The `sources.name` and `sources.source_type` M5a gives every capture. */
const CAPTURED = 'manual_capture';

interface Capture {
  readonly status: string;
  readonly job_id: string | null;
}
interface Stats {
  readonly total_jobs: number;
  readonly mappable_locations: number;
  readonly location_confidence: Record<string, number>;
}

async function api<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) {
    throw new Error(
      `${API}${path} returned ${response.status}. This suite needs a seeded stack: ` +
        `run \`make up && make migrate && make seed\` first.`,
    );
  }
  return (await response.json()) as T;
}

test.describe('seeded corpus in the browser', () => {
  test('a real Greenhouse posting is rendered with its company', async ({ page }) => {
    const { items } = await api<{ items: Job[] }>('/jobs?limit=100');
    expect(items.length, 'the seeded database must contain jobs').toBeGreaterThan(0);

    await page.goto('/explore');

    const first = items[0]!;
    await expect(page.getByRole('heading', { name: first.title, level: 3 })).toBeVisible();
    await expect(page.getByText(first.company.canonical_name).first()).toBeVisible();

    // Not just one row: the list must render the corpus, not a single lucky item.
    const headings = page.getByRole('article').getByRole('heading', { level: 3 });
    await expect
      .poll(async () => headings.count(), { message: 'job rows rendered' })
      .toBeGreaterThan(1);
  });

  test('every rendered location carries a confidence from the I1 vocabulary', async ({ page }) => {
    await page.goto('/explore');

    // Wait for the client fetch to land before counting.
    await expect(page.getByRole('article').first()).toBeVisible();

    // Scoped to job rows on purpose. The ConfidenceLegend renders the same
    // ladder component for all five levels to document the visual language, so
    // an unscoped query would be asserting against the legend, not the data.
    const ladders = page.getByRole('article').getByRole('img', {
      name: /^Location confidence:/,
    });
    const count = await ladders.count();
    expect(count, 'locations must render a confidence ladder').toBeGreaterThan(0);

    const allowed = ['Verified', 'Approximate', 'City only', 'Remote', 'Unknown'];
    for (let index = 0; index < count; index += 1) {
      const label = await ladders.nth(index).getAttribute('aria-label');
      expect(label, 'every ladder needs an accessible label').toBeTruthy();
      // "Location confidence: City only, 3 of 5. <meaning>"
      const level = label!.replace('Location confidence: ', '').split(',')[0]!;
      expect(allowed, `unrecognised confidence "${level}"`).toContain(level);
    }
  });

  test('nothing on screen claims a precision M0 has not earned (I1)', async ({ page }) => {
    const stats = await api<Stats>('/stats');
    // Guard the guard: if the fixture ever does contain geocoded rows, this test
    // must be rewritten rather than silently passing on a false premise.
    expect(stats.mappable_locations, 'M0 geocodes nothing').toBe(0);
    expect(stats.location_confidence['verified']).toBe(0);
    expect(stats.location_confidence['approximate']).toBe(0);

    await page.goto('/explore');
    await expect(page.getByRole('article').first()).toBeVisible();

    // Job rows only — the legend legitimately shows all five levels.
    const ladders = page.getByRole('article').getByRole('img', {
      name: /^Location confidence:/,
    });
    const count = await ladders.count();
    expect(count, 'there must be ladders to check').toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      const label = await ladders.nth(index).getAttribute('aria-label');
      // The legend documents all five levels; a *job's* ladder must not.
      expect(label, 'a job location claimed verified placement in M0').not.toContain(
        'Verified, 5 of 5',
      );
      expect(label, 'a job location claimed approximate placement in M0').not.toContain(
        'Approximate, 4 of 5',
      );
    }

    // Proof this test is capable of failing: the same aria-label string it
    // rejects above does exist on the page, in the legend, where it belongs.
    // Without this, scoping the query too narrowly would make the assertions
    // above pass by matching nothing at all.
    await expect(
      page.getByRole('img', { name: /Location confidence: Verified, 5 of 5/ }),
    ).toBeVisible();
  });

  test('a multi-location posting renders one row per stated location (A2)', async ({ page }) => {
    const { items } = await api<{ items: Job[] }>('/jobs?limit=100');
    const multi = items.find((job) => job.locations.length > 1);
    expect(multi, 'the fixture must include a multi-location posting').toBeTruthy();

    await page.goto('/explore');
    const article = page
      .getByRole('article')
      .filter({ has: page.getByRole('heading', { name: multi!.title, level: 3 }) });
    await expect(article).toBeVisible();

    for (const location of multi!.locations) {
      await expect(article.getByText(location.raw_text, { exact: true })).toBeVisible();
    }
  });

  test('the fixture source is labelled as a fixture, not as a live feed (I7)', async ({ page }) => {
    await page.goto('/operate');
    await expect(page.getByText('committed fixture').first()).toBeVisible();
  });

  test('the seeded capture is on its job page, badged as added by hand (I7)', async ({ page }) => {
    // M5a. `make seed` pastes one real posting and confirms it, so the capture
    // path is walkable from `make demo` rather than only from a person with
    // something in their clipboard. This is the end of that chain: a job in
    // the corpus, reached the ordinary way, saying out loud that it did not
    // arrive from a poll.
    //
    // The job is found through the API rather than named here, so the test
    // tracks the seed instead of a snapshot of it.
    const { captures, total } = await api<{ captures: Capture[]; total: number }>(
      '/capture?status=confirmed',
    );
    expect(total, 'the seed must plant exactly one confirmed capture — `make seed` prints it').toBe(
      1,
    );
    const jobId = captures[0]!.job_id;
    expect(
      jobId,
      'a confirmed capture carries a job; the schema refuses one that does not',
    ).not.toBeNull();

    await page.goto(`/explore/jobs/${jobId}`);
    await expect(page.getByTestId('captured-badge')).toBeVisible();
    // The sentence is the part that matters more than the badge: a captured
    // posting cannot be closed by the freshness machinery, because nothing
    // ever asks the page it came from a second time.
    await expect(page.getByText(/Nothing re-reads it/)).toBeVisible();
  });

  test('the source health table does not call that capture a live feed (I7)', async ({ page }) => {
    // The badge and this label are two screens describing one source, and
    // until M5a they disagreed: `/operate` had a binary — fixture, or else
    // live — so the first captured posting to reach the seeded corpus was
    // labelled with the same word as `greenhouse`.
    await page.goto('/operate');
    const row = page.getByRole('row').filter({ hasText: CAPTURED });
    await expect(row).toBeVisible();
    await expect(row.getByText('added by hand')).toBeVisible();
    await expect(row.getByText('live', { exact: true })).toHaveCount(0);
  });

  test('the corpus readout reports zero mappable locations rather than hiding it', async ({
    page,
  }) => {
    const stats = await api<Stats>('/stats');
    await page.goto('/analyze');
    await expect(page.getByText(String(stats.total_jobs)).first()).toBeVisible();
    // The honest reading is the default one: the page states it on screen
    // rather than leaving a bare 0 for the reader to interpret.
    //
    // The wording changed at M4a and the change is the point. "Nothing geocoded
    // yet" described a missing feature; a geocoder exists now and the number is
    // still zero because no ATS posting in the corpus names a street. That is a
    // property of the data rather than a gap in the product, and it is the more
    // useful thing to tell somebody looking at a zero.
    await expect(page.getByText('no posting states a street').first()).toBeVisible();
  });
});
