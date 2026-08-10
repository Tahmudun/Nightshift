'use client';

/**
 * The ranked list: your corpus, grouped by eligibility, best first inside each
 * group.
 *
 * `matching.md` §5.3. **The bands are headings and never points.** Grouping by
 * eligibility and then sorting by score inside the group is the compromise
 * between two things that both matter: a list where a hard blocker does not
 * affect position is not usable, and a score that has silently absorbed a
 * penalty for uncertainty is a lie. Making the grouping a visible structure
 * satisfies both — the ordering reflects eligibility and the number never does.
 *
 * Three things this component refuses to do, each because it would be the
 * plausible-looking version of the same page:
 *
 * - **Hide an ineligible posting.** §3.3: shown and dimmed with the reason
 *   named. A hidden row is a parsing bug the reader cannot see, and the reader
 *   is the only person who can tell us the rules misread a posting.
 * - **Sort on the raw total.** `assessed_out_of` is not always 100, so 40 of 50
 *   beats 45 of 100. The API sorts; this renders the order it was given, and
 *   the percentage beside each row is what makes that order checkable.
 * - **Print `0%` for a posting nothing could be assessed on.** Those sort last
 *   and say so. Zero is a measurement.
 */

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { fetchMatches } from '@/lib/api';
import type { EligibilityState, RankedJob } from '@/lib/schemas';

const TERM = 'font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';

/**
 * The heading for each band, in a person's words rather than the enum's.
 * `JobEligibility` makes the same move on the detail page and for the same
 * reason: "likely_ineligible" is jargon on exactly the verdict somebody least
 * wants to read.
 */
const BAND_HEADING: Record<EligibilityState, string> = {
  eligible: 'You meet what these postings state',
  likely_eligible: 'You probably meet what these state',
  uncertain: 'Not enough to tell either way',
  likely_ineligible: 'Probably not a fit, with the reason on each',
  ineligible: 'These state something you do not meet',
};

/**
 * What the band does *not* mean. The last two matter most: this system reads
 * postings with rules, the rules are wrong sometimes, and a band must never
 * sound like a decision anybody has made about the reader.
 */
const BAND_CAVEAT: Record<EligibilityState, string> = {
  eligible: 'Read against what each posting says in writing. It says nothing about your chances.',
  likely_eligible: 'Read against what each posting says in writing.',
  uncertain: 'Nothing here is a no. Filling in your profile moves postings out of this group.',
  likely_ineligible: 'Not rejections. Employers hire below their stated minimums constantly.',
  ineligible:
    'Still listed, still applyable. Open one to see the sentence we read it from — if that ' +
    'sentence does not say what we claim, we are wrong and you should apply.',
};

/** Dimmed, never hidden (§3.3, AMENDMENTS A7). */
const DIMMED: ReadonlySet<EligibilityState> = new Set(['likely_ineligible', 'ineligible']);

function Row({ row }: { readonly row: RankedJob }) {
  const { job, match } = row;
  const share = match.fraction === null ? null : `${Math.round(match.fraction * 100)}%`;

  return (
    <article className="border-b border-ink-800 px-5 py-3" data-testid="ranked-row">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <div className="min-w-0 flex-1">
          <h4 className="truncate text-[14px] text-paper">
            <Link
              className="underline-offset-2 hover:text-signal-400 hover:underline"
              href={`/explore/jobs/${job.id}`}
            >
              {job.title}
            </Link>
          </h4>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.12em] text-signal-600">
            {job.company.canonical_name}
          </p>
        </div>

        <div className="shrink-0 text-right">
          {share === null ? (
            // Never `0%`. A null fraction is a pair nobody could score, and zero
            // would report it as measured and found wanting.
            <p className={TERM} data-testid="row-unassessed">
              nothing to assess
            </p>
          ) : (
            <>
              <p className="font-mono text-[15px] text-paper tnum" data-testid="row-fraction">
                {share}
              </p>
              {/* The raw numbers under the percentage, because the percentage is
                  a ratio of two numbers that are not the same on every row —
                  which is the whole reason the list sorts on it. */}
              <p className="font-mono text-[10px] text-paper-faint tnum" data-testid="row-total">
                {match.overall_score} of {match.assessed_out_of}
              </p>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

export function RankedMatches() {
  const { data, error, isPending } = useQuery({
    queryKey: ['matches'],
    queryFn: () => fetchMatches(),
  });

  if (isPending) {
    return (
      <p className="px-5 py-8 font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
        Loading matches…
      </p>
    );
  }

  if (error !== null) {
    return (
      <div className="border border-alert-900 bg-alert-900/30 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
          Could not load matches
        </p>
        <p className="mt-1.5 text-[13px] text-paper-dim">{error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="ranked-matches">
      {/* Above the list, not under it. This number is the difference between a
          ranked list of your corpus and a ranked list of the part of it that
          happens to have been scored, and a reader who has scrolled to the
          bottom has already drawn a conclusion. */}
      <div className="border border-ink-700 bg-ink-900/40 px-5 py-3">
        <p className="text-[13px] leading-relaxed text-paper-dim">
          <span className="text-paper tnum">{data.total}</span> postings ranked
          {data.not_yet_scored > 0 && (
            <span data-testid="not-yet-scored">
              , and <span className="text-paper tnum">{data.not_yet_scored}</span> open postings not
              scored yet. Those are computed in the background and are not zeroes — they are absent
              from this ordering rather than at the bottom of it.
            </span>
          )}
        </p>
        {data.deferred_components.length > 0 && (
          <p className="mt-2 text-[12px] leading-relaxed text-paper-faint">
            Every score here is out of what each posting could be assessed on, and none of them
            includes{' '}
            {data.deferred_components.map((row) => row.name.replace(/_/g, ' ')).join(' or ')} —{' '}
            {data.deferred_components.reduce((sum, row) => sum + row.weight, 0)} points this
            milestone does not compute.
          </p>
        )}
      </div>

      {data.bands.map((band) => (
        <section
          key={band.state}
          data-testid={`band-${band.state}`}
          className={[
            'border border-ink-700 bg-ink-900/40',
            DIMMED.has(band.state) ? 'opacity-70' : '',
          ].join(' ')}
        >
          <div className="border-b border-ink-700 px-5 py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4">
              <h3 className="text-[14px] text-paper">{BAND_HEADING[band.state]}</h3>
              <p className={`${TERM} tnum`}>{band.items.length}</p>
            </div>
            <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-paper-faint">
              {BAND_CAVEAT[band.state]}
            </p>
          </div>

          {band.items.length === 0 ? (
            // An empty band is printed, not dropped. §3.3's promise that an
            // ineligible posting is shown rather than hidden is only checkable
            // if the heading is there when there is nothing under it.
            <p className="px-5 py-3 text-[13px] italic text-paper-dim">Nothing in this group.</p>
          ) : (
            band.items.map((row) => <Row key={row.job.id} row={row} />)
          )}

          {band.unassessed > 0 && (
            <p className="px-5 py-2 text-[12px] text-paper-faint" data-testid="unassessed-note">
              {band.unassessed} of these could not be assessed on anything and sit at the end of
              this group rather than at the bottom of it.
            </p>
          )}
        </section>
      ))}

      <p className="text-[11px] text-paper-faint">
        Ruleset {data.ruleset_version}. Groups are groups, never points — an eligibility verdict
        never changes a score (§5.2). Open any posting for the full breakdown.
      </p>
    </div>
  );
}
