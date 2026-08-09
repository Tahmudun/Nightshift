/**
 * Whether this posting is open to you, and every reason behind the answer.
 *
 * Invariant I4 says a bare number is a bug. The same is true of a bare verdict,
 * and more so: "ineligible" with nothing beside it is a rejection nobody can
 * check, argue with, or correct. So the state never appears without its
 * blockers and its unknowns.
 *
 * **This section is never hidden and never hides a job.** AMENDMENTS A13 and
 * `matching.md` §3.3: an ineligible posting is shown and dimmed with the
 * blocker named, because a hidden row is a parsing bug the reader cannot see.
 * Whatever the verdict, the job is still on the page and still applyable.
 *
 * Three distinctions are load-bearing and none is cosmetic:
 *
 *   blocker vs unknown       a wall, versus an open question
 *   blocks vs soft_blocks    a stated bar you do not clear, versus a shortfall
 *   askable vs unassessable  a question your profile can answer, versus one the
 *                            posting's own wording leaves open
 *
 * Collapsing either of the first two turns something the reader could act on
 * into something that reads as a refusal. Collapsing the third does the
 * opposite and is subtler: it offers an action that cannot work.
 */

import Link from 'next/link';
import type { Eligibility, EligibilityState, EligibilityUnknown } from '@/lib/schemas';

/** An unknown a profile field could settle, narrowed so the field is not optional. */
type AskableUnknown = EligibilityUnknown & { profile_field: string };

/**
 * A predicate rather than a `!` after the filter. `Array.filter` does not narrow
 * the element type, so `row.profile_field!` would compile while asserting
 * something the compiler has not checked — and the thing being asserted is
 * precisely the distinction this component was fixed to respect.
 */
const isAskable = (row: EligibilityUnknown): row is AskableUnknown => row.profile_field !== null;

const TERM = 'font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';

/**
 * The words shown to a person, which are deliberately not the enum values.
 * "likely_ineligible" is jargon; "probably not a fit" is a sentence, and the
 * difference matters most on exactly the verdict a person least wants to read.
 */
const HEADLINE: Record<EligibilityState, string> = {
  eligible: 'You meet what this posting states',
  likely_eligible: 'You probably meet what this posting states',
  uncertain: 'Not enough in your profile to tell',
  likely_ineligible: 'Probably not a fit, and you can see why',
  ineligible: 'This posting states something you do not meet',
};

/**
 * Every state gets a sentence saying what the verdict does *not* mean. The
 * ineligible one is the important one: this system reads postings with rules
 * and the rules are wrong sometimes, so it must never sound like a decision
 * anybody has made about the reader.
 */
const CAVEAT: Record<EligibilityState, string> = {
  eligible: 'Read against what the posting says in writing. It says nothing about your chances.',
  likely_eligible: 'Read against what the posting says in writing.',
  uncertain: 'Nothing here is a no. Fill in what is missing and this can answer.',
  likely_ineligible: 'Not a rejection. Employers hire below their stated minimums constantly.',
  ineligible:
    'Read by rules, from the posting’s own words, quoted below. Rules misread postings — ' +
    'if the quote does not say what we claim, we are wrong and you should apply anyway.',
};

/**
 * Colour never carries the verdict on its own — `jobStatus.ts` made the same
 * call for closure states after the M0 review, and this is a stronger case for
 * it. The headline is a sentence a screen reader reads out in full.
 */
const TONE: Record<EligibilityState, string> = {
  eligible: 'text-paper',
  likely_eligible: 'text-paper',
  uncertain: 'text-paper-dim',
  likely_ineligible: 'text-paper-dim',
  ineligible: 'text-paper-dim',
};

/**
 * The profile field an unknown asks for, in words rather than as a column name.
 *
 * Kept in step with the gate's `_ASKS_FOR` by
 * `test_the_page_has_words_for_every_profile_field_an_unknown_can_ask_for`. The
 * fallback below is `?? row.profile_field`, so a missing phrase prints
 * "Add years_experience" at a person rather than throwing — which is why the
 * drift needs a test rather than a runtime guard.
 */
const ASKS: Record<string, string> = {
  graduation_year: 'your graduation year',
  degree: 'your degree',
  years_experience: 'your years of experience',
  is_enrolled: 'whether you are currently enrolled',
  work_authorization: 'your work authorization',
};

