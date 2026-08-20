import { expect, test, type Page } from '@playwright/test';

/**
 * The daily queue, walked in a browser.
 *
 * The claim under test is not "the page renders". It is that **each row the
 * page shows is true of the data behind it**, and that the rows this system
 * still cannot compute are named rather than drawn empty.
 *
 * Everything here is driven through the product's own controls — the date
 * input, the interview field, the archive button — rather than through the
 * API. A queue populated by direct writes would prove the queries work and
 * nothing about whether a person can reach them.
 *
 * Idempotency, learned from `pipeline.spec.ts`: the corpus is the developer's
 * own database, so this file normalises what it finds on *entry* rather than
 * trusting a previous run's tidy exit. It also clears the dates it sets, so
 * `make acceptance` leaves nothing behind from M2d.
 */

test.describe.configure({ mode: 'serial' });

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

/** `next dev` compiles a dynamic route on first request. */
const FIRST_COMPILE = 30_000;

const STAGE_CHIP =
  /^(discovered|saved|preparing|applied|assessment|interview|offer|rejected|withdrawn|closed)( · archived)?$/i;

/**
 * `pipeline.spec.ts` holds offsets 0 and 1, and these files run in parallel.
 *
 * The two tests below take **different** jobs on purpose. An
 * `interview_scheduled` event is append-only and cannot be deleted, so the
 * interview test's role carries its event forever; if the follow-up test used
 * the same role, its "the row is gone" assertion would fail on the second run
 * of the day. That is precisely the bug M2b's pipeline test shipped and this
 * file is written to avoid.
 */
const FOLLOW_UP_JOB = 2;
const INTERVIEW_JOB = 3;

async function jobAt(offset: number): Promise<{ id: string; title: string }> {
  const response = await fetch(`${API}/jobs?limit=1&offset=${offset}&status=open`);
  const body = (await response.json()) as { items: { id: string; title: string }[] };
  expect(body.items.length, 'the seeded corpus has fewer jobs than this test needs').toBe(1);
  return body.items[0]!;
}

function isoDaysFromNow(days: number): string {
  const when = new Date(Date.now() + days * 86_400_000);
  return when.toISOString();
}

/** Open the job, save it if untracked, land on a restored application page. */
async function openApplication(page: Page, job: { id: string; title: string }): Promise<void> {
  await page.goto(`/explore/jobs/${job.id}`);
  await expect(page.getByRole('heading', { name: job.title })).toBeVisible({
    timeout: FIRST_COMPILE,
  });

  const save = page.getByRole('button', { name: /^save$/i });
  const chip = page.getByRole('link', { name: STAGE_CHIP });
  await expect(save.or(chip).first()).toBeVisible({ timeout: FIRST_COMPILE });
  if (await save.isVisible()) {
    await save.click();
  }
  await expect(chip).toBeVisible();
  await chip.click();

  await expect(page.getByTestId('current-stage')).toBeVisible({ timeout: FIRST_COMPILE });
  const restore = page.getByRole('button', { name: /^restore$/i });
  if (await restore.isVisible()) {
    await restore.click();
    await expect(page.getByRole('button', { name: /^archive$/i })).toBeVisible();
  }
}

/** The section heading, and the list of row links under it. */
function section(page: Page, title: RegExp) {
  return page.getByRole('heading', { name: title });
}

/**
 * One section's container, so an assertion is about *that* list.
 *
 * Every assertion below is scoped this way rather than to the page. A role can
 * legitimately be in two sections at once — a closed listing you also owe a
 * follow-up on — so "this title appears somewhere on the queue" is a much
 * weaker claim than the one these tests intend to make.
 */
function rowsOf(page: Page, key: string) {
  return page.getByTestId(`queue-section-${key}`);
}

