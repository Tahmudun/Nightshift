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
  fullyParallel: true,
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
      // Reused unconditionally: an API already running for `make dev` is the
      // same API, and re-binding port 8000 would just fail.
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
