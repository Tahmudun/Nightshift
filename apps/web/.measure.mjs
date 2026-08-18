/**
 * The M4d Task 1 instrument, run twice in the same window on the same GPU, so
 * the difference is the change and not the weather.
 *
 *   node .measure.mjs <lng> <lat> <zoom> <pitch> <bearing> [sky|buildings]
 *
 * `sky` (the default) samples with and without the sky layer.
 * `buildings` samples ADR 0031's Three.js city against the MapLibre
 * `fill-extrusion` skyline it replaced — by putting MapLibre's own layers back
 * (clearing the retirement filter) and hiding ours, which is the only honest
 * A/B: same frame, same camera, same everything else.
 */
import { chromium } from '@playwright/test';

const [lng, lat, zoom, pitch, bearing, subject = 'sky'] = process.argv.slice(2);

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

console.log(
  'renderer:',
  await page.evaluate(
    () =>
      window.__nightshiftCity.frames && document.body.innerText.match(/Renderer.*|Typical.*/)?.[0],
  ),
);

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
  const report = await page.evaluate(() =>
    JSON.parse(JSON.stringify(window.__nightshiftCity.frames.report())),
  );
  console.log(label, JSON.stringify(report));
  return report;
}

if (subject === 'buildings') {
  // Wait for the city to actually be on the GPU, or the first sample measures
  // a frame that is still assembling itself.
  await page.waitForFunction(() => window.__nightshiftCity.signals.city.ready === true, null, {
    timeout: 180000,
  });
  console.log(
    'city:',
    await page.evaluate(() => JSON.stringify(window.__nightshiftCity.signals.city)),
  );
  await sample('ours (three) ');
  await page.evaluate(() => {
    const map = window.__nightshiftCity.map;
    for (const id of ['buildings', 'buildings-crown']) map.setFilter(id, null);
    // Our group is inside the custom layer's scene, so it is switched off the
    // only way anything outside that layer can: by taking the layer out.
    map.removeLayer('nightshift-signals');
  });
  await page.waitForTimeout(2500);
  await sample('maplibre     ');
} else {
  await sample('with sky   ');
  await page.evaluate(() => window.__nightshiftCity.map.removeLayer('nightshift-sky'));
  await page.waitForTimeout(1500);
  await sample('without sky');
}
await browser.close();
