/**
 * Parsing a `Range` header, because the basemap is 91 MB and nobody wants it all.
 *
 * The pmtiles protocol is byte ranges over one archive: MapLibre asks for a
 * header, then a directory, then a handful of kilobytes per tile. A server that
 * ignores `Range` technically still works and sends 91 MB per tile, which is
 * not a subtle failure but is a silent one — the map appears, slowly, and
 * nothing says why.
 *
 * Kept out of the route handler so it can be tested as what it is: string
 * parsing with a lot of edge cases and no I/O.
 *
 * RFC 9110 §14 shapes the two "ignore it" branches. A `Range` in units we do
 * not speak, or one that is syntactically broken, is not an error — a server
 * MAY ignore it and send the whole representation, which is a better outcome
 * than a 400 for a client that would have coped. An *unsatisfiable* range is
 * different: the client asked a coherent question about bytes that do not
 * exist, and 416 is the honest answer.
 */

export type ByteRange =
  | { readonly kind: 'full' }
  /** Inclusive on both ends, as `Content-Range` reports them. */
  | { readonly kind: 'partial'; readonly start: number; readonly end: number }
  | { readonly kind: 'unsatisfiable' };

const FULL: ByteRange = { kind: 'full' };
const UNSATISFIABLE: ByteRange = { kind: 'unsatisfiable' };

/** Digits only. `parseInt` would accept `12abc`, and `Number('')` is 0. */
function digits(text: string): number | null {
  if (!/^\d+$/.test(text)) return null;
  const value = Number(text);
  return Number.isSafeInteger(value) ? value : null;
}

export function parseByteRange(header: string | null | undefined, size: number): ByteRange {
  if (!header) return FULL;

  const match = /^bytes=(.*)$/i.exec(header.trim());
  if (!match?.[1]) return FULL;

  const spec = match[1].trim();
  // Multiple ranges require a multipart/byteranges response. Serving the whole
  // archive is a correct answer to a request we choose not to satisfy piecewise,
  // and no pmtiles client asks for one.
  if (spec.includes(',')) return FULL;

  const parts = /^(\d*)-(\d*)$/.exec(spec);
  if (!parts) return FULL;

  const [, rawStart, rawEnd] = parts;
  if (rawStart === '' && rawEnd === '') return FULL;

  // `bytes=-N` — the last N bytes. Nothing in pmtiles.js uses it; it costs four
  // lines and its absence would be a spec violation waiting for a client that
  // does.
  if (rawStart === '') {
    const suffix = digits(rawEnd ?? '');
    if (suffix === null) return FULL;
    if (suffix === 0 || size === 0) return UNSATISFIABLE;
    return { kind: 'partial', start: Math.max(0, size - suffix), end: size - 1 };
  }

  const start = digits(rawStart ?? '');
  if (start === null) return FULL;
  if (start >= size) return UNSATISFIABLE;

  if (rawEnd === '') return { kind: 'partial', start, end: size - 1 };

  const end = digits(rawEnd ?? '');
  if (end === null) return FULL;
  // A backwards range is malformed rather than unsatisfiable, so it is ignored.
  if (end < start) return FULL;

  return { kind: 'partial', start, end: Math.min(end, size - 1) };
}
