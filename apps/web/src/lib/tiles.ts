/**
 * The tile archives this build pins, and what it believes about each.
 *
 * There are two — `basemap` is streets, water and land, `buildings` is New
 * York's own measured footprints (§5.3) — and they are handled identically
 * because ADR 0022 gave them the same shape: baked by a maintainer script,
 * published as a release asset, pinned by digest, downloaded once by
 * `make tiles`, served from local disk. The Python side keeps the same pair in
 * `nightshift.domain.basemap.ARTIFACTS`.
 *
 * The manifests are imported rather than read at runtime, deliberately. They are
 * committed files that change only when somebody re-bakes, so resolving them
 * through the filesystem would buy nothing and cost the one thing that actually
 * bites here: a repo-root lookup. `process.cwd()` is `apps/web` under
 * `next dev` and something else under `next start`, and a path that resolves
 * differently depending on how the server was launched is exactly the bug that
 * only shows up on the machine you are not using. Importing makes the bundler
 * resolve the path once, at build time, and typechecks the shape for free.
 *
 * **Nothing here may import a node module.** The map component is a client
 * component and it needs the bounds and the URLs, so a single `node:path`
 * import in this file fails the build with a stack trace that names webpack
 * rather than the cause. Anything that touches the filesystem lives in
 * `tiles.server.ts`, which only the route handler imports.
 */

// Reaches out of `apps/web`, which nothing else here does. The manifests live at
// the repository root because both toolchains read them — Python writes them,
// TypeScript renders from them — and inventing a shared package for two JSON
// files would cost more than the odd-looking path does.
import basemapJson from '../../../../data/basemap.manifest.json';
import buildingsJson from '../../../../data/buildings.manifest.json';

/** The archives `make tiles` fetches. Also the only legal path segments. */
export const TILE_ARTIFACTS = ['basemap', 'buildings'] as const;

export type TileArtifact = (typeof TILE_ARTIFACTS)[number];

export interface TileManifest {
  readonly filename: string;
  readonly url: string;
  readonly sha256: string;
  readonly size_bytes: number;
  /** The bake date, `YYYYMMDD`. Carried in `filename` too, so a re-bake moves the path. */
  readonly protomaps_build: string;
  /** What produced the tiles: a Protomaps build for the basemap, `nyc-open-data:<dataset>` for buildings. */
  readonly protomaps_version: string;
  /**
   * When the *source data* was current.
   *
   * The key is a leftover from the basemap being the only artifact, and it is
   * kept rather than renamed because the Python model, the committed basemap
   * manifest and ADR 0022 all use it. The value is honest for both — OSM's
   * replication timestamp, or the moment the NYC export was pulled.
   */
  readonly osm_replication_time: string;
  readonly bbox: readonly [number, number, number, number];
  readonly minzoom: number;
  readonly maxzoom: number;
  readonly attribution: string;
  readonly licence: string;
  readonly baked_on: string;
}

/**
 * The buildings census, which exists so that §5.3's promise is auditable.
 *
 * *"A footprint missing a height gets a documented default and is recorded as
 * having taken it."* This is that record: how many structures the city
 * publishes, and how many of them arrive with no measured roof height. The
 * coverage page can quote the fraction rather than implying the whole skyline
 * was surveyed.
 */
export interface BuildingsManifest extends TileManifest {
  readonly structures: number;
  readonly structures_without_height: number;
}

function withTypedBbox<T extends { bbox: number[] }>(
  manifest: T,
): Omit<T, 'bbox'> & {
  bbox: readonly [number, number, number, number];
} {
  // The JSON import types `bbox` as `number[]`, which loses the arity every
  // consumer depends on. Asserted once, here, rather than at each call site.
  const [west = 0, south = 0, east = 0, north = 0] = manifest.bbox;
  return { ...manifest, bbox: [west, south, east, north] as const };
}

export const basemapManifest: TileManifest = withTypedBbox(basemapJson);

export const buildingsManifest: BuildingsManifest = withTypedBbox(buildingsJson);

const MANIFESTS: Readonly<Record<TileArtifact, TileManifest>> = {
  basemap: basemapManifest,
  buildings: buildingsManifest,
};

/** Narrow an arbitrary path segment to an artifact this build knows. */
export function isTileArtifact(value: string): value is TileArtifact {
  return (TILE_ARTIFACTS as readonly string[]).includes(value);
}

export function tileManifest(artifact: TileArtifact): TileManifest {
  return MANIFESTS[artifact];
}

/**
 * The URL the map style points at.
 *
 * The digest is in the query string so that a re-bake changes the URL. Without
 * it a browser that cached the previous archive would keep serving it against a
 * style built for the new one, and the failure would be a scattering of missing
 * tiles rather than anything that names itself.
 */
export function tileUrl(artifact: TileArtifact): string {
  return `/api/tiles/${artifact}?v=${MANIFESTS[artifact].sha256.slice(0, 12)}`;
}

export const BASEMAP_URL = tileUrl('basemap');
export const BUILDINGS_URL = tileUrl('buildings');

/**
 * The basemap archive's bounds, named.
 *
 * `bbox` is `[west, south, east, north]` and every consumer wants a different
 * pair of them in a different order — MapLibre's `maxBounds` wants
 * `[[w, s], [e, n]]`, a camera limit wants them one at a time. Indexing into a
 * four-element array at each call site is how a north/south swap gets written,
 * and a swapped bound is a map of nowhere that still renders.
 *
 * The basemap's, not the buildings': the two differ, because the buildings
 * archive stops at the city line and the basemap carries the harbour and the
 * far shore. Bounding the camera by the buildings would cut off the water the
 * skyline is read against.
 */
export const BASEMAP_BOUNDS = {
  west: basemapManifest.bbox[0],
  south: basemapManifest.bbox[1],
  east: basemapManifest.bbox[2],
  north: basemapManifest.bbox[3],
} as const;
