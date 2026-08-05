/**
 * What a posting asks for, in the posting's own words.
 *
 * Every row on screen is a slice of `descriptionText` taken at the offsets the
 * API sent. Nothing here summarises, rephrases, or reconstructs a sentence from
 * the normalized `value` — a reader must be able to check any claim against the
 * description printed further down the same page, and that only works if the
 * quote is literally from it.
 *
 * Three absences are distinguished, because merging them would each be a
 * different lie:
 *
 *   no description        the source gave us nothing to read
 *   version is null       we have not read it
 *   version, zero rows    we read it and these rules found nothing
 *
 * The last two look identical in the data if you only count rows, which is why
 * `requirements_extractor_version` crosses the boundary at all.
 */

import type { JobRequirement, RequirementNecessity } from '@/lib/schemas';

const TERM = 'font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';
const ABSENT = 'mt-2 text-[13px] italic text-paper-dim';

/** Required first: a hard ask outranks a nice-to-have, on screen as in the gate. */
const ORDER: readonly RequirementNecessity[] = ['required', 'preferred', 'mentioned'];

const HEADING: Record<RequirementNecessity, string> = {
  required: 'Required',
  preferred: 'Preferred',
  mentioned: 'Mentioned, not required',
};

const BLURB: Record<RequirementNecessity, string> = {
  required: 'Stated under a heading this posting treats as a requirement.',
  preferred: 'Stated as a preference, a bonus, or a nice-to-have.',
  mentioned: 'Named somewhere in the posting, under no requirement heading at all.',
};

/**
 * The sentence a span sits inside, cut out of the description.
 *
 * Bounded at sentence punctuation and at newlines, then at 240 characters so a
 * posting written as one unpunctuated paragraph cannot paste itself in whole.
 * A span outside the text yields nothing rather than a clamped quote — clamping
 * would move the claim onto words it did not come from.
 */
export function sentenceAround(text: string, start: number, end: number): string | null {
  if (start < 0 || end > text.length || end <= start) return null;

  const isBoundary = (character: string) => '.!?\n'.includes(character);

  let from = start;
  while (from > 0 && !isBoundary(text[from - 1]!) && start - from < 240) from -= 1;
  let to = end;
  while (to < text.length && !isBoundary(text[to]!) && to - end < 240) to += 1;
  if (to < text.length && isBoundary(text[to]!) && text[to] !== '\n') to += 1;

  const quoted = text.slice(from, to).trim();
  return quoted.length > 0 ? quoted : null;
}

function RequirementRow({
  requirement,
  descriptionText,
}: {
  readonly requirement: JobRequirement;
  readonly descriptionText: string | null;
}) {
  const quote =
    descriptionText === null
      ? null
      : sentenceAround(descriptionText, requirement.char_start, requirement.char_end);

  return (
    <li className="border-l-2 border-ink-500 pl-3">
      <p className="flex flex-wrap items-baseline gap-x-2 text-[14px] text-paper">
        <span>{requirement.value}</span>
        <span className={TERM}>{requirement.kind.replace(/_/g, ' ')}</span>
        {requirement.has_equivalence && (
          // A13: this is not a hard blocker. Saying so on the row is what stops
          // a reader reading "PhD" and closing the tab.
          <span
            data-testid="equivalence-marker"
            className="rounded-sm bg-ink-700 px-1.5 py-0.5 text-[11px] text-paper-dim"
          >
            or equivalent
          </span>
        )}
      </p>
      {quote !== null && (
        <p
          data-testid="requirement-quote"
          className="mt-1 max-w-2xl text-[13px] leading-relaxed text-paper-dim"
        >
          {quote}
        </p>
      )}
    </li>
  );
}

export function JobRequirements({
  requirements,
  descriptionText,
  extractorVersion,
}: {
  readonly requirements: readonly JobRequirement[];
  readonly descriptionText: string | null;
  readonly extractorVersion: string | null;
}) {
  const groups = ORDER.map((necessity) => ({
    necessity,
    rows: requirements.filter((row) => row.necessity === necessity),
  })).filter((group) => group.rows.length > 0);

  return (
    <section>
      <h2 className={TERM}>What this posting asks for</h2>

      {extractorVersion === null ? (
        <p className={ABSENT}>
          This posting has not been read yet, so nothing is claimed about what it requires.
        </p>
      ) : requirements.length === 0 ? (
        <p className={ABSENT}>
          Read, but no requirements this system could read were found in it. That is a limit of
          these rules, not a statement that the posting asks for nothing.
        </p>
      ) : (
        <>
          <div className="mt-3 space-y-5">
            {groups.map((group) => (
              <section key={group.necessity} aria-label={HEADING[group.necessity]}>
                <h3 className={TERM}>{HEADING[group.necessity]}</h3>
                <p className="mt-1 text-[12px] text-paper-faint">{BLURB[group.necessity]}</p>
                <ul className="mt-2 space-y-3">
                  {group.rows.map((row) => (
                    <RequirementRow
                      key={`${row.kind}-${row.value}-${row.char_start}`}
                      requirement={row}
                      descriptionText={descriptionText}
                    />
                  ))}
                </ul>
              </section>
            ))}
          </div>
          <p className="mt-4 text-[12px] text-paper-faint">
            Extracted by rules {extractorVersion}, quoting the posting. Nothing here is compared
            against you yet — that arrives with the eligibility gate.
          </p>
        </>
      )}
    </section>
  );
}
