import { expect, test, type Page } from '@playwright/test';

import { API, apiFetch } from './api';

/**
 * The review queue, against a real API and a real seeded corpus.
 *
 * **This is the first end-to-end coverage `/operate/capture` has ever had**,
 * and `docs/reviews/milestone-5d-review.md` §4 named its absence as a gap it
 * was stating rather than closing. The gap turned out to be hiding a defect
 * that thirteen component tests could not see, because every one of them began
 * by pasting: a capture made through the MCP server — the whole point of M5d —
 * had a row in the database, a `pending` status, and no screen. The tool told
 * the reader to "confirm or discard it at `/operate/capture`", and that page
 * was a paste box.
 *
 * So the first test here is the one a component test cannot write: **a
 * proposal this browser never created, read back from the API.**
 *
 * ## Why nothing here confirms the seeded capture
 *
 * The corpus is the developer's own database and this suite runs against it
 * repeatedly. Confirming the seeded proposal would empty the queue and take
 * every later run of this file down with it; `make seed` only re-plants it
 * because `capture_paste` is idempotent over *pending* rows, and a decided row
 * is not one. Every test below therefore ends on **Decide later**, which is
 * also the honest way to exercise the third exit from a form that used to have
 * only two.
 *
 * The confirm path is covered where it is safe: a paste this file makes itself,
 * with a unique marker, discarded on the way out.
 */

test.describe.configure({ mode: 'serial' });

/** `next dev` compiles a route on first request (see search-and-detail.spec.ts). */
const FIRST_COMPILE = 30_000;

interface PendingCapture {
  readonly id: string;
  readonly proposed: { readonly title: string | null; readonly company_name: string | null };
  readonly assistant: { readonly company_name: string | null } | null;
  readonly assistant_rejected_fields: readonly string[];
}

/**
 * What the seed left waiting, read from the API rather than assumed.
 *
 * The demo capture is rendered from a committed Greenhouse recording, so its
 * employer and title are stable — but hard-coding them here would make this
 * file fail with "expected Jump Trading" if the recording were ever swapped,
 * which reads as a bug in the screen rather than in the fixture.
 */
async function seededPending(): Promise<PendingCapture> {
  const response = await apiFetch(`${API}/capture?status=pending`);
  expect(response.ok, `GET /capture?status=pending returned ${response.status}`).toBe(true);
  const body = (await response.json()) as { captures: PendingCapture[] };
  // The assisted one specifically, not simply the newest. An abandoned row
  // from an interrupted run would otherwise be picked up and the assertions
  // below would fail describing the wrong capture.
  const assisted = body.captures.find((capture) => capture.assistant?.company_name);
  expect(
    assisted,
    'no assisted capture is pending review — has `make seed` run since M5d?',
  ).toBeTruthy();
  return assisted!;
}

/** The queue row for one capture, found by the title it shows. */
function rowFor(page: Page, capture: PendingCapture) {
  return page
    .getByTestId('capture-queue-row')
    .filter({ hasText: capture.proposed.title ?? 'title not read' });
}

async function openCapturePage(page: Page) {
  await page.goto('/operate/capture');
  await expect(page.getByRole('heading', { name: 'Add a posting' })).toBeVisible({
    timeout: FIRST_COMPILE,
  });
}

test('a capture this browser never made is waiting on the queue', async ({ page }) => {
  const pending = await seededPending();
  await openCapturePage(page);

  const row = rowFor(page, pending);
  await expect(row).toBeVisible();
  // The seed's proposal carries a parser title; if it ever does not, the row
  // says "title not read" rather than nothing, and this assertion is what
  // notices the difference.
  await expect(row).toContainText(pending.proposed.title ?? 'title not read');
  await expect(row).toContainText('Claude quoted from the page');
});

test('opening one shows both readings where they disagree, and what was refused', async ({
  page,
}) => {
  // ADR 0039 §2, end to end. The seed's assistant quotes the employer as
  // "Jump" — a real substring of "Jump Trading", so a legitimate quote — which
  // disagrees with the parser. Neither wins, and the box opens empty.
  const pending = await seededPending();
  expect(
    pending.assistant?.company_name,
    'the seeded capture no longer carries a disagreeing employer quote',
  ).toBeTruthy();
  expect(pending.proposed.company_name).not.toBe(pending.assistant?.company_name);

  await openCapturePage(page);
  await rowFor(page, pending).getByRole('button', { name: 'Review it' }).click();
  await expect(page.getByTestId('capture-review')).toBeVisible();

  await expect(page.getByLabel('Employer')).toHaveValue('');
  const note = page.getByText('Two readings disagreed');
  await expect(note).toContainText(pending.proposed.company_name!);
  await expect(note).toContainText(pending.assistant!.company_name!);

  // The evidence has to be on the decision screen. This reader never saw the
  // posting — the paste happened in somebody's Claude session.
  await expect(page.getByTestId('capture-raw-text')).toContainText(pending.proposed.company_name!);

  // A refusal is the check working, and the form has to say so as a note
  // rather than as an error.
  if (pending.assistant_rejected_fields.length > 0) {
    await expect(page.getByTestId('capture-refused-quotes')).toContainText(
      'not in the text you pasted',
    );
  }

  await page.getByRole('button', { name: 'Decide later' }).click();
  await expect(rowFor(page, pending)).toBeVisible();
});

test('the review says the corpus already holds this job', async ({ page }) => {
  // ADR 0039 §4, and the reason `GET /capture/{id}` runs the check rather than
  // only the paste does. The seed confirms one capture of this posting and
  // leaves a second pending, which is the realistic case: somebody already has
  // the job and is capturing it again from somewhere else.
  const pending = await seededPending();
  await openCapturePage(page);
  await rowFor(page, pending).getByRole('button', { name: 'Review it' }).click();

  const held = page.getByTestId('capture-already-have');
  await expect(held).toBeVisible();
  await expect(held).toContainText('Nightshift already has');
  await expect(held.getByRole('link').first()).toHaveAttribute('href', /\/explore\/jobs\//);

  await page.getByRole('button', { name: 'Decide later' }).click();
});

test('a paste is a proposal, and pasting it twice is still one proposal', async ({ page }) => {
  // M5a's rule and ADR 0039 §3's, in the browser. The marker keeps this run's
  // paste distinct from every previous run's, so the idempotence being
  // asserted is this test's own and not a leftover row's.
  const marker = `e2e-${Date.now()}`;
  const paste = `Staff Platform Engineer\nNightshift Test Co · New York, NY\n\n${marker}\n`;

  await openCapturePage(page);
  await page.getByLabel('The posting').fill(paste);
  await page.getByRole('button', { name: 'Read it' }).click();

  const review = page.getByTestId('capture-review');
  await expect(review).toBeVisible();
  await expect(review).toContainText('Nothing is saved yet');
  await expect(page.getByLabel('Title')).toHaveValue('Staff Platform Engineer');
  await expect(page.getByTestId('capture-already-existed')).toHaveCount(0);

  await page.getByRole('button', { name: 'Decide later' }).click();

  // The same text again, with the trailing whitespace a second copy-paste
  // really produces. One proposal, and the screen says so.
  await page.getByLabel('The posting').fill(`${paste}\n  `);
  await page.getByRole('button', { name: 'Read it' }).click();
  await expect(page.getByTestId('capture-already-existed')).toContainText('not a second one');

  // Leave nothing pending behind: this file's own row is discarded, the
  // seed's is not.
  await page.getByRole('button', { name: 'Throw it away' }).click();
  await expect(page.getByTestId('capture-review')).toHaveCount(0);
});
