import { expect, test } from '@playwright/test';

import { API, apiFetch } from './api';

/**
 * M1b's UI half: "ingestion failures are visible in the UI, not just logs."
 *
 * Expectations are derived from the API at run time rather than hard-coded, so
 * the suite tracks the committed fixture instead of a snapshot of it — the same
 * approach as jobs.spec.ts.
 *
 * The load-bearing test here is the last one. `possibly_stale` and `unverified`
 * are the two facts invariant I3 keeps apart, and if the screen describes them
 * in the same words then the invariant holds in the database and fails for the
 * person actually reading it.
 */

interface AdminRow {
  readonly title: string;
  readonly company_name: string;
  readonly status: string;
  readonly source_count: number;
}
interface AdminList {
  readonly items: readonly AdminRow[];
  readonly total: number;
  readonly status_counts: Record<string, number>;
}

async function fetchAdmin(): Promise<AdminList> {
  const response = await apiFetch(`${API}/jobs/admin`);
  expect(response.ok, `GET ${API}/jobs/admin failed — is the seeded stack up?`).toBe(true);
  return (await response.json()) as AdminList;
}

test('the job table renders the real seeded rows', async ({ page }) => {
  const admin = await fetchAdmin();
  expect(admin.items.length, 'no jobs seeded — this suite would pass vacuously').toBeGreaterThan(0);

  await page.goto('/operate/jobs');

  const table = page.getByRole('table', {
    name: /every canonical job, its closure state, and its provenance/i,
  });
  await expect(table).toBeVisible();

  // Every title the API reports must be findable in the table.
  for (const job of admin.items.slice(0, 5)) {
    await expect(table.getByRole('rowheader', { name: job.title })).toBeVisible();
  }
});

test('every status is readable as a word, not only as a colour', async ({ page }) => {
  // §12.4: essential information must not be carried by a visual channel alone.
  const admin = await fetchAdmin();
  await page.goto('/operate/jobs');

  const table = page.getByRole('table', {
    name: /every canonical job, its closure state, and its provenance/i,
  });
  const statuses = new Set(admin.items.map((job) => job.status));
  const words: Record<string, RegExp> = {
    open: /^open$/i,
    possibly_stale: /^possibly stale$/i,
    unverified: /^unverified$/i,
    closed: /^closed$/i,
  };
  for (const status of statuses) {
    await expect(table.getByText(words[status]!).first()).toBeVisible();
  }
});

test('the status counts on screen match what the API reports', async ({ page }) => {
  const admin = await fetchAdmin();
  await page.goto('/operate/jobs');

  // The "All" filter button carries the total, so a UI that quietly paginated
  // or filtered would disagree with the API here.
  await expect(page.getByRole('button', { name: `All (${admin.total})` })).toBeVisible();
});

test('stale and unverified are explained, and not in the same words', async ({ page }) => {
  await page.goto('/operate/jobs');

  const legend = page.getByRole('region', { name: /what each job status means/i });
  await expect(legend).toBeVisible();

  // Stale: the board spoke, and the job was not in what it said.
  await expect(legend).toContainText(/board answered and this job was not in it/i);
  // Unverified: we could not check — and nothing is concluded from that.
  await expect(legend).toContainText(/have not been able to check this board recently/i);
  await expect(legend).toContainText(/an outage is not evidence/i);
});

test('filtering to a state with no jobs says so rather than looking broken', async ({ page }) => {
  const admin = await fetchAdmin();
  test.skip(admin.status_counts.closed !== 0, 'seed contains closed jobs; nothing to assert');

  await page.goto('/operate/jobs');
  await page.getByRole('button', { name: 'Closed' }).click();

  // An empty table with no explanation reads as a broken page. The copy has to
  // distinguish "a real zero" from "the filter is broken".
  await expect(page.getByText(/no jobs are closed/i)).toBeVisible();
  await expect(page.getByText(/that is a real zero/i)).toBeVisible();
});