test('the queue page names every section and every absence', async ({ page }) => {
  await page.goto('/operate');
  // `.` rather than an apostrophe: the link renders `&rsquo;` (U+2019), and a
  // regex with an ASCII `'` silently matches nothing.
  await page.getByRole('link', { name: /open today.s queue/i }).click();

  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible({
    timeout: FIRST_COMPILE,
  });

  // Every section renders, including the empty ones. An unasked question and
  // an answered one are different, and the page makes both statements.
  await expect(section(page, /^If you do one thing today$/)).toBeVisible();
  await expect(section(page, /^Follow up$/)).toBeVisible();
  await expect(section(page, /^Interviews approaching$/)).toBeVisible();
  await expect(section(page, /^Saved and going quiet$/)).toBeVisible();
  await expect(section(page, /^Closed while you were tracking it$/)).toBeVisible();
  await expect(section(page, /^Gaps on roles you are tracking$/)).toBeVisible();
  await expect(section(page, /^New internships worth a look$/)).toBeVisible();

  // ADR 0019: this row is PRODUCT-SPEC's "resume mismatch warnings" under
  // another name, because it is differenced against confirmed skills and never
  // against an unconfirmed extraction. The word must not appear on it.
  const gaps = rowsOf(page, 'requirement_gaps');
  await expect(gaps).toContainText(/confirmed skills/i);
  await expect(gaps).not.toContainText(/resume/i);

  // M3d Task 7. The section built from a match score says what it is a list of
  // — a row whose ordering a reader cannot see the reason for is a row they
  // have to take on trust, which is what this whole milestone is against.
  await expect(rowsOf(page, 'best_new_internships')).toContainText(
    /first listed in the last \d+ days/i,
  );

  // I7: the rows M3 has not brought, named with their reason and visible
  // without expanding anything. The internship row is deliberately absent from
  // this list now — it is a section above.
  const deferred = page.getByTestId('deferred-queue-rows');
  await expect(deferred).toBeVisible();
  await expect(deferred).not.toContainText(/best new internships/i);
  await expect(deferred).not.toContainText(/resume mismatch warnings/i);
  await expect(deferred).not.toContainText(/one thing to do today/i);
  // The one row M3 does not unblock, and its reason changed with the milestone:
  // the score exists now and the deadlines still do not.
  await expect(deferred).toContainText(/high-match roles closing soon/i);
  await expect(deferred).toContainText(/the sources/i);
  await expect(deferred).not.toContainText(/milestone 3/i);

  // The thresholds are the API's, rendered rather than restated.
  await expect(page.getByTestId('queue-thresholds')).toContainText(/7 days/);
});

test('a due next action puts a role in Follow up, and the row links to it', async ({ page }) => {
  const job = await jobAt(FOLLOW_UP_JOB);
  await openApplication(page, job);
  const applicationUrl = page.url();
  const title = new RegExp(job.title, 'i');

  // Set a next action in the past through the product's own date input. It
  // commits on blur, so the blur is the action rather than a formality.
  const nextAction = page.getByLabel('Next action');
  await nextAction.fill(isoDaysFromNow(-3).slice(0, 10));
  await nextAction.blur();

  await page.goto('/operate/queue');
  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible({
    timeout: FIRST_COMPILE,
  });

  // The row is in Follow up specifically, it names the role, and it says why.
  const row = rowsOf(page, 'follow_up').getByRole('link', { name: title }).first();
  await expect(row).toBeVisible();
  await expect(row).toContainText(/you set a next action for/i);

  // Clicking it lands on the application it is about — the whole point of the
  // page is that every row is a way in.
  await row.click();
  await expect(page.getByTestId('current-stage')).toBeVisible({ timeout: FIRST_COMPILE });
  expect(page.url()).toBe(applicationUrl);

  // -- clean up: clear the date, and assert the row goes away ---------------
  // The removal is the assertion as well as the teardown. A row that outlives
  // its reason is the failure mode this section exists to avoid.
  const clear = page.getByLabel('Next action');
  await clear.fill('');
  await clear.blur();

  await page.goto('/operate/queue');
  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible();
  await expect(rowsOf(page, 'follow_up').getByRole('link', { name: title })).toHaveCount(0);
});

test('an interview inside the horizon appears, and archiving removes it', async ({ page }) => {
  const job = await jobAt(INTERVIEW_JOB);
  await openApplication(page, job);
  const title = new RegExp(job.title, 'i');

  const when = isoDaysFromNow(2).slice(0, 16); // `datetime-local` wants no seconds.
  await page.getByLabel('Interview').fill(when);
  await page.getByRole('button', { name: /add interview/i }).click();
  await expect(page.getByRole('button', { name: /add interview/i })).toBeDisabled();

  await page.goto('/operate/queue');
  const row = rowsOf(page, 'interviews_approaching').getByRole('link', { name: title }).first();
  await expect(row).toBeVisible({ timeout: FIRST_COMPILE });
  await expect(row).toContainText(/interview scheduled for/i);

  // -- archiving removes it from every section ------------------------------
  // §7.2's second rule, asserted end to end rather than only in the query
  // tests. This is the teardown too: an `interview_scheduled` event is
  // append-only and cannot be deleted, so archiving is the only way to take
  // this role back out of the queue.
  await row.click();
  await expect(page.getByTestId('current-stage')).toBeVisible({ timeout: FIRST_COMPILE });
  await page.getByRole('button', { name: /^archive$/i }).click();
  await expect(page.getByRole('button', { name: /^restore$/i })).toBeVisible();

  await page.goto('/operate/queue');
  await expect(page.getByRole('heading', { name: 'Today', level: 1 })).toBeVisible();
  for (const key of [
    'follow_up',
    'interviews_approaching',
    'stale_saved',
    'closed_while_saved',
    'requirement_gaps',
    'todays_one_thing',
    // Archiving keeps a role out of the suggestion row too, and for a
    // different reason: archiving is how somebody says *not this one*, so
    // re-offering it would be the page arguing with them.
    'best_new_internships',
  ]) {
    await expect(rowsOf(page, key).getByRole('link', { name: title })).toHaveCount(0);
  }
});
