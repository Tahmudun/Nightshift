/**
 * The tile route, tested against real files on disk, for both archives.
 *
 * The interesting cases are the two failures, not the success. A clean clone
 * that never ran `make setup` and a cache holding the wrong archive both produce
 * a map that does not draw, and the difference between a useful afternoon and a
 * wasted one is entirely in what the response says.
 *
 * Every case runs for `basemap` and for `buildings`. They share a handler, which
 * is exactly why: a shared handler that was only ever exercised through one of
 * its inputs is how the second archive gets a message naming the first one's
 * filename.
 *
 * The fixture is a *sparse* file of the exact pinned length — `truncate` extends
 * with zeros without allocating them — so the size check runs against the real
 * number this build pins rather than against a relaxed test value. It costs no
 * disk and takes no time.
 */

import { mkdtemp, open, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';

import { TILE_ARTIFACTS, type TileArtifact, tileManifest } from '@/lib/tiles';

import { GET, HEAD } from './route';

/** Recognisable bytes at the head of the archive, so a range can be checked. */
const HEAD_BYTES = Buffer.from('PMTiles\x03nightshift-fixture');

let directory: string;

function archivePath(artifact: TileArtifact): string {
  return path.join(directory, tileManifest(artifact).filename);
}

async function writeArchive(artifact: TileArtifact, size: number): Promise<void> {
  const handle = await open(archivePath(artifact), 'w');
  try {
    await handle.write(HEAD_BYTES, 0, HEAD_BYTES.length, 0);
    await handle.truncate(size);
  } finally {
    await handle.close();
  }
}

function context(artifact: string): { params: Promise<{ artifact: string }> } {
  return { params: Promise.resolve({ artifact }) };
}

function get(artifact: string, range?: string): Promise<Response> {
  const headers = range ? { range } : undefined;
  return GET(
    new Request(`http://localhost/api/tiles/${artifact}`, headers ? { headers } : {}),
    context(artifact),
  );
}

function head(artifact: string): Promise<Response> {
  return HEAD(new Request(`http://localhost/api/tiles/${artifact}`), context(artifact));
}

/** Read a response body without leaving the file handle open. */
async function body(response: Response): Promise<Buffer> {
  return Buffer.from(await response.arrayBuffer());
}

beforeAll(async () => {
  directory = await mkdtemp(path.join(tmpdir(), 'nightshift-tiles-'));
  process.env.NIGHTSHIFT_BASEMAP_DIR = directory;
});

afterAll(async () => {
  delete process.env.NIGHTSHIFT_BASEMAP_DIR;
  await rm(directory, { recursive: true, force: true });
});

describe('a path segment this build does not publish', () => {
  it('is a 404 rather than instructions for fetching it', async () => {
    // 503 means "this archive exists and your machine does not have it yet",
    // which is a sentence about `make setup`. This is not that.
    expect((await get('streets')).status).toBe(404);
    expect((await head('streets')).status).toBe(404);
  });

  it('does not reach the filesystem with a traversal', async () => {
    const response = await get('../../../../etc/passwd');
    expect(response.status).toBe(404);
    expect(await response.text()).not.toContain('root:');
  });
});

describe.each(TILE_ARTIFACTS)('the %s archive', (artifact) => {
  const manifest = tileManifest(artifact);

  describe('when it has not been downloaded', () => {
    beforeEach(async () => {
      await rm(archivePath(artifact), { force: true });
    });

    it('answers 503 and names the command that fixes it', async () => {
      const response = await get(artifact);
      expect(response.status).toBe(503);
      const text = await response.text();
      expect(text).toContain('make setup');
      expect(text).toContain(manifest.filename);
      // The message must name *this* archive. A shared handler that reports the
      // basemap's filename for a missing buildings archive sends the reader to
      // check a file that is already there.
      expect(text).toContain(artifact);
    });

    it('does not answer 404, which pmtiles reports as a parse error', async () => {
      // A 404 body is HTML, pmtiles.js tries to read it as an archive header,
      // and the console shows a decoding failure with nothing about a missing
      // file. The segment is a known one, so absence is 503.
      expect((await get(artifact)).status).not.toBe(404);
    });

    it('answers HEAD the same way rather than pretending the file is there', async () => {
      expect((await head(artifact)).status).toBe(503);
    });
  });

  describe('when it is the wrong file', () => {
    it('refuses a file of the wrong length and says both numbers', async () => {
      await writeArchive(artifact, manifest.size_bytes - 1);
      const response = await get(artifact);
      expect(response.status).toBe(503);
      const text = await response.text();
      expect(text).toContain(String(manifest.size_bytes));
      expect(text).toContain('make tiles');
    });
  });

  describe('when it is the pinned one', () => {
    beforeEach(async () => {
      await writeArchive(artifact, manifest.size_bytes);
    });

    it('serves a byte range as 206 with the bytes asked for', async () => {
      const response = await get(artifact, 'bytes=0-6');
      expect(response.status).toBe(206);
      expect(response.headers.get('content-range')).toBe(`bytes 0-6/${manifest.size_bytes}`);
      expect(response.headers.get('content-length')).toBe('7');
      expect((await body(response)).toString()).toBe('PMTiles');
    });

    it('serves a range from the middle of the archive', async () => {
      const response = await get(artifact, 'bytes=8-17');
      expect(response.status).toBe(206);
      expect((await body(response)).toString()).toBe('nightshift');
    });

    it('advertises range support, so a client does not fetch the lot per tile', async () => {
      const response = await get(artifact, 'bytes=0-0');
      expect(response.headers.get('accept-ranges')).toBe('bytes');
      await body(response);
    });

    it('answers 416 for bytes past the end, with the real length', async () => {
      const response = await get(artifact, `bytes=${manifest.size_bytes}-`);
      expect(response.status).toBe(416);
      expect(response.headers.get('content-range')).toBe(`bytes */${manifest.size_bytes}`);
    });

    it('reports the full length for a request with no range', async () => {
      const response = await get(artifact);
      expect(response.status).toBe(200);
      expect(response.headers.get('content-length')).toBe(String(manifest.size_bytes));
      expect(response.headers.get('content-range')).toBeNull();
      await response.body?.cancel();
    });

    it('tags the response with the pinned digest', async () => {
      const response = await get(artifact, 'bytes=0-0');
      expect(response.headers.get('etag')).toBe(`"${manifest.sha256}"`);
      await body(response);
    });

    it('carries its own licence on every response', async () => {
      // Two archives, two sets of terms, and the response must carry the one
      // that applies to the bytes in it.
      //
      // Decoded, because a header value is a byte string and the NYC licence
      // contains an em dash. Before this was handled, `new Response` threw on
      // every *successful* buildings tile — while both failure paths, which
      // carry no such header, passed. A 500 on the happy path only.
      const response = await get(artifact, 'bytes=0-0');
      const sent = response.headers.get('x-attribution') ?? '';
      expect(decodeURIComponent(sent)).toBe(manifest.licence);
      expect(manifest.licence.length).toBeGreaterThan(0);
      await body(response);
    });

    it('answers HEAD with the length and no body', async () => {
      const response = await head(artifact);
      expect(response.status).toBe(200);
      expect(response.headers.get('content-length')).toBe(String(manifest.size_bytes));
      expect(response.headers.get('accept-ranges')).toBe('bytes');
      expect(response.body).toBeNull();
    });
  });
});
