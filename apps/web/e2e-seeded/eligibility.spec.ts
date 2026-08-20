import { expect, test } from '@playwright/test';

/**
 * M3b in a browser: whether a posting is open to you, and what happens to the
 * posting when the answer is no.
 *
 * Three of these tests check things no unit or component test can reach, and
 * that is the reason the file exists rather than another `JobEligibility.test.tsx`:
 *
 *   1. The **blocker quotes the description printed on the same page.** The
 *      component receives `posting_says` already formed; only a live stack can
 *      show that the string it received is a literal slice of the description
 *      rendered beside it. Same discipline as `requirements.spec.ts`, applied
 *      to a claim about a person instead of a claim about a posting.
 *   2. **An `ineligible` posting is still listed and still saveable.**
 *      `matching.md` §3.3, and it is a property of the *list* — the component
 *      that renders the verdict cannot possibly assert it.
 *   3. **The verdict follows the profile.** Clearing a field and reloading the
 *      same URL changes the answer, which is what "computed on read, stored
 *      nowhere" means when a person can see it (ADR 0017).
 *
 * **This file writes to the developer's own profile, which no other spec here
 * does, and the limit of its tidiness is stated rather than implied.** The gate
 * is a function of (posting x profile) and the seeded profile is entirely
 * empty, so a read-only version of this file could not reach a single blocker —
 * the three tests above would all skip. So it snapshots the six gate columns
 * before writing anything and restores them in `afterAll`, which Playwright
 * runs even when a test fails.
 *
 * What that does **not** cover is the process being killed mid-run. There is no
 * entry normalisation that fixes it either: after a kill the profile holds this
 * file's values and nothing on disk remembers what preceded them, so the next
 * run's snapshot is of the wrong thing. The exposure is six columns on a
 * single-user development database and the honest mitigation is that it is
 * written down here, not that it is solved.
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

/** `next dev` compiles a dynamic route on first request (see search-and-detail.spec.ts). */
const FIRST_COMPILE = 30_000;

/** The six `users` columns the gate reads. Nothing else here is touched. */
const GATE_FIELDS = [
  'graduation_year',
  'graduation_month',
  'degree',
  'years_experience',
  'is_enrolled',
  'work_authorization',
] as const;

type GateProfile = Record<(typeof GATE_FIELDS)[number], unknown>;

/**
 * A profile that fails several stated bars at once, chosen from what the seeded
 * corpus actually states rather than invented: it has one posting requiring
 * current enrollment and a 2026-2028 graduation window, and several stating a
 * years minimum. A 2024 graduate who is not enrolled hits all three.
 */
const BLOCKED: GateProfile = {
  graduation_year: 2024,
  graduation_month: 5,
  degree: 'BS in Computer Science',
  years_experience: 0,
  is_enrolled: false,
  work_authorization: 'unspecified',
};

interface Unknown {
  dimension: string;
  profile_field: string | null;
  why: string;
}

interface Blocker {
  dimension: string;
  outcome: string;
  posting_says: string | null;
}

interface JobDetail {
  id: string;
  title: string;
  description_text: string | null;
  eligibility: { state: string; blockers: Blocker[]; unknowns: Unknown[] } | null;
}

async function readProfile(): Promise<GateProfile> {
  const body = (await (await fetch(`${API}/profile`)).json()) as Record<string, unknown>;
  return Object.fromEntries(GATE_FIELDS.map((key) => [key, body[key]])) as GateProfile;
}

async function patchProfile(patch: Partial<GateProfile>): Promise<void> {
  const response = await fetch(`${API}/profile`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    throw new Error(`PATCH /profile answered ${response.status}: ${await response.text()}`);
  }
}

