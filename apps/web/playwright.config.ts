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
  /**
   * Fifteen seconds for a web assertion, against Playwright's default of five.
   *
   * The same measurement, from the other end. Capping workers at two was not
   * enough: on 2026-08-12 a *navigation* test failed inside `make acceptance`
   * waiting for the Operate heading, while the other worker was rasterising New
   * York. Nothing was broken — `next dev` compiles a route the first time it is
   * requested, and a compile that normally takes two seconds takes longer than
   * five when the CPU is busy drawing a city.
   *
   * Raising the budget costs nothing on a passing run, because every `expect`
   * here polls and returns the moment it is satisfied. It costs ten extra
   * seconds on a genuine failure, which is a good trade for never again reading
   * "the Operate page is broken" and finding out the machine was busy.
   */
  expect: { timeout: 15_000 },
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
