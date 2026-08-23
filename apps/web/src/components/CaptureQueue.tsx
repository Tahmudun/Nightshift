'use client';

/**
 * What is waiting for you to decide.
 *
 * M5d gave a reader's own Claude a `capture_posting` tool, and gave its result
 * a sentence pointing at `/operate/capture` — *"the reader confirms or
 * discards it at `review_url`"*. That screen was a paste box. A capture made
 * in Claude Desktop had a row in the database, a status of `pending`, an
 * origin of `linkedin`, and **no way to be looked at**: the review form only
 * ever showed the capture the current browser tab had just created.
 *
 * ADR 0039 §3 calls the pending set *"a review queue — a to-do list"*, and
 * argues from there that a repeat paste must not make a second item on it.
 * This is the list that claim is about.
 *
 * **Two things it says out loud rather than by implication.** A row names who
 * read each field, because a capture that arrived from an assistant was read
 * by something with a different failure mode than the parser (ADR 0039 §2).
 * And the empty state names the signed-in account, because a token minted for
 * one account with a browser signed into another is a working setup in which
 * every capture lands in a queue nobody is looking at — and an empty queue
 * looks exactly like an empty queue. That cost a walk-through an afternoon on
 * 2026-08-21; see `docs/reviews/milestone-5c-desktop-walk.md` finding 5.
 */

import { ORIGIN_LABEL, readCapture, type FieldReading } from '@/lib/capture';
import type { Capture } from '@/lib/schemas';

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * A field, summarised for a row that is not the review form.
 *
 * A queue row is a thing to open, so it shows enough to recognise the posting
 * and nothing that could be mistaken for a decision. Where the two readers
 * disagreed it says so instead of picking the parser's answer — the same rule
 * `readField` applies in the form, one line long.
 */
function summarise(reading: FieldReading, noun: string): { text: string; certain: boolean } {
  // Both uncertain cases name the field. Without the noun the row reads
  // "Campus AI Research Engineer (Intern) · two readings disagree", which puts
  // the doubt on the title standing next to it rather than on the employer it
  // is actually about.
  if (reading.source === 'conflict')
    return { text: `${noun}: two readings disagree`, certain: false };
  if (reading.source === 'none') return { text: `${noun} not read`, certain: false };
  return { text: reading.value, certain: true };
}

function Summary({ reading, noun }: { readonly reading: FieldReading; readonly noun: string }) {
  const { text, certain } = summarise(reading, noun);
  return certain ? (
    <span className="text-paper">{text}</span>
  ) : (
    <span className="italic text-paper-faint">{text}</span>
  );
}

interface CaptureQueueProps {
  readonly captures: readonly Capture[];
  readonly isLoading: boolean;
  readonly error: Error | null;
  /** The signed-in address, for the empty state. Null while it is unknown. */
  readonly email: string | null;
  readonly onOpen: (captureId: string) => void;
  /** The id currently being fetched, so its own row can say so. */
  readonly opening: string | null;
}

export function CaptureQueue({
  captures,
  isLoading,
  error,
  email,
  onOpen,
  opening,
}: CaptureQueueProps) {
  if (isLoading) {
    return (
      <p data-testid="capture-queue-loading" className="text-[13px] text-paper-dim">
        Checking what is waiting…
      </p>
    );
  }

  // A queue that cannot be read is not an empty queue, and saying "nothing is
  // waiting" here would be inventing an answer out of a failed request — the
  // same mistake I3 forbids about a source outage.
  if (error !== null) {
    return (
      <p role="alert" data-testid="capture-queue-error" className="text-[13px] text-alert-400">
        The review queue could not be read, so this page cannot tell you whether anything is
        waiting. {error.message}
      </p>
    );
  }

  if (captures.length === 0) {
    return (
      <p data-testid="capture-queue-empty" className="max-w-2xl text-[13px] text-paper-dim">
        Nothing is waiting for review. Postings captured through your own Claude land here — if one
        is missing, check that Claude is connected to the account you are signed in as
        {email === null ? '' : ` (${email})`}.
      </p>
    );
  }

  return (
    <div data-testid="capture-queue" className="space-y-3">
      <h2 className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
        Waiting for you · {captures.length}
      </h2>
      <ul className="space-y-2">
        {captures.map((capture) => {
          const reading = readCapture(capture.proposed, capture.assistant);
          const quoted = capture.assistant !== null || capture.assistant_rejected_fields.length > 0;
          return (
            <li
              key={capture.id}
              data-testid="capture-queue-row"
              className="flex flex-wrap items-center justify-between gap-3 border border-ink-700 bg-ink-900/60 px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="text-[14px] leading-relaxed">
                  <Summary reading={reading.title} noun="title" />
                  <span className="text-paper-faint"> · </span>
                  <Summary reading={reading.company_name} noun="employer" />
                </p>
                <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
                  {ORIGIN_LABEL[capture.origin]} · {formatWhen(capture.created_at)}
                  {quoted && ' · Claude quoted from the page'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => onOpen(capture.id)}
                disabled={opening !== null}
                className="shrink-0 border border-ink-500 bg-ink-800 px-3 py-1.5 text-[13px] text-paper disabled:opacity-40"
              >
                {opening === capture.id ? 'Opening…' : 'Review it'}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
