import { defineConfig, devices } from '@playwright/test';

/**
 * The suite that runs with nothing behind it.
 *
 * Two things live here and they share that property. The M0 shell tests assert
 * the app degrades honestly when the API is not running — a dashboard showing a
 * blank panel instead of "api unreachable" is the failure mode §25 is about. The
 * M4b city tests assert New York draws with no API and no network at all, which
 * is the same claim from the other side.
 *
 * `webServer` starts the Next dev server only; the API is deliberately absent.
 * Tests that need real data are integration tests and run against a seeded stack.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  /**
   * Capped, and the cap is load-bearing since `city.spec.ts` arrived.
   *
   * Playwright's default is half the cores — four here — and each city worker
   * builds a MapLibre map with no GPU behind it, so four of them rasterise a
   * million footprints on the same CPU. Measured on 2026-08-12: at four workers
   * a mouse-drag pan and an unrelated *navigation* test both timed out; at two,
   * all twenty-three pass. The failures were nothing to do with the code under
   * test — a slow machine looks exactly like a broken feature, and a suite that
   * fails that way teaches people to re-run it rather than read it.
   */
  workers: 2,
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
