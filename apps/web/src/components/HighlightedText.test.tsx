import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HighlightedText } from './HighlightedText';

const PROJECT_LINE = 'Transit Delay Tracker - Python, PostgreSQL';

describe('HighlightedText', () => {
  it('renders every character of the text exactly once, even when spans overlap', () => {
    // The property that matters. Spans overlap by design — a project's span
    // contains the skills inside it — and the obvious implementation (wrap each
    // span in turn) either duplicates the overlap or drops it. Either way the
    // resume on screen stops being the resume that was read, which is the one
    // thing this pane exists to guarantee.
    render(
      <HighlightedText
        text={PROJECT_LINE}
        spans={[
          { id: 'project', start: 0, end: 41 },
          { id: 'python', start: 24, end: 30 },
          { id: 'postgres', start: 32, end: 42 },
        ]}
        activeId="python"
      />,
    );
    expect(screen.getByTestId('highlighted-text').textContent).toBe(PROJECT_LINE);
  });

  it('renders the plain text when nothing is highlighted', () => {
    render(<HighlightedText text={PROJECT_LINE} spans={[]} activeId={null} />);
    expect(screen.getByTestId('highlighted-text').textContent).toBe(PROJECT_LINE);
  });

  it('keeps the text whole for a span starting at the first character', () => {
    render(
      <HighlightedText
        text={PROJECT_LINE}
        spans={[{ id: 'a', start: 0, end: 7 }]}
        activeId={null}
      />,
    );
    expect(screen.getByTestId('highlighted-text').textContent).toBe(PROJECT_LINE);
  });

  it('keeps the text whole for a span ending at the last character', () => {
    render(
      <HighlightedText
        text={PROJECT_LINE}
        spans={[{ id: 'a', start: 32, end: PROJECT_LINE.length }]}
        activeId={null}
      />,
    );
    expect(screen.getByTestId('highlighted-text').textContent).toBe(PROJECT_LINE);
  });

  it('keeps the text whole for two adjacent spans with no gap', () => {
    render(
      <HighlightedText
        text={PROJECT_LINE}
        spans={[
          { id: 'a', start: 0, end: 21 },
          { id: 'b', start: 21, end: PROJECT_LINE.length },
        ]}
        activeId={null}
      />,
    );
    expect(screen.getByTestId('highlighted-text').textContent).toBe(PROJECT_LINE);
  });

  it('gives the active span a treatment the inactive ones do not have', () => {
    render(
      <HighlightedText
        text={PROJECT_LINE}
        spans={[
          { id: 'python', start: 24, end: 30 },
          { id: 'postgres', start: 32, end: 42 },
        ]}
        activeId="python"
      />,
    );
    const active = screen.getByTestId('highlighted-text').querySelectorAll('[data-active="true"]');
    expect(active).toHaveLength(1);
    expect(active[0]).toHaveTextContent('Python');
  });

  it('marks every segment covered by the active span, not only the first', () => {
    // An active span that another span cuts in two must still read as one
    // highlight. Without this, clicking a project lights up its first three
    // words and stops, which looks like the claim covering less than it does.
    render(
      <HighlightedText
        text={PROJECT_LINE}
        spans={[
          { id: 'project', start: 0, end: PROJECT_LINE.length },
          { id: 'python', start: 24, end: 30 },
        ]}
        activeId="project"
      />,
    );
    const segments = screen
      .getByTestId('highlighted-text')
      .querySelectorAll('[data-active="true"]');
    expect(segments.length).toBeGreaterThan(1);
    expect([...segments].map((node) => node.textContent).join('')).toBe(PROJECT_LINE);
  });

  it('highlights nothing at all for a span that runs past the end of the text', () => {
    // Dropped, not clamped. Clamping would move the claim onto whatever words
    // happen to be in range, which reads as evidence and is not.
    //
    // The obvious assertion here — that `textContent` is still 'short' — cannot
    // fail: an out-of-range slice is the empty string either way. Mutating the
    // range check proved it, so the assertion is on the marks instead.
    render(<HighlightedText text="short" spans={[{ id: 'a', start: 2, end: 99 }]} activeId="a" />);
    const pane = screen.getByTestId('highlighted-text');
    expect(pane.textContent).toBe('short');
    expect(pane.querySelectorAll('mark')).toHaveLength(0);
  });
});