export function JobEligibility({ eligibility }: { eligibility: Eligibility | null }) {
  // Null means the posting has no extracted requirements at all. Saying
  // "eligible" here would be a claim about a person derived from a posting
  // nobody has read — the one thing this section must never do.
  if (eligibility === null) {
    return (
      <section data-testid="eligibility">
        <h2 className={TERM}>Eligibility</h2>
        <p className="mt-2 max-w-2xl text-[13px] italic leading-relaxed text-paper-dim">
          Nothing has been read out of this posting yet, so there is nothing to check you against.
          That is different from meeting its requirements, and it is not shown as if it were.
        </p>
      </section>
    );
  }

  const { state, blockers, unknowns } = eligibility;
  const hard = blockers.filter((row) => row.outcome === 'blocks');
  const soft = blockers.filter((row) => row.outcome === 'soft_blocks');
  // A null `profile_field` means no field would resolve it, so the two get
  // different headings and only one gets a link. See `eligibilityUnknownSchema`.
  const askable = unknowns.filter(isAskable);
  const unassessable = unknowns.filter((row) => row.profile_field === null);

  // `uncertain` has two causes and only one of them has an action behind it.
  // The generic pair below say "not enough in *your profile*" and "fill in what
  // is missing and this can answer" — both false when every open question came
  // from the posting's own wording. That is the same broken promise the
  // unassessable section was split out to stop making, one heading further up,
  // and the split did not fix it here. Found reviewing the fix, not the bug.
  const nothingToFillIn = state === 'uncertain' && askable.length === 0;
  const headline = nothingToFillIn ? 'The posting’s own wording leaves this open' : HEADLINE[state];
  const caveat = nothingToFillIn
    ? 'Nothing here is a no. What is unresolved is in how the posting is written, not in ' +
      'anything missing from your profile.'
    : CAVEAT[state];

  return (
    <section data-testid="eligibility">
      <h2 className={TERM}>Eligibility</h2>

      <p className={`mt-2 text-[15px] leading-snug ${TONE[state]}`} data-testid="eligibility-state">
        {headline}
      </p>
      <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-paper-dim">{caveat}</p>

      {hard.length > 0 && (
        <div className="mt-4" data-testid="eligibility-blockers">
          <h3 className={TERM}>What the posting requires that you do not meet</h3>
          <ul className="mt-2 space-y-3">
            {hard.map((row) => (
              <li key={row.dimension} className="border-l-2 border-ink-700 pl-3">
                <p className="text-[13px] leading-relaxed text-paper">{row.why}</p>
                {row.posting_says !== null && (
                  <p className="mt-1 text-[13px] italic leading-relaxed text-paper-dim">
                    The posting says “{row.posting_says}”
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {soft.length > 0 && (
        <div className="mt-4" data-testid="eligibility-gaps">
          {/* Deliberately a different heading from the block above. A years
              shortfall is a gap, not a bar, and the gate never lets one produce
              an `ineligible` — the page must not imply otherwise. */}
          <h3 className={TERM}>Where you fall short of what it asks</h3>
          <ul className="mt-2 space-y-3">
            {soft.map((row) => (
              <li key={row.dimension} className="border-l-2 border-ink-700 pl-3">
                <p className="text-[13px] leading-relaxed text-paper-dim">{row.why}</p>
                {row.posting_says !== null && (
                  <p className="mt-1 text-[13px] italic leading-relaxed text-paper-dim">
                    The posting says “{row.posting_says}”
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {askable.length > 0 && (
        <div className="mt-4" data-testid="eligibility-unknowns">
          <h3 className={TERM}>What would let this answer</h3>
          <ul className="mt-2 space-y-1">
            {askable.map((row) => (
              <li key={row.dimension} className="text-[13px] leading-relaxed text-paper-dim">
                {row.why}.{' '}
                <Link
                  href="/operate/profile"
                  className="text-paper underline underline-offset-2 hover:text-paper"
                >
                  Add {ASKS[row.profile_field] ?? row.profile_field}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {unassessable.length > 0 && (
        <div className="mt-4" data-testid="eligibility-unassessable">
          {/* A separate heading, and no link under it. These are questions the
              posting's own wording leaves open — "or equivalent experience" —
              and no profile field settles one. Under "What would let this
              answer" with an "Add your degree" link beside it, the reader does
              the work and the verdict does not move. */}
          <h3 className={TERM}>What nothing in your profile can settle</h3>
          <ul className="mt-2 space-y-1">
            {unassessable.map((row) => (
              <li key={row.dimension} className="text-[13px] leading-relaxed text-paper-dim">
                {row.why}. Worth reading the posting itself on this one.
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-4 text-[11px] text-paper-faint" data-testid="eligibility-version">
        Ruleset {eligibility.gate_version}. Computed from this posting each time you open it, and
        not stored.
      </p>
    </section>
  );
}
