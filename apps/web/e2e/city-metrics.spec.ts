import type { Page } from '@playwright/test';
import { expect, test } from '@playwright/test';

/**
 * The metrics run: M4's acceptance numbers, and the machine that produced them.
 *
 * **Skipped unless asked for**, because it is not a pass/fail test. It drives
 * four named scenarios, reads the frame timer after each, and prints a table to
 * paste into `docs/PROGRESS.md`. Run it:
 *
 * ```
 * cd apps/web && NIGHTSHIFT_METRICS=1 npx playwright test e2e/city-metrics.spec.ts --headed
 * ```
 *
 * **`--headed` is not a convenience, it is the measurement.** Headless Chromium
 * has no GPU and rasterises through SwiftShader on the CPU, so a headless run of
 * this file produces true numbers about a software rasteriser and false ones
 * about a desktop. The run refuses to be quoted either way without its renderer
 * line, which is printed with every table — and `city-acceptance.spec.ts`
 * asserts that the *page* carries the same caveat, so nobody has to remember
 * this comment.
 *
 * There is no threshold here on purpose. A threshold that passes on one
 * machine's GPU and fails on another's is a CI job that teaches people to
 * re-run it; the criterion in `CLAUDE.md` §6 is that the numbers exist, are
 * recorded, and say what they are.
 */

import { CITY_DEBUG_KEY } from '../src/lib/map/debug';

test.describe.configure({ timeout: 300_000 });

test.skip(
  !process.env.NIGHTSHIFT_METRICS,
  'the metrics run is opt-in: NIGHTSHIFT_METRICS=1, and --headed for a real GPU',
);

const UNRESOLVED = {
  kind: 'unresolved',
  latitude: null,
  longitude: null,
  building_id: null,
  location_confidence: 'city_only',
  resolution_method: 'source_text_parse',
  stated: 'New York, NY',
  inherited: false,
  office_label: null,
  office_address: null,
} as const;

function uuid(prefix: string, index: number): string {
  return `00000000-0000-4000-8000-${`${prefix}${index}`.padStart(12, '0').slice(-12)}`;
}

function corpus(count: number, employers: number) {
  return Array.from({ length: count }, (_, index) => ({
    job_id: uuid('a', index),
    title: `Software Engineer ${index}`,
    company_id: uuid('c', index % employers),
    company_name: `Employer ${String(index % employers).padStart(3, '0')}`,
    employment_type: 'full_time',
    remote_policy: 'on_site',
    status: 'open',
    // A third of the corpus is new enough to pulse, so the animated path is
    // measured rather than a still city being reported as fast.
    first_seen_at: index % 3 === 0 ? new Date().toISOString() : '2026-01-01T00:00:00Z',
    last_seen_at: '2026-08-12T00:00:00Z',
    last_verified_at: '2026-08-12T00:00:00Z',
    application_deadline: null,
    placement: UNRESOLVED,
  }));
}

async function measure(page: Page, gesture: () => Promise<void>) {
  await page.evaluate(
    (key) => window[key as typeof CITY_DEBUG_KEY]!.frames.reset(),
    CITY_DEBUG_KEY,
  );
  await gesture();
  return page.evaluate(
    (key) => window[key as typeof CITY_DEBUG_KEY]!.frames.report(),
    CITY_DEBUG_KEY,
  );
}

async function drag(page: Page, from: [number, number], to: [number, number], button?: 'right') {
  await page.mouse.move(from[0], from[1]);
  await page.mouse.down(button ? { button } : undefined);
  await page.mouse.move(to[0], to[1], { steps: 40 });
  await page.mouse.up(button ? { button } : undefined);
}

for (const roles of [200, 5_000]) {
  test(`frame times at ${roles.toLocaleString('en-US')} roles`, async ({ page }) => {
    await page.setViewportSize({ width: 1680, height: 1000 });
    await page.route('**/city/signals**', async (route) => {
      const signals = corpus(roles, roles === 5_000 ? 200 : 20);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          signals,
          counts: { building: 0, area: 0, unresolved: signals.length, total: signals.length },
          limit: 5000,
          truncated: false,
        }),
      });
    });

    await page.goto('/explore/city');
    await expect(page.getByRole('button', { name: 'Reset view' })).toBeVisible({ timeout: 90_000 });
    await expect
      .poll(
        () =>
          page.evaluate((key) => {
            const city = window[key as typeof CITY_DEBUG_KEY];
            if (!city?.map.getLayer('nightshift-signals')) return -1;
            return city.signals.drawn;
          }, CITY_DEBUG_KEY),
        { timeout: 90_000 },
      )
      .toBe(roles);

    const renderer = await page.evaluate(() => {
      const canvas = document.querySelector('canvas.maplibregl-canvas') as HTMLCanvasElement;
      const gl = canvas.getContext('webgl2') ?? canvas.getContext('webgl');
      const info = gl?.getExtension('WEBGL_debug_renderer_info');
      return info && gl ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : 'unknown';
    });

    const rows: string[] = [];
    const record = async (name: string, gesture: () => Promise<void>) => {
      const report = await measure(page, gesture);
      rows.push(
        report === null
          ? `| ${name} | no frames presented | | | | |`
          : `| ${name} | ${report.frames} | ${report.p50.toFixed(1)} | ${report.p95.toFixed(1)} | ` +
              `${report.worst.toFixed(1)} | ${(report.missed * 100).toFixed(0)}% |`,
      );
    };

    // Idle: the pulses are the only thing moving. This is the number that says
    // whether simply having the city open costs anything.
    await record('Idle, pulses only', async () => {
      await page.waitForTimeout(4_000);
    });

    await record('Pan', async () => {
      for (let i = 0; i < 4; i += 1) await drag(page, [840, 520], [640, 380]);
    });

    await record('Orbit (right-drag)', async () => {
      for (let i = 0; i < 4; i += 1) await drag(page, [840, 520], [640, 520], 'right');
    });

    await record('Zoom', async () => {
      for (let i = 0; i < 12; i += 1) {
        await page.mouse.move(840, 520);
        await page.mouse.wheel(0, i % 2 === 0 ? -240 : 240);
        await page.waitForTimeout(120);
      }
    });

    await record('Re-sort the whole field', async () => {
      for (const name of ['Openings', 'Newest', 'Name']) {
        await page.getByRole('radio', { name }).click();
        await page.waitForTimeout(900);
      }
    });

    console.log(
      [
        ``,
        `### ${roles.toLocaleString('en-US')} roles — ${renderer}`,
        ``,
        `| Scenario | Frames | p50 ms | p95 ms | Worst ms | Missed |`,
        `|---|---|---|---|---|---|`,
        ...rows,
        ``,
      ].join('\n'),
    );

    // The only assertion: the machine was identified. A table with no renderer
    // on it cannot be read, and would eventually be quoted as if it could.
    expect(renderer).not.toBe('unknown');
  });
}
