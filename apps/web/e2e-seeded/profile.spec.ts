import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test, type Page } from '@playwright/test';

/**
 * M2's fourth acceptance criterion, walked in a browser:
 *
 *   "No parsed resume fact is stored as confirmed without a user action"
 *
 * This test IS the criterion, not a proxy for it. Step 4 is the whole thing:
 * after a resume has been read and its claims listed, the profile is checked
 * and still says nothing.
 *
 * Idempotence, the M2b way: this file **normalises what it finds on entry**
 * rather than trusting its own tidy exit. It runs against the developer's own
 * database, so a run that died halfway must not poison the next one. Every
 * resume it creates carries a name only this file uses, and it deletes those
 * on the way in as well as on the way out.
 */

test.describe.configure({ mode: 'serial' });

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

/** `next dev` compiles a dynamic route on first request (see search-and-detail.spec.ts). */
const FIRST_COMPILE = 30_000;

const FIXTURES = join(process.cwd(), '..', '..', 'services', 'api', 'tests', 'fixtures', 'resumes');
const RESUME_TEXT = readFileSync(join(FIXTURES, 'nadia_okonkwo.txt'), 'utf8');
const PROSE_TEXT = readFileSync(join(FIXTURES, 'prose_only.txt'), 'utf8');

/** Only resumes this file made. Anything else on the profile is a human's. */
const MINE = /^e2e /;

interface Resume {
  id: string;
  name: string;
}

interface Skill {
  id: string;
  name: string;
}

async function listResumes(): Promise<Resume[]> {
  const response = await fetch(`${API}/resumes`);
  const body = (await response.json()) as { items: Resume[] };
  return body.items;
}

async function skills(): Promise<Skill[]> {
  const response = await fetch(`${API}/profile`);
  const body = (await response.json()) as { skills: Skill[] };
  return body.skills;
}

/** Delete every resume this file has ever created. Safe to run at any point. */
async function clearMine(): Promise<void> {
  for (const resume of await listResumes()) {
    if (MINE.test(resume.name)) {
      await fetch(`${API}/resumes/${resume.id}`, { method: 'DELETE' });
    }
  }
}