/**
 * The first seeded posting whose verdict has the wanted shape, read from the
 * API rather than hardcoded — the seed has been reshaped in four milestones.
 *
 * Throws when the corpus is empty, which is a different thing from "no posting
 * has this shape". Without that line every test here would skip green against
 * an unseeded stack and the file would report success having checked nothing.
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

const isIneligible = (job: JobDetail) => job.eligibility?.state === 'ineligible';

let found: GateProfile;

test.beforeAll(async () => {
  found = await readProfile();
});

test.afterAll(async () => {
  await patchProfile(found);
});

test.describe('whether a posting is open to you', () => {
  test('a verdict never appears without the reasons behind it', async ({ page }) => {
    // I4 applied to a state rather than to a score. Read-only: whatever the
    // developer's profile says, the section must carry its verdict and its
    // ruleset version, and it must never be a bare enum value.
    const job = await findJob((j) => j.eligibility !== null);
    test.skip(job === null, 'no seeded posting has any extracted requirements');

    await page.goto(`/explore/jobs/${job!.id}`);
    const section = page.getByTestId('eligibility');
    await expect(section).toBeVisible({ timeout: FIRST_COMPILE });

    const state = await page.getByTestId('eligibility-state').innerText();
    expect(state.trim().length).toBeGreaterThan(0);
    expect(state).not.toContain('_');
    await expect(page.getByTestId('eligibility-version')).toContainText('m3b.');
  });

  test('a blocker quotes the description printed on the same page', async ({ page }) => {
    // The criterion, not a proxy for it. A component that paraphrased the
    // posting, or rebuilt the sentence from the normalized value, would pass
    // every other assertion in this file.
    await patchProfile(BLOCKED);
    const job = await findJob(isIneligible);
    test.skip(job === null, 'no seeded posting blocks this profile');

    await page.goto(`/explore/jobs/${job!.id}`, { timeout: FIRST_COMPILE });
    const blockers = page.getByTestId('eligibility-blockers');
    await expect(blockers).toBeVisible({ timeout: FIRST_COMPILE });

    // Both sides whitespace-collapsed so a quote spanning a line break still
    // matches. Collapsing both is what makes this a test of the words rather
    // than of the layout.
    const collapse = (s: string) => s.replace(/\s+/g, ' ').trim();
    const description = collapse(await page.getByTestId('job-description').innerText());
    expect(description.length).toBeGreaterThan(0);

    const quoted = job!.eligibility!.blockers.filter(
      (b) => b.outcome === 'blocks' && b.posting_says !== null,
    );
    expect(quoted.length).toBeGreaterThan(0);
    for (const blocker of quoted) {
      expect(description).toContain(collapse(blocker.posting_says!));
      await expect(blockers).toContainText(collapse(blocker.posting_says!));
    }
  });

  test('an ineligible posting is still listed, and still saveable', async ({ page }) => {
    // A13 and `matching.md` §3.3: a hidden row is a parsing bug nobody can see.
    // The gate is allowed to be wrong; it is not allowed to be wrong invisibly.
    await patchProfile(BLOCKED);
    const job = await findJob(isIneligible);
    test.skip(job === null, 'no seeded posting blocks this profile');

    // Searched by title rather than scanned, because the list is paged and
    // "not on page one" is not the same finding as "hidden".
    await page.goto(`/explore?q=${encodeURIComponent(job!.title)}`, { timeout: FIRST_COMPILE });
    await expect(page.getByRole('link', { name: job!.title }).first()).toBeVisible({
      timeout: FIRST_COMPILE,
    });

    await page.goto(`/explore/jobs/${job!.id}`);
    await expect(page.getByTestId('eligibility-blockers')).toBeVisible({ timeout: FIRST_COMPILE });
    // The control is "Save", or — if this developer already tracks the role —
    // the link that button becomes. Either is an open door. The failure this
    // guards is a blocked posting whose apply path has been taken away, which
    // is the same harm as hiding the row with an extra step in front of it.
    //
    // **By test id and not by its words**, since M3c Task 12. It used to be
    // `getByRole('link', { name: /saved|applied|interview|offer|rejected/i })`
    // — five of `STAGE_LABELS`' ten stages, hand-copied — and `make acceptance`
    // put `verify.py` in front of this suite, which leaves an archived
    // application on exactly this posting at stage **Preparing**. The control
    // was on screen, reading "Preparing · archived", and this test reported that
    // an ineligible posting had had its apply path taken away.
    //
    // Third hand-transcribed map to go wrong in three milestones (M3b's review
    // found `ASKS`). The rule that keeps falling over is the same one: if a
    // vocabulary lives in a `Record<Enum, string>`, a test must not keep its own
    // copy of a subset of it.
    await expect(page.getByTestId('save-or-track')).toBeVisible({ timeout: FIRST_COMPILE });
  });

  test('the verdict follows the profile rather than a stored row', async ({ page }) => {
    // ADR 0017 made visible. Nothing is invalidated, no worker runs, no cache
    // is cleared: the same URL answers differently because the answer is
    // computed when it is asked for.
    await patchProfile(BLOCKED);
    const job = await findJob(isIneligible);
    test.skip(job === null, 'no seeded posting blocks this profile');

    await page.goto(`/explore/jobs/${job!.id}`, { timeout: FIRST_COMPILE });
    await expect(page.getByTestId('eligibility-blockers')).toBeVisible({ timeout: FIRST_COMPILE });

    await patchProfile({ graduation_year: null, graduation_month: null, is_enrolled: null });
    await page.reload();
    await expect(page.getByTestId('eligibility')).toBeVisible({ timeout: FIRST_COMPILE });
    // The two blockers that produced `ineligible` both came from fields just
    // cleared, so the wall is gone. The posting still asks what it asked —
    // this is the person's answer changing, not the posting's.
    await expect(page.getByTestId('eligibility-blockers')).toHaveCount(0);
  });

  test('no unknown offers an action that could not resolve it', async ({ page }) => {
    // Task 12's finding, in the place it was found. A posting saying "PhD or
    // equivalent experience" is unassessable however complete the profile is,
    // and the hatch is checked before the profile's degree is read — so this
    // reader has a degree on file and the pre-fix page still said "Add your
    // degree". They follow it, fill a field that is already filled, and the
    // verdict does not move.
    await patchProfile(BLOCKED);
    const job = await findJob((j) =>
      (j.eligibility?.unknowns ?? []).some((u) => u.profile_field === null),
    );
    // Thrown, not skipped, and this is the one test in the file that does so.
    //
    // The other four skip because their subject depends on which postings the
    // corpus holds and a corpus without an `ineligible` case is a legitimate
    // state. This one does not: the seeded corpus is committed fixtures, and it
    // deterministically contains Datadog's "AI Research Scientist", whose degree
    // requirement extracts as `phd` with `has_equivalence`. So "no seeded
    // posting is unassessable" is never true of this repository — it means the
    // rule regressed, or the browser is talking to a server built before the
    // rule existed.
    //
    // Both of those happened. The second one is why this line is not a
    // `test.skip`: on 2026-08-09 this suite reused a three-day-old API and the
    // skip reported the milestone's headline fix as covered.
    if (job === null) {
      throw new Error(
        'no seeded posting is unassessable on any dimension, which the committed ' +
          'corpus makes impossible — either _degree_rule stopped returning ' +
          'cannot_assess, or this browser is talking to a stale API. Check with: ' +
          'lsof -nP -iTCP:8000 -sTCP:LISTEN',
      );
    }

    // No `!` below: the throw above narrows `job`, which is a small second
    // reason to prefer it — an assertion the compiler has not checked is what
    // this milestone's review found in JobEligibility.tsx.
    await page.goto(`/explore/jobs/${job.id}`, { timeout: FIRST_COMPILE });
    const section = page.getByTestId('eligibility-unassessable');
    await expect(section).toBeVisible({ timeout: FIRST_COMPILE });
    await expect(section.getByRole('link')).toHaveCount(0);

    // And it is not filed under the heading that promises an answer. Asserted
    // on the *askable* section's contents rather than on its absence, because
    // the same posting may legitimately have both kinds at once.
    const askable = page.getByTestId('eligibility-unknowns');
    if ((await askable.count()) > 0) {
      const unassessableWhy = job.eligibility!.unknowns.filter((u) => u.profile_field === null);
      for (const unknown of unassessableWhy) {
        await expect(askable).not.toContainText(unknown.why);
      }
    }
  });
});
