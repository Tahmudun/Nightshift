/**
 * Look at the city.
 *
 * ADR 0031 makes the human holding `docs/design/references/02-*.jpg` the
 * acceptance test for M4e's look, which means the loop is render → look →
 * adjust rather than render → assert. This is the render half.
 *
 *   node .look.mjs out.png <lng> <lat> <zoom> <pitch> <bearing> [bare]
 *
 * `bare` hides the header, the overlay panels and MapLibre's own controls, so
 * the frame is the city and nothing else. The panels are real product and are
 * judged too — but not in the same screenshot as a sky.
 *
 * The frame time it prints is a **software rasteriser's** and is not evidence
 * about anything: headless Chromium has no GPU here. Frame cost is measured by
 * the M4d Task 1 instrument in a real browser. This number is printed only so
 * a capture that silently fell back to 2fps cannot be mistaken for a fast one.
 */
import { chromium } from '@playwright/test';

const [out, lng, lat, zoom, pitch, bearing, bare, headed] = process.argv.slice(2);

// `headed` runs a real window on a real GPU. Headless Chromium here falls back
// to a software rasteriser and reports ~600 ms frames over a city that draws in
// 16 — a number that is not evidence about anything, which is why the frame
// report below says so out loud.
const browser = await chromium.launch({ headless: bare !== 'headed' && headed !== 'headed' });
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
});
await page.goto('http://localhost:3000/explore/city', { waitUntil: 'networkidle' });
await page.waitForFunction(() => !!window.__nightshiftCity, null, { timeout: 90000 });
await page.waitForTimeout(6000);

await page.evaluate(
  ([lng, lat, zoom, pitch, bearing]) => {
    window.__nightshiftCity.map.jumpTo({
      center: [+lng, +lat],
      zoom: +zoom,
      pitch: +pitch,
      bearing: +bearing,
    });
  },
  [lng, lat, zoom, pitch, bearing],
);

if (bare === 'bare') {
  await page.evaluate(() => {
    // Found from the canvas outward rather than by class name: the overlay
    // wrapper's classes are Tailwind utilities and would silently stop
    // matching the first time one of them changed.
    const container = document.querySelector('canvas.maplibregl-canvas')?.closest('.maplibregl-map');
    const root = container?.parentElement;
    if (root) {
      for (const child of root.children) {
        if (child !== container) child.style.display = 'none';
      }
    }
    for (const node of document.querySelectorAll('header, .maplibregl-control-container')) {
      node.style.display = 'none';
    }
  });
}

await page.waitForTimeout(8000);
await page.screenshot({ path: out });

const frames = await page.evaluate(() => {
  const timer = window.__nightshiftCity?.frames;
  const report = timer?.report?.() ?? timer?.summary?.() ?? null;
  return report === null ? null : JSON.parse(JSON.stringify(report));
});
console.log('saved', out, frames === null ? '' : `(software raster: ${JSON.stringify(frames)})`);

await browser.close();