async function paste(page: Page, name: string, text: string): Promise<void> {
  await page.goto('/operate/profile', { timeout: FIRST_COMPILE });
  await page.getByLabel(/name this resume/i).fill(name);
  await page.getByLabel(/paste the text/i).fill(text);
  await page.getByRole('button', { name: /read this text/i }).click();
  await expect(page).toHaveURL(/\/operate\/resumes\//, { timeout: FIRST_COMPILE });
}

test.beforeAll(async () => {
  await clearMine();
});

test.afterAll(async () => {
  await clearMine();
});

test('a resume proposes, and confirms nothing until it is told to', async ({ page }) => {
  // Five navigations across three routes, two of which `next dev` compiles on
  // demand, while three other workers are doing the same. It passed alone and
  // timed out at 30s in the full suite — measured, not guessed: the failure was
  // `page.reload` running out the *test* budget, not any assertion going red.
  // Trimming the walk to fit would remove coverage to make a clock happy.
  test.slow();

  const before = new Set((await skills()).map((skill) => skill.name));
  // Restored to what it was, not to null, which is what this test used to do.
  // Harmless while the seeded profile was empty and destructive the moment it
  // was not: `make seed` gives the dev user the fixture resume's graduation date
  // as of M3c Task 12, and blanking it here would leave the demo profile
  // quietly missing a field every run — and, because graduation year is a
  // scoring input, withdraw every score in the database on the way out.
  const graduationBefore = (await (await fetch(`${API}/profile`)).json()) as {
    graduation_year: number | null;
    graduation_month: number | null;
  };

  await paste(page, 'e2e nadia', RESUME_TEXT);

  // 3. The proposals are listed, each showing the words it came from.
  const proposals = page.getByTestId(/^proposal-/);
  await expect(proposals.first()).toBeVisible({ timeout: FIRST_COMPILE });
  const count = await proposals.count();
  expect(count, 'the fixture resume proves several things').toBeGreaterThan(5);
  await expect(page.getByTestId('review-status')).toContainText(/nothing here has been saved/i);
  await expect(proposals.first()).toContainText(/characters \d+–\d+/);

  // 4. THE CRITERION. Go and look at the profile: it has not changed.
  await page.goto('/operate/profile');
  await expect(page.getByRole('heading', { name: 'Skills' })).toBeVisible();
  const afterReading = new Set((await skills()).map((skill) => skill.name));
  expect([...afterReading].sort(), 'reading a resume confirmed something').toEqual(
    [...before].sort(),
  );

  // 5. Confirm one skill and the graduation; reject another skill.
  const resume = (await listResumes()).find((row) => MINE.test(row.name))!;
  await page.goto(`/operate/resumes/${resume.id}`);

  const detail = (await (await fetch(`${API}/resumes/${resume.id}`)).json()) as {
    extractions: { id: string; kind: string; value: Record<string, unknown> }[];
  };
  const unconfirmedSkills = detail.extractions.filter(
    (row) => row.kind === 'skill' && !before.has(String(row.value.name)),
  );
  expect(unconfirmedSkills.length, 'two skills nobody has confirmed yet').toBeGreaterThan(1);
  const keep = unconfirmedSkills[0]!;
  const drop = unconfirmedSkills[1]!;
  const graduation = detail.extractions.find((row) => row.kind === 'graduation')!;

  for (const id of [keep.id, graduation.id]) {
    await page
      .getByTestId(`proposal-${id}`)
      .getByRole('button', { name: /^confirm$/i })
      .click();
  }
  await page
    .getByTestId(`proposal-${drop.id}`)
    .getByRole('button', { name: /^reject$/i })
    .click();
  await page.getByRole('button', { name: /save these decisions/i }).click();
  await expect(page.getByText(/2 confirmed, 1 rejected/i)).toBeVisible();

  // 6. Exactly what was confirmed, and nothing else.
  await page.goto('/operate/profile');
  const kept = page.getByText(String(keep.value.name), { exact: true });
  await expect(kept.first()).toBeVisible();
  await expect(kept.first().locator('..')).toContainText(/from your resume/i);
  const confirmed = new Set((await skills()).map((skill) => skill.name));
  expect(confirmed.has(String(keep.value.name))).toBe(true);
  expect(confirmed.has(String(drop.value.name)), 'a rejected skill reached the profile').toBe(
    false,
  );
  await expect(page.getByLabel(/graduation year/i)).toHaveValue(String(graduation.value.year));

  // 7. It persisted — this is a row in Postgres, not component state.
  await page.reload();
  await expect(page.getByText(String(keep.value.name), { exact: true }).first()).toBeVisible();

  // 9. Deleting the resume keeps the fact. The skill belongs to the person.
  await fetch(`${API}/resumes/${resume.id}`, { method: 'DELETE' });
  const survived = await skills();
  expect(survived.map((skill) => skill.name)).toContain(String(keep.value.name));

  // Put the profile back exactly as this test found it, so it can run again.
  for (const skill of survived) {
    if (!before.has(skill.name)) {
      await fetch(`${API}/profile/skills/${skill.id}`, { method: 'DELETE' });
    }
  }
  await fetch(`${API}/profile`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      graduation_year: graduationBefore.graduation_year,
      graduation_month: graduationBefore.graduation_month,
    }),
  });
});

test('a resume that proves nothing says so, and changes nothing', async ({ page }) => {
  const before = new Set((await skills()).map((skill) => skill.name));

  await paste(page, 'e2e prose', PROSE_TEXT);

  // §6.2 and I7: the failure is stated and the manual form is offered. An
  // empty pane implying success is the one outcome that must never happen.
  await expect(page.getByText(/nothing could be proven from this file/i)).toBeVisible({
    timeout: FIRST_COMPILE,
  });
  await expect(page.getByRole('link', { name: /add them yourself/i })).toBeVisible();
  await expect(page.getByTestId(/^proposal-/)).toHaveCount(0);

  // And the text it read is still on screen, so "we found nothing" is checkable.
  await expect(page.getByTestId('highlighted-text')).toContainText('passionate self-starter');

  const after = new Set((await skills()).map((skill) => skill.name));
  expect([...after].sort()).toEqual([...before].sort());
});

test('the profile names what it will not work out for you', async ({ page }) => {
  // I7's surface for M2c, on the page where somebody would expect a resume to
  // be read for them.
  await page.goto('/operate/profile', { timeout: FIRST_COMPILE });
  const deferred = page.getByTestId('deferred-profile');
  await expect(deferred).toContainText(/work authorization/i);
  await expect(deferred).toContainText(/\.docx/);
});
