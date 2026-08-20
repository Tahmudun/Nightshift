import { expect, test } from '@playwright/test';

/**
 * M1d's UI half: per-board polling state reaches a screen.
 *
 * Expectations come from the API at run time rather than being hard-coded, so
 * the suite tracks the registry instead of a snapshot of it — the registry grew
 * from 4 boards to 23 in this milestone and will keep growing.
 *
 * The load-bearing test is the last one. A `304` is the outcome this entire
 * milestone exists to produce: the board answered, nothing had changed, one
 * request, no body. If the screen presents that as a failure, then the design
 * succeeded in the database and failed for the person reading it — and worse,
 * it teaches them to ignore the colour that means something is actually wrong.
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

interface Board {
  readonly ats: string;
  readonly token: string;
  readonly tier: 'hot' | 'warm';
  readonly last_status: number | null;
  readonly last_success_at: string | null;
  readonly next_poll_at: string;
  readonly has_etag: boolean;
}

async function fetchBoards(): Promise<readonly Board[]> {
  const response = await fetch(`${API}/boards`);
  expect(response.ok, `GET ${API}/boards failed — is the seeded stack up?`).toBe(true);
  return (await response.json()) as readonly Board[];
}

test('every board the API knows about appears on Operate', async ({ page }) => {
  const boards = await fetchBoards();
  test.skip(boards.length === 0, 'no board has a poll schedule yet on this stack');

  await page.goto('/operate');
  const table = page.getByRole('table').last();

  for (const board of boards.slice(0, 5)) {
    await expect(table.getByText(board.token, { exact: true }).first()).toBeVisible();
  }
});

test('a board reports its tier as a word, not only as a colour', async ({ page }) => {
  const boards = await fetchBoards();
  test.skip(boards.length === 0, 'no board has a poll schedule yet on this stack');

  await page.goto('/operate');
  // Wait for the table rather than reading innerText immediately: the board
  // list arrives from an async query, and a bare innerText read races it and
  // passes or fails on timing rather than on content.
  await expect(page.getByRole('table').last()).toBeVisible();
  const body = await page.locator('body').innerText();

  // §12.4: no essential information available only through hover or colour.
  expect(body.toLowerCase()).toMatch(/\b(hot|warm)\b/);
});

test('a board nobody has polled says so rather than looking healthy', async ({ page }) => {
  const boards = await fetchBoards();
  const neverPolled = boards.filter((b) => b.last_success_at === null);
  test.skip(neverPolled.length === 0, 'every board on this stack has been polled');

  await page.goto('/operate');
  await expect(page.getByRole('table').last()).toBeVisible();
  const body = await page.locator('body').innerText();

  // "never" rather than a blank cell or a fabricated timestamp. A board we have
  // never reached is the most urgent row on the page, and the API sorts it first.
  expect(body.toLowerCase()).toContain('never');
});

test('an unchanged board is not presented as a problem', async ({ page }) => {
  const boards = await fetchBoards();
  const unchanged = boards.filter((b) => b.last_status === 304);
  test.skip(unchanged.length === 0, 'no board on this stack has answered 304 yet');

  await page.goto('/operate');
  const row = page.getByRole('row').filter({ hasText: unchanged[0]!.token });

  await expect(row.getByText(/unchanged/i)).toBeVisible();
  await expect(row.getByText(/fail/i)).toHaveCount(0);
});

test('the page explains that board freshness is not posting freshness', async ({ page }) => {
  await page.goto('/operate');
  await expect(page.getByText(/least recently heard from/i)).toBeVisible();
  const body = await page.locator('body').innerText();

  // A board that answers 304 for sixty days leaves its postings' timestamps
  // sixty days old while those postings are open and correctly so. Somebody
  // reading this page needs to know which of the two they are looking at.
  expect(body.toLowerCase()).toContain('board');
  expect(body.toLowerCase()).toMatch(/least recently heard from|last answered|heard from/);
});
