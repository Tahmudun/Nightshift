import { expect, test } from '@playwright/test';

/**
 * M2a: search, filters and the two detail pages, against the seeded corpus.
 *
 * Expectations come from the API at run time wherever the number could move,
 * following the convention in operate-boards.spec.ts — the seed grew from 10
 * jobs to 31 during M1a and will grow again.
 *
 * The load-bearing tests are the last three. A filter that silently returns
 * everything looks exactly like a working one, and a detail page that renders
 * an absent field as blank looks exactly like a field the source provided as
 * empty. Both failures are invisible unless something asserts on them.
 */

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

/**
 * The seeded stack runs `next dev`, which compiles a route the first time it is
 * requested. The first navigation into /explore/jobs/[id] therefore pays a
 * multi-second compile that has nothing to do with the product, and the default
 * 5s assertion timeout is not enough for it. Verified by probe: the same click
 * navigates correctly once the route is warm.
 */
const FIRST_COMPILE = 30_000;

async function totalFor(query: string): Promise<number> {
  const response = await fetch(`${API}/jobs?${query}`);
  const body = (await response.json()) as { total: number };
  return body.total;
}

test.describe('search and filters', () => {
  test('a title search narrows the list and survives a reload', async ({ page }) => {
    // Same remedy, same reason as `profile.spec.ts` (milestone-2c review §2.6).
    // Typing calls `router.replace` per change, which under `next dev` is a
    // server round-trip rather than the client-side navigation it is in a
    // build; this test also reloads, paying that cost twice. It passes alone
    // and timed out once in the full suite after M2d added three more tests to
    // the parallel pool. Marked slow rather than trimmed — cutting the reload
    // would remove the assertion that the URL really is the state.
    test.slow();
    const everything = await totalFor('limit=1');
    const narrowed = await totalFor('limit=1&q=engineer');
    expect(narrowed).toBeGreaterThan(0);
    expect(narrowed).toBeLessThan(everything);

    await page.goto('/explore');
    await expect(page.getByText(/showing \d+ of \d+/)).toBeVisible();

    await page.getByLabel(/^search$/i).fill('engineer');
    await expect(page.getByText(new RegExp(`showing \\d+ of ${narrowed}\\b`))).toBeVisible();

    // The URL is the state, so the filter has to survive a reload.
    await expect(page).toHaveURL(/[?&]q=engineer/);
    await page.reload();
    await expect(page.getByLabel(/^search$/i)).toHaveValue('engineer');
    await expect(page.getByText(new RegExp(`showing \\d+ of ${narrowed}\\b`))).toBeVisible();
  });

  test('the description search is opt-in and visibly wider', async ({ page }) => {
    const titleOnly = await totalFor('limit=1&q=engineer');
    const widened = await totalFor('limit=1&q=engineer&include_description=true');
    expect(widened).toBeGreaterThan(titleOnly);

    await page.goto('/explore?q=engineer');
    await expect(page.getByText(new RegExp(`of ${titleOnly}\\b`))).toBeVisible();
    // click(), not check(). The checkbox is controlled by the URL, and the
    // round trip through router.replace is async — check() clicks and then
    // immediately asserts the DOM, catching the input mid-revert.
    await page.getByLabel(/also search descriptions/i).click();
    await expect(page).toHaveURL(/include_description=true/);
    await expect(page.getByText(new RegExp(`of ${widened}\\b`))).toBeVisible();
  });

  test('a city filter returns only roles naming that city', async ({ page }) => {
    await page.goto('/explore');
    await page.getByLabel(/^city$/i).fill('New York');
    const expected = await totalFor('limit=1&city=New York');
    expect(expected).toBeGreaterThan(0);
    await expect(page.getByText(new RegExp(`of ${expected}\\b`))).toBeVisible();
  });

  test('an empty season result says what it hid rather than only that it is empty', async ({
    page,
  }) => {
    // M3b Task 11, and it asserts a defect that was written and then caught.
    //
    // No internship in the seeded corpus states a season in its title, so
    // filtering by Summer returns nothing — and the first version of this page
    // rendered the caveats only in the branch that has rows. The screen said
    // "No roles match these filters" and nothing else: the product asserting
    // there are no summer internships, when the truth is that neither of its
    // internships says when it runs.
    //
    // The assertion is count-agnostic on purpose. It named the singular
    // wording until M5a, when `make seed` planted a second season-less
    // internship (the captured posting) and the caveat correctly pluralised —
    // so a test about *whether the caveat renders at all* went red over a
    // change to how many roles it counts.
    //
    // This is the browser check, because the component test cannot see which
    // branch the real page takes.
    await page.goto('/explore?internship_season=summer');

    await expect(page.getByText(/no roles match these filters/i)).toBeVisible();
    await expect(
      page.getByText(/further internships? (does|do) not say when (it runs|they run)/i),
    ).toBeVisible();
  });

  test('the skill filter states what it is based on, on the page', async ({ page }) => {
    // The condition this filter shipped under, and it is checked where a person
    // would read it rather than only in the component's own test.
    await page.goto('/explore');
    await expect(page.getByText(/0\.861 recall/i)).toBeVisible();
    await expect(page.getByLabel(/^skill$/i)).toBeEnabled();
  });

  test('the filters it will not fake are named on the page, unexpanded', async ({ page }) => {
    await page.goto('/explore');
    // Visible without expanding anything — the same rule the coverage page is
    // held to. A gap behind a disclosure is a gap nobody sees.
    await expect(page.getByText(/which borough it is in/i)).toBeVisible();
    await expect(page.getByText(/no score exists yet/i)).toBeVisible();
    await expect(page.getByLabel(/borough/i)).toBeDisabled();
  });
});

