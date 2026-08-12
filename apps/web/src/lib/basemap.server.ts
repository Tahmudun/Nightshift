/**
 * Where the archive is on this machine. Server side only.
 *
 * Split out of `basemap.ts` rather than living beside it, because that file is
 * imported by the map component and a client bundle cannot contain `node:os`.
 * The split is enforced by the build: reuniting them fails `next build` with a
 * webpack stack trace that names neither file.
 *
 * `NIGHTSHIFT_BASEMAP_DIR` is read by the Python side too — one setting, two
 * runtimes, so moving the cache cannot leave `make basemap` finding it and the
 * browser not.
 */

import { homedir } from 'node:os';
import path from 'node:path';

import { basemapManifest } from './basemap';

/** The directory `make basemap` downloads into. */
export function basemapCacheDir(): string {
  const override = process.env.NIGHTSHIFT_BASEMAP_DIR;
  if (override) return override;
  return path.join(homedir(), '.cache', 'nightshift', 'basemap');
}

/** The full path to the archive this build expects. */
export function basemapPath(): string {
  return path.join(basemapCacheDir(), basemapManifest.filename);
}
