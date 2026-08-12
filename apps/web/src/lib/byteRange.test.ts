/**
 * The `Range` parser, and the two ways of being wrong that look alike.
 *
 * A malformed range and an unsatisfiable one are both "the client asked for
 * something odd", and collapsing them is the mistake this file exists to
 * prevent: the first should be ignored and answered with the whole file, the
 * second should be answered with 416. Getting it backwards means either a 416
 * for a client that would have coped, or a 200 with 91 MB for a client that
 * asked for bytes past the end.
 */

import { describe, expect, it } from 'vitest';

import { parseByteRange } from './byteRange';

const SIZE = 1000;

describe('no range at all', () => {
  it.each([null, undefined, ''])('%p asks for the whole thing', (header) => {
    expect(parseByteRange(header, SIZE)).toEqual({ kind: 'full' });
  });
});

describe('ranges that are honoured', () => {
  it('reads a closed range inclusively at both ends', () => {
    // The off-by-one that matters: bytes=0-99 is 100 bytes, and pmtiles reads
    // fixed-width headers, so getting this wrong corrupts the archive's
    // directory rather than showing a seam.
    expect(parseByteRange('bytes=0-99', SIZE)).toEqual({ kind: 'partial', start: 0, end: 99 });
  });

  it('reads an open-ended range to the last byte', () => {
    expect(parseByteRange('bytes=900-', SIZE)).toEqual({ kind: 'partial', start: 900, end: 999 });
  });

  it('reads a suffix range as the last N bytes', () => {
    expect(parseByteRange('bytes=-100', SIZE)).toEqual({ kind: 'partial', start: 900, end: 999 });
  });

  it('clamps a suffix longer than the file to the whole file', () => {
    expect(parseByteRange('bytes=-5000', SIZE)).toEqual({ kind: 'partial', start: 0, end: 999 });
  });

  it('clamps an end past the last byte rather than refusing', () => {
    expect(parseByteRange('bytes=990-5000', SIZE)).toEqual({
      kind: 'partial',
      start: 990,
      end: 999,
    });
  });

  it('reads a single byte', () => {
    expect(parseByteRange('bytes=5-5', SIZE)).toEqual({ kind: 'partial', start: 5, end: 5 });
  });

  it('reads the last byte', () => {
    expect(parseByteRange('bytes=999-', SIZE)).toEqual({ kind: 'partial', start: 999, end: 999 });
  });

  it('ignores case and surrounding whitespace', () => {
    expect(parseByteRange('  BYTES=0-9  ', SIZE)).toEqual({ kind: 'partial', start: 0, end: 9 });
  });
});

describe('ranges that are unsatisfiable', () => {
  it('refuses a start at the end of the file', () => {
    expect(parseByteRange('bytes=1000-1099', SIZE)).toEqual({ kind: 'unsatisfiable' });
  });

  it('refuses a start past the end of the file', () => {
    expect(parseByteRange('bytes=5000-', SIZE)).toEqual({ kind: 'unsatisfiable' });
  });

  it('refuses a zero-length suffix', () => {
    // `bytes=-0` asks for the last nothing bytes. RFC 9110 names it
    // unsatisfiable rather than empty.
    expect(parseByteRange('bytes=-0', SIZE)).toEqual({ kind: 'unsatisfiable' });
  });

  it('refuses any range into an empty file', () => {
    expect(parseByteRange('bytes=0-99', 0)).toEqual({ kind: 'unsatisfiable' });
    expect(parseByteRange('bytes=-1', 0)).toEqual({ kind: 'unsatisfiable' });
  });
});

describe('ranges that are ignored rather than refused', () => {
  it.each([
    ['items=0-99', 'a unit we do not speak'],
    ['bytes=abc-def', 'not numbers'],
    ['bytes=12abc-99', 'numbers with a tail'],
    ['bytes=', 'no spec at all'],
    ['bytes=-', 'neither end given'],
    ['0-99', 'no unit'],
    ['bytes 0-99', 'no equals sign'],
    ['bytes=99-0', 'backwards'],
    ['bytes=1.5-9', 'not an integer'],
    ['bytes=-1e3', 'exponent notation'],
  ])('%s (%s) falls back to the whole file', (header) => {
    expect(parseByteRange(header, SIZE)).toEqual({ kind: 'full' });
  });

  it('falls back rather than answering only the first of several ranges', () => {
    // Answering one range of a multi-range request with a plain 206 is the
    // dangerous version of this: the client believes it received the bytes it
    // asked for, and the rest are silently absent.
    expect(parseByteRange('bytes=0-99,200-299', SIZE)).toEqual({ kind: 'full' });
  });

  it('refuses to be talked past a safe integer', () => {
    expect(parseByteRange('bytes=99999999999999999999-', SIZE)).toEqual({ kind: 'full' });
  });
});
