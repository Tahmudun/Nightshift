import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import { API, apiFetch } from './api';

/**
 * M3c in a browser: the score, and everything it is made of.
 *
 * The load-bearing test is the second one, for `requirements.spec.ts`' reason
 * one milestone on. Anything can render a number with six sections under it.
 * What this milestone claims is that **every quoted word on the panel is a
 * literal slice of text printed on the same page or confirmed by the person
 * reading it** — `matching.md` §7.2 — and the only way to check that is to take
 * the rendered quote and go looking for it in the rendered description. A panel
 * that paraphrased, or rebuilt the sentence from the normalized requirement
 * value, would pass every other assertion in this file.
 *
 * Four things here are unreachable from `MatchPanel.test.tsx` and
 * `RankedMatches.test.tsx`, which is why this file exists beside them:
 *
 *   1. The quote and the description are rendered by two different components,
 *      from two different fields, and only a real posting puts both on screen.
 *   2. **The ranked order is a claim about a list the API sorted.** A component
 *      test renders the order it was handed. This one checks that the order on
 *      screen follows the *fraction* — so 30 of 40 sits above 30 of 100 — which
 *      is the whole reason `assessed_out_of` is stored.
 *   3. **The same posting reports one score on two surfaces.** The ranked row
 *      and the detail panel read different endpoints.
 *   4. **A dimmed band is still a listed band.** §3.3, and a property of the
 *      page rather than of any component in it.
 *
 * **It writes nothing**, and normalises on entry instead. The specs that run
 * before it write profile columns and confirm skills, and both of those delete
 * every `match_result` row by design (M3c Task 8) — so this file's first act is
 * to run the same sweep the worker's cron runs, which is `make score`. Without
 * that it would report "the corpus is not scored" and be telling the truth
 * about a database another spec emptied thirty seconds earlier.
 */

/** `next dev` compiles a dynamic route on first request (see search-and-detail.spec.ts). */
const FIRST_COMPILE = 30_000;

const API_DIR = join(process.cwd(), '..', '..', 'services', 'api');
const VENV_PYTHON = join(API_DIR, '.venv', 'bin', 'python');

interface Evidence {
  component: string;
  points: number;
  job_span_text: string | null;
  job_span_field: string | null;
  job_char_start: number | null;
  job_char_end: number | null;
  user_span_text: string | null;
  proposed_by: string;
}

interface Component {
  component: string;
  points: number;
  weight: number;
  assessable: boolean;
  why: string;
  evidence: Evidence[];
}

interface Match {
  overall_score: number;
  assessed_out_of: number;
  fraction: number | null;
  eligibility_status: string;
  components: Component[];
  penalty_score: number;
  penalties: { name: string; points: number; applicable: boolean; why: string }[];
  ruleset_version: string;
}

interface JobDetail {
  id: string;
  title: string;
  description_text: string | null;
  match: Match | null;
}

interface RankedJob {
  job: { id: string; title: string };
  match: Match;
}

interface Ranking {
  bands: { state: string; items: RankedJob[] }[];
  total: number;
  not_yet_scored: number;
  /** What the list is sorted by, in the API's own words (M3d Task 6). */
  ordering: string;
}

/** Whitespace-collapsed on both sides, so a quote spanning a line break matches. */
const collapse = (s: string) => s.replace(/\s+/g, ' ').trim();

/**
 * `fetch`, retried once on a transport error.
 *
 * Not defensive padding — this file failed exactly here on its first full-suite
 * run, with `TypeError: fetch failed / ECONNRESET`, having passed every time it
 * was run alone. The mechanism is `scoreWhatIsDue` below: it is
 * `execFileSync`, so it freezes Node's event loop for a couple of seconds,
 * which is long enough for uvicorn to close an idle keep-alive socket that an
 * earlier spec's `fetch` left in undici's pool. The next request picks up that
 * dead socket and the reset arrives before any response does.
 *
 * A retry is the right shape and a longer timeout is not: nothing is slow here,
 * one connection is stale, and the second attempt opens a new one.
 */
async function readJson<T>(path: string): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return (await (await apiFetch(`${API}${path}`)).json()) as T;
    } catch (error) {
      if (attempt > 0) throw error;
    }
  }
}

async function ranking(): Promise<Ranking> {
  return readJson<Ranking>('/matches?limit=200');
}

