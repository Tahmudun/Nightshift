/**
 * The score, and everything it is made of.
 *
 * Invariant I4 in one component: **a bare number in the UI is a bug.** So the
 * total never renders alone. Six components with their weights, each with its
 * own sentence and the evidence rows behind it quoted on both sides; two
 * penalties with what they cost and why; the ten points §5.1 defers, named.
 *
 * Nothing here is generated. Every sentence on screen is a string the scoring
 * rules produced and the database stored beside the points it explains
 * (`matching.md` §4.5). This file chooses layout and headings; it does not
 * compose a claim.
 *
 * Four distinctions are load-bearing and collapsing any of them is a lie:
 *
 *   assessable vs zero      the posting said too little to ask, versus you do
 *                           not match. Both store 0 (§5.1.1)
 *   applicable vs no cost   there was nothing to ask, versus nothing was missing
 *   required vs preferred   a bar you do not clear, versus a nice-to-have (§4.1)
 *   score vs eligibility    they sit side by side and are never reconciled (§5.2)
 *
 * `matching.md` §6 lists nine elements. Seven are computed and two are named as
 * not built — see `NOT_BUILT` below, which is a list this page prints rather
 * than a comment nobody re-reads.
 */

import type {
  Match,
  MatchComponent,
  MatchComponentDetail,
  MatchEvidence,
  MatchPenalty,
  UnmetRequirement,
} from '@/lib/schemas';

const TERM = 'font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';
const ABSENT = 'mt-2 text-[13px] italic text-paper-dim';

/**
 * The words a person reads, which are deliberately not the enum values.
 * `project` is "what you have built", because "project evidence" is the name of
 * a column and not a thing anybody says.
 */
const COMPONENT_HEADING: Record<MatchComponent, string> = {
  role: 'The kind of role',
  skill: 'Skills the posting names',
  project: 'What you have built',
  location: 'Where it is, and how it is worked',
  freshness: 'How recently it was published',
  priority: 'Whether it is pitched at early career',
};

/**
 * §6's last two elements. Named on the page rather than omitted, for
 * `DEFERRED_FILTERS`' reason one subsystem over: an absent element is an
 * invisible gap, and a named one is a decision a reader can check.
 *
 * **Recommended resume is here and not in the seven.** `match_results.resume_id`
 * exists, has a foreign key, and has no writer — it is null on every stored row.
 * A section rendering "your general resume" from nothing would be the most
 * plausible-looking fabrication on this page.
 */
const NOT_BUILT = [
  {
    name: 'Recommended resume',
    reason:
      'which stored resume best covers what this posting asks for. The column exists and ' +
      'nothing computes it yet, so no resume is suggested rather than a default one being named.',
  },
  {
    name: 'Recommended emphasis',
    reason:
      'advice on how to present yourself for this role. This system has no basis for it and ' +
      'will not invent one.',
  },
  {
    name: 'Suggested next action',
    reason:
      'what to do about this posting today. The daily queue owns next actions and computes ' +
      'them from where an application actually is.',
  },
] as const;

/**
 * Somebody's exact words, marked as theirs.
 *
 * A `<mark>` rather than italics or quotation marks: the whole point of an
 * evidence row is that these characters were not written by this system, and
 * that has to survive being read aloud as well as being looked at.
 *
 * **`from` is why this takes a prop at all**, and it is for the browser walk
 * rather than for the layout — the two sides are checked against two different
 * haystacks. A quote from the posting must be a literal slice of the text
 * printed below; a quote from the reader must be a literal slice of something
 * they confirmed. With one shared test id the walk could only ask whether *some*
 * mark loosely matched, which it did, and which let a paraphrase through
 * (M3c review §3).
 */
function Quoted({ children, from }: { readonly children: string; readonly from: 'job' | 'user' }) {
  return (
    <mark className="bg-signal-900/50 px-1 text-paper" data-testid={`quoted-${from}-span`}>
      {children}
    </mark>
  );
}

/** A percentage, or `null` when nothing could be assessed — never 0%. */
function percent(fraction: number | null): string | null {
  return fraction === null ? null : `${Math.round(fraction * 100)}%`;
}

