/**
 * Where the archives are on this machine. Server side only.
 *
 * Split out of `tiles.ts` rather than living beside it, because that file is
 * imported by the map component and a client bundle cannot contain `node:os`.
 * The split is enforced by the build: reuniting them fails `next build` with a
 * webpack stack trace that names neither file.
 *
 * `NIGHTSHIFT_BASEMAP_DIR` is read by the Python side too — one setting, two
 * runtimes, so moving the cache cannot leave `make tiles` finding it and the
 * browser not. It keeps its basemap-era name because it is a committed setting
 * in `.env.example` that both languages parse, and both archives live in the
 * one directory.
 */

import { homedir } from 'node:os';
import path from 'node:path';

import { type TileArtifact, tileManifest } from './tiles';

/** The directory `make tiles` downloads into. */
export function tileCacheDir(): string {
  const override = process.env.NIGHTSHIFT_BASEMAP_DIR;
  if (override) return override;
  return path.join(homedir(), '.cache', 'nightshift', 'basemap');
}

/** The full path to the archive this build expects for `artifact`. */
export function tilePath(artifact: TileArtifact): string {
  // `path.join` with a filename that came from a committed manifest, never from
  // the request — the route narrows the URL segment to `TileArtifact` before it
  // gets here, so a `..` in the path cannot reach this function.
  return path.join(tileCacheDir(), tileManifest(artifact).filename);
}
