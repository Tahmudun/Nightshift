import { defineConfig, devices } from '@playwright/test';

/**
 * The seeded counterpart to playwright.config.ts.
 *
 * That config starts the web server with no API, on purpose, to exercise the
 * degraded path. This one assumes a running, seeded stack and proves M0
 * acceptance criterion 5 — that a real Greenhouse board's jobs reach a browser.
 *
 * Run via `make test-e2e-seeded`, or as part of `make acceptance`.
 *
 * Both servers this suite needs are declared below rather than left to the
 * caller. Postgres and Redis are still the caller's job — `make up && make
 * migrate && make seed` — and their absence surfaces as the API failing its
 * readiness check, since /health returns 200 only when both are reachable.
 */
export default defineConfig({
  testDir: './e2e-seeded',
  // One test at a time, across the whole suite.
  //
  // Every spec here shares one database and one dev user, and three of them
  // write to that user: `profile.spec.ts` confirms and removes skills,
  // `eligibility.spec.ts` rewrites the six gate columns, `matching.spec.ts`
  // reads the scores those two invalidate. A confirmed skill or a changed
  // graduation year **deletes every `match_result` row** (M3c Task 8's
  // invalidation), so run in parallel these files do not merely interleave —
  // one empties the table another is asserting against, and the failure reads
  // as "the corpus is not scored" rather than as a race.
  //
  // The suite takes about a minute. That is not a price worth paying to keep a
  // latent flake, and the flake was latent before M3c: two files already wrote
  // the same six profile columns while a third read verdicts computed from them.
  fullyParallel: true,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'npm run dev',
      url: 'http://localhost:3000/explore',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      // The venv binary locally, the PATH one in CI, where deps are installed
      // into the runner's Python. Picking at run time keeps this the same
      // command in both places instead of two that can drift apart.
      command:
        'if [ -x .venv/bin/uvicorn ]; then UV=.venv/bin/uvicorn; else UV=uvicorn; fi; ' +
        'exec "$UV" nightshift.api.main:app --host 127.0.0.1 --port 8000 --no-access-log',
      cwd: '../../services/api',
      // /health is 200 only when Postgres and Redis both answer, so this doubles
      // as the check that the stack really is seeded and reachable.
      url: 'http://127.0.0.1:8000/health',
      // Reused unconditionally, and the reason this comment used to give was
      // wrong. It said "an API already running for `make dev` is the same API".
      // On 2026-08-09 the API already running was three days old, this suite
      // reused it, and the one test covering that morning's fix skipped itself
      // green with "no seeded posting is unassessable" — a true sentence about
      // a binary from Tuesday.
      //
      // Still reused, because refusing would break the ordinary `make dev` +
      // `make test-e2e-seeded` loop and re-binding port 8000 would fail anyway.
      // Playwright cannot tell a fresh server from a stale one; what it can do
      // is refuse to pass when the deterministic seeded corpus fails to produce
      // a case it certainly contains, which is why `eligibility.spec.ts` throws
      // there instead of skipping. `scripts/verify.py` guards its own half
      // differently — it starts its own API and now refuses to run at all if
      // the port is taken.
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
