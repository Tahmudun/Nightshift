/**
 * The M4d Task 1 instrument, run with and without the sky in the same window on
 * the same GPU, so the difference is the sky and not the weather.
 */
import { chromium } from '@playwright/test';

const [lng, lat, zoom, pitch, bearing] = process.argv.slice(2);

const browser = await chromium.launch({ headless: false });
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
await page.waitForTimeout(6000);

console.log('renderer:', await page.evaluate(() => window.__nightshiftCity.frames && document.body.innerText.match(/Renderer.*|Typical.*/)?.[0]));

/** Spin the camera so frames are actually being drawn, then read the window. */
async function sample(label) {
  await page.evaluate(() => window.__nightshiftCity.frames.reset());
  await page.evaluate(async () => {
    const map = window.__nightshiftCity.map;
    const start = performance.now();
    while (performance.now() - start < 6000) {
      map.setBearing((map.getBearing() + 0.6) % 360);
      await new Promise((r) => requestAnimationFrame(r));
    }
  });
  const report = await page.evaluate(() => JSON.parse(JSON.stringify(window.__nightshiftCity.frames.report())));
  console.log(label, JSON.stringify(report));
  return report;
}

await sample('with sky   ');
await page.evaluate(() => window.__nightshiftCity.map.removeLayer('nightshift-sky'));
await page.waitForTimeout(1500);
await sample('without sky');
await browser.close();
