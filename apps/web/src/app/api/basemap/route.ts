/**
 * Serving the local basemap archive to MapLibre, over byte ranges.
 *
 * The whole point of `city.md` §5.2 is that the tiles are a file on this
 * machine, so this route is the shortest path from that file to the browser:
 * one archive, no tile server, no key, no network.
 *
 * It is served by Next rather than by FastAPI on purpose. `make test-e2e` runs
 * the web app with no API behind it — the degraded path — and §5.6 requires a
 * usable product there. A basemap that came from the Python service would make
 * the degraded path a blank screen instead of a city with no jobs on it.
 *
 * **When the archive is absent this returns 503 and says what to run.** A clean
 * clone that skipped `make setup` is the expected way to arrive here, and the
 * alternative — a 404 that pmtiles.js reports as a parse error — is the "broken
 * map rather than a clear error message" §5.2 explicitly rules out.
 */

import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { Readable } from 'node:stream';

import { basemapManifest } from '@/lib/basemap';
import { basemapPath } from '@/lib/basemap.server';
import { parseByteRange } from '@/lib/byteRange';

// The archive is on local disk, outside the build. Rendering this route ahead
// of time would bake in whatever the filesystem looked like at build time.
export const dynamic = 'force-dynamic';

const CONTENT_TYPE = 'application/octet-stream';

function unavailable(detail: string): Response {
  return new Response(`${detail}\n`, {
    status: 503,
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
  });
}

export async function GET(request: Request): Promise<Response> {
  const file = basemapPath();

  let size: number;
  try {
    size = (await stat(file)).size;
  } catch {
    return unavailable(
      `No basemap archive at ${file}.\n\n` +
        'Run `make setup` (or `make basemap`) once, with a network connection. ' +
        'It downloads ~91 MB of NYC vector tiles and nothing after it needs the network.',
    );
  }

  // One `stat` we already needed, used for a second thing. A file of the wrong
  // length is not the pinned archive, and serving it would produce a map that
  // half-renders — the digest is checked by `make basemap`, but a file swapped
  // out afterwards would otherwise go unnoticed until the tiles looked wrong.
  if (size !== basemapManifest.size_bytes) {
    return unavailable(
      `The basemap at ${file} is ${size} bytes; this build pins ` +
        `${basemapManifest.size_bytes}.\n\n` +
        'Delete it and run `make basemap` to fetch the archive this commit describes.',
    );
  }

  const range = parseByteRange(request.headers.get('range'), size);

  if (range.kind === 'unsatisfiable') {
    return new Response(null, {
      status: 416,
      headers: { 'accept-ranges': 'bytes', 'content-range': `bytes */${size}` },
    });
  }

  const [start, end] = range.kind === 'partial' ? [range.start, range.end] : [0, size - 1];
  const length = end - start + 1;

  const headers: Record<string, string> = {
    'content-type': CONTENT_TYPE,
    'content-length': String(length),
    'accept-ranges': 'bytes',
    // The archive is immutable for a given digest, and the URL carries that
    // digest (see BASEMAP_URL), so a stale cache entry can never be served
    // against a style that expects different bytes.
    'cache-control': 'public, max-age=31536000, immutable',
    etag: `"${basemapManifest.sha256}"`,
    // A licence condition rather than a nicety: this is OpenStreetMap data, and
    // it travels with every response as well as being drawn on the map.
    'x-attribution': basemapManifest.licence,
  };
  if (range.kind === 'partial') {
    headers['content-range'] = `bytes ${start}-${end}/${size}`;
  }

  const stream = Readable.toWeb(
    createReadStream(file, { start, end }),
  ) as unknown as ReadableStream<Uint8Array>;

  return new Response(stream, { status: range.kind === 'partial' ? 206 : 200, headers });
}

/**
 * MapLibre's pmtiles client probes with HEAD in some paths, and a HEAD that
 * 405s makes it fall back to fetching the whole archive.
 */
export async function HEAD(): Promise<Response> {
  const file = basemapPath();
  try {
    const { size } = await stat(file);
    return new Response(null, {
      status: 200,
      headers: {
        'content-type': CONTENT_TYPE,
        'content-length': String(size),
        'accept-ranges': 'bytes',
        etag: `"${basemapManifest.sha256}"`,
      },
    });
  } catch {
    return new Response(null, { status: 503 });
  }
}
