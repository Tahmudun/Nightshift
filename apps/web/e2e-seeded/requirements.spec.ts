import { expect, test } from '@playwright/test';

/**
 * M3a in a browser: a posting's requirements, shown in the posting's own words.
 *
 * The load-bearing test is the second one. Anything can render a list of
 * technologies; what this milestone claims is that **every claim on the page is
 * a literal quote from the description printed on the same page**, and that is
 * only checkable by taking the rendered quote and looking for it in the
 * rendered description. A component that summarised, rephrased, or rebuilt the
 * sentence from the normalized value would pass every other assertion here.
 *
 * This test writes nothing. It picks a job from the seeded corpus at run time
 * rather than naming a UUID — the seed has been reshaped in three milestones so
 * far — so there is nothing to normalise on entry and nothing left behind on
 * exit. State the property, then check it: this file is read-only against the
 * stack, which is why it can run in any order and any number of times.
 */

/**
 * The API, reached through the web app's own origin (M5b, ADR 0037).
 *
 * Was `http://127.0.0.1:8000`. It moved because the API now requires a session
 * and the session is a first-party cookie on `localhost:3000` — a request
 * straight to the API's own host would carry no cookie and get a 401. Going
 * through the rewrite is also the path the browser takes, so these setup calls
 * and the pages they set up for now agree about what they are talking to.
 */
const API = '/api/ns';

/** `next dev` compiles a dynamic route on first request (see search-and-detail.spec.ts). */
const FIRST_COMPILE = 30_000;

interface Requirement {
  kind: string;
  value: string;
  raw_text: string;
  char_start: number;
  char_end: number;
  necessity: string;
  has_equivalence: boolean;
}

interface JobDetail {
  id: string;
  description_text: string | null;
  requirements: Requirement[];
  requirements_extractor_version: string | null;
}

/**
 * A seeded job carrying `wanted`, chosen from the API rather than hardcoded.
 *
 * Returns null when no posting has that *shape*, so a test can skip with a
 * reason — a corpus that stops containing a shape is a fact about the corpus,
 * not a broken feature.
 *
 * It throws when the corpus is empty, which is a different thing entirely.
 * Without that line every test in this file skips green against an unseeded
 * stack, and the whole suite reports success having checked nothing. This
 * project has shipped that failure once already: M2a's first filter timing was
 * measured against zero jobs and produced five plausible numbers.
 */
async function findJob(wanted: (job: JobDetail) => boolean): Promise<JobDetail | null> {
  const list = (await (await fetch(`${API}/jobs?limit=100`)).json()) as {
    items: { id: string }[];
    total: number;
  };
  if (list.total === 0) {
    throw new Error('the seeded corpus is empty — run `make seed` before this suite');
  }
  for (const item of list.items) {
    const detail = (await (await fetch(`${API}/jobs/${item.id}`)).json()) as JobDetail;
    if (wanted(detail)) return detail;
  }
  return null;
}

const hasRequired = (job: JobDetail) =>
  job.requirements.some((r) => r.necessity === 'required' && r.kind === 'technology');

test.describe('what a posting requires', () => {
  test('the required section names a technology the posting asks for', async ({ page }) => {
    const job = await findJob(hasRequired);
    test.skip(job === null, 'no seeded posting states a required technology');

    await page.goto(`/explore/jobs/${job!.id}`);
    const section = page.getByRole('region', { name: /^required$/i });
    await expect(section).toBeVisible({ timeout: FIRST_COMPILE });

    const expected = job!.requirements.find(
      (r) => r.necessity === 'required' && r.kind === 'technology',
    )!;
    await expect(section).toContainText(expected.value);
  });

  test('every claim on the page is a quote from the description on the page', async ({ page }) => {
    // The criterion, not a proxy for it.
    const job = await findJob(hasRequired);
    test.skip(job === null, 'no seeded posting states a required technology');

    await page.goto(`/explore/jobs/${job!.id}`, { timeout: FIRST_COMPILE });
    await expect(page.getByRole('region', { name: /^required$/i })).toBeVisible({
      timeout: FIRST_COMPILE,
    });

    // The description as the reader sees it, whitespace-collapsed so a quote
    // spanning a line break still matches. Collapsing both sides is what makes
    // this a test of the words rather than of the layout.
    const collapse = (s: string) => s.replace(/\s+/g, ' ').trim();
    const description = collapse(await page.getByTestId('job-description').innerText());
    expect(description.length).toBeGreaterThan(0);

    const quotes = await page.getByTestId('requirement-quote').allInnerTexts();
    expect(quotes.length).toBeGreaterThan(0);
    for (const quote of quotes) {
      expect(description).toContain(collapse(quote));
    }
  });

  test('a preferred technology is not presented as required', async ({ page }) => {
    const job = await findJob(
      (j) =>
        hasRequired(j) &&
        j.requirements.some((r) => r.necessity === 'preferred' && r.kind === 'technology'),
    );
    test.skip(job === null, 'no seeded posting states both a required and a preferred technology');

    // A value the posting lists under both headings proves nothing either way,
    // so the check is only meaningful on one that appears under exactly one.
    const required = new Set(
      job!.requirements.filter((r) => r.necessity === 'required').map((r) => r.value),
    );
    const preferredOnly = job!.requirements.find(
      (r) => r.necessity === 'preferred' && r.kind === 'technology' && !required.has(r.value),
    );
    test.skip(preferredOnly === undefined, 'every preferred technology is also required here');

    await page.goto(`/explore/jobs/${job!.id}`, { timeout: FIRST_COMPILE });
    const section = page.getByRole('region', { name: /^required$/i });
    await expect(section).toBeVisible({ timeout: FIRST_COMPILE });
    await expect(section).not.toContainText(preferredOnly!.value);
    await expect(page.getByRole('region', { name: /^preferred$/i })).toContainText(
      preferredOnly!.value,
    );
  });

  test('the page names the rules behind the rows', async ({ page }) => {
    const job = await findJob((j) => j.requirements.length > 0);
    test.skip(job === null, 'no seeded posting has any requirements');

    await page.goto(`/explore/jobs/${job!.id}`, { timeout: FIRST_COMPILE });
    await expect(page.getByText(job!.requirements_extractor_version!)).toBeVisible({
      timeout: FIRST_COMPILE,
    });
  });
});
