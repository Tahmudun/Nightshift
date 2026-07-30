import { defineConfig, devices } from '@playwright/test';

/**
 * M0 e2e scope: the shell renders, the three modes are reachable, and the app
 * degrades honestly when the API is not running. That last one is the case worth
 * automating — a dashboard that shows a blank panel instead of "api unreachable"
 * is the failure mode §25 is about.
 *
 * `webServer` starts the Next dev server only; the API is deliberately absent so
 * the degraded path is what gets exercised. Tests that need real data are
 * integration tests and run against a seeded stack.
 */
export default defineConfig({
  testDir: './e2e',
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