function Evidence({ row }: { readonly row: MatchEvidence }) {
  const compared = Object.entries(row.compared);

  return (
    <li className="border-l-2 border-ink-500 pl-3">
      {row.job_span_text !== null && (
        <p className="text-[13px] leading-relaxed text-paper">
          The posting says <Quoted from="job">{row.job_span_text}</Quoted>
          {/* Which of the posting's strings this came from. Role relevance is
              decided on the title and everything else on the description, and a
              reader searching the description for a title phrase would conclude
              we made it up. */}
          {row.job_span_field === 'title' && (
            <span className={`ml-2 ${TERM}`} data-testid="evidence-field">
              in the title
            </span>
          )}
        </p>
      )}
      {row.user_span_text !== null && (
        <p className="mt-1 text-[13px] leading-relaxed text-paper-dim">
          You have confirmed <Quoted from="user">{row.user_span_text}</Quoted>
        </p>
      )}
      {/* §2.1's exempt components quote nobody — there is no claim about your
          qualifications to quote — and record what they weighed instead. */}
      {compared.length > 0 && row.job_span_text === null && (
        <dl className="flex flex-wrap gap-x-4 gap-y-1" data-testid="evidence-compared">
          {compared.map(([key, value]) => (
            <div key={key} className="flex items-baseline gap-1.5">
              <dt className={TERM}>{key.replace(/_/g, ' ')}</dt>
              <dd className="text-[13px] text-paper-dim">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {/* The second branch is unreachable today and stays anyway (ADR 0018).
          Nothing proposes: M3c Task 11 measured what an embedding would say and
          the answer was `Java` from a confirmed `Python`. But if a row carrying
          that source ever did arrive, labelling it "matched by a vocabulary
          rule" is the failure worth preventing — an unreachable branch that is
          correct beats a reachable one that lies. */}
      <p className="mt-1 text-[11px] text-paper-faint">
        {/* A nice-to-have says so rather than printing a bare `0`. The row is
            here because §4.1 means what it says — a preferred technology is
            worth nothing — and "0" beside a skill somebody has confirmed reads
            as a judgement of them rather than of the posting's wording. */}
        {row.compared.necessity === 'preferred'
          ? 'worth nothing — the posting lists this as a nice-to-have'
          : `${row.points > 0 ? `+${row.points}` : row.points} · ${
              row.proposed_by === 'rule'
                ? 'matched by a vocabulary rule'
                : 'proposed by the embedding'
            }`}
      </p>
    </li>
  );
}

function Component({ component }: { readonly component: MatchComponentDetail }) {
  return (
    <section
      className="border-t border-ink-700 pt-3"
      data-testid={`component-${component.component}`}
      aria-label={COMPONENT_HEADING[component.component]}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <h3 className="text-[14px] text-paper">{COMPONENT_HEADING[component.component]}</h3>
        {/* An unassessable component prints no number at all. Rendering "0 of
            30" beside "the posting names no technologies" is the two statements
            §5.1.1 exists to keep apart, printed on one line. */}
        {component.assessable ? (
          <p className="font-mono text-[12px] text-paper-dim tnum">
            {component.points} of {component.weight}
          </p>
        ) : (
          <p className={`${TERM} shrink-0`} data-testid="not-assessed">
            not assessed
          </p>
        )}
      </div>
      <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-paper-dim">{component.why}</p>
      {component.evidence.length > 0 && (
        <ul className="mt-2 space-y-2">
          {component.evidence.map((row, index) => (
            <Evidence key={`${row.component}-${row.job_char_start}-${index}`} row={row} />
          ))}
        </ul>
      )}
    </section>
  );
}

function Penalty({ penalty }: { readonly penalty: MatchPenalty }) {
  return (
    <li className="border-l-2 border-ink-700 pl-3" data-testid={`penalty-${penalty.name}`}>
      <p className="flex flex-wrap items-baseline justify-between gap-x-4">
        <span className="text-[13px] leading-relaxed text-paper-dim">{penalty.why}</span>
        {/* An inapplicable penalty prints no number, for the same reason an
            unassessable component does not: "0" and "there was nothing to ask"
            are different sentences. */}
        {penalty.applicable ? (
          <span className="shrink-0 font-mono text-[12px] text-paper-dim tnum">
            {penalty.points}
          </span>
        ) : (
          <span className={`${TERM} shrink-0`}>nothing to ask</span>
        )}
      </p>
    </li>
  );
}

function Gaps({ rows }: { readonly rows: readonly UnmetRequirement[] }) {
  const hard = rows.filter((row) => row.necessity === 'required');
  const soft = rows.filter((row) => row.necessity === 'preferred');

  return (
    <>
      {hard.length > 0 && (
        <section data-testid="unmet-required">
          <h3 className={TERM}>What it asks for that you have nothing on file for</h3>
          <p className="mt-1 max-w-2xl text-[12px] text-paper-faint">
            Nothing you have confirmed answers these. That is about what is on file, not about what
            you can do — adding a skill or a project changes this list.
          </p>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            {hard.map((row) => (
              <li key={`${row.kind}-${row.value}`} className="text-[13px] text-paper">
                {row.value}
                {row.has_equivalence && (
                  <span className="ml-1.5 text-[11px] text-paper-dim">or equivalent</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {soft.length > 0 && (
        // A different heading, deliberately. §4.1: a `preferred` requirement
        // never produces a penalty and never counts as a gap in the score.
        // Rendered like the block above it, a nice-to-have reads as a bar.
        <section data-testid="unmet-preferred">
          <h3 className={TERM}>Nice-to-haves you have nothing on file for</h3>
          <p className="mt-1 max-w-2xl text-[12px] text-paper-faint">
            These cost you nothing. The posting names them as preferences, and the score charges
            nothing for them.
          </p>
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            {soft.map((row) => (
              <li key={`${row.kind}-${row.value}`} className="text-[13px] text-paper-dim">
                {row.value}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

export function MatchPanel({
  match,
  unmetRequirements,
}: {
  readonly match: Match | null;
  readonly unmetRequirements: readonly UnmetRequirement[] | null;
}) {
  // Three situations with one honest sentence between them: the sweep has not
  // reached this pair, the posting has no description to read, or the stored row
  // was computed under rules that no longer exist. All three are "no score",
  // which is true of each, and none of them is a number.
  if (match === null) {
    return (
      <section data-testid="match">
        <h2 className={TERM}>How this scores for you</h2>
        <p className={ABSENT}>
          Not scored yet. Scores are computed in the background and refresh whenever the posting or
          your profile changes, so this fills in on its own — it is not a zero.
        </p>
      </section>
    );
  }

  const share = percent(match.fraction);
  const unassessable = match.components.filter((row) => !row.assessable);

  return (
    <section data-testid="match">
      <h2 className={TERM}>How this scores for you</h2>

      <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        {/* The total and its denominator, never one without the other.
            `assessed_out_of` is not always 100, and "40" on its own invites the
            reader to supply the missing "of 100" themselves. */}
        <p className="font-mono text-[22px] text-paper tnum" data-testid="match-score">
          {match.overall_score}
          <span className="text-[14px] text-paper-dim"> of {match.assessed_out_of}</span>
        </p>
        {share !== null && (
          <p className="text-[13px] text-paper-dim" data-testid="match-fraction">
            {share} of what could be assessed
          </p>
        )}
      </div>

      {match.assessed_out_of < 100 && (
        <p
          className="mt-1 max-w-2xl text-[13px] leading-relaxed text-paper-dim"
          data-testid="partial-denominator"
        >
          Out of {match.assessed_out_of}, not 100:{' '}
          {unassessable.map((row) => COMPONENT_HEADING[row.component].toLowerCase()).join(', ')}{' '}
          could not be assessed from what this posting says. Scoring those as zero would subtract
          points for how the employer writes.
        </p>
      )}

      <div className="mt-5 space-y-4">
        {match.components.map((component) => (
          <Component key={component.component} component={component} />
        ))}
      </div>

      <section className="mt-5 border-t border-ink-700 pt-3">
        <h3 className={TERM}>What was subtracted</h3>
        <ul className="mt-2 space-y-2">
          {match.penalties.map((penalty) => (
            <Penalty key={penalty.name} penalty={penalty} />
          ))}
        </ul>
        <p className="mt-2 font-mono text-[12px] text-paper-dim tnum" data-testid="penalty-total">
          {match.penalty_score} in total
        </p>
      </section>

      {unmetRequirements !== null && unmetRequirements.length > 0 && (
        <div className="mt-5 space-y-4 border-t border-ink-700 pt-3">
          <Gaps rows={unmetRequirements} />
        </div>
      )}

      {match.deferred_components.length > 0 && (
        <section className="mt-5 border-t border-ink-700 pt-3" data-testid="deferred-components">
          <h3 className={TERM}>Not part of this score</h3>
          <ul className="mt-2 space-y-2">
            {match.deferred_components.map((row) => (
              <li key={row.name} className="text-[13px] leading-relaxed text-paper-dim">
                <span className="text-paper">{row.name.replace(/_/g, ' ')}</span> ({row.weight}{' '}
                points) — {row.reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-5 border-t border-ink-700 pt-3" data-testid="match-not-built">
        <h3 className={TERM}>Not built</h3>
        <ul className="mt-2 space-y-2">
          {NOT_BUILT.map((row) => (
            <li key={row.name} className="text-[13px] leading-relaxed text-paper-dim">
              <span className="text-paper">{row.name}</span> — {row.reason}
            </li>
          ))}
        </ul>
      </section>

      <p className="mt-4 text-[11px] text-paper-faint" data-testid="match-version">
        Ruleset {match.ruleset_version}
        {match.model_version === null
          ? ', rules only — no model produced any part of this'
          : `, with proposals from ${match.model_version}`}
        . Every line above quotes something stored; nothing here is written for you.
      </p>
    </section>
  );
}
