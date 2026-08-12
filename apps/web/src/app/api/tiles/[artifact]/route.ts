/**
 * Serving the local tile archives to MapLibre, over byte ranges.
 *
 * The whole point of `city.md` §5.2 is that the tiles are files on this machine,
 * so this route is the shortest path from those files to the browser: two
 * archives, no tile server, no key, no network.
 *
 * One route rather than two because the archives differ in nothing this handler
 * cares about. Both are pmtiles, both are pinned by digest, both fail the same
 * two ways — absent, or the wrong file at the right name — and a second copy of
 * this logic is a second place for the range arithmetic to be subtly different.
 *
 * It is served by Next rather than by FastAPI on purpose. `make test-e2e` runs
 * the web app with no API behind it — the degraded path — and §5.6 requires a
 * usable product there. A basemap that came from the Python service would make
 * the degraded path a blank screen instead of a city with no jobs on it.
 *
 * **When an archive is absent this returns 503 and says what to run.** A clean
 * clone that skipped `make setup` is the expected way to arrive here, and the
 * alternative — a 404 that pmtiles.js reports as a parse error — is the "broken
 * map rather than a clear error message" §5.2 explicitly rules out.
 */

import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { Readable } from 'node:stream';

import { parseByteRange } from '@/lib/byteRange';
import { isTileArtifact, type TileArtifact, tileManifest } from '@/lib/tiles';
import { tilePath } from '@/lib/tiles.server';

// The archives are on local disk, outside the build. Rendering this route ahead
// of time would bake in whatever the filesystem looked like at build time.
export const dynamic = 'force-dynamic';

const CONTENT_TYPE = 'application/octet-stream';

/** Next 15 hands route params in as a promise. */
type Context = { readonly params: Promise<{ readonly artifact: string }> };

/**
 * Make a manifest string safe to put in a header value.
 *
 * HTTP header values are byte strings, and `new Response` throws — it does not
 * warn, and it does not truncate — on any character above 0xFF. The buildings
 * licence contains an em dash, so the first version of this route threw on every
 * successful tile request for that archive while the two failure paths, which
 * carry no such header, passed their tests.
 *
 * Percent-encoded rather than stripped: the value is a licence, and quietly
 * deleting characters from a licence to fit a transport constraint is the wrong
 * trade. `decodeURIComponent` returns the original text.
 */
function headerSafe(value: string): string {
  return value.replace(/[^ -~]/g, (character) => encodeURIComponent(character));
}

function unavailable(detail: string): Response {
  return new Response(`${detail}\n`, {
    status: 503,
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
  });
}

/**
 * A path segment this build does not publish is a 404 and stays one.
 *
 * The distinction matters: 503 means "this archive exists and your machine does
 * not have it yet", which is a sentence about `make setup`. A request for
 * `/api/tiles/../../etc/passwd` is not that, and answering it with instructions
 * would be nonsense. The narrowing also means `tilePath` never sees a string
 * that came from a URL.
 */
function resolveArtifact(raw: string): TileArtifact | null {
  return isTileArtifact(raw) ? raw : null;
}

export async function GET(request: Request, context: Context): Promise<Response> {
  const artifact = resolveArtifact((await context.params).artifact);
  if (!artifact) return new Response('No such tile archive.\n', { status: 404 });

  const manifest = tileManifest(artifact);
  const file = tilePath(artifact);

  let size: number;
  try {
    size = (await stat(file)).size;
  } catch {
    return unavailable(
      `No ${artifact} archive at ${file}.\n\n` +
        'Run `make setup` (or `make tiles`) once, with a network connection. ' +
        'It downloads the pinned NYC tile archives and nothing after it needs the network.',
    );
  }

  // One `stat` we already needed, used for a second thing. A file of the wrong
  // length is not the pinned archive, and serving it would produce a map that
  // half-renders — the digest is checked by `make tiles`, but a file swapped
  // out afterwards would otherwise go unnoticed until the tiles looked wrong.
  if (size !== manifest.size_bytes) {
    return unavailable(
      `The ${artifact} archive at ${file} is ${size} bytes; this build pins ` +
        `${manifest.size_bytes}.\n\n` +
        'Delete it and run `make tiles` to fetch the archive this commit describes.',
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
    // An archive is immutable for a given digest, and the URL carries that
    // digest (see `tileUrl`), so a stale cache entry can never be served
    // against a style that expects different bytes.
    'cache-control': 'public, max-age=31536000, immutable',
    etag: `"${manifest.sha256}"`,
    // A licence condition rather than a nicety: this is OpenStreetMap data for
    // the basemap and NYC Open Data for the buildings, and the terms travel
    // with every response as well as being drawn on the map.
    'x-attribution': headerSafe(manifest.licence),
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
export async function HEAD(_request: Request, context: Context): Promise<Response> {
  const artifact = resolveArtifact((await context.params).artifact);
  if (!artifact) return new Response(null, { status: 404 });

  const file = tilePath(artifact);
  try {
    const { size } = await stat(file);
    return new Response(null, {
      status: 200,
      headers: {
        'content-type': CONTENT_TYPE,
        'content-length': String(size),
        'accept-ranges': 'bytes',
        etag: `"${tileManifest(artifact).sha256}"`,
      },
    });
  } catch {
    return new Response(null, { status: 503 });
  }
}
