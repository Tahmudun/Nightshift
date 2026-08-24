/**
 * Which reader proposed a field, and what the form should therefore open on.
 *
 * M5d / ADR 0039 §2. A capture can now carry two readings of the same text:
 * Nightshift's line parser, and a quote from the reader's own Claude. They
 * fail differently — a parser misreads what is there, an assistant can point
 * at the wrong part of a page — so the review form has to say which one it is
 * showing, and has to have an answer for the case where they disagree.
 *
 * **When they disagree, neither wins.** The form shows both and opens on
 * neither, because a silent winner at that exact moment is what the whole
 * two-step design exists to prevent: a pre-filled value is a default, and a
 * default is what a tired person accepts at 11pm.
 *
 * Pure and outside the component on purpose (CLAUDE.md §3). It is the only
 * part of this screen with a rule in it, and a rule inside a `.tsx` is a rule
 * only an end-to-end test can reach.
 */

import type { AssistantQuote, CaptureProposal } from '@/lib/schemas';

/** Who offered the value the form is showing. */
export type FieldSource = 'parser' | 'assistant' | 'agreed' | 'conflict' | 'none';

export interface FieldReading {
  /** What the input opens on. Empty for `conflict` and `none`. */
  readonly value: string;
  readonly source: FieldSource;
  /** Both readings, for `conflict`. Null otherwise. */
  readonly parser: string | null;
  readonly assistant: string | null;
}

/** Whitespace and case are not a disagreement. */
function same(a: string, b: string): boolean {
  return (
    a.trim().replace(/\s+/g, ' ').toLowerCase() === b.trim().replace(/\s+/g, ' ').toLowerCase()
  );
}

export function readField(parser: string | null, assistant: string | null): FieldReading {
  const p = parser?.trim() === '' ? null : parser;
  const a = assistant?.trim() === '' ? null : assistant;

  if (p !== null && a !== null) {
    return same(p, a)
      ? { value: p, source: 'agreed', parser: p, assistant: a }
      : { value: '', source: 'conflict', parser: p, assistant: a };
  }
  if (p !== null) return { value: p, source: 'parser', parser: p, assistant: null };
  if (a !== null) return { value: a, source: 'assistant', parser: null, assistant: a };
  return { value: '', source: 'none', parser: null, assistant: null };
}

export interface CaptureReading {
  readonly title: FieldReading;
  readonly company_name: FieldReading;
  readonly location_text: FieldReading;
}

export function readCapture(
  proposed: CaptureProposal,
  assistant: AssistantQuote | null,
): CaptureReading {
  return {
    title: readField(proposed.title, assistant?.title ?? null),
    company_name: readField(proposed.company_name, assistant?.company_name ?? null),
    location_text: readField(proposed.location_text, assistant?.location_text ?? null),
  };
}

/** What the reader is told about where they found this. */
export const ORIGIN_LABEL: Readonly<Record<string, string>> = {
  linkedin: 'From LinkedIn',
  indeed: 'From Indeed',
  other: 'From a link',
  none: 'Pasted text',
};

/**
 * The origin line for one capture — Q13, answered 2026-08-24.
 *
 * `origin` is derived from `source_url` alone, so a capture made in Claude
 * Desktop without a link is `none`, exactly like a capture typed into the
 * browser form. The live walk hit this: a real LinkedIn posting arrived
 * through the MCP server and its queue row read **"Pasted text"**, which is
 * true of somebody using the form and false of what actually happened.
 *
 * **The honest distinction is not which website.** Nothing recorded that, and
 * pattern-matching a provenance claim out of the body text would invent a fact
 * about where a posting came from — the same class of thing
 * `location_confidence` exists to refuse. What *is* recorded is whether an
 * assistant took part, because its quotes are in their own columns. So a
 * capture with quotes and no link is one whose origin **was not recorded**,
 * and saying that is better than naming the wrong channel or rendering a
 * confident blank.
 *
 * The other half of Q13's answer lives in `capture_posting`'s tool
 * description, which now asks for the URL instead of never mentioning it.
 */
export function originLabel(origin: string, assistant: AssistantQuote | null): string {
  if (origin === 'none' && assistant !== null) return 'Origin not recorded';
  return ORIGIN_LABEL[origin] ?? 'Origin not recorded';
}
