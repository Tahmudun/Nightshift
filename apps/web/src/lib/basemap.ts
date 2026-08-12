/**
 * Where the basemap archive is, and what this build believes about it.
 *
 * The manifest is imported rather than read at runtime, deliberately. It is a
 * committed file that changes only when somebody re-bakes the tiles, so
 * resolving it through the filesystem would buy nothing and cost the one thing
 * that actually bites here: a repo-root lookup. `process.cwd()` is `apps/web`
 * under `next dev` and something else under `next start`, and a path that
 * resolves differently depending on how the server was launched is exactly the
 * bug that only shows up on the machine you are not using. Importing it makes
 * the bundler resolve the path once, at build time, and typechecks the shape
 * for free.
 *
 * **Nothing here may import a node module.** The map component is a client
 * component and it needs the bounds and the URL, so a single `node:path` import
 * in this file fails the build with a stack trace that names webpack rather
 * than the cause. Anything that touches the filesystem lives in
 * `basemap.server.ts`, which only the route handler imports.
 */

// Reaches out of `apps/web`, which nothing else here does. The manifest lives
// at the repository root because both toolchains read it — Python writes it,
// TypeScript renders from it — and inventing a shared package for a single JSON
// file would cost more than the odd-looking path does.
import manifest from '../../../../data/basemap.manifest.json';

export interface BasemapManifest {
  readonly filename: string;
  readonly url: string;
  readonly sha256: string;
  readonly size_bytes: number;
  readonly protomaps_build: string;
  readonly protomaps_version: string;
  readonly osm_replication_time: string;
  readonly bbox: readonly [number, number, number, number];
  readonly minzoom: number;
  readonly maxzoom: number;
  readonly attribution: string;
  readonly licence: string;
  readonly baked_on: string;
}

const bbox = manifest.bbox as number[];

export const basemapManifest: BasemapManifest = {
  ...manifest,
  // The JSON import types `bbox` as `number[]`, which loses the arity every
  // consumer depends on. Asserted once, here, rather than at each call site.
  bbox: [bbox[0] ?? 0, bbox[1] ?? 0, bbox[2] ?? 0, bbox[3] ?? 0],
};

/**
 * The archive's bounds, named.
 *
 * `bbox` is `[west, south, east, north]` and every consumer wants a different
 * pair of them in a different order — MapLibre's `maxBounds` wants
 * `[[w, s], [e, n]]`, a camera limit wants them one at a time. Indexing into a
 * four-element array at each call site is how a north/south swap gets written,
 * and a swapped bound is a map of nowhere that still renders.
 */
export const BASEMAP_BOUNDS = {
  west: basemapManifest.bbox[0],
  south: basemapManifest.bbox[1],
  east: basemapManifest.bbox[2],
  north: basemapManifest.bbox[3],
} as const;

/**
 * The URL the map style points at.
 *
 * The digest is in the query string so that a re-bake changes the URL. Without
 * it a browser that cached the previous archive would keep serving it against
 * a style built for the new one, and the failure would be a scattering of
 * missing tiles rather than anything that names itself.
 */
export const BASEMAP_URL = `/api/basemap?v=${basemapManifest.sha256.slice(0, 12)}`;