/**
 * Score whatever is due, through the same function the ARQ cron calls.
 *
 * The venv binary locally, the PATH one in CI — the same fork
 * `playwright.seeded.config.ts` makes for uvicorn, and for the same reason.
 */
function scoreWhatIsDue(): string {
  const python = existsSync(VENV_PYTHON) ? VENV_PYTHON : 'python';
  return execFileSync(python, ['-m', 'nightshift.cli', 'score'], {
    cwd: API_DIR,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

let scored: Ranking;

test.beforeAll(async () => {
  scoreWhatIsDue();
  scored = await ranking();
  // Thrown rather than skipped, for `eligibility.spec.ts`' reason. The corpus is
  // committed fixtures and the sweep above just ran against it, so "nothing is
  // scored" is not a fact about this corpus — it means the sweep found no user,
  // no open postings, or this browser is talking to a different database than
  // the one that command wrote to.
  if (scored.total === 0) {
    throw new Error(
      `the seeded corpus scored nothing (${scored.not_yet_scored} awaiting the sweep), which ` +
        '`make seed` makes impossible — either the dev user is missing, or this suite is ' +
        'pointed at a database `nightshift.cli score` did not write to.',
    );
  }
});

test.describe('how a posting scores for you', () => {
  test('a score never appears as a bare number', async ({ page }) => {
    // I4, on the surface the invariant is written about. Every part named in
    // "stores its components, its penalties, its ruleset_version, and its
    // evidence" has to be on the page, not merely in the response that fed it.
    const row = scored.bands.flatMap((band) => band.items)[0]!;

    await page.goto(`/explore/jobs/${row.job.id}`, { timeout: FIRST_COMPILE });
    const panel = page.getByTestId('match');
    await expect(panel).toBeVisible({ timeout: FIRST_COMPILE });

    // The total, and never without its denominator: `assessed_out_of` is not
    // always 100 and "30" alone invites the reader to supply the missing
    // "of 100" themselves.
    await expect(page.getByTestId('match-score')).toContainText(
      `${row.match.overall_score} of ${row.match.assessed_out_of}`,
    );

    // Six components, each with its own sentence.
    for (const component of row.match.components) {
      const section = page.getByTestId(`component-${component.component}`);
      await expect(section).toContainText(collapse(component.why));
    }
    expect(row.match.components).toHaveLength(6);

    await expect(page.getByTestId('penalty-total')).toContainText(String(row.match.penalty_score));
    await expect(page.getByTestId('match-version')).toContainText(row.match.ruleset_version);
  });

  test('every quoted word on the panel is text printed on the same page', async ({ page }) => {
    // THE CRITERION (`matching.md` §7.2), where a person reads it rather than
    // where a test asserts it. Two halves, and both must hold:
    //
    //   the posting's side  a literal slice of the posting rendered below it
    //   the person's side   words they confirmed, and never a proposal
    //
    // **Read off the screen on both sides.** The first version of this test took
    // the span from the API and asked whether *some* `<mark>` on the page
    // matched it — through Playwright's `hasText`, which is case-insensitive and
    // substring-based. A panel rendering `{span.toLowerCase()}` passed it, and
    // so would one rendering "Python programming" for a span reading "Python".
    // It was checking that the API's own span was in the description, which the
    // API guarantees and the page cannot break. Measured: the mutation was run
    // and the test stayed green (M3c review §3).
    //
    // So the comparison is now rendered-to-rendered. Nothing in this test reads
    // a span from the API at all; the numbers below come from the page.
    const withQuotes = await mostQuoted();

    await page.goto(`/explore/jobs/${withQuotes.id}`, { timeout: FIRST_COMPILE });
    await expect(page.getByTestId('match')).toBeVisible({ timeout: FIRST_COMPILE });

    // Title as well as description: role relevance quotes the title, which is
    // printed at the top of this page, and "on the same page" is the claim.
    const printed = collapse(
      [
        await page.getByRole('heading', { level: 1 }).innerText(),
        await page.getByTestId('job-description').innerText(),
      ].join(' \n '),
    );
    expect(printed.length).toBeGreaterThan(0);

    const jobQuotes = await page.getByTestId('quoted-job-span').allInnerTexts();
    expect(
      jobQuotes.length,
      'no quote from the posting is on this page, which the seeded demo profile makes ' +
        'impossible — run `make reset-db` if the dev user has no confirmed skills',
    ).toBeGreaterThan(0);
    for (const quote of jobQuotes) {
      expect(printed, `the panel prints "${quote}" as the posting's own words`).toContain(
        collapse(quote),
      );
    }

    // The reader's side, against `/profile` — which serves confirmed records
    // only. `resume_extractions` is a different endpoint holding proposals, and
    // §7.2 forbids this page from quoting it.
    const confirmed = await readJson<{
      skills: { name: string }[];
      projects: { name: string; evidence: string | null }[];
      preferred_roles: string[];
      preferred_locations: string[];
    }>('/profile');
    const onFile = [
      ...confirmed.skills.map((skill) => skill.name),
      ...confirmed.projects.flatMap((project) => [project.name, project.evidence ?? '']),
      ...confirmed.preferred_roles,
      ...confirmed.preferred_locations,
    ].map(collapse);

    const userQuotes = await page.getByTestId('quoted-user-span').allInnerTexts();
    expect(
      userQuotes.length,
      'nothing on this page claims anything about the reader',
    ).toBeGreaterThan(0);
    for (const quote of userQuotes) {
      const span = collapse(quote);
      expect(
        onFile.some((entry) => entry.includes(span)),
        `the panel says you confirmed "${span}" and no confirmed record contains it`,
      ).toBe(true);
    }
  });

  test('nothing on the page says a model proposed anything', async ({ page }) => {
    // ADR 0018 where it would be read. `MatchPanel` keeps the branch that would
    // label an embedding-proposed row, deliberately and unreachably; this is the
    // assertion that it stays unreachable on real data rather than only in the
    // fixture the component test hands it.
    const row = scored.bands.flatMap((band) => band.items)[0]!;
    await page.goto(`/explore/jobs/${row.job.id}`, { timeout: FIRST_COMPILE });
    const panel = page.getByTestId('match');
    await expect(panel).toBeVisible({ timeout: FIRST_COMPILE });

    await expect(panel).not.toContainText(/proposed by the embedding/i);
    await expect(page.getByTestId('match-version')).toContainText(/rules only/i);
  });

  test('a component nothing could be assessed on prints no number', async ({ page }) => {
    // §5.1.1's distinction, on the page that would collapse it. "0 of 30" beside
    // "this posting names no required technologies" is two different statements
    // — you do not match, and there was nothing to ask — printed as one.
    const partial = scored.bands
      .flatMap((band) => band.items)
      .find(
        (row) => row.match.assessed_out_of < 100 && row.match.components.some((c) => !c.assessable),
      );
    expect(
      partial,
      'no seeded posting has an unassessable component, which the committed corpus makes ' +
        'impossible — 24 of its 31 postings name no required technology at all',
    ).toBeDefined();

    await page.goto(`/explore/jobs/${partial!.job.id}`, { timeout: FIRST_COMPILE });
    await expect(page.getByTestId('match')).toBeVisible({ timeout: FIRST_COMPILE });

    for (const component of partial!.match.components.filter((c) => !c.assessable)) {
      const section = page.getByTestId(`component-${component.component}`);
      await expect(section.getByTestId('not-assessed')).toBeVisible();
      await expect(section).not.toContainText(`0 of ${component.weight}`);
    }

    // And the denominator says why it is not 100, naming them.
    await expect(page.getByTestId('partial-denominator')).toContainText(
      `Out of ${partial!.match.assessed_out_of}, not 100`,
    );
  });
});

/**
 * `fraction * sqrt(assessed_out_of / 100)` — `matching.md` §5.3, the key M3d
 * Task 6 chose by measurement.
 *
 * Recomputed from the two numbers on the wire rather than read off the page,
 * because the printed share and the sort key are deliberately different things:
 * a row reading 17% can sit above one reading 30%, and only this arithmetic
 * tells that apart from a broken list.
 */
function rankKey(row: RankedJob): number | null {
  const outOf = row.match.assessed_out_of;
  return outOf === 0 ? null : row.match.overall_score / (Math.sqrt(outOf) * 10);
}

test.describe('the ranked list', () => {
  test('is ordered on the key it says it uses, not on the printed share', async ({ page }) => {
    // Until M3d Task 7 this test asserted the printed percentages descend, and
    // it was red: Task 6 had replaced the sort key and moved on. Reading
    // `ordering` off the response first turns the next such change into a loud
    // refusal instead of a wrong assertion about a right answer.
    expect(scored.ordering).toBe('coverage_weighted_fraction');

    // Only worth checking because this corpus distinguishes the two orderings.
    const rows = scored.bands.flatMap((band) => band.items).filter((row) => row.match.fraction);
    const byKey = rows.map((row) => row.job.id);
    const byTotal = [...rows]
      .sort((a, b) => b.match.overall_score - a.match.overall_score)
      .map((row) => row.job.id);
    expect(
      byKey,
      'this corpus cannot tell the two orderings apart, so this test proves nothing',
    ).not.toEqual(byTotal);

    await page.goto('/explore/matches', { timeout: FIRST_COMPILE });
    await expect(page.getByTestId('ranked-matches')).toBeVisible({ timeout: FIRST_COMPILE });

    for (const band of scored.bands) {
      const items = band.items.filter((row) => row.match.fraction !== null);
      if (items.length < 2) continue;
      const rendered = await page
        .getByTestId(`band-${band.state}`)
        .getByTestId('row-fraction')
        .allInnerTexts();
      const percentages = rendered.map((text) => Number.parseInt(text, 10));

      // The page shows the API's rows in the API's order, unaltered.
      expect(percentages, `${band.state} does not render the order it was sent`).toEqual(
        items.map((row) => Math.round(row.match.fraction! * 100)),
      );
      // And that order is the documented key, descending.
      const keys = items.map((row) => rankKey(row)!);
      expect(keys, `${band.state} is out of order on screen`).toEqual(
        [...keys].sort((a, b) => b - a),
      );
    }
  });

  test('a posting you do not meet is dimmed and listed, never hidden', async ({ page }) => {
    // §3.3 and AMENDMENTS A7, as a property of the page. The band with nothing
    // in it must still print its heading, and a posting in a dimmed band must
    // still be a link to the posting.
    await page.goto('/explore/matches', { timeout: FIRST_COMPILE });
    await expect(page.getByTestId('ranked-matches')).toBeVisible({ timeout: FIRST_COMPILE });

    for (const band of scored.bands) {
      await expect(page.getByTestId(`band-${band.state}`)).toBeVisible();
    }

    const blocked = scored.bands.find(
      (band) => ['ineligible', 'likely_ineligible'].includes(band.state) && band.items.length > 0,
    );
    expect(
      blocked,
      'no seeded posting is out of reach for the demo profile, which the committed corpus ' +
        'makes impossible — it holds several postings stating a years minimum and the ' +
        'seeded profile has zero years',
    ).toBeDefined();

    const section = page.getByTestId(`band-${blocked!.state}`);
    // Dimmed, and the dimming is a class on the section rather than anything
    // that removes it from the page or from the accessibility tree.
    await expect(section).toHaveClass(/opacity-70/);
    for (const row of blocked!.items.slice(0, 3)) {
      await expect(section.getByRole('link', { name: row.job.title }).first()).toBeVisible();
    }
  });

  test('the ranked row and the posting report one score', async ({ page }) => {
    // Two endpoints, two components, one claim about a person. A transposition
    // in either read path is invisible from inside either one.
    const row = scored.bands.flatMap((band) => band.items).find((r) => r.match.fraction !== null)!;

    await page.goto('/explore/matches', { timeout: FIRST_COMPILE });
    const listed = page.getByTestId('ranked-row').filter({ hasText: row.job.title }).first();
    await expect(listed.getByTestId('row-total')).toContainText(
      `${row.match.overall_score} of ${row.match.assessed_out_of}`,
      { timeout: FIRST_COMPILE },
    );

    await listed.getByRole('link', { name: row.job.title }).click();
    await expect(page).toHaveURL(new RegExp(`/explore/jobs/${row.job.id}`), {
      timeout: FIRST_COMPILE,
    });
    await expect(page.getByTestId('match-score')).toContainText(
      `${row.match.overall_score} of ${row.match.assessed_out_of}`,
      { timeout: FIRST_COMPILE },
    );
  });
});

/** The scored posting whose panel quotes the most text, read from the API. */
async function mostQuoted(): Promise<JobDetail> {
  let best: JobDetail | null = null;
  let bestCount = -1;
  for (const row of scored.bands.flatMap((band) => band.items)) {
    const detail = await readJson<JobDetail>(`/jobs/${row.job.id}`);
    const count = (detail.match?.components ?? []).reduce(
      (sum, component) =>
        sum +
        component.evidence.filter((e) => e.job_span_text !== null || e.user_span_text !== null)
          .length,
      0,
    );
    if (count > bestCount) {
      best = detail;
      bestCount = count;
    }
  }
  return best!;
}
