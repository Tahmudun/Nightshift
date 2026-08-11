/**
 * The tile route, tested against a real file on disk.
 *
 * The interesting cases are the two failures, not the success. A clean clone
 * that never ran `make setup` and a cache holding the wrong archive both produce
 * a map that does not draw, and the difference between a useful afternoon and a
 * wasted one is entirely in what the response says.
 *
 * The fixture is a *sparse* file of the exact pinned length — `truncate`
 * extends with zeros without allocating them — so the size check runs against
 * the real number this build pins rather than against a relaxed test value. It
 * costs no disk and takes no time.
 */

import { mkdtemp, open, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { basemapManifest } from '@/lib/basemap';

import { GET, HEAD } from './route';

/** Recognisable bytes at the head of the archive, so a range can be checked. */
const HEAD_BYTES = Buffer.from('PMTiles\x03nightshift-fixture');

let directory: string;
let archive: string;

async function writeArchive(size: number): Promise<void> {
  const handle = await open(archive, 'w');
  try {
    await handle.write(HEAD_BYTES, 0, HEAD_BYTES.length, 0);
    await handle.truncate(size);
  } finally {
    await handle.close();
  }
}

function get(range?: string): Promise<Response> {
  const headers = range ? { range } : undefined;
  return GET(new Request('http://localhost/api/basemap', headers ? { headers } : {}));
}

/** Read a response body without leaving the file handle open. */
async function body(response: Response): Promise<Buffer> {
  return Buffer.from(await response.arrayBuffer());
}

beforeAll(async () => {
  directory = await mkdtemp(path.join(tmpdir(), 'nightshift-basemap-'));
  archive = path.join(directory, basemapManifest.filename);
  process.env.NIGHTSHIFT_BASEMAP_DIR = directory;
});

afterAll(async () => {
  delete process.env.NIGHTSHIFT_BASEMAP_DIR;
  await rm(directory, { recursive: true, force: true });
});

describe('when the archive has not been downloaded', () => {
  it('answers 503 and names the command that fixes it', async () => {
    await rm(archive, { force: true });
    const response = await get();
    expect(response.status).toBe(503);
    const text = await response.text();
    expect(text).toContain('make setup');
    expect(text).toContain(basemapManifest.filename);
  });

  it('does not answer 404, which pmtiles reports as a parse error', async () => {
    await rm(archive, { force: true });
    // A 404 body is HTML, pmtiles.js tries to read it as an archive header, and
    // the console shows a decoding failure with nothing about a missing file.
    expect((await get()).status).not.toBe(404);
  });

  it('answers HEAD the same way rather than pretending the file is there', async () => {
    await rm(archive, { force: true });
    expect((await HEAD()).status).toBe(503);
  });
});

describe('when the archive is the wrong one', () => {
  it('refuses a file of the wrong length and says both numbers', async () => {
    await writeArchive(basemapManifest.size_bytes - 1);
    const response = await get();
    expect(response.status).toBe(503);
    const text = await response.text();
    expect(text).toContain(String(basemapManifest.size_bytes));
    expect(text).toContain('make basemap');
  });
});

describe('when the archive is the pinned one', () => {
  beforeAll(async () => {
    await writeArchive(basemapManifest.size_bytes);
  });

  it('serves a byte range as 206 with the bytes asked for', async () => {
    const response = await get('bytes=0-6');
    expect(response.status).toBe(206);
    expect(response.headers.get('content-range')).toBe(`bytes 0-6/${basemapManifest.size_bytes}`);
    expect(response.headers.get('content-length')).toBe('7');
    expect((await body(response)).toString()).toBe('PMTiles');
  });

  it('serves a range from the middle of the archive', async () => {
    const response = await get('bytes=8-17');
    expect(response.status).toBe(206);
    expect((await body(response)).toString()).toBe('nightshift');
  });

  it('advertises range support, so a client does not fetch 91 MB per tile', async () => {
    const response = await get('bytes=0-0');
    expect(response.headers.get('accept-ranges')).toBe('bytes');
    await body(response);
  });

  it('answers 416 for bytes past the end, with the real length', async () => {
    const response = await get(`bytes=${basemapManifest.size_bytes}-`);
    expect(response.status).toBe(416);
    expect(response.headers.get('content-range')).toBe(`bytes */${basemapManifest.size_bytes}`);
  });

  it('reports the full length for a request with no range', async () => {
    const response = await get();
    expect(response.status).toBe(200);
    expect(response.headers.get('content-length')).toBe(String(basemapManifest.size_bytes));
    expect(response.headers.get('content-range')).toBeNull();
    await response.body?.cancel();
  });

  it('tags the response with the pinned digest', async () => {
    const response = await get('bytes=0-0');
    expect(response.headers.get('etag')).toBe(`"${basemapManifest.sha256}"`);
    await body(response);
  });

  it('carries the OpenStreetMap licence on every response', async () => {
    const response = await get('bytes=0-0');
    expect(response.headers.get('x-attribution')).toContain('ODbL');
    await body(response);
  });

  it('answers HEAD with the length and no body', async () => {
    const response = await HEAD();
    expect(response.status).toBe(200);
    expect(response.headers.get('content-length')).toBe(String(basemapManifest.size_bytes));
    expect(response.headers.get('accept-ranges')).toBe('bytes');
    expect(response.body).toBeNull();
  });
});
