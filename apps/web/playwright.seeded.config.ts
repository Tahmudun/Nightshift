import { defineConfig, devices } from '@playwright/test';

/**
 * The seeded counterpart to playwright.config.ts.
 *
 * That config starts the web server with no API, on purpose, to exercise the
 * degraded path. This one assumes a running, seeded stack and proves M0
 * acceptance criterion 5 — that a real Greenhouse board's jobs reach a browser.
 *
 * Run via `make test-e2e-seeded`, or as part of `make acceptance`. It does not
 * start Postgres, Redis, or the API: if they are missing the suite fails with a
 * message telling you which make target to run, which is more useful than a
 * skipped test.
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
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000/explore',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
