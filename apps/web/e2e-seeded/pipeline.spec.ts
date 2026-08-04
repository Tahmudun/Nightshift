import { expect, test, type Page } from '@playwright/test';

/**
 * M2's headline acceptance criterion, walked in a browser:
 *
 *   "full discover→save→apply→track loop works with zero 3D"
 *
 * This test IS the criterion, not a proxy for it.
 *
 * Two things about running it against a shared seeded stack:
 *
 * 1. It must be idempotent across runs. The corpus is the developer's own
 *    database, so a job saved by yesterday's run is still saved today. Every
 *    assertion below is about the END state, never about the transition from
 *    empty.
 * 2. It runs serially and picks its job by offset, so two tests in this file
 *    never contend for the same role.
 *
 * The plan's version of this file archived on the way out and then could not
 * recover on the next run: an archived application is excluded from the
 * pipeline list by default and refuses every mutation until it is restored.
 * So each test *begins* by restoring whatever it finds, and the archive step
 * is asserted and then undone. The end state is a restored application, which
 * is a state the next run can start from.
 */

test.describe.configure({ mode: 'serial' });

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

/** `next dev` compiles a dynamic route on first request (see search-and-detail.spec.ts). */
const FIRST_COMPILE = 30_000;

/**
 * Every stage label the tracked-chip can carry. Listed in full rather than as
 * the handful this file expects, so a run that finds a role in an unexpected
 * stage reports that instead of timing out on a locator that never matches.
 */
const STAGE_CHIP =
  /^(discovered|saved|preparing|applied|assessment|interview|offer|rejected|withdrawn|closed)( · archived)?$/i;

async function jobAt(offset: number): Promise<{ id: string; title: string }> {
  const response = await fetch(`${API}/jobs?limit=1&offset=${offset}&status=open`);
  const body = (await response.json()) as { items: { id: string; title: string }[] };
  expect(body.items.length, 'the seeded corpus has fewer jobs than this test needs').toBe(1);
  return body.items[0]!;
}

/**
 * Open a job, save it if it is not already tracked, and land on its
 * application page with the application in a restored (non-archived) state.
 */
async function openApplication(page: Page, job: { id: string; title: string }): Promise<void> {
  await page.goto(`/explore/jobs/${job.id}`);
  await expect(page.getByRole('heading', { name: job.title })).toBeVisible({
    timeout: FIRST_COMPILE,
  });

  // The save control renders an inert placeholder until it knows whether this
  // job is already tracked. Asking `isVisible()` before then answers "no" for
  // a button that is about to appear, the click is skipped, and the test then
  // waits for a chip that will never come. Settle first, then decide.
  const save = page.getByRole('button', { name: /^save$/i });
  const chip = page.getByRole('link', { name: STAGE_CHIP });
  await expect(save.or(chip).first()).toBeVisible({ timeout: FIRST_COMPILE });

  if (await save.isVisible()) {
    await save.click();
  }
  // End-state assertion: whether this run saved it or a previous one did, the
  // control now reports a stage rather than offering to save.
  await expect(chip).toBeVisible();
  await chip.click();

  await expect(page.getByTestId('current-stage')).toBeVisible({ timeout: FIRST_COMPILE });
  const restore = page.getByRole('button', { name: /^restore$/i });
  if (await restore.isVisible()) {
    await restore.click();
    await expect(page.getByRole('button', { name: /^archive$/i })).toBeVisible();
  }

  // Normalise the stage rather than trusting the previous run to have cleaned
  // up after itself. A test that only survives its own tidy exit is a test
  // that fails the first time somebody interrupts it — and the developer's
  // database is shared with whatever they were doing by hand.
  if (!/saved/i.test((await page.getByTestId('current-stage').textContent()) ?? '')) {
    await page.getByLabel('Stage').selectOption('saved');
    await page.getByRole('button', { name: /set stage/i }).click();
    await expect(page.getByTestId('current-stage')).toContainText(/saved/i);
  }
}

