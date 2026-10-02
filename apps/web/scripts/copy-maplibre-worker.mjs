/**
 * Copy MapLibre's web worker into `public/maplibre/`, where the city map loads
 * it from. Runs as `predev` and `prebuild`, so it happens before every way this
 * app is started or built (`make dev` and both Playwright configs go through
 * `npm run dev`; CI and `npm start` go through `npm run build`).
 *
 * MapLibre 6 is ESM-only and loads its worker from a URL instead of from an
 * inlined blob. Next's bundler turns `new URL(worker, import.meta.url)` into a
 * hashed asset without the worker's `maplibre-gl-shared.mjs` sibling, and the
 * worker then fails on its first import: the page says "Worker failed to load"
 * and draws nothing. MapLibre's own Next.js instructions are this script —
 * serve both files from `public/` and point `setWorkerUrl` at them.
 *
 * Copied from `node_modules` on every run rather than committed, so the worker
 * always matches the installed main bundle. A worker one version off is a map
 * that fails in ways no test here would name.
 */
import { copyFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const dist = path.join(
  path.dirname(createRequire(import.meta.url).resolve('maplibre-gl/package.json')),
  'dist',
);
const dest = path.join(import.meta.dirname, '..', 'public', 'maplibre');

mkdirSync(dest, { recursive: true });
// Both, not just the worker: it imports the shared chunk by relative path.
for (const file of ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs']) {
  copyFileSync(path.join(dist, file), path.join(dest, file));
}
