import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SourceKind } from './SourceHealthTable';
import { CAPTURE_SOURCE_TYPE } from '@/lib/schemas';

/**
 * What the source health table calls each kind of source.
 *
 * This column was a binary — `fixture` or `live` — which was true while there
 * were two kinds of source and false the day there were three. `make seed`
 * now plants a captured posting (M5a), so `/operate` has a `manual_capture`
 * row in it, and the binary labelled it **live**: the same word it gives
 * `greenhouse`, about the one source in the table that is never read twice.
 *
 * That is I7 failing in the direction that is hardest to notice, and it is the
 * exact failure the job page's "added by hand" badge exists to prevent one
 * screen over.
 */
describe('SourceKind', () => {
  it('labels a committed fixture as one', () => {
    render(<SourceKind sourceType="fixture" />);
    expect(screen.getByText(/committed fixture/i)).toBeVisible();
  });

  it('labels a polled board as live', () => {
    render(<SourceKind sourceType="ats_greenhouse" />);
    expect(screen.getByText(/^live$/i)).toBeVisible();
  });

  it('never calls a captured posting live, and says nothing re-reads it', () => {
    render(<SourceKind sourceType={CAPTURE_SOURCE_TYPE} />);
    expect(screen.queryByText(/^live$/i)).toBeNull();
    expect(screen.getByText(/added by hand/i)).toBeVisible();
  });

  it('falls back to live for a source type it has never heard of', () => {
    // Deliberate: `source_type` crosses the wire as a bare string, so an
    // unknown value is a real possibility and rendering nothing at all would
    // leave a blank cell that reads as a missing source rather than a new one.
    render(<SourceKind sourceType="something_new" />);
    expect(screen.getByText(/^live$/i)).toBeVisible();
  });
});