test('discover, save, apply, track — the whole loop', async ({ page }) => {
  const job = await jobAt(0);
  await openApplication(page, job);

  // -- apply: we record it, we never submit it -----------------------------
  // Invariant I5, asserted in the browser: there is no control that applies.
  await expect(page.getByRole('button', { name: /^apply$/i })).toHaveCount(0);

  const applied = page.getByRole('button', { name: /i applied/i });
  if (await applied.isVisible()) {
    await applied.click();
  }
  await expect(page.getByTestId('current-stage')).toContainText(/applied/i);

  // Once applied, the posting link is the recorded URL and it opens elsewhere.
  const posting = page.getByRole('link', { name: /open the posting/i });
  if (await posting.isVisible()) {
    await expect(posting).toHaveAttribute('target', '_blank');
    await expect(posting).toHaveAttribute('rel', /noreferrer/);
  }

  // -- track: a note, and a stage change ------------------------------------
  const note = `checked at ${new Date().toISOString()}`;
  await page.getByLabel('Note').fill(note);
  await page.getByRole('button', { name: /add note/i }).click();
  await expect(page.getByText(note)).toBeVisible();

  await page.getByLabel('Stage').selectOption('interview');
  await page.getByRole('button', { name: /set stage/i }).click();
  await expect(page.getByTestId('current-stage')).toContainText(/interview/i);

  // The history holds every step, and each transition is labelled with its
  // class rather than presented as a bare move.
  const history = page.getByRole('list', { name: /history/i });
  await expect(history.getByText(/saved/i).first()).toBeVisible();
  await expect(history.getByText(/^(correction|advance|reopen)$/i).first()).toBeVisible();

  // -- archive is real, and reversible --------------------------------------
  await page.getByRole('button', { name: /^archive$/i }).click();
  await expect(page.getByText(/archived/i).first()).toBeVisible();
  await page.getByRole('button', { name: /^restore$/i }).click();
  await expect(page.getByRole('button', { name: /^archive$/i })).toBeVisible();

  // -- leave it where it was found ------------------------------------------
  // The run must end in the state it began in, or the next run takes a
  // different path through the page: "I applied" is hidden at `interview`, so
  // a second run would assert `applied` against a stage of `interview`. That
  // is exactly what happened on the first attempt at running this file twice.
  //
  // The reset is not only cleanup — `interview -> saved` is a backward move,
  // and the history must record it as a correction rather than refuse it.
  await page.getByLabel('Stage').selectOption('saved');
  await page.getByRole('button', { name: /set stage/i }).click();
  await expect(page.getByTestId('current-stage')).toContainText(/saved/i);
  await expect(history.getByText(/^correction$/i).first()).toBeVisible();
});

test('history cannot be rewritten from the UI', async ({ page }) => {
  const job = await jobAt(1);
  await openApplication(page, job);

  // No edit and no delete anywhere in the history. The trigger refuses both at
  // the database, and the UI must not offer what the database will refuse.
  const history = page.getByRole('list', { name: /history/i });
  await expect(history.getByRole('button', { name: /edit|delete|remove/i })).toHaveCount(0);
  await expect(page.getByText(/there is no delete/i)).toBeVisible();
});

test('the application page names what tracking cannot record yet', async ({ page }) => {
  const job = await jobAt(1);
  await openApplication(page, job);

  // I7, the same practice /analyze/coverage and the M2a filter panel follow.
  const deferred = page.getByTestId('deferred-tracking');
  await expect(deferred).toContainText(/contacts/i);
  await expect(deferred).toContainText(/M3/);

  // "Selected resume" left this list when M2c shipped it. A deferred entry for
  // a feature that exists is the same lie as a hidden one, in reverse — and
  // this test is what caught the list still claiming it.
  await expect(deferred).not.toContainText(/resume/i);
});

test('the pipeline shows the tracked roles and states its archived count', async ({ page }) => {
  await page.goto('/operate/pipeline');
  await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible({
    timeout: FIRST_COMPILE,
  });
  // Archived rows are counted in the open rather than silently omitted (A7).
  await expect(page.getByRole('button', { name: /archived \(\d+\)/i })).toBeVisible();
  await expect(page.getByText(/nothing here moves on its own/i)).toBeVisible();
});