test.describe('detail pages', () => {
  test('a role opens, and names what the source did not provide', async ({ page }) => {
    await page.goto('/explore');
    await page
      .getByRole('link', { name: /engineer/i })
      .first()
      .click();
    await page.waitForURL(/\/explore\/jobs\//, { timeout: FIRST_COMPILE });

    // A10: our observation is labelled as ours, never as "posted".
    await expect(page.getByText(/first seen by nightshift/i)).toBeVisible();
    await expect(page.getByText(/last verified/i)).toBeVisible();
    await expect(page.getByText(/^posted$/i)).toHaveCount(0);
  });

  test('a role page names what it does not compute, with no number on it', async ({ page }) => {
    // **This test used to read `toContainText(/match score/i)`** and it was
    // right when M2a wrote it: the score did not exist and the page said so
    // under "Not yet computed". M3c Task 10 built the score and took it off that
    // list, which made the assertion stale in the one direction a stale
    // assertion is worst — it went on passing until somebody ran the seeded
    // suite again, three tasks later.
    //
    // The claim worth keeping is the one underneath it, and it is I7 rather than
    // I4: whatever this page does not compute is *named*, so a reader can check
    // for the absence, and nothing on that list carries a number that would make
    // it look computed after all.
    await page.goto('/explore');
    await page
      .getByRole('link', { name: /engineer/i })
      .first()
      .click();
    await page.waitForURL(/\/explore\/jobs\//, { timeout: FIRST_COMPILE });

    const deferred = page.getByTestId('deferred-facts');
    await expect(deferred).toBeVisible();
    await expect(deferred).toContainText(/not yet computed/i);
    const named = await deferred.getByRole('listitem').allInnerTexts();
    expect(
      named.length,
      'the section lists nothing, so there is nothing to check for',
    ).toBeGreaterThan(0);
    // No number of any kind beside a thing this page cannot compute — a
    // percentage least of all.
    await expect(deferred).not.toContainText(/\d/);
  });

  test('an employer page counts every closure state, including the zeros', async ({ page }) => {
    await page.goto('/explore');
    await page
      .getByRole('link', { name: /engineer/i })
      .first()
      .click();
    await page.waitForURL(/\/explore\/jobs\//, { timeout: FIRST_COMPILE });
    // The employer link by where it goes, not by who the employer is. This
    // named the three seeded boards until M5a, when `make seed` planted a
    // captured posting from a fourth employer and it happened to sort first
    // among the roles whose title says "engineer" — so the step above landed
    // on a real job page and this one waited thirty seconds for a name that
    // was never going to be there. A corpus this suite reads at run time
    // everywhere else should not be spelled out here.
    await page.locator('a[href^="/explore/companies/"]').first().click();
    await page.waitForURL(/\/explore\/companies\//, { timeout: FIRST_COMPILE });
    for (const state of ['open', 'possibly_stale', 'unverified', 'closed']) {
      await expect(page.getByTestId(`count-${state}`)).toBeVisible();
    }
    // Closed is counted rather than hidden, which is the whole point.
    await expect(page.getByTestId('count-closed')).toHaveText(/^\d+$/);
  });
});
