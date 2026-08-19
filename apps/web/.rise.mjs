/**
 * Watch the city move.
 *
 * `.look.mjs` answers "what does this pose look like"; this answers "does
 * anything on it actually change", by saving four stills across one rise cycle
 * so they can be flipped through. It exists because M4e's beacons shipped with
 * an animation that was real in the uniform, advancing on the clock, and drawn
 * identically every frame — a failure a single screenshot cannot show and a
 * frame counter cannot either.
 *
 *   node .rise.mjs out-prefix <lng> <lat> <zoom> <pitch> <bearing>
 *
 * Saves `out-prefix-0.png` through `-3.png`, 1.25 s apart. The panels are
 * hidden, as in `.look.mjs`'s `bare`.
 *
 * `city-acceptance.spec.ts` asserts the same property numerically and is the
 * thing that gates a merge. This is for looking.
 */
import { chromium } from '@playwright/test';
const [prefix, lng, lat, zoom, pitch, bearing] = process.argv.slice(2);
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1200, height: 800 },
  deviceScaleFactor: 1,
});
await page.goto('http://localhost:3000/explore/city', { waitUntil: 'networkidle' });
await page.waitForFunction(() => !!window.__nightshiftCity, null, { timeout: 90000 });
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
await page
  .waitForFunction(() => window.__nightshiftCity?.signals?.city?.ready === true, null, {
    timeout: 180000,
  })
  .catch(() => {});
await page.evaluate(() => {
  const root = document
    .querySelector('canvas.maplibregl-canvas')
    ?.closest('.maplibregl-map')?.parentElement;
  if (root)
    for (const c of root.children)
      if (!c.classList.contains('maplibregl-map')) c.style.display = 'none';
  for (const n of document.querySelectorAll('header, .maplibregl-control-container'))
    n.style.display = 'none';
});
await page.waitForTimeout(2000);
for (let i = 0; i < 4; i += 1) {
  await page.screenshot({ path: `${prefix}-${i}.png` });
  await page.waitForTimeout(1250);
}
console.log('saved', prefix);
await browser.close();
