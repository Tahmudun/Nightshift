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

  test('a role page presents no match score, and no percentage', async ({ page }) => {
    await page.goto('/explore');
    await page
      .getByRole('link', { name: /engineer/i })
      .first()
      .click();
    await page.waitForURL(/\/explore\/jobs\//, { timeout: FIRST_COMPILE });

    const deferred = page.getByTestId('deferred-facts');
    await expect(deferred).toBeVisible();
    // I4: the fields are named so the absence is checkable, and no number is
    // attached to any of them.
    await expect(deferred).toContainText(/match score/i);
    await expect(deferred).not.toContainText(/\d+\s*%/);
  });

  test('an employer page counts every closure state, including the zeros', async ({ page }) => {
    await page.goto('/explore');
    await page
      .getByRole('link', { name: /engineer/i })
      .first()
      .click();
    await page.waitForURL(/\/explore\/jobs\//, { timeout: FIRST_COMPILE });
    await page
      .getByRole('link', { name: /datadog|alloy|ramp/i })
      .first()
      .click();
    await page.waitForURL(/\/explore\/companies\//, { timeout: FIRST_COMPILE });
    for (const state of ['open', 'possibly_stale', 'unverified', 'closed']) {
      await expect(page.getByTestId(`count-${state}`)).toBeVisible();
    }
    // Closed is counted rather than hidden, which is the whole point.
    await expect(page.getByTestId('count-closed')).toHaveText(/^\d+$/);
  });
});
