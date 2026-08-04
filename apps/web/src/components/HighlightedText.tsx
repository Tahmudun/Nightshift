'use client';

/**
 * The resume, with the words each claim came from marked in it.
 *
 * Spans overlap by design — a project's span contains the skills inside it — so
 * this cannot wrap each span in turn. It cuts the text at every boundary
 * instead, and asks of each resulting segment which spans cover it. That is the
 * only version that renders every character exactly once, which is the property
 * `HighlightedText.test.tsx` pins down: **the text on screen must be the text
 * that was read**, not a reconstruction of it.
 *
 * No `dangerouslySetInnerHTML` anywhere. This is a person's resume; it goes in
 * as text nodes.
 */

import { Fragment } from 'react';

export interface Span {
  readonly id: string;
  readonly start: number;
  readonly end: number;
}

interface Segment {
  readonly start: number;
  readonly end: number;
  readonly covering: readonly string[];
}

/**
 * Cut `text` at every span boundary and label each piece with what covers it.
 *
 * Exported for its own sake: the segmentation is the part that can be subtly
 * wrong, and a wrong segmentation still renders something plausible.
 */
export function segment(text: string, spans: readonly Span[]): Segment[] {
  // A span whose bounds fall outside the text would highlight nothing while
  // still asserting something. Dropped rather than clamped — clamping would
  // move the claim onto words it did not come from.
  const usable = spans.filter(
    (span) => span.start >= 0 && span.end <= text.length && span.end > span.start,
  );

  const boundaries = new Set<number>([0, text.length]);
  for (const span of usable) {
    boundaries.add(span.start);
    boundaries.add(span.end);
  }
  const ordered = [...boundaries].sort((a, b) => a - b);

  const segments: Segment[] = [];
  for (let index = 0; index < ordered.length - 1; index += 1) {
    const start = ordered[index]!;
    const end = ordered[index + 1]!;
    segments.push({
      start,
      end,
      covering: usable.filter((span) => span.start <= start && span.end >= end).map((s) => s.id),
    });
  }
  return segments;
}

export function HighlightedText({
  text,
  spans,
  activeId,
}: {
  readonly text: string;
  readonly spans: readonly Span[];
  readonly activeId: string | null;
}) {
  return (
    <pre
      data-testid="highlighted-text"
      className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-paper"
    >
      {segment(text, spans).map((piece) => {
        const body = text.slice(piece.start, piece.end);
        if (piece.covering.length === 0) {
          return <Fragment key={piece.start}>{body}</Fragment>;
        }
        const isActive = activeId !== null && piece.covering.includes(activeId);
        return (
          <mark
            key={piece.start}
            id={isActive ? `span-${activeId}` : undefined}
            data-active={isActive}
            className={
              isActive
                ? 'bg-signal-900 text-paper ring-1 ring-signal-400'
                : 'bg-signal-900/50 text-paper'
            }
          >
            {body}
          </mark>
        );
      })}
    </pre>
  );
}
